"""Declarations and definitions (design/step-4.md)."""

import pytest

from mime.compiler import analyze

NUMBER = '@number = {type = i64, abstract = "a whole number"}\n'
SAME = 'define @same {@number} -> @number {\n  ret @number\n}\nabstract = "the @number it is given"\n'


def kinds(source: str) -> list[str]:
    return [d.kind for d in analyze(source)[1]]


def define(head: str, body: str = 'ret @number', word: str = '@f') -> str:
    return f'define {word} {head} {{\n  {body}\n}}\nabstract = "x"\n'


def test_the_step_4_program_is_clean() -> None:
    program, diagnostics = analyze(NUMBER + SAME)
    assert diagnostics == []
    assert program is not None
    assert program.types == {'number': 'i64'}
    assert [(f.word, f.inputs, f.output) for f in program.functions] == [('same', ('number',), 'number')]


def test_an_empty_module_is_clean() -> None:
    assert kinds('') == []


def test_whitespace_and_line_breaks_do_not_matter() -> None:
    source = '@number = {\n  type = i64,\n\tabstract = "a whole number"\n}\ndefine @same {@number}->@number{ret @number}abstract="x"'
    assert kinds(source) == []


def test_escapes_are_allowed_in_strings() -> None:
    assert kinds('@number = {type = i64, abstract = "costs $5, at \\@ 5, a \\"price\\" with a \\\\"}') == []


@pytest.mark.parametrize(
    ('source', 'expected'),
    [
        # syntax: the parser stops at the first one
        ('@number = type = i64}', ['syntax']),
        ('@number = {type = i64, abstract = "never closed}', ['syntax']),
        ('@number = {type = i64, abstract = "bad \\n escape"}', ['syntax']),
        ('$Number = {type = i64, abstract = "x"}', ['syntax']),
        ('@number = {type = i64 abstract = "x"}', ['syntax']),
        ('@number = {type = i64, abstract = "x"},' + SAME, ['syntax']),
        ('@number = {type = i64, abstract = "x",}', ['trailing-comma']),
        ('; a note\n' + NUMBER, ['comment']),
        ('// a note\n' + NUMBER, ['comment']),
        ('# a note\n' + NUMBER, ['comment']),
        ('@pair = {abstract = "x", @first = {type = i64, abstract = "y"}}', ['nested-entry']),
        ('@pair = {type = {type = i64}, abstract = "x"}', ['nested-entry']),
        ('number = {type = i64, abstract = "x"}', ['unknown-language-word']),
        ('@f = {type = {@number} -> @number}', ['syntax']),
        ('@f = {description = "x", takes = @n, returns = @n, body = input}', ['unknown-key']),
        (NUMBER + SAME + '@late = {type = i64, abstract = "x"}', []),
        (define('{@late} -> @late', 'ret @late') + '@late = {type = i64, abstract = "x"}', ['forward-reference'] * 2),
        (NUMBER + 'define @f(@number) -> @number {ret @number} abstract = "x"', ['syntax']),
        (NUMBER + 'define i64 {@number} -> @number {ret @number} abstract = "x"', ['syntax']),
        (NUMBER + 'define @f {@number} @number {ret @number} abstract = "x"', ['syntax']),
        (NUMBER + 'define @f {@number}: @number {ret @number} abstract = "x"', ['syntax']),
        (NUMBER + 'define @f {@number} => @number {ret @number} abstract = "x"', ['syntax']),
        (NUMBER + 'define @f {@number} -> @number -> @number {ret @number} abstract = "x"', ['syntax']),
        (NUMBER + 'define @f {@number} -> @number {}  abstract = "x"', ['syntax']),
        (NUMBER + 'define @f {@number} -> @number {ret @number}', ['syntax']),
        (NUMBER + 'define @f {@number} -> @number {ret @number} abstract = x', ['syntax']),
        (NUMBER + 'define @f {i64} -> @number {ret 1} abstract = "x"', ['syntax']),
        (NUMBER + 'define @f {@number,} -> @number {ret @number} abstract = "x"', ['trailing-comma']),
        # checks: the checker reports every one
        ('@number = {type = i64}', ['missing-key']),
        ('@number = {}', ['missing-key']),
        ('@number = {abstract = "x", type = i64}', ['key-order']),
        ('@number = {type = i64, abstract = "x", abstract = "y"}', ['duplicate-key']),
        ('@number = {sort = i64, abstract = "x"}', ['unknown-key']),
        ('@number = {type = i64, description = "x"}', ['unknown-key']),
        ('@number = {type = i64, abstract = "x", takes = @number}', ['unknown-key']),
        (NUMBER + NUMBER, ['duplicate-word']),
        (NUMBER + SAME + SAME, ['duplicate-word']),
        (NUMBER + SAME.replace('@same', '@number'), ['duplicate-word']),
        ('@number = {type = i64, abstract = ""}', ['bad-value']),
        ('@number = {type = i64, abstract = number}', ['bad-value']),
        ('@number = {type = i32, abstract = "x"}', ['bad-value']),
        ('@number = {type = @number, abstract = "x"}', ['bad-value']),
        ('@pair = {type = {@a, @b}, abstract = "x"}', ['bad-value']),
        ('@number = {type = 5, abstract = "x"}', ['bad-value']),
        (NUMBER + define('{@numbr} -> @number'), ['undeclared-word', 'not-a-value']),
        (NUMBER + define('{@number, @number} -> @number'), ['duplicate-word']),
        (NUMBER + define('{@number} -> @numbr'), ['undeclared-word']),
        (NUMBER + define('{@number} -> i32'), ['bad-value']),
        (NUMBER + define('{@number} -> nope'), ['unknown-language-word']),
        (NUMBER + SAME + define('{@same} -> @number', 'ret 1'), ['bad-value']),
        (NUMBER + SAME + define('{@number} -> @same'), ['bad-value']),
        (NUMBER + define('{@number} -> @number', 'ret 1'), ['unused-local']),
    ],
)
def test_each_mistake_has_its_kind(source: str, expected: list[str]) -> None:
    assert kinds(source) == expected


