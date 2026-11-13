#!/usr/bin/env python3
"""CI check for the harness itself: run the mock models and assert what each must score.

python3 bench/harness/smoke.py [--require-node]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import execute
import models
import report
import run


def check(cond: bool, msg: str, errors: list[str]) -> None:
    if not cond:
        errors.append(msg)


class _Obj:
    """A stand-in for an SDK response object."""

    def __init__(self, **kw: object) -> None:
        self.__dict__.update(kw)

    def model_dump(self, mode: str = 'python', exclude_none: bool = False) -> dict:
        out = {}
        for k, v in self.__dict__.items():
            if exclude_none and v is None:
                continue
            out[k] = v.model_dump(mode, exclude_none) if isinstance(v, _Obj) else v
            if isinstance(v, list):
                out[k] = [x.model_dump(mode, exclude_none) if isinstance(x, _Obj) else x for x in v]
        return out


class _FakeMessages:
    def __init__(self, replies: list[tuple[str, str]]) -> None:
        self.replies = replies
        self.calls: list[dict] = []

    def create(self, **kw: object) -> _Obj:
        self.calls.append(kw)
        stop, text = self.replies[len(self.calls) - 1]
        content = [_Obj(type='thinking', thinking='', signature='sig'), _Obj(type='text', text=text, citations=None)]
        usage = _Obj(input_tokens=100, output_tokens=40, cache_creation_input_tokens=None, cache_read_input_tokens=5)
        return _Obj(id='msg', content=content, stop_reason=stop, usage=usage)


def check_anthropic_adapter(errors: list[str]) -> None:
    """The real adapter against a fake client: request shape, usage, retries, refusals. No network."""
    task = next(t for t in run.taskset.load_tasks(['t1-001-sum-list']))
    cfg = next(m for m in run.load_settings()[1] if m['provider'] == 'anthropic')
    settings = run.load_settings()[0]
    skill = {'text': None, 'tokens': 0}
    job = run.Job('generate', task.id, None, 'python', cfg, 'self-repair', task.spec, task.tier, task)
    good = models.fenced(task.ref('python'), 'python')
    cases = [
        ('retry', [('end_turn', 'no code fence, no program: )('), ('end_turn', good)], 'pass', 2),
        ('refusal', [('refusal', '')], 'refusal', 1),
    ]
    for name, replies, want_status, want_attempts in cases:
        fake = _FakeMessages(replies)
        adapter = models.AnthropicModel(cfg['id'], cfg['effort'], cfg['max_tokens'], client=_Obj(messages=fake))
        with tempfile.TemporaryDirectory(prefix='mime-bench-fake-') as tmp:
            row = run.run_sample(job, 0, settings, skill, adapter, Path(tmp))
            raw = Path(tmp) / row['raw_dir']
            check((raw / 'a1.response.json').is_file(), f'adapter/{name}: raw provider response not archived', errors)
        check(
            row['status'] == want_status and row['attempts'] == want_attempts,
            f'adapter/{name}: got {row["status"]} after {row["attempts"]} attempts',
            errors,
        )
        first = fake.calls[0]
        for banned in ('temperature', 'top_p', 'top_k', 'seed', 'fallbacks'):
            check(banned not in first, f'adapter: request must not send {banned}', errors)
        check(
            first['thinking'] == {'type': 'adaptive'} and first['output_config'] == {'effort': cfg['effort']},
            'adapter: thinking must be adaptive with the configured effort',
            errors,
        )
        check(
            isinstance(first['system'], str) and all(m['role'] != 'system' for m in first['messages']),
            'adapter: the system prompt must go in the top-level system field',
            errors,
        )
        check(
            row['tokens']['input'] == 105 * len(fake.calls) and row['tokens']['output'] == 40 * len(fake.calls),
            f'adapter/{name}: token ledger must sum provider usage, got {row["tokens"]}',
            errors,
        )
        if name == 'retry':
            replay = fake.calls[1]['messages'][1]
            check(
                replay['role'] == 'assistant'
                and isinstance(replay['content'], list)
                and replay['content'][0]['type'] == 'thinking',
                'adapter: a retry must replay the earlier content blocks unchanged',
                errors,
            )


def check_failures(errors: list[str]) -> None:
    """Missing credentials must stop a run cleanly, and any crash must mark the run aborted."""

    class NoKey:
        def create(self, **kw: object) -> None:
            raise TypeError('Could not resolve authentication method')

    adapter = models.AnthropicModel('claude-haiku-5-5', 'medium', client=_Obj(messages=NoKey()))
    task = run.taskset.load_tasks(['t1-001-sum-list'])[0]
    orc = models.Oracle('python', task.spec, task.ref('python'))
    try:
        adapter.complete([{'role': 'user', 'content': 'x'}], seed=1, attempt=1, oracle=orc)
        errors.append('adapter: a request without credentials must raise ProviderError')
    except models.ProviderError:
        pass
    with tempfile.TemporaryDirectory(prefix='mime-bench-crash-') as tmp:
        out = Path(tmp) / 'crash-mock'
        real = run.run_sample

        def boom(*a: object, **kw: object) -> dict:
            raise RuntimeError('simulated crash')

        run.run_sample = boom
        try:
            run.main(
                [
                    '--mock',
                    '--model',
                    'mock-reference',
                    '--track',
                    'generate',
                    '--lang',
                    'python',
                    '--mode',
                    'zero-shot',
                    '--samples',
                    '1',
                    '--out',
                    str(out),
                ]
            )
            errors.append('run: a crash must propagate')
        except RuntimeError:
            pass
        finally:
            run.run_sample = real
        man = json.loads((out / 'manifest.json').read_text())
        check(
            man['status'] == 'aborted' and 'simulated crash' in man.get('error', ''),
            f'run: a crash must mark the manifest aborted, got {man["status"]}',
            errors,
        )


def _probe(body: str) -> str:
    """A Python solve() that returns 1 if the probe got through, else 0."""
    return 'def solve():\n' + ''.join(f'    {line}\n' for line in body.strip().splitlines())


def check_sandbox(errors: list[str], require: bool) -> str:
    """Hostile programs that must be stopped by the bwrap sandbox. Returns a one-line summary."""
    if reason := execute.sandbox_available('bwrap'):
        if require:
            errors.append(f'sandbox: {reason}')
        return f'sandbox probes skipped ({reason})'
    spec = run.taskset.Spec('probe', 'solve', [], 'i64', [{'args': [], 'expected': 0}])
    with tempfile.TemporaryDirectory(prefix='mime-bench-canary-', dir=Path.home()) as home_tmp:
        canary = Path(home_tmp) / 'secret.json'
        canary.write_text('{"results": [{"value": 12345}]}')
        os.environ['MIME_BENCH_CANARY'] = 'leaked'
        reads = f'try:\n    open({str(canary)!r}).read()\n    return 1\nexcept OSError:\n    return 0'
        env = "import os\nreturn 1 if 'MIME_BENCH_CANARY' in os.environ else 0"
        blocked = {
            'network': "import socket\ntry:\n    socket.create_connection(('1.1.1.1', 53), timeout=2)\n"
            '    return 1\nexcept OSError:\n    return 0',
            'read a host file': reads,
            'read the environment': env,
            'write to the host': f"try:\n    open({str(Path(home_tmp) / 'planted')!r}, 'w').write('x')\n"
            '    return 1\nexcept OSError:\n    return 0',
            'write to /usr': "try:\n    open('/usr/planted', 'w').write('x')\n    return 1\nexcept OSError:\n    return 0",
            'see host processes': f"import os\nreturn 1 if os.path.exists('/proc/{os.getpid()}') else 0",
        }
        for name, body in blocked.items():
            r = execute.run(_probe(body), 'python', spec, timeout=5, sandbox='bwrap')
            check(r.ok, f'sandbox: a program could {name} ({r.status}: {r.message})', errors)
        # Controls: outside the sandbox the same probes get through, so the probes test something.
        for name in ('read a host file', 'read the environment'):
            r = execute.run(_probe(blocked[name]), 'python', spec, timeout=5, sandbox='none')
            if name == 'read the environment':
                check(r.ok, 'sandbox control: the plain runner must not pass the environment either', errors)
            else:
                check(not r.ok, f'sandbox control: the probe "{name}" is broken; it fails even unsandboxed', errors)
        # Planting a symlink or a FIFO in place of the output must not leak or hang the harness.
        swaps = {
            'symlink': f"os.symlink({str(canary)!r}, 'out.json')",
            'fifo': "os.mkfifo('out.json')",
        }
        for name, swap in swaps.items():
            body = f"import atexit, os\natexit.register(lambda: (os.remove('out.json'), {swap}))\nreturn 0"
            leak = run.taskset.Spec('probe', 'solve', [], 'i64', [{'args': [], 'expected': 12345}])
            for box in ('bwrap', 'none'):
                r = execute.run(_probe(body), 'python', leak, timeout=5, sandbox=box)
                check(
                    r.status == 'runtime_error' and '12345' not in json.dumps(r.to_json()),
                    f'sandbox: a planted {name} output was read ({box}: {r.status}: {r.message})',
                    errors,
                )
        del os.environ['MIME_BENCH_CANARY']
    hogs = {
        'timeout': ('while True:\n    pass\nreturn 0', 'timeout'),
        'memory': ('x = bytearray(4 << 30)\nreturn 0', 'runtime_error'),
    }
    for name, (body, want) in hogs.items():
        r = execute.run(_probe(body), 'python', spec, timeout=2, sandbox='bwrap')
        check(r.status == want, f'sandbox: {name} probe ended as {r.status}, expected {want}', errors)
    return 'sandbox probes passed'


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--require-node', action='store_true')
    p.add_argument('--require-sandbox', action='store_true', help='fail if the bwrap sandbox cannot run')
    args = p.parse_args(argv)
    errors: list[str] = []

    # pass@k estimator
    check(report.pass_at_k(10, 0, 5) == 0.0, 'pass@5 with c=0 must be 0', errors)
    check(report.pass_at_k(10, 10, 5) == 1.0, 'pass@5 with c=n must be 1', errors)
    check(abs(report.pass_at_k(10, 3, 1) - 0.3) < 1e-12, 'pass@1 must be c/n', errors)
    check(abs(report.pass_at_k(10, 1, 5) - 0.5) < 1e-12, 'pass@5 with n=10, c=1 must be 0.5', errors)
    check(report.pass_at_k(3, 1, 5) is None, 'pass@k with n<k must be undefined', errors)

    langs = ['python']
    if execute.available('typescript') is None:
        langs.append('typescript')
    elif args.require_node:
        errors.append(f'typescript: {execute.available("typescript")}')

    with tempfile.TemporaryDirectory(prefix='mime-bench-smoke-') as tmp:
        out = Path(tmp) / 'smoke-mock'
        code = run.main(['--mock', '--samples', '6', '--lang', *langs, 'mime', '--out', str(out)])
        check(code == 0, f'run.py exited {code}', errors)
        rows = [json.loads(line) for line in (out / 'scores.jsonl').read_text().splitlines()]
        cells: dict[tuple, list[dict]] = defaultdict(list)
        for r in rows:
            cells[(r['track'], r['style'], r['lang'], r['model'], r['mode'])].append(r)

        def rate(**want: str | None) -> float:
            picked = [
                r
                for key, rs in cells.items()
                for r in rs
                if all(dict(zip(('track', 'style', 'lang', 'model', 'mode'), key))[k] == v for k, v in want.items())
            ]
            if not picked:
                errors.append(f'no rows for {want}')
                return -1.0
            return sum(r['passed'] for r in picked) / len(picked)

        for lang in langs:
            for track in ('generate', 'edit'):
                check(
                    rate(track=track, lang=lang, model='mock-reference') == 1.0,
                    f'{track}/{lang}: mock-reference must always pass',
                    errors,
                )
                check(
                    rate(track=track, lang=lang, model='mock-constant') == 0.0,
                    f'{track}/{lang}: mock-constant must always fail',
                    errors,
                )
                check(
                    rate(track=track, lang=lang, model='mock-flaky', mode='self-repair') == 1.0,
                    f'{track}/{lang}: mock-flaky must pass after self-repair',
                    errors,
                )
            z = rate(track='generate', lang=lang, model='mock-flaky', mode='zero-shot')
            check(0.0 < z < 1.0, f'generate/{lang}: mock-flaky zero-shot should pass sometimes, got {z}', errors)
            for style in ('honest', 'none', 'misleading'):
                check(
                    rate(track='names', style=style, lang=lang, model='mock-reference') == 1.0,
                    f'names/{style}/{lang}: mock-reference (reads definitions) must pass',
                    errors,
                )
                check(
                    rate(track='names', style=style, lang=lang, model='mock-constant') == 0.0,
                    f'names/{style}/{lang}: mock-constant must fail the composition rule',
                    errors,
                )
            check(
                rate(track='names', style='honest', lang=lang, model='mock-name-truster') == 1.0,
                f'names/honest/{lang}: mock-name-truster must pass',
                errors,
            )
            for style in ('none', 'misleading'):
                check(
                    rate(track='names', style=style, lang=lang, model='mock-name-truster') == 0.0,
                    f'names/{style}/{lang}: mock-name-truster must fail',
                    errors,
                )

        # mime: only the cells whose task has a mime reference run (design/step-12.md section 1).
        check(
            rate(track='generate', lang='mime', model='mock-reference') == 1.0,
            'generate/mime: mock-reference must always pass',
            errors,
        )
        check(
            rate(track='generate', lang='mime', model='mock-constant') == 0.0,
            'generate/mime: mock-constant must always fail',
            errors,
        )
        check(
            rate(track='generate', lang='mime', model='mock-flaky', mode='self-repair') == 1.0,
            'generate/mime: mock-flaky must pass after self-repair',
            errors,
        )
        mime_items = {r['task'] for r in rows if r['lang'] == 'mime'}
        check(mime_items == {'t1-002-clamp'}, f'mime cells must run only for clamp, ran {sorted(mime_items)}', errors)
        broken = [r for r in rows if r['lang'] == 'mime' and r['status'] == 'compile_error']
        check(bool(broken), 'some mime sample must end as a compile_error', errors)

        flaky = [r for r in rows if r['model'] == 'mock-flaky' and r['mode'] == 'self-repair' and r['attempts'] == 2]
        check(bool(flaky), 'some mock-flaky self-repair sample must need 2 attempts', errors)
        for r in flaky:
            t = r['tokens']
            check(
                t['retry'] > 0 and t['total'] == t['input'] + t['output'] and t['calls'] == 2,
                f'token ledger wrong for a retried sample: {t}',
                errors,
            )
            check(
                r['tokens_until_pass'] == t['total'], 'tokens_until_pass must equal total for a passing sample', errors
            )
            second = json.loads((out / r['raw_dir'] / 'a2.prompt.json').read_text())
            check(
                len(second) == 4 and 'did not pass' in second[-1]['content'],
                'the retry prompt must carry the earlier answer and the feedback',
                errors,
            )
            break

        man = json.loads((out / 'manifest.json').read_text())
        if execute.sandbox_available('bwrap') is None:
            check(man['sandbox']['backend'] == 'bwrap', 'mock runs must use the sandbox when it works', errors)
        check(man['status'] == 'complete', 'manifest status must be complete', errors)
        for key in ('git', 'skill_file', 'tasks_sha256', 'harness_sha256', 'runtimes', 'models', 'settings'):
            check(key in man, f'manifest lacks {key}', errors)
        text = report.build(out)
        check('## Names track' in text and 'Mock run' in text, 'report lacks sections', errors)

        dry = run.main(['--mock', '--dry-run'])
        check(dry == 0, 'dry run failed', errors)
        check(run.main(['--dry-run']) == 0, 'a dry run of the real models failed', errors)
        check(run.main([]) == 2, 'a real run without --allow-spend must be refused', errors)

    check_anthropic_adapter(errors)
    check_failures(errors)
    sandbox_note = check_sandbox(errors, args.require_sandbox)

    for e in errors:
        print(f'error: {e}')
    print(f'{"FAIL" if errors else "OK"}: smoke test, languages {", ".join([*langs, "mime"])}; {sandbox_note}')
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
