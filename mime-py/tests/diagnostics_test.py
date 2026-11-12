"""The fields of a diagnostic: `entry`, `key` and `text` (design/diagnostics.md)."""

import pytest

from mime.compiler import analyze

NUMBER = '$number = {description = "a whole number", sort = i64}\n'


def where(source: str) -> list[tuple[str | None, str | None, str | None]]:
    return [(d.entry, d.key, d.text) for d in analyze(source)[1]]


@pytest.mark.parametrize(
    ('source', 'expected'),
    [
        # mistakes the lexer finds, inside an entry the parser has started
        (
            '$number = {description = "never closed, sort = i64}',
            ('$number', 'description', '"never closed, sort = i64}'),
        ),
        ('$number = {description = "bad \\n escape", sort = i64}', ('$number', 'description', '\\n')),
        ('$number = {description = "x", sort = I64}', ('$number', 'sort', 'I64')),
        ('$number = {description = "x", sort = i64x-y}', ('$number', 'sort', 'i64x-y')),
        ('$number = {description = "x", // note\n sort = i64}', ('$number', None, '// note')),
        # mistakes outside any entry
        ('$Number = {description = "x", sort = i64}', (None, None, '$Number')),
        ('# note\n' + NUMBER, (None, None, '# note')),
        ('number = {description = "x", sort = i64}', (None, None, 'number')),
        # mistakes the parser finds
        ('$number = {description = "x" sort = i64}', ('$number', None, 'sort')),
        ('$number = {description = "x", sort = {}}', ('$number', 'sort', '{')),
        ('$number = {description = "x", sort = i64', ('$number', None, None)),
        # something missing has no text
        ('$number = {description = "x"}', ('$number', None, None)),
        # the text is copied from the source, escapes and all
        ('$number = {description = "a \\"whole\\" $numbr", sort = i64}', ('$number', 'description', '$numbr')),
        ('$number = {description = "", sort = i64}', ('$number', 'description', '""')),
    ],
)
def test_where_a_mistake_is(source: str, expected: tuple[str | None, str | None, str | None]) -> None:
    assert where(source) == [expected]


def test_positions_are_still_recorded() -> None:
    (d,) = analyze('$number = {description = "x", sort = i64X}')[1]
    assert (d.line, d.column) == (1, 41)
