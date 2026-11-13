"""The run cases of the clean goldens, `goldens/clean/NAME.runs.json`, which every backend must pass (step-8.md section 5)."""

import json
import shutil
from pathlib import Path

import pytest

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
    """The one layout of a run file: one case per line, its keys in the order `symbol`, `inputs`, `output`."""
    return '[\n' + ',\n'.join('  ' + json.dumps(c) for c in cases) + '\n]\n'


def load(name: str) -> list[dict[str, object]]:
    return json.loads((CLEAN / f'{name}.runs.json').read_text(encoding='utf-8'))


def every_case() -> list[tuple[str, str, list[str], str]]:
    """(golden, symbol, inputs, output) for every case of every clean golden."""
    out = []
    for p in sorted(CLEAN.glob('*.runs.json')):
        name = p.name.removesuffix('.runs.json')
        out += [(name, str(c['symbol']), list(c['inputs']), str(c['output'])) for c in load(name)]  # type: ignore[arg-type]
    return out
