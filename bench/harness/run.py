#!/usr/bin/env python3
"""Model-agnostic benchmark runner. See bench/README.md for the methodology.

python3 bench/harness/run.py --mock --dry-run     plan only: no calls, nothing written
python3 bench/harness/run.py --mock               run the mock models end to end
python3 bench/harness/run.py                      real models: refused until wired up and approved
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

import execute
import models
import taskset
from count_tokens import TOKENIZER, Ledger, approx_tokens, messages_tokens
from taskset import EXT, LANGS, REPO, RESULTS, STYLES, EditCase, Spec, Task

TRACKS = ('generate', 'names', 'edit', 'repair', 'contracts')
RUNNABLE_TRACKS = ('generate', 'names', 'edit')
MODES = ('zero-shot', 'self-repair', 'agentic')
LANG_NAME = {'python': 'Python', 'typescript': 'TypeScript', 'mime': 'mime'}


@dataclass
class Job:
    track: str
    item: str  # task or edit-case id
    style: str | None  # names track only
    lang: str
    model: dict
    mode: str
    spec: Spec
    tier: int | None
    task: Task | None = None
    edit: EditCase | None = None

    @property
    def key(self) -> str:
        parts = (
            [self.track, self.item] + ([self.style] if self.style else []) + [self.lang, self.model['id'], self.mode]
        )
        return '/'.join(parts)

    def unavailable(self) -> str | None:
        if reason := execute.available(self.lang):
            return reason
        if self.lang == 'mime':
            return 'no mime reference or compiler'
        return None


# ---------------------------------------------------------------------------
# prompts


def template(name: str) -> str:
    return (taskset.PROMPTS / f'{name}.md').read_text()


def fill(text: str, **values: str) -> str:
    def sub(m: re.Match) -> str:
        key = m.group(1)
        if key not in values:
            raise KeyError(f'prompt placeholder {{{{{key}}}}} has no value')
        return values[key]

    return re.sub(r'\{\{(\w+)\}\}', sub, text)


def literal(value: object, lang: str) -> str:
    """A test value written as a literal of the target language (true is True in Python)."""
    return repr(value) if lang == 'python' else json.dumps(value)


def render_examples(spec: Spec, lang: str) -> str:
    lines = []
    for c in spec.examples():
        args = ', '.join(literal(a, lang) for a in c['args'])
        lines.append(f'- `{spec.entry}({args})` returns `{literal(c["expected"], lang)}`')
    return '\n'.join(lines)


def initial_messages(job: Job, skill: str | None) -> list[dict]:
    lang = LANG_NAME[job.lang]
    skill_block = f'\n# {lang} reference\n\n{skill}\n' if job.lang == 'mime' and skill else ''
    system = fill(template('system'), language=lang, skill=skill_block)
    common = {
        'language': lang,
        'native_signature': job.spec.native_signature(job.lang),
        'examples': render_examples(job.spec, job.lang),
    }
    if job.track == 'generate':
        user = fill(template('generate'), task=job.task.description(), **common)
    elif job.track == 'names':
        variant = job.task.variants[job.style]
        user = fill(
            template('names'),
            task=job.task.description(),
            library=variant.lib(job.lang).rstrip(),
            fence=models.FENCE[job.lang],
            entry=job.spec.entry,
            **common,
        )
    elif job.track == 'edit':
        user = fill(
            template('edit'),
            program=job.edit.before(job.lang).rstrip(),
            change=job.edit.change(),
            fence=models.FENCE[job.lang],
            examples=common['examples'],
        )
    else:
        raise ValueError(job.track)
    return [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]


def feedback(result: execute.Result, mode: str, show: int) -> str:
    lines = [f'Status: {result.status}', f'Message: {result.message}']
    if mode == 'agentic' and result.failures:
        lines.append('Failing cases:')
        for f in result.failures[:show]:
            lines.append('- ' + json.dumps(f))
    return fill(template('feedback'), diagnostic='\n'.join(lines))


# ---------------------------------------------------------------------------
# answers


FENCE_RE = re.compile(r'```([\w+-]*)[^\n]*\n(.*?)```', re.DOTALL)
ALIASES = {'python': {'python', 'py', ''}, 'typescript': {'typescript', 'ts', ''}, 'mime': {'mime', ''}}


def extract_code(text: str, lang: str) -> str | None:
    blocks = FENCE_RE.findall(text)
    tagged = [code for tag, code in blocks if tag.lower() in ALIASES[lang]]
    if tagged:
        return tagged[-1]
    if blocks:
        return blocks[-1][1]
    return text.strip() or None


def oracle(job: Job) -> models.Oracle:
    if job.track == 'generate':
        return models.Oracle(job.lang, job.spec, job.task.ref(job.lang))
    if job.track == 'names':
        variants = job.task.variants
        return models.Oracle(job.lang, job.spec, variants[job.style].ref(job.lang), variants['honest'].ref(job.lang))
    return models.Oracle(job.lang, job.spec, job.edit.after(job.lang))


def evaluate(job: Job, code: str | None, timeout: float, sandbox: str) -> execute.Result:
    if code is None:
        return execute.Result('no_code', 'no program found in the reply', 0, len(job.spec.cases))
    source = code
    if job.track == 'names':
        variant = job.task.variants[job.style]
        if err := taskset.check_composition(code, job.lang, variant.words, job.spec):
            return execute.Result('constraint', err, 0, len(job.spec.cases))
        source = variant.lib(job.lang).rstrip() + '\n\n\n' + code
    return execute.run(source, job.lang, job.spec, timeout, sandbox)


# ---------------------------------------------------------------------------
# planning


def build_jobs(args: argparse.Namespace, chosen_models: list[dict]) -> tuple[list[Job], list[str]]:
    jobs: list[Job] = []
    notes: list[str] = []
    for track in args.track:
        if track not in RUNNABLE_TRACKS:
            notes.append(f'track {track}: unavailable (needs the mime compiler)')
            continue
        items: list[tuple[str, str | None, Spec, int | None, Task | None, EditCase | None]] = []
        if track == 'generate':
            items = [(t.id, None, t.spec, t.tier, t, None) for t in taskset.load_tasks(args.task)]
        elif track == 'names':
            for t in taskset.load_tasks(args.task):
                items += [(t.id, s, t.spec, t.tier, t, None) for s in STYLES if t.variants]
        else:
            items = [(e.id, None, e.spec, None, None, e) for e in taskset.load_edits(args.task)]
        for item, style, spec, tier, task, edit in items:
            for lang in args.lang:
                for model in chosen_models:
                    for mode in args.mode:
                        jobs.append(Job(track, item, style, lang, model, mode, spec, tier, task, edit))
    return jobs, notes


def load_settings() -> tuple[dict, list[dict]]:
    cfg = tomllib.loads((taskset.HARNESS / 'models.toml').read_text())
    return cfg['settings'], cfg.get('model', [])


def load_skill(settings: dict) -> dict:
    path = REPO / settings['skill_file']
    if not path.exists():
        return {'path': settings['skill_file'], 'sha256': None, 'tokens': 0, 'text': None}
    text = path.read_text()
    return {
        'path': settings['skill_file'],
        'sha256': hashlib.sha256(text.encode()).hexdigest(),
        'tokens': approx_tokens(text),
        'text': text,
    }


def run_dir(args: argparse.Namespace, git: dict, mock: bool) -> Path:
    if args.out:
        return Path(args.out)
    base = f'{dt.date.today().isoformat()}-{git["short"]}' + ('-mock' if mock else '')
    path = RESULTS / base
    n = 2
    while path.exists():
        path = RESULTS / f'{base}-{n}'
        n += 1
    return path


def manifest(args, settings, chosen, skill, git, notes, out: Path) -> dict:
    return {
        'schema': 1,
        'run_id': out.name,
        'date': dt.datetime.now(dt.UTC).isoformat(timespec='seconds'),
        'argv': sys.argv[1:],
        'git': git,
        'compiler': {'commit': git['commit'], 'dirty': git['dirty'], 'available': execute.available('mime') is None},
        'skill_file': {k: v for k, v in skill.items() if k != 'text'},
        'tasks_sha256': taskset.sha256_files(
            taskset.tree_files(taskset.TASKS) + taskset.tree_files(taskset.EDITS), taskset.BENCH
        ),
        'harness_sha256': taskset.sha256_files([p for p in taskset.tree_files(taskset.HARNESS)], taskset.BENCH),
        'runtimes': execute.runtime_versions(),
        'sandbox': execute.sandbox_info(settings['sandbox']),
        'tokenizer': TOKENIZER if all(m['provider'] == 'mock' for m in chosen) else 'provider-reported usage',
        'settings': settings,
        'models': [{**m, 'sampling': models.SAMPLING[m['provider']]} for m in chosen],
        'seed_sent_to_provider': False,
        'tracks': args.track,
        'modes': args.mode,
        'languages': args.lang,
        'notes': notes,
        'status': 'running',
    }


# ---------------------------------------------------------------------------
# running


def run_sample(job: Job, index: int, settings: dict, skill: dict, model, out: Path) -> dict:
    raw = out / 'raw' / job.key / f's{index:02d}'
    seed = settings['base_seed'] + index
    max_attempts = 1 if job.mode == 'zero-shot' else settings['max_attempts']
    messages = initial_messages(job, skill['text'])
    spec_tokens = skill['tokens'] if job.lang == 'mime' else 0
    ledger = Ledger()
    orc = oracle(job)
    result = execute.Result('budget', 'budget exhausted before the first call')
    raw.mkdir(parents=True, exist_ok=False)
    attempt = 0
    for attempt in range(1, max_attempts + 1):
        if ledger.total >= settings['budget_tokens']:
            result = execute.Result('budget', f'{ledger.total} tokens used; budget is {settings["budget_tokens"]}')
            attempt -= 1
            break
        stem = raw / f'a{attempt}'
        stem.with_suffix('.prompt.json').write_text(json.dumps(messages, indent=2) + '\n')
        comp = model.complete(messages, seed=seed, attempt=attempt, oracle=orc)
        # The provider's usage may count the spec differently from our estimate; never exceed its input.
        ledger.add(comp.input_tokens, comp.output_tokens, min(spec_tokens, comp.input_tokens))
        stem.with_suffix('.output.txt').write_text(comp.text)
        if comp.raw is not None:
            stem.with_suffix('.response.json').write_text(json.dumps(comp.raw, indent=2) + '\n')
        if comp.stop_reason == 'refusal':
            code = None
            result = execute.Result('refusal', 'the provider declined the request', 0, len(job.spec.cases))
        else:
            code = extract_code(comp.text, job.lang)
            result = evaluate(job, code, settings['timeout_seconds'], settings['sandbox'])
        if code is not None:
            (raw / f'a{attempt}.solution.{EXT[job.lang]}').write_text(code)
        usage = {'input_tokens': comp.input_tokens, 'output_tokens': comp.output_tokens, 'spec_tokens': spec_tokens}
        stem.with_suffix('.result.json').write_text(
            json.dumps({**result.to_json(), 'stop_reason': comp.stop_reason, 'usage': usage}, indent=2) + '\n'
        )
        if result.ok or result.status == 'refusal':
            break
        messages = messages + [
            {'role': 'assistant', 'content': comp.text, **({'native': comp.native} if comp.native else {})},
            {'role': 'user', 'content': feedback(result, job.mode, settings['agentic_failing_cases'])},
        ]
    return {
        'track': job.track,
        'task': job.item,
        'style': job.style,
        'tier': job.tier,
        'lang': job.lang,
        'model': job.model['id'],
        'model_size': job.model.get('size'),
        'mode': job.mode,
        'sample': index,
        'seed': seed,
        'effort': job.model.get('effort'),
        'passed': result.ok,
        'status': result.status,
        'attempts': attempt,
        'tests_passed': result.passed,
        'tests_total': result.total,
        'tokens': ledger.to_json(),
        'tokens_until_pass': ledger.total if result.ok else None,
        'raw_dir': str(raw.relative_to(out)),
    }


def dry_run(jobs: list[Job], notes: list[str], samples: int, settings: dict, skill: dict, show_prompt: bool) -> int:
    runnable = [j for j in jobs if not j.unavailable()]
    skipped = [j for j in jobs if j.unavailable()]
    real = sorted({j.model['id'] for j in jobs if j.model['provider'] != 'mock'})
    calls_min = len(runnable) * samples
    calls_max = sum(samples * (1 if j.mode == 'zero-shot' else settings['max_attempts']) for j in runnable)
    first_tokens = sum(messages_tokens(initial_messages(j, skill['text'])) for j in runnable) * samples
    print('DRY RUN: no model is called and nothing is written.\n')
    by_track: dict[tuple[str, str], int] = {}
    for j in runnable:
        by_track[(j.track, j.lang)] = by_track.get((j.track, j.lang), 0) + 1
    print(f'{"track":<10} {"language":<12} {"cells":>6}')
    for (track, lang), n in sorted(by_track.items()):
        print(f'{track:<10} {lang:<12} {n:>6}')
    print(f'\ncells runnable: {len(runnable)}   skipped: {len(skipped)}   samples per cell: {samples}')
    print(f'model calls: {calls_min} to {calls_max}')
    print(f'input tokens of first attempts (approx): {first_tokens}')
    print(f'skill file: {skill["path"]} ({"missing" if skill["sha256"] is None else str(skill["tokens"]) + " tokens"})')
    box = settings['sandbox']
    print(f'sandbox: {box} ({execute.sandbox_available(box) or "works here"})')
    for reason in sorted({f'{j.lang}: {j.unavailable()}' for j in skipped}):
        print(f'skipped {reason}')
    for note in notes:
        print(note)
    if real:
        print(f'\nREAL MODELS: {", ".join(real)}. A real run spends API credit: it needs --allow-spend.')
        print('Output tokens (thinking included) are not estimated here; they usually dominate the cost.')
        if not any(j.model.get('size') == 'small' for j in jobs if j.model['provider'] != 'mock'):
            print('WARNING: no small model selected (rule 5).')
    if show_prompt and runnable:
        print(f'\n--- first prompt ({runnable[0].key}) ---')
        for m in initial_messages(runnable[0], skill['text']):
            print(f'[{m["role"]}]\n{m["content"]}')
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--mock', action='store_true', help='use the mock models from models.toml')
    p.add_argument('--dry-run', action='store_true', help='print the plan; call nothing, write nothing')
    p.add_argument('--track', nargs='+', choices=TRACKS, default=list(RUNNABLE_TRACKS))
    p.add_argument('--mode', nargs='+', choices=MODES, default=list(MODES))
    p.add_argument('--lang', nargs='+', choices=LANGS, default=list(LANGS))
    p.add_argument('--model', nargs='+', help='model ids (default: all mock models with --mock, else all real ones)')
    p.add_argument('--task', nargs='+', help='task or edit-case ids (default: all)')
    p.add_argument('--samples', type=int, help='samples per cell (default from models.toml)')
    p.add_argument('--out', help='results folder (default: results/<date>-<commit>[-mock])')
    p.add_argument('--show-prompt', action='store_true', help='with --dry-run, print the first prompt')
    p.add_argument('--allow-dirty', action='store_true', help='allow a real run on a dirty working tree')
    p.add_argument('--allow-spend', action='store_true', help='required for a real run: it spends API credit')
    args = p.parse_args(argv)

    settings, all_models = load_settings()
    pool = [m for m in all_models if (m['provider'] == 'mock') == args.mock]
    if args.model:
        unknown = set(args.model) - {m['id'] for m in pool}
        if unknown:
            p.error(f'unknown {"mock" if args.mock else "real"} model(s): {", ".join(sorted(unknown))}')
        pool = [m for m in pool if m['id'] in args.model]
    if not pool:
        print('No real models are configured in models.toml. The owner chooses them; until then use --mock.')
        return 2
    samples = args.samples or settings['samples']
    skill = load_skill(settings)
    jobs, notes = build_jobs(args, pool)

    if args.dry_run:
        return dry_run(jobs, notes, samples, settings, skill, args.show_prompt)

    git = taskset.git_info()
    if not args.mock:
        if not args.allow_spend:
            print("Refusing a real run without --allow-spend: it spends API credit and needs the owner's approval.")
            print('Use --dry-run to see how many calls it would make.')
            return 2
        if git['dirty'] and not args.allow_dirty:
            print('Refusing a real run on a dirty working tree: the manifest could not name the code that ran.')
            return 2
        if not any(m.get('size') == 'small' for m in pool):
            print('Refusing a real run without a small model (rule 5).')
            return 2
        if settings['sandbox'] == 'none' or (reason := execute.sandbox_available(settings['sandbox'])):
            print(
                f'Refusing a real run without a working sandbox for model code: '
                f'{reason if settings["sandbox"] != "none" else "models.toml sets sandbox = none"}'
            )
            return 2
    elif reason := execute.sandbox_available(settings['sandbox']):
        # Mock answers are our own references, so they may run unsandboxed; say so in the manifest.
        notes.append(f'sandbox {settings["sandbox"]} unavailable ({reason}); mock code ran unsandboxed')
        settings = {**settings, 'sandbox': 'none'}

    adapters = {m['id']: models.make(m) for m in pool}
    try:
        for adapter in adapters.values():
            if hasattr(adapter, 'connect'):
                adapter.connect()
    except models.ProviderError as e:
        print(f'Cannot start: {e}')
        return 2

    out = run_dir(args, git, args.mock)
    out.mkdir(parents=True, exist_ok=False)
    man = manifest(args, settings, pool, skill, git, notes, out)
    (out / 'manifest.json').write_text(json.dumps(man, indent=2) + '\n')

    skipped: dict[str, int] = {}
    rows = 0
    with (out / 'scores.jsonl').open('w') as scores:
        for job in jobs:
            if reason := job.unavailable():
                skipped[f'{job.lang}: {reason}'] = skipped.get(f'{job.lang}: {reason}', 0) + 1
                continue
            for i in range(samples):
                try:
                    row = run_sample(job, i, settings, skill, adapters[job.model['id']], out)
                except models.ProviderError as e:
                    man.update(status='aborted', error=str(e), rows=rows, at=f'{job.key}/s{i:02d}')
                    (out / 'manifest.json').write_text(json.dumps(man, indent=2) + '\n')
                    print(f'\nAborted at {job.key}/s{i:02d}: {e}')
                    print(f'{rows} samples kept in {out}; the run is marked "aborted" and does not count.')
                    return 3
                scores.write(json.dumps(row) + '\n')
                scores.flush()
                rows += 1
            print(f'{job.key}: done')
    man.update(
        status='complete',
        samples=samples,
        rows=rows,
        skipped=skipped,
        finished=dt.datetime.now(dt.UTC).isoformat(timespec='seconds'),
    )
    (out / 'manifest.json').write_text(json.dumps(man, indent=2) + '\n')
    print(f'\n{rows} samples written to {out}')
    for reason, n in sorted(skipped.items()):
        print(f'skipped {n} cells ({reason})')
    for note in notes:
        print(note)
    return 0


if __name__ == '__main__':
    sys.exit(main())
