"""Bodies: lines of operations ending in `ret` (design/step-4.md)."""

import json
import re
import shutil
from pathlib import Path

import pytest

from mime.cli import main
from mime.compiler import analyze

NUMBER = '@number = {type = i64, abstract = "a whole number"}\n'
GOLDENS = Path(__file__).parent / 'goldens'
needs_clang = pytest.mark.skipif(shutil.which('clang') is None, reason='mime run needs clang')
MIN, MAX = -(2**63), 2**63 - 1


def function(lines: str, word: str = '@f', head: str = '{@number} -> @number') -> str:
    return f'define {word} {head} {{\n{lines}\n}}\nabstract = "x"\n'


def kinds(source: str) -> list[str]:
    return [d.kind for d in analyze(source)[1]]


@pytest.mark.parametrize(
    'lines',
    [
        'ret @number',
        '%r = add i64 @number, 1\nret %r',
        '%a = add i64 @number, @number\n%b = mul i64 %a, %a\n%c = sub i64 %b, %a\nret %c',
        '%a = sub i64 0, @number\n  ret %a',
        f'%a = add i64 @number, {MIN}\n%b = add i64 %a, {MAX}\nret %b',
    ],
)
def test_valid_bodies(lines: str) -> None:
    assert kinds(NUMBER + function(lines)) == []


@pytest.mark.parametrize('ret', ['7', '-7', '0'])
def test_a_function_with_no_inputs_returns_a_constant(ret: str) -> None:
    assert kinds(NUMBER + function(f'ret {ret}', head='{} -> @number')) == []


def test_two_functions_may_share_a_result_word() -> None:
    source = NUMBER + function('%s = add i64 @number, 1\nret %s') + function('%s = mul i64 @number, 2\nret %s', '@g')
    assert kinds(source) == []


@pytest.mark.parametrize(
    ('lines', 'expected'),
    [
        # parser: stops at the first
        ('ret @number + 1', ['syntax']),
        ('ret @number - 1', ['syntax']),
        ('ret @number -1', ['syntax']),
        ('%r = add(i64, @number, 1)\nret %r', ['syntax']),
        ('%r = add {i64, @number, 1}\nret %r', ['syntax']),
        ('%r = add i64 mul i64 @number, 2, 1\nret %r', ['nested-operation']),
        ('%r = add i64 @number 1\nret %r', ['syntax']),
        ('%r = add i64 @number, 1, 2\nret %r', ['syntax']),
        ('r = add i64 @number, 1\nret r', ['syntax']),
        ('%r = @number\nret %r', ['syntax']),
        ('%r = add i64 @number, 007\nret %r', ['syntax']),
        ('%r = add i64 @number, -0\nret %r', ['syntax']),
        ('%r = add i64 @number, 12a\nret %r', ['syntax']),
        ('%r = add i64 @number, 5-3\nret %r', ['syntax']),
        ('%r = add i64 @number, 1', ['syntax']),
        ('ret @number\n%r = add i64 @number, 1', ['syntax']),
        ('ret i64 @number', ['syntax']),
        ('%r = phi i64 @number, 1\nret %r', ['syntax']),
        ('%r = add nsw i64 @number, 1\nret %r', ['syntax']),
        ('@done:\nret @number', ['syntax']),
        ('let %r = add {i64, @number, 1} in %r', ['syntax']),
        ('ret input', ['syntax']),
        ('ret nope', ['unknown-language-word']),
        # checker: reports every one
        ('%r = div i64 @number, 2\nret %r', ['unknown-language-word']),
        ('%r = sdiv i64 @number, 2\nret %r', ['bad-value']),
        ('%r = type i64 @number, 2\nret %r', ['bad-value']),
        ('%r = add i32 @number, 1\nret %r', ['bad-value']),
        ('%r = add @number @number, 1\nret %r', ['syntax']),
        (f'%r = add i64 @number, {MAX + 1}\nret %r', ['bad-value']),
        ('%r = add i64 @number, @nope\nret %r', ['undeclared-word']),
        ('%r = add i64 @number, %r\nret %r', ['forward-reference']),
        ('%r = add i64 @number, %s\n%s = add i64 %r, 1\nret %s', ['forward-reference']),
        ('@number = add i64 @number, 1\nret @number', ['syntax']),
        ('%r = add i64 @number, 1\n%r = add i64 %r, 1\nret %r', ['duplicate-word']),
        ('%r = add i64 @number, 1\nret @number', ['unused-local']),
        ('%a = add i64 @number, 1\n%b = add i64 @number, 2\nret %b', ['unused-local']),
        ('ret @nope', ['unused-local', 'undeclared-word']),
    ],
)
def test_body_mistakes(lines: str, expected: list[str]) -> None:
    assert kinds(NUMBER + function(lines)) == expected


def test_a_local_spelled_like_an_input() -> None:
    # The hint uses the spelling; what is reported does not, so a renaming cannot change it.
    diagnostics = analyze(NUMBER + function('ret %number'))[1]
    assert [(d.kind, d.text) for d in diagnostics] == [('unused-local', '@number'), ('undeclared-word', '%number')]
    assert diagnostics[1].hint == 'an input is its word: write `@number`'


