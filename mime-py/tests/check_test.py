import pytest

from mime.compiler import analyze

NUMBER = '$number = {description = "a whole number", sort = i64}\n'
SAME = '$same = {description = "the number it is given", takes = $number, returns = $number, body = input}\n'


def kinds(source: str) -> list[str]:
    return [d.kind for d in analyze(source)[1]]


def test_the_step_1_program_is_clean() -> None:
    program, diagnostics = analyze(NUMBER + SAME)
    assert diagnostics == []
    assert program is not None
    assert program.sorts == {'number': 'i64'}
    assert [f.word for f in program.functions] == ['same']


def test_an_empty_module_is_clean() -> None:
    assert kinds('') == []


def test_whitespace_and_line_breaks_do_not_matter() -> None:
    source = '$number = {\n  description = "a whole number",\n\tsort = i64\n}\n'
    assert kinds(source) == []


def test_escapes_are_allowed_in_strings() -> None:
    assert kinds('$number = {description = "costs \\$5, a \\"price\\" with a \\\\", sort = i64}') == []


@pytest.mark.parametrize(
    ('source', 'expected'),
    [
        # syntax: the parser stops at the first one
        ('$number = description = "x"}', ['syntax']),
        ('$number = {description = "never closed, sort = i64}', ['syntax']),
        ('$number = {description = "bad \\n escape", sort = i64}', ['syntax']),
        ('$Number = {description = "x", sort = i64}', ['syntax']),
        ('$number = {description = "x" sort = i64}', ['syntax']),
        ('$number = {description = "x", sort = i64},' + SAME, ['syntax']),
        ('$number = {description = "x", sort = i64,}', ['trailing-comma']),
        ('; a note\n' + NUMBER, ['comment']),
        ('// a note\n' + NUMBER, ['comment']),
        ('# a note\n' + NUMBER, ['comment']),
        ('$pair = {description = "x", $first = {description = "y", sort = i64}}', ['nested-entry']),
        ('$pair = {description = "x", sort = {description = "y", sort = i64}}', ['nested-entry']),
        ('number = {description = "x", sort = i64}', ['unknown-language-word']),
        # checks: the checker reports every one
        (
            NUMBER + '$same = {description = "x", takes = number, returns = $number, body = input}',
            ['unknown-language-word'],
        ),
        ('$number = {description = "x", type = i64}', ['unknown-key']),
        ('$number = {description = "x", sort = i64, body = input}', ['unknown-key']),
        ('$number = {description = "x"}', ['missing-key']),
        ('$number = {}', ['missing-key']),
        (NUMBER + '$same = {description = "x", takes = $number, body = input}', ['missing-key']),
        ('$number = {sort = i64, description = "x"}', ['key-order']),
        ('$number = {description = "x", description = "y", sort = i64}', ['duplicate-key']),
        (NUMBER + NUMBER, ['duplicate-word']),
        (NUMBER + '$same = {description = "x", takes = $numbr, returns = $number, body = input}', ['undeclared-word']),
        (SAME + NUMBER, ['forward-reference', 'forward-reference']),
        (
            NUMBER + SAME + '$twice = {description = "x", takes = $same, returns = $number, body = input}',
            ['not-a-sort'],
        ),
        ('$number = {description = "costs $5", sort = i64}', ['bad-reference']),
        ('$number = {description = "", sort = i64}', ['bad-value']),
        ('$number = {description = number, sort = i64}', ['bad-value']),
        ('$number = {description = "x", sort = i32}', ['bad-value']),
        ('$number = {description = "x", sort = $number}', ['bad-value']),
        (NUMBER + '$same = {description = "x", takes = i64, returns = $number, body = input}', ['bad-value']),
        (NUMBER + '$same = {description = "x", takes = $number, returns = $number, body = $number}', ['bad-value']),
    ],
)
def test_each_mistake_has_its_kind(source: str, expected: list[str]) -> None:
    assert kinds(source) == expected


def test_the_checker_reports_every_mistake_in_order() -> None:
    source = '$same = {body = input, description = "x", takes = $numbr, returns = number}\n$n = {description = ""}\n'
    assert kinds(source) == ['key-order', 'undeclared-word', 'unknown-language-word', 'missing-key', 'bad-value']


def test_hints_point_at_the_fix() -> None:
    by_kind = {d.kind: d for d in analyze('$number = {description = "x", type = i64}')[1]}
    assert by_kind['unknown-key'].hint == 'did you mean `sort`?'
    (d,) = analyze(NUMBER + '$same = {description = "x", takes = $numbr, returns = $number, body = input}')[1]
    assert d.hint == 'did you mean `$number`?'
    (d,) = analyze('$number = {description = "x", sort = i32}')[1]
    assert d.hint == '`i32` arrives in a later step; the only sort in step 1 is `i64`'


def test_a_typo_hint_prefers_earlier_words() -> None:
    earlier = '$numbers = {description = "x", sort = i64}\n'
    later = '$number = {description = "x", sort = i64}\n'
    typo = '$same = {description = "x", takes = $numbe, returns = $numbers, body = input}\n'
    (d,) = analyze(earlier + typo + later)[1]
    assert d.hint == 'did you mean `$numbers`?'


def test_a_typo_hint_for_a_later_word_says_to_move_it() -> None:
    typo = '$same = {description = "x", takes = $numbr, returns = $numbr, body = input}\n'
    hints = {d.hint for d in analyze(typo + NUMBER)[1]}
    assert hints == {'did you mean `$number`? It is declared later, so also move its entry above `$same`'}


def test_positions_are_one_based_lines_and_columns() -> None:
    (d,) = analyze(NUMBER + '$same = {description = "x", takes = $numbr, returns = $number, body = input}')[1]
    assert (d.line, d.column) == (2, 37)
    (d,) = analyze('$number = {description = "costs $5", sort = i64}')[1]
    assert (d.line, d.column) == (1, 33)


def test_renaming_every_word_keeps_a_program_clean() -> None:
    renamed = NUMBER.replace('$number', '$w0') + SAME.replace('$number', '$w0').replace('$same', '$w1')
    program, diagnostics = analyze(renamed)
    assert diagnostics == []
    assert program is not None
    assert [f.word for f in program.functions] == ['w1']
