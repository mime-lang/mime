"""The renaming invariant, checked on every golden (design/step-5.md section 6)."""

from pathlib import Path

import pytest

from mime.compiler import analyze, run
from mime.diag import FatalError
from mime.parser import parse
from mime.printer import canon, rename_text, words_in
from tests.run_cases import BACKENDS, every_case

GOLDENS = Path(__file__).parent / 'goldens'
# Every golden program, clean or with mistakes, as a path relative to `GOLDENS`.
NAMES = sorted(str(p.relative_to(GOLDENS).with_suffix('')) for p in GOLDENS.glob('*/*.mime') if '.' not in p.stem)


def scramble(source: str) -> tuple[str, dict[str, str]]:
    """Rename every word and local to a name that says nothing, of a different length, in reverse order."""
    words = words_in(source)
    mapping = {w: f'{w[0]}q{len(words) - i}zz{i * 7}' for i, w in enumerate(words)}
    return rename_text(source, mapping), mapping


@pytest.mark.parametrize('name', NAMES)
def test_renaming_keeps_the_diagnostics(name: str) -> None:
    source = (GOLDENS / f'{name}.mime').read_text()
    renamed, mapping = scramble(source)
    if mapping:
        assert renamed != source
    before, after = analyze(source)[1], analyze(renamed)[1]

    def entry(e: str | None) -> str | None:
        return e if e is None else mapping.get(e, e)

    assert [(d.kind, entry(d.entry), d.key) for d in before] == [(d.kind, d.entry, d.key) for d in after]


@pytest.mark.parametrize('name', NAMES)
def test_renaming_keeps_the_canonical_form(name: str) -> None:
    source = (GOLDENS / f'{name}.mime').read_text()
    try:
        module = parse(source)
    except FatalError:
        pytest.skip('the program does not parse, so it has no canonical form')
    renamed, _ = scramble(source)
    assert canon(parse(renamed)) == canon(module)


@pytest.mark.parametrize('name', NAMES)
def test_the_canonical_form_is_a_fixed_point(name: str) -> None:
    source = (GOLDENS / f'{name}.mime').read_text()
    try:
        form = canon(parse(source))
    except FatalError:
        pytest.skip('the program does not parse')
    assert canon(parse(form)) == form
    assert [d.kind for d in analyze(form)[1]] == [d.kind for d in analyze(source)[1]]


@pytest.mark.parametrize('backend', BACKENDS)
@pytest.mark.parametrize(('name', 'symbol', 'inputs', 'output'), every_case())
def test_renaming_keeps_the_behavior(name: str, symbol: str, inputs: list[str], output: str, backend: str) -> None:
    # A symbol is data, which no renaming changes, so the same run case names the same function after renaming.
    renamed, _ = scramble((GOLDENS / 'clean' / f'{name}.mime').read_text())
    program, _ = analyze(renamed)
    assert program is not None
    assert run(program, symbol, inputs, backend=backend) == output + '\n'
