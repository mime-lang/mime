"""The run cases of the clean goldens, `goldens/clean/NAME.runs.json`, which every backend must pass (step-8.md section 5)."""

import json
import shutil
from pathlib import Path

import pytest

from mime.checker import Program
from mime.compiler import run
from mime.diag import ToolError

CLEAN = Path(__file__).parent / 'goldens' / 'clean'
BACKENDS = [
    pytest.param('interp', id='interp'),
    pytest.param(
        'llvm',
        id='llvm',
        marks=pytest.mark.skipif(shutil.which('clang') is None, reason='the llvm backend needs clang'),
    ),
]


def layout(cases: list[dict[str, object]]) -> str:
    """The one layout of a run file: one case per line, its keys in the order `symbol`, `inputs`, then `output` or
    `limit`."""
    return '[\n' + ',\n'.join('  ' + json.dumps(c) for c in cases) + '\n]\n'


def load(name: str) -> list[dict[str, object]]:
    return json.loads((CLEAN / f'{name}.runs.json').read_text(encoding='utf-8'))


def every_case() -> list[tuple[str, str, list[str], str]]:
    """(golden, symbol, inputs, expected) for every case of every clean golden. `expected` is the printed output with
    its newline, or the start of the message of a limit the run must reach (design/step-9.md section 6)."""
    out = []
    for p in sorted(CLEAN.glob('*.runs.json')):
        name = p.name.removesuffix('.runs.json')
        for c in load(name):
            expected = LIMITS[str(c['limit'])] if 'limit' in c else str(c['output']) + '\n'
            out.append((name, str(c['symbol']), [str(x) for x in c['inputs']], expected))  # type: ignore[union-attr]
    return out


LIMITS = {'stack': 'ran out of stack'}


def outcome(program: Program, symbol: str, inputs: list[str], backend: str) -> str:
    """What a run prints, or the message it stops with."""
    try:
        return run(program, symbol, inputs, backend=backend)
    except ToolError as e:
        return str(e)


def matches(got: str, expected: str) -> bool:
    return got == expected if expected.endswith('\n') else expected in got