def test_the_checker_reports_every_mistake_in_order() -> None:
    source = '@same = {abstract = "x", type = i32}\n@n = {type = i64, abstract = ""}\n'
    assert kinds(source) == ['key-order', 'bad-value', 'bad-value']


def test_hints_point_at_the_fix() -> None:
    def hint(source: str) -> str:
        (d,) = analyze(source)[1]
        assert d.hint is not None
        return d.hint

    assert hint('@number = {sort = i64, abstract = "x"}') == 'renamed: write `type`'
    assert hint('@number = {type = i64, description = "x"}') == 'renamed: write `abstract`'
    assert hint(NUMBER + define('{@numbr} -> @number', 'ret 1')) == 'did you mean `@number`?'
    assert hint('@number = {type = i32, abstract = "x"}') == 'the only type is `i64`'
    assert hint('@f = {type = {@n} -> @n}').startswith('write the type: `define @f')
    assert hint(NUMBER + 'define @f(@number) -> @number {ret @number} abstract = "x"').startswith('write the type')
    assert hint(NUMBER + define('{@number} -> @number', 'ret 1')) == 'remove `@number` from the type, or use it'


def test_positions_are_one_based_lines_and_columns() -> None:
    (d,) = analyze(NUMBER + define('{@numbr} -> @number', 'ret 1'))[1]
    assert (d.line, d.column) == (2, 12)
    (d,) = analyze('@number = {type = i64, abstract = "costs @ 5"}')[1]
    assert (d.line, d.column) == (1, 42)


def test_renaming_every_word_keeps_a_program_clean() -> None:
    renamed = (NUMBER + SAME).replace('@number', '@w0').replace('@same', '@w1')
    program, diagnostics = analyze(renamed)
    assert diagnostics == []
    assert program is not None
    assert [f.word for f in program.functions] == ['w1']


def test_data_words_and_definitions_interleave() -> None:
    # Every entry refers only to earlier entries, whatever its kind (design/layout.md section 1).
    source = NUMBER + SAME + '@count = {type = i64, abstract = "how many, like @same"}\n'
    source += define('{@count} -> @count', 'ret @count', '@tally')
    assert kinds(source) == []


def test_an_input_declared_later_is_one_mistake() -> None:
    source = define('{@late} -> @late', 'ret @late') + '@late = {type = i64, abstract = "x"}'
    diagnostics = analyze(source)[1]
    assert [d.kind for d in diagnostics] == ['forward-reference', 'forward-reference']
    assert {d.hint for d in diagnostics} == {'move the entry for `@late` above `@f`'}


@pytest.mark.parametrize(
    ('lines', 'expected'),
    [
        # reading the misspelled input itself is not reported again: that follows the word, not its spelling
        ('ret @numbr', ['undeclared-word']),
        # reading the word it was probably meant to be is reported, since guessing that depends on spelling
        ('%r = add i64 @number, 1\nret %r', ['undeclared-word', 'not-a-value']),
        ('%r = add i64 @numbr, @number\nret %r', ['undeclared-word', 'not-a-value']),
    ],
)
def test_a_misspelled_input_however_the_body_reads_it(lines: str, expected: list[str]) -> None:
    assert kinds(NUMBER + define('{@numbr} -> @number', lines)) == expected


def test_a_function_as_an_input_is_one_mistake() -> None:
    assert kinds(NUMBER + SAME + define('{@same} -> @number', 'ret @same')) == ['bad-value']


def test_a_misspelled_input_hints_the_word() -> None:
    typo, _ = analyze(NUMBER + define('{@numbr} -> @number', '%r = add i64 @number, 1\nret %r'))[1]
    assert (typo.kind, typo.text, typo.hint) == ('undeclared-word', '@numbr', 'did you mean `@number`?')


def test_an_undeclared_word_with_no_close_match_says_how_to_declare_it() -> None:
    (d,) = analyze(NUMBER + define('{@number} -> @total'))[1]
    assert d.hint == 'declare it above `@f`: `@total = {type = i64, abstract = "…"}`'


def test_the_abstract_inside_the_body() -> None:
    (d,) = analyze(NUMBER + 'define @f {@number} -> @number { ret @number abstract = "x" }')[1]
    assert (d.message, d.hint) == (
        'the abstract goes after the body',
        'close the body with `}`, then write `abstract = "…"`',
    )
