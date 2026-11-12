"""Checked references in descriptions (design/step-2.md)."""

import pytest

from mime.compiler import analyze

NUMBER = '$number = {description = "a whole number", sort = i64}\n'


def same(description: str) -> str:
    return f'$same = {{description = "{description}", takes = $number, returns = $number, body = input}}\n'


def kinds(source: str) -> list[str]:
    return [d.kind for d in analyze(source)[1]]


@pytest.mark.parametrize(
    'description',
    [
        'the $number it is given',
        'a $number, unchanged',
        "the $number's value",
        'the given ($number)',
        'a $number. Nothing else',
        'costs \\$5',
        'a $number, which costs \\$0',
        'no references at all',
    ],
)
def test_valid_references(description: str) -> None:
    assert kinds(NUMBER + same(description)) == []


def test_a_reference_may_name_a_function_entry() -> None:
    twice = '$again = {description = "like $same", takes = $number, returns = $number, body = input}\n'
    assert kinds(NUMBER + same('x') + twice) == []


@pytest.mark.parametrize(
    ('source', 'expected'),
    [
        (NUMBER + same('the $numbr it is given'), ['undeclared-word']),
        (NUMBER + same('the $same it is'), ['forward-reference']),
        (
            '$number = {description = "less than $limit", sort = i64}\n$limit = {description = "x", sort = i64}',
            ['forward-reference'],
        ),
        (NUMBER + same('costs $5'), ['bad-reference']),
        (NUMBER + same('costs 5$'), ['bad-reference']),
        (NUMBER + same('a $Number'), ['bad-reference']),
        (NUMBER + same('a $numberX'), ['bad-reference']),
        (NUMBER + same('a $number-ish value'), ['bad-reference']),
        (NUMBER + same('a $númber'), ['bad-reference']),
        (NUMBER + same('$numbr and $5 and $same'), ['undeclared-word', 'bad-reference', 'forward-reference']),
    ],
)
def test_reference_mistakes(source: str, expected: list[str]) -> None:
    assert kinds(source) == expected


def test_only_descriptions_are_scanned() -> None:
    # A string in another slot is a bad value, and its `$` is not read as a reference.
    assert kinds('$number = {description = "x", sort = "$nothing"}') == ['bad-value']


def test_hints() -> None:
    (d,) = analyze(NUMBER + same('the $numbr it is given'))[1]
    assert d.hint == 'did you mean `$number`?'
    (d,) = analyze(NUMBER + same('the $same it is'))[1]
    assert d.message == 'the description of `$same` refers to `$same` itself'
    later = '$number = {description = "less than $limit", sort = i64}\n$limit = {description = "x", sort = i64}'
    (d,) = analyze(later)[1]
    assert d.message == '`$limit` is declared after `$number`'
    assert d.hint == 'a description may refer only to earlier entries; move the entry for `$limit` above `$number`'
    (d,) = analyze(NUMBER + same('costs $5'))[1]
    assert d.hint == 'write `\\$` for a dollar sign'
    (d,) = analyze(NUMBER + same('a $numberX'))[1]
    assert d.message == '`$number` is followed by `X`, which cannot appear in a name'


def test_a_glued_character_is_read_as_in_code() -> None:
    # In code, `$numberX` is a syntax error; in a description it is the same mistake, not `$number` then `X`.
    assert kinds('$numberX = {description = "x", sort = i64}') == ['syntax']
    assert kinds(NUMBER + same('a $numberX')) == ['bad-reference']


def test_renaming_every_word_keeps_references_valid() -> None:
    source = (
        NUMBER
        + same('the $number it is given')
        + ('$again = {description = "like $same, on a $number", takes = $number, returns = $number, body = input}\n')
    )
    renamed = source.replace('$number', '$w0').replace('$same', '$w1').replace('$again', '$w2')
    assert kinds(source) == []
    assert kinds(renamed) == []
    broken = source.replace('$same,', '$again,')
    assert kinds(broken) == ['forward-reference']
    assert kinds(broken.replace('$number', '$w0').replace('$same', '$w1').replace('$again', '$w2')) == [
        'forward-reference'
    ]


def test_a_typo_for_a_later_word_says_to_move_it() -> None:
    source = '$number = {description = "less than $limt", sort = i64}\n$limit = {description = "x", sort = i64}'
    (d,) = analyze(source)[1]
    assert d.hint == 'did you mean `$limit`? It is declared later, so also move its entry above `$number`'


def test_the_position_is_the_dollar_sign_in_the_source() -> None:
    # `\"` counts as two columns, as it does in the source text.
    (d,) = analyze('$number = {description = "a \\"whole\\" $numbr", sort = i64}')[1]
    assert (d.line, d.column) == (1, 39)


def test_references_in_a_duplicate_entry_are_still_checked() -> None:
    assert kinds(NUMBER + '$number = {description = "a $missing", sort = i64}') == ['duplicate-word', 'undeclared-word']
