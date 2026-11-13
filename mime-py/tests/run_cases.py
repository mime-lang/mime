"""The run cases of the clean goldens, `goldens/clean/NAME.runs.json`, which every backend must pass (step-8.md section 5)."""

import json
import re
import shutil
from pathlib import Path

import pytest

from mime.checker import Program
from mime.compiler import run
from mime.diag import ToolError, Trap

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
    """The one layout of a run file: one case per line, its keys in the order `symbol`, `inputs`, then `output`,
    `trap` or `limit`."""
    return '[\n' + ',\n'.join('  ' + json.dumps(c) for c in cases) + '\n]\n'


def load(name: str) -> list[dict[str, object]]:
    return json.loads((CLEAN / f'{name}.runs.json').read_text(encoding='utf-8'))


def every_case() -> list[tuple[str, str, list[str], str]]:
    """(golden, symbol, inputs, expected) for every case of every clean golden. `expected` is the printed output with
    its newline, the trap it must reach as `trap: MESSAGE` (design/step-13.md section 3), or the start of the message
    of a limit the run must reach (design/step-9.md section 6)."""
    out = []
    for p in sorted(CLEAN.glob('*.runs.json')):
        name = p.name.removesuffix('.runs.json')
        for c in load(name):
            if 'limit' in c:
                expected = LIMITS[str(c['limit'])]
            elif 'trap' in c:
                expected = f'trap: {c["trap"]}\n'
            else:
                expected = str(c['output']) + '\n'
            out.append((name, str(c['symbol']), [str(x) for x in c['inputs']], expected))  # type: ignore[union-attr]
    return out


LIMITS = {'stack': 'ran out of stack'}


def outcome(program: Program, symbol: str, inputs: list[str], backend: str) -> str:
    """What a run prints, or the message it stops with. A trap is `trap: MESSAGE` on the interpreter, which promises
    its report, and `trap` on any other backend, which only promises to trap (design/step-13.md section 3)."""
    try:
        return run(program, symbol, inputs, backend=backend)
    except Trap as e:
        return f'trap: {e.diagnostic.message}\n' if backend == 'interp' else 'trap\n'
    except ToolError as e:
        return str(e)


def matches(got: str, expected: str) -> bool:
    if got == 'trap\n':  # a backend other than the interpreter trapped, which is all it promises
        return expected.startswith('trap: ')
    return got == expected if expected.endswith('\n') else expected in got


# The rules about a whole program's words: a data word nothing refers to, and an input its function's abstract
# leaves out. Tests of other mistakes write short programs that break these on purpose, so they leave them out.
CONTEXT = frozenset({'unused-word', 'unmentioned-input'})


def abstract_for(head: str) -> str:
    """A placeholder abstract that names every input of `head`, such as `{@a, @b} -> @c`, so a test program stays clean.

    Its English says nothing: the tests that use it are about bodies, not abstracts.
    """
    inputs = re.findall(r'@\w+', head.split('->')[0])
    return 'abstract = "x' + (' of ' + ' and '.join(inputs) if inputs else '') + '"'
