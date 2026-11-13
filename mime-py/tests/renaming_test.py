"""The renaming invariant, checked on every golden (design/step-5.md section 6)."""

import itertools
import random
from dataclasses import replace
from pathlib import Path

import pytest

from mime.compiler import analyze
from mime.diag import FatalError
from mime.parser import Definition, Module, item_refs, item_word, parse
from mime.printer import canon, keep_words, layout, rename_text, words_in
from tests.run_cases import BACKENDS, every_case, matches, outcome

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
@pytest.mark.parametrize(('name', 'symbol', 'inputs', 'expected'), every_case())
def test_renaming_keeps_the_behavior(name: str, symbol: str, inputs: list[str], expected: str, backend: str) -> None:
    # A symbol is data, which no renaming changes, so the same run case names the same function after renaming.
    renamed, _ = scramble((GOLDENS / 'clean' / f'{name}.mime').read_text())
    program, _ = analyze(renamed)
    assert program is not None
    assert matches(outcome(program, symbol, inputs, backend), expected)


CLEAN = sorted(n for n in NAMES if n.startswith('clean/'))


def shuffle(module: Module, rng: random.Random) -> Module:
    """The module with its data words and declarations moved to random places that still declare before use, and
    its definitions in their order (design/step-11.md section 1)."""
    items = list(module.items)
    defines = [i for i, x in enumerate(items) if isinstance(x, Definition)]
    first: dict[str, int] = {}  # word -> the item a reference to it must come after
    for i, x in enumerate(items):
        first.setdefault(item_word(x), i)
    after: dict[int, set[int]] = {i: {first[w] for w in item_refs(x) if w in first} - {i} for i, x in enumerate(items)}
    for a, b in itertools.pairwise(defines):
        after[b].add(a)
    order: list[int] = []
    while len(order) < len(items):
        ready = [i for i in range(len(items)) if i not in order and after[i] <= set(order)]
        order.append(rng.choice(ready))
    return replace(module, items=tuple(items[i] for i in order))


@pytest.mark.parametrize('name', CLEAN)
def test_placement_and_renaming_keep_the_canonical_form(name: str) -> None:
    module = parse((GOLDENS / f'{name}.mime').read_text())
    form = canon(module)
    rng = random.Random(name)
    for _ in range(10):
        moved = layout(shuffle(module, rng))
        assert analyze(moved)[1] == []
        renamed, _ = scramble(moved)
        assert canon(parse(renamed)) == form


def test_keep_words_moves_words_and_declarations_and_keeps_the_definitions() -> None:
    source = (GOLDENS / 'clean' / 'even_odd.mime').read_text()
    n, flag, rest = source.split('\n', 2)
    assert n.startswith('@n =')
    assert flag.startswith('@flag =')
    swapped = f'{flag}\n{n}\n{rest}'  # @even reads @n before @flag, so canon puts @n back first
    assert keep_words(parse(swapped)) == keep_words(parse(source))
    assert keep_words(parse(swapped)).startswith(f'{n}\n{flag}\n\ndeclare @odd')
