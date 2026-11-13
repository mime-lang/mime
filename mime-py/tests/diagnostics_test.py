"""The fields of a diagnostic: `entry`, `key` and `text` (design/diagnostics.md)."""

import pytest

from mime.compiler import analyze
from mime.diag import Diagnostic

NUMBER = '@number = {type = i64, abstract = "a whole number"}\n'


def mistakes(source: str) -> list[Diagnostic]:
    """The mistakes in `source` besides `unused-word`, which these programs are not about."""
    return [d for d in analyze(source)[1] if d.kind != 'unused-word']


def where(source: str) -> list[tuple[str | None, str | None, str | None]]:
    return [(d.entry, d.key, d.text) for d in mistakes(source)]


def define(lines: str) -> str:
    return NUMBER + f'define @f {{@number}} -> @number {{\n{lines}\n}}\nabstract = "x"\n'


@pytest.mark.parametrize(
    ('source', 'expected'),
    [
        # mistakes the lexer finds, inside an entry the parser has started
        ('@number = {type = i64, abstract = "never closed}', ('@number', 'abstract', '"never closed}')),
        ('@number = {type = i64, abstract = "bad \\n escape"}', ('@number', 'abstract', '\\n')),
        ('@number = {type = I64, abstract = "x"}', ('@number', 'type', 'I64')),
        ('@number = {type = i64x-y, abstract = "x"}', ('@number', 'type', 'i64x-y')),
        ('@number = {type = i64, // note\n abstract = "x"}', ('@number', None, '// note')),
        (define('ret $number'), ('@f', 'body', '$number')),
        # mistakes outside any entry
        ('$Number = {type = i64, abstract = "x"}', (None, None, '$Number')),
        ('# note\n' + NUMBER, (None, None, '# note')),
        ('number = {type = i64, abstract = "x"}', (None, None, 'number')),
        # mistakes the parser finds
        ('@number = {type = i64 abstract = "x"}', ('@number', None, 'abstract')),
        ('@number = {type = i64, abstract = "x"', ('@number', None, None)),
        (define('%r = add {i64, @number, 1}\nret %r'), ('@f', 'body', '{')),
        (NUMBER + 'define @f(@number) -> @number {ret @number} abstract = "x"', ('@f', 'type', '(')),
        # something missing has no text
        ('@number = {type = i64}', ('@number', None, None)),
        # the text is copied from the source, escapes and all
        ('@number = {type = i64, abstract = "a \\"whole\\" @numbr"}', ('@number', 'abstract', '@numbr')),
        ('@number = {type = i64, abstract = ""}', ('@number', 'abstract', '""')),
        (define('ret @nope'), ('@f', 'type', '@number')),
    ],
)
def test_where_a_mistake_is(source: str, expected: tuple[str | None, str | None, str | None]) -> None:
    assert where(source)[0] == expected


def test_positions_are_still_recorded() -> None:
    (d,) = mistakes('@number = {type = i64X, abstract = "x"}')
    assert (d.line, d.column) == (1, 22)
