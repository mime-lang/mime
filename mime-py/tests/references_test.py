"""Checked references in abstracts (design/step-2.md, with the keys of step-4.md)."""

import pytest

from mime.compiler import analyze
from mime.diag import Diagnostic
from tests.run_cases import CONTEXT

NUMBER = '@number = {type = i64, abstract = "a whole number"}\n'


def mistakes(source: str) -> list[Diagnostic]:
    """The mistakes in `source` besides those in `CONTEXT`, which these programs are not about."""
    return [d for d in analyze(source)[1] if d.kind not in CONTEXT]


def same(abstract: str, word: str = '@same') -> str:
    return f'define {word} {{@number}} -> @number {{\n  ret @number\n}}\nabstract = "{abstract}"\n'


def kinds(source: str) -> list[str]:
    # These programs test other mistakes, so the rules about a whole program's words are not reported here; they have
    # tests of their own (check_test.py).
    return [d.kind for d in analyze(source)[1] if d.kind not in CONTEXT]


@pytest.mark.parametrize(
    'abstract',
    [
        'the @number it is given',
        'a @number, unchanged',
        "the @number's value",
        'the given (@number)',
        'a @number. Nothing else',
        'costs $5',
        'at \\@ 5 each',
        'a @number, which costs $0',
        'no references at all',
    ],
)
def test_valid_references(abstract: str) -> None:
    assert kinds(NUMBER + same(abstract)) == []


def test_an_abstract_may_name_an_earlier_definition() -> None:
    assert kinds(NUMBER + same('x') + same('like @same', '@again')) == []


@pytest.mark.parametrize(
    ('source', 'expected'),
    [
        (NUMBER + same('the @numbr it is given'), ['undeclared-word']),
        (NUMBER + same('the @same it is'), ['forward-reference']),
        (NUMBER + same('like @again') + same('x', '@again'), ['forward-reference']),
        (
            '@number = {type = i64, abstract = "less than @limit"}\n@limit = {type = i64, abstract = "x"}',
            ['forward-reference'],
        ),
        ('@number = {type = i64, abstract = "used by @same"}\n' + same('x'), ['forward-reference']),
        (NUMBER + same('at @ 5'), ['bad-reference']),
        (NUMBER + same('costs 5@'), ['bad-reference']),
        (NUMBER + same('a @Number'), ['bad-reference']),
        (NUMBER + same('write to help@example'), ['undeclared-word']),
        (NUMBER + same('a @numberX'), ['bad-reference']),
        (NUMBER + same('a @number-ish value'), ['bad-reference']),
        (NUMBER + same('a @númber'), ['bad-reference']),
        (NUMBER + same('@numbr and @ 5 and @same'), ['undeclared-word', 'bad-reference', 'forward-reference']),
    ],
)
def test_reference_mistakes(source: str, expected: list[str]) -> None:
    assert kinds(source) == expected


def test_only_abstracts_are_scanned() -> None:
    # A string in another slot is a bad value, and its `@` is not read as a reference.
    assert kinds('@number = {type = "@nothing", abstract = "x"}') == ['bad-value']


def test_hints() -> None:
    (d,) = mistakes(NUMBER + same('the @numbr it is given'))
    assert d.hint == 'did you mean `@number`?'
    (d,) = mistakes(NUMBER + same('the @same it is'))
    assert d.message == 'the abstract of `@same` refers to `@same` itself'
    later = '@number = {type = i64, abstract = "less than @limit"}\n@limit = {type = i64, abstract = "x"}'
    (d,) = mistakes(later)
    assert d.message == '`@limit` is declared after `@number`'
    assert d.hint == 'an abstract may refer only to earlier entries; move the entry for `@limit` above `@number`'
    (d,) = mistakes(NUMBER + same('at @ 5'))
    assert d.hint == 'write `\\@` for an at sign'
    (d,) = mistakes(NUMBER + same('a @numberX'))
    assert d.message == '`@number` is followed by `X`, which cannot appear in a name'


def test_an_abstract_that_names_a_result() -> None:
    source = NUMBER + (
        'define @f {@number} -> @number {\n  %double = add i64 @number, @number\n  ret %double\n}\n'
        'abstract = "the @double of it"\n'
    )
    (d,) = mistakes(source)
    assert (d.kind, d.key, d.text) == ('undeclared-word', 'abstract', '@double')
    assert d.hint == '`%double` is a local in the body of `@f`; an abstract refers only to entries'


def test_a_glued_character_is_read_as_in_code() -> None:
    # In code, `@numberX` is a syntax error; in an abstract it is the same mistake, not `@number` then `X`.
    assert kinds('@numberX = {type = i64, abstract = "x"}') == ['syntax']
    assert kinds(NUMBER + same('a @numberX')) == ['bad-reference']


def test_a_typo_for_a_later_word_says_to_move_it() -> None:
    source = '@number = {type = i64, abstract = "less than @limt"}\n@limit = {type = i64, abstract = "x"}'
    (d,) = mistakes(source)
    assert d.hint == 'did you mean `@limit`? It is declared later, so also move its entry above `@number`'


def test_the_position_is_the_dollar_sign_in_the_source() -> None:
    # `\"` counts as two columns, as it does in the source text.
    (d,) = mistakes('@number = {type = i64, abstract = "a \\"whole\\" @numbr"}')
    assert (d.line, d.column) == (1, 48)


def test_references_in_a_duplicate_entry_are_still_checked() -> None:
    assert kinds(NUMBER + '@number = {type = i64, abstract = "a @missing"}') == ['duplicate-word', 'undeclared-word']


def test_renaming_every_word_keeps_references_valid() -> None:
    source = NUMBER + same('the @number it is given') + same('like @same, on a @number', '@again')

    def rename(s: str) -> str:
        return s.replace('@number', '@w0').replace('@same', '@w1').replace('@again', '@w2')

    assert kinds(source) == []
    assert kinds(rename(source)) == []
    broken = source.replace('like @same,', 'like @again,')
    assert kinds(broken) == ['forward-reference']
    assert kinds(rename(broken)) == ['forward-reference']


def test_a_data_word_may_refer_to_an_earlier_function() -> None:
    assert kinds(NUMBER + same('x') + '@count = {type = i64, abstract = "how often @same runs"}') == []


def test_a_reference_to_a_later_function_says_to_move_it() -> None:
    (d,) = mistakes('@number = {type = i64, abstract = "used by @same"}\n' + same('x'))
    assert d.hint == 'an abstract may refer only to earlier entries; move the entry for `@same` above `@number`'