def test_a_body_reads_only_its_inputs() -> None:
    other = '@other = {type = i64, abstract = "another number"}\n'
    (d,) = analyze(NUMBER + other + function('%r = add i64 @number, @other\nret %r'))[1]
    assert (d.kind, d.text) == ('not-a-value', '@other')
    assert d.hint is not None
    assert d.hint.endswith('to read it, list it in the inputs')


def test_a_typo_for_a_result_suggests_the_result() -> None:
    # The misspelled local and the unread one are both reported: guessing which local a typo means depends on
    # spelling, so it may change the hint but never what is reported (design/step-5.md section 1).
    unused, typo = analyze(NUMBER + function('%double = add i64 @number, @number\nret %doubel'))[1]
    assert (unused.kind, unused.text) == ('unused-local', '%double')
    assert (typo.kind, typo.hint) == ('undeclared-word', 'did you mean `%double`?')


def test_a_wrong_return_leaves_the_right_result_unused() -> None:
    (d,) = analyze(NUMBER + function('%a = add i64 @number, 1\n%b = mul i64 %a, 2\nret %a'))[1]
    assert (d.kind, d.text) == ('unused-local', '%b')


def test_an_ignored_input_is_reported_on_the_type() -> None:
    (d,) = analyze(NUMBER + function('ret 7'))[1]
    assert (d.kind, d.key, d.text) == ('unused-local', 'type', '@number')


def test_renaming_results_keeps_a_program_clean() -> None:
    source = NUMBER + function('%a = add i64 @number, 1\n%b = mul i64 %a, %a\nret %b')
    names = {'a': 'w9', 'b': 'w8', 'number': 'w0', 'f': 'w1'}
    renamed = re.sub(r'([@%])([a-z][a-z0-9_]*)', lambda m: m.group(1) + names.get(m.group(2), m.group(2)), source)
    assert renamed != source
    assert kinds(renamed) == []


@needs_clang
@pytest.mark.parametrize(
    ('golden', 'word', 'args', 'expected'),
    [
        ('affine', '@affine', ['5'], 16),
        ('affine', '@affine', ['-1'], -2),
        ('arithmetic', '@square', ['-12'], 144),
        ('arithmetic', '@less', ['0'], -1),
        ('arithmetic', '@negate', ['9'], -9),
        ('arithmetic', '@difference', ['10', '3'], 7),
        ('arithmetic', '@seven', [], 7),
        # overflow wraps
        ('arithmetic', '@less', [str(MIN)], MAX),
        ('arithmetic', '@negate', [str(MIN)], MIN),
        ('arithmetic', '@sum', ['-1'], MAX),
        ('arithmetic', '@square', [str(2**32)], 0),
        ('arithmetic', '@difference', [str(MIN), '1'], MAX),
        ('affine', '@affine', [str(MAX)], MAX - 1),
    ],
)
def test_run(golden: str, word: str, args: list[str], expected: int, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(['run', str(GOLDENS / f'{golden}.mime'), word, *args]) == 0
    assert int(capsys.readouterr().out) == expected


def test_uses_finds_results(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / 'p.mime'
    p.write_text(NUMBER + function('%a = add i64 @number, 1\n%b = mul i64 %a, %a\nret %b'))
    assert main(['uses', str(p), '%a']) == 0
    assert json.loads(capsys.readouterr().out) == [{'entry': '@f', 'key': 'body', 'text': '%a'}] * 2


def test_every_lowered_instruction_wraps() -> None:
    ir = (GOLDENS / 'affine.ll').read_text() + (GOLDENS / 'arithmetic.ll').read_text()
    assert re.search(r'\b(nsw|nuw)\b', ir) is None


@pytest.mark.parametrize(
    ('lines', 'hint'),
    [
        ('ret @number -1', 'arithmetic is written as an operation'),
        ('ret @number-1', 'arithmetic is written as an operation'),
        ('%r = add i64 @number -1\nret %r', None),
        ('ret @my-word', 'a name is a lowercase letter'),
        ('ret $number', 'words are written `@name`'),
        ('ret i64 @number', 'the type comes from the definition'),
        ('%r = phi i64 @number, 1\nret %r', 'use block parameters'),
        ('%r = add nsw i64 @number, 1\nret %r', 'overflow always wraps'),
        ('let %r = add {i64, @number, 1} in %r', 'write `%x = add i64 %a, %b`'),
        ('ret input', 'the inputs are the words of the type'),
    ],
)
def test_hints_for_old_forms_and_llvm_habits(lines: str, hint: str | None) -> None:
    (d,) = analyze(NUMBER + function(lines))[1]
    assert d.kind in ('syntax', 'unknown-language-word', 'undeclared-word')
    if hint is not None:
        assert d.hint is not None
        assert d.hint.startswith(hint)
