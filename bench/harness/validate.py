#!/usr/bin/env python3
"""CI check for the benchmark. Exit code 0 means every check passed.

  python3 bench/harness/validate.py [--require-node] [--mime BIN]

Checks:
  tasks     folder names, tests.json schema, task.md signature, references pass, mutants fail
  variants  the three name styles are one program up to renaming; each style's reference passes
  edit      after.* pass the tests and before.* fail at least one
  repair    every stored diagnostic.json matches live `mime check` output, verbatim
  results   every scored sample has its raw prompt, output and result files
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import execute
import taskset
from taskset import EDIT_ID, EXT, STYLES, TASK_ID, TYPES, Spec

INT32 = 2**31
MANIFEST_KEYS = ('run_id', 'date', 'git', 'compiler', 'skill_file', 'tasks_sha256', 'settings', 'models', 'status')


class Checker:
    def __init__(self, require_node: bool) -> None:
        self.errors: list[str] = []
        self.notes: list[str] = []
        self.require_node = require_node

    def err(self, where: object, msg: str) -> None:
        self.errors.append(f'{where}: {msg}')

    def langs(self) -> list[str]:
        """Baseline languages to execute here."""
        out = ['python']
        reason = execute.available('typescript')
        if reason is None:
            out.append('typescript')
        elif self.require_node:
            self.err('typescript', reason)
        elif 'node: skipped' not in self.notes:
            self.notes.append('node: skipped')
            self.notes.append(f'TypeScript references were NOT run ({reason}); CI runs them with --require-node')
        return out


def value_ok(v: object, t: str) -> bool:
    if t == 'bool':
        return type(v) is bool
    if t == 'i64':
        return type(v) is int and -INT32 <= v < INT32
    if t == 'list<i64>':
        return isinstance(v, list) and all(value_ok(x, 'i64') for x in v)
    return False


def check_spec(c: Checker, where: str, path: Path, expect_id: str, tier: int | None) -> Spec | None:
    try:
        data = json.loads(path.read_text())
        spec = Spec.load(path)
    except (OSError, ValueError, KeyError, TypeError) as e:
        c.err(where, f'tests.json: {type(e).__name__}: {e}')
        return None
    if spec.id != expect_id:
        c.err(where, f'tests.json "task" is {spec.id!r}, expected the folder name {expect_id!r}')
    if tier is not None and data.get('tier') != tier:
        c.err(where, f'tests.json "tier" is {data.get("tier")!r}, but the folder name says {tier}')
    for t in [*spec.params, spec.returns]:
        if t not in TYPES:
            c.err(where, f'unknown type {t!r}; allowed: {", ".join(TYPES)}')
            return None
    if len(spec.cases) < 5:
        c.err(where, f'needs at least 5 cases, has {len(spec.cases)}')
    if not spec.examples():
        c.err(where, 'needs at least one case marked "example": true')
    if len(spec.examples()) == len(spec.cases):
        c.err(where, 'every case is an example; keep some hidden from the prompt')
    seen = set()
    for i, case in enumerate(spec.cases):
        extra = set(case) - {'args', 'expected', 'example'}
        if extra:
            c.err(where, f'case {i}: unknown keys {sorted(extra)}')
        args = case.get('args')
        if not isinstance(args, list) or len(args) != len(spec.params):
            c.err(where, f'case {i}: "args" must be a list of {len(spec.params)} values')
            continue
        for a, t in zip(args, spec.params):
            if not value_ok(a, t):
                c.err(where, f'case {i}: argument {json.dumps(a)} is not a 32-bit-safe {t}')
        if not value_ok(case.get('expected'), spec.returns):
            c.err(where, f'case {i}: expected {json.dumps(case.get("expected"))} is not a 32-bit-safe {spec.returns}')
        key = json.dumps(args)
        if key in seen:
            c.err(where, f'case {i}: duplicate args {key}')
        seen.add(key)
    return spec


def must_pass(c: Checker, where: str, source: str, lang: str, spec: Spec) -> None:
    r = execute.run(source, lang, spec)
    if not r.ok:
        detail = json.dumps(r.failures[0]) if r.failures else ''
        c.err(where, f'reference does not pass in {lang}: {r.status}: {r.message} {detail}'.rstrip())


def check_tasks(c: Checker) -> None:
    nums: dict[str, str] = {}
    for d in sorted(p for p in taskset.TASKS.iterdir() if p.is_dir()):
        where = f'tasks/{d.name}'
        m = TASK_ID.match(d.name)
        if not m:
            c.err(where, 'folder name must look like t<tier 1-3>-<3 digits>-<slug>, e.g. t1-001-sum-list')
            continue
        if m['num'] in nums:
            c.err(where, f'id {m["num"]} is already used by {nums[m["num"]]}')
        nums[m['num']] = d.name
        for name in ('task.md', 'tests.json', 'ref.py', 'ref.ts'):
            if not (d / name).is_file():
                c.err(where, f'missing {name}')
        if not (d / 'ref.mime').is_file() and not (d / 'ref.mime.todo').is_file():
            c.err(where, 'missing ref.mime (or ref.mime.todo until the compiler exists)')
        if not (d / 'tests.json').is_file():
            continue
        spec = check_spec(c, where, d / 'tests.json', d.name, int(m['tier']))
        if spec is None:
            continue
        if (d / 'task.md').is_file() and f'`{spec.neutral_signature()}`' not in (d / 'task.md').read_text():
            c.err(where, f'task.md must state the signature as `{spec.neutral_signature()}`')
        for lang in c.langs():
            ref = d / f'ref.{EXT[lang]}'
            if ref.is_file():
                must_pass(c, where, ref.read_text(), lang, spec)
        mutants = sorted((d / 'mutants').glob('*.py')) if (d / 'mutants').is_dir() else []
        if not mutants:
            c.err(where, 'needs at least one mutant in mutants/*.py')
        for mut in mutants:
            r = execute.run(mut.read_text(), 'python', spec)
            if r.ok:
                c.err(f'{where}/mutants/{mut.name}', 'passes every test; the tests are too weak to reject it')
            elif r.status == 'compile_error':
                c.err(f'{where}/mutants/{mut.name}', f'does not compile: {r.message}')
        if (d / 'variants').exists():
            check_variants(c, d, spec)


def check_variants(c: Checker, d: Path, spec: Spec) -> None:
    vdir = d / 'variants'
    where = f'tasks/{d.name}/variants'
    try:
        maps = json.loads((vdir / 'names.json').read_text())
        words = maps['words']
    except (OSError, ValueError, KeyError) as e:
        c.err(where, f'names.json: {type(e).__name__}: {e}')
        return
    for style in ('none', 'misleading'):
        mp = maps.get(style, {})
        if sorted(mp) != sorted(words):
            c.err(where, f'names.json "{style}" must map exactly the words {words}')
            return
        if len(set(mp.values())) != len(mp):
            c.err(where, f'names.json "{style}" maps two words to one name')
    if any(not v.startswith('w') or not v[1:].isdigit() for v in maps['none'].values()):
        c.err(where, 'names.json "none" names must be opaque labels like w1, w2')
    for w, v in maps['misleading'].items():
        if v == w:
            c.err(where, f'names.json "misleading" keeps {w!r} honest; every name must lie')
    if spec.entry in words:
        c.err(where, f'the entry {spec.entry!r} must not be a library word')
    honest = vdir / 'honest'
    files = sorted(p.name for p in honest.iterdir()) if honest.is_dir() else []
    for need in ('lib.py', 'lib.ts', 'ref.py', 'ref.ts'):
        if need not in files:
            c.err(f'{where}/honest', f'missing {need}')
    for style in STYLES:
        sdir = vdir / style
        if style != 'honest':
            for name in files:
                expected = taskset.rename((honest / name).read_text(), maps[style])
                target = sdir / name
                if not target.is_file() or target.read_text() != expected:
                    c.err(
                        f'{where}/{style}/{name}',
                        f'is not the honest file under the names.json renaming; run harness/make_variants.py {d.name}',
                    )
        style_words = words if style == 'honest' else [maps[style][w] for w in words]
        for lang in c.langs():
            lib, ref = sdir / f'lib.{EXT[lang]}', sdir / f'ref.{EXT[lang]}'
            if not lib.is_file() or not ref.is_file():
                continue
            if err := taskset.check_composition(ref.read_text(), lang, style_words, spec):
                c.err(f'{where}/{style}/ref.{EXT[lang]}', f'breaks the composition rule: {err}')
            must_pass(c, f'{where}/{style}', lib.read_text().rstrip() + '\n\n\n' + ref.read_text(), lang, spec)


def check_edits(c: Checker) -> None:
    for d in sorted(p for p in taskset.EDITS.iterdir() if p.is_dir()):
        where = f'edit/{d.name}'
        if not EDIT_ID.match(d.name):
            c.err(where, 'folder name must look like e<3 digits>-<slug>')
        for name in ('change.md', 'tests.json', 'before.py', 'before.ts', 'after.py', 'after.ts'):
            if not (d / name).is_file():
                c.err(where, f'missing {name}')
        if not (d / 'before.mime').is_file() and not (d / 'before.mime.todo').is_file():
            c.err(where, 'missing before.mime (or before.mime.todo until the compiler exists)')
        if not (d / 'tests.json').is_file():
            continue
        spec = check_spec(c, where, d / 'tests.json', d.name, None)
        if spec is None:
            continue
        for lang in c.langs():
            after, before = d / f'after.{EXT[lang]}', d / f'before.{EXT[lang]}'
            if after.is_file():
                must_pass(c, where, after.read_text(), lang, spec)
            if before.is_file() and execute.run(before.read_text(), lang, spec).ok:
                c.err(where, f'before.{EXT[lang]} already passes the tests; the change request is a no-op')


def check_repairs(c: Checker, mime_bin: str | None) -> None:
    cases = sorted(p for p in taskset.REPAIRS.iterdir() if p.is_dir())
    if not cases:
        c.notes.append('repair: no cases yet (they need the mime compiler)')
        return
    if not mime_bin:
        c.err(
            'repair',
            f'{len(cases)} case(s) but no `mime` compiler to re-check diagnostics against '
            '(put it on PATH or pass --mime)',
        )
        return
    for d in cases:
        where = f'repair/{d.name}'
        for name in ('broken.mime', 'diagnostic.json', 'expected.mime', 'tests.json'):
            if not (d / name).is_file():
                c.err(where, f'missing {name}')
        if not (d / 'broken.mime').is_file() or not (d / 'diagnostic.json').is_file():
            continue
        live = subprocess.run(
            [mime_bin, 'check', 'broken.mime'], check=False, cwd=d, capture_output=True, text=True
        )
        try:
            stored = json.loads((d / 'diagnostic.json').read_text())
            current = json.loads(live.stdout)
        except ValueError as e:
            c.err(where, f'diagnostic is not JSON: {e}')
            continue
        if stored != current:
            c.err(where, 'diagnostic.json no longer matches live `mime check broken.mime`; recapture and review')
        if (d / 'expected.mime').is_file():
            ok = subprocess.run(
                [mime_bin, 'check', 'expected.mime'], check=False, cwd=d, capture_output=True, text=True
            )
            if ok.returncode != 0:
                c.err(where, 'expected.mime does not check clean')


def check_results(c: Checker) -> None:
    for run in sorted(p for p in taskset.RESULTS.iterdir() if p.is_dir()):
        if run.name.endswith('-mock') or '-mock-' in run.name:
            continue  # mock runs test the harness; git ignores them
        where = f'results/{run.name}'
        if not (run / 'manifest.json').is_file() or not (run / 'scores.jsonl').is_file():
            c.err(where, 'needs manifest.json and scores.jsonl')
            continue
        man = json.loads((run / 'manifest.json').read_text())
        for key in MANIFEST_KEYS:
            if key not in man:
                c.err(where, f'manifest.json lacks {key!r}')
        if man.get('status') != 'complete':
            c.err(where, f'manifest status is {man.get("status")!r}, not "complete"')
        for i, line in enumerate((run / 'scores.jsonl').read_text().splitlines()):
            row = json.loads(line)
            raw = run / row['raw_dir']
            for a in range(1, row['attempts'] + 1):
                for suffix in ('prompt.json', 'output.txt', 'result.json'):
                    if not (raw / f'a{a}.{suffix}').is_file():
                        c.err(
                            f'{where} row {i}',
                            f'missing raw file {row["raw_dir"]}/a{a}.{suffix}; '
                            'a result without its raw outputs does not count',
                        )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--require-node', action='store_true', help='fail if TypeScript cannot run (CI sets this)')
    p.add_argument('--mime', help='mime compiler binary (default: MIME_BIN or `mime` on PATH)')
    args = p.parse_args(argv)
    c = Checker(args.require_node)
    check_tasks(c)
    check_edits(c)
    check_repairs(c, args.mime or os.environ.get('MIME_BIN') or shutil.which('mime'))
    check_results(c)
    for note in c.notes:
        if note != 'node: skipped':
            print(f'note: {note}')
    for e in c.errors:
        print(f'error: {e}')
    print(f'{"FAIL" if c.errors else "OK"}: {len(c.errors)} error(s)')
    return 1 if c.errors else 0


if __name__ == '__main__':
    sys.exit(main())
