"""Arithmetic bodies (design/step-3.md)."""

import json
import re
import shutil
from pathlib import Path

import pytest

from mime.cli import main
from mime.compiler import analyze

NUMBER = '$number = {description = "a whole number", sort = i64}\n'
GOLDENS = Path(__file__).parent / 'goldens'
needs_clang = pytest.mark.skipif(shutil.which('clang') is None, reason='mime run needs clang')
MIN, MAX = -(2**63), 2**63 - 1


def function(body: str, word: str = '$f') -> str:
    return f'{word} = {{description = "x", takes = $number, returns = $number, body = {body}}}\n'


def kinds(source: str) -> list[str]:
    return [d.kind for d in analyze(source)[1]]


@pytest.mark.parametrize(
    'body',
    [
        'input',
        '7',
        '-7',
        '0',
        'let $r = add {i64, input, 1} in $r',
        'let $a = add {i64, input, input} in let $b = mul {i64, $a, $a} in let $c = sub {i64, $b, $a} in $c',
        'let $a = sub {i64, 0, input} in\n  $a',
        f'let $a = add {{i64, {MIN}, {MAX}}} in $a',
    ],
)
def test_valid_bodies(body: str) -> None:
    assert kinds(NUMBER + function(body)) == []


def test_two_functions_may_share_a_local_word() -> None:
    source = (
        NUMBER + function('let $s = add {i64, input, 1} in $s') + function('let $s = mul {i64, input, 2} in $s', '$g')
    )
    assert kinds(source) == []


@pytest.mark.parametrize(
    ('body', 'expected'),
    [
        # parser: stops at the first
        ('input + 1', ['syntax']),
        ('input - 1', ['syntax']),
        ('add(i64, input, 1)', ['syntax']),
        ('add {i64, input, 1}', ['syntax']),
        ('let $r = add {i64, mul {i64, input, 2}, 1} in $r', ['nested-operation']),
        ('let $r = add {i64, input, 1} $r', ['syntax']),
        ('let r = add {i64, input, 1} in r', ['syntax']),
        ('let $r = $s in $r', ['syntax']),
        ('let $r = add {i64, input, 1,} in $r', ['trailing-comma']),
        ('let $r = add {i64, input, 007} in $r', ['syntax']),
        ('let $r = add {i64, input, -0} in $r', ['syntax']),
        ('let $r = add {i64, input, 12a} in $r', ['syntax']),
        ('let $r = add {i64, input, 5-3} in $r', ['syntax']),
        # checker: reports every one
        ('let $r = div {i64, input, 2} in $r', ['unknown-language-word']),
        ('let $r = sdiv {i64, input, 2} in $r', ['bad-value']),
        ('let $r = i64 {i64, input, 2} in $r', ['bad-value']),
        ('let $r = add {$number, input, 1} in $r', ['bad-value']),
        ('let $r = add {i32, input, 1} in $r', ['bad-value']),
        ('let $r = add {i64, input} in $r', ['bad-value']),
        ('let $r = add {i64, input, 1, 2} in $r', ['bad-value']),
        (f'let $r = add {{i64, input, {MAX + 1}}} in $r', ['bad-value']),
        ('let $r = add {i64, input, sort} in $r', ['bad-value']),
        ('let $r = add {i64, input, nope} in $r', ['unknown-language-word']),
        ('let $r = add {i64, input, $nope} in $r', ['undeclared-word']),
        ('let $r = add {i64, input, $r} in $r', ['forward-reference']),
        ('let $r = add {i64, input, $s} in let $s = add {i64, $r, 1} in $s', ['forward-reference']),
        ('let $r = add {i64, input, $number} in $r', ['not-a-value']),
        ('let $number = add {i64, input, 1} in $number', ['duplicate-word']),
        ('let $r = add {i64, input, 1} in let $r = add {i64, $r, 1} in $r', ['duplicate-word']),
        ('let $r = add {i64, input, 1} in input', ['unused-local']),
        ('let $a = add {i64, input, 1} in let $b = add {i64, input, 2} in $b', ['unused-local']),
        ('$nope', ['undeclared-word']),
        ('"input"', ['bad-value']),
    ],
)
def test_body_mistakes(body: str, expected: list[str]) -> None:
    assert kinds(NUMBER + function(body)) == expected


def test_let_outside_a_body() -> None:
    assert kinds('$n = {description = "x", sort = let $a = add {i64, 1, 2} in $a}') == ['bad-value']


def test_a_typo_for_a_local_suggests_the_local() -> None:
    (d,) = analyze(NUMBER + function('let $double = add {i64, input, input} in $doubel'))[1]
    assert d.hint == 'did you mean `$double`?'


def test_a_wrong_return_leaves_the_right_local_unused() -> None:
    (d,) = analyze(NUMBER + function('let $a = add {i64, input, 1} in let $b = mul {i64, $a, 2} in $a'))[1]
    assert (d.kind, d.text) == ('unused-local', '$b')


def test_renaming_locals_keeps_a_program_clean() -> None:
    source = NUMBER + function('let $a = add {i64, input, 1} in let $b = mul {i64, $a, $a} in $b')
    renamed = source.replace('$a', '$w9').replace('$b', '$w8').replace('$number', '$w0').replace('$f', '$w1')
    assert kinds(renamed) == []


@needs_clang
@pytest.mark.parametrize(
    ('golden', 'word', 'arg', 'expected'),
    [
        ('affine', '$affine', '5', 16),
        ('affine', '$affine', '-1', -2),
        ('arithmetic', '$square', '-12', 144),
        ('arithmetic', '$less', '0', -1),
        ('arithmetic', '$negate', '9', -9),
        ('arithmetic', '$seven', '123', 7),
        # overflow wraps
        ('arithmetic', '$less', str(MIN), MAX),
        ('arithmetic', '$negate', str(MIN), MIN),
        ('arithmetic', '$sum', '-1', MAX),
        ('arithmetic', '$square', str(2**32), 0),
        ('affine', '$affine', str(MAX), MAX - 1),
    ],
)
def test_run(golden: str, word: str, arg: str, expected: int, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(['run', str(GOLDENS / f'{golden}.mime'), word, arg]) == 0
    assert int(capsys.readouterr().out) == expected


def test_uses_finds_locals(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / 'p.mime'
    p.write_text(NUMBER + function('let $a = add {i64, input, 1} in let $b = mul {i64, $a, $a} in $b'))
    assert main(['uses', str(p), '$a']) == 0
    assert json.loads(capsys.readouterr().out) == [{'entry': '$f', 'key': 'body', 'text': '$a'}] * 2


def test_every_lowered_instruction_wraps() -> None:
    ir = (GOLDENS / 'affine.ll').read_text() + (GOLDENS / 'arithmetic.ll').read_text()
    assert re.search(r'\b(nsw|nuw)\b', ir) is None


@pytest.mark.parametrize(
    ('body', 'hint'),
    [
        ('input -1', 'arithmetic is written as an operation'),
        ('input-1', 'arithmetic is written as an operation'),
        ('let $r = add {i64, input -1} in $r', 'arithmetic is written as an operation'),
        ('$my-word', 'a name is a lowercase letter'),
    ],
)
def test_infix_spellings_get_the_arithmetic_hint(body: str, hint: str) -> None:
    (d,) = analyze(NUMBER + function(body))[1]
    assert d.kind == 'syntax'
    assert d.hint is not None
    assert d.hint.startswith(hint)


def test_a_description_that_names_a_local() -> None:
    source = NUMBER + (
        '$f = {description = "the $double of it", takes = $number, returns = $number, '
        'body = let $double = add {i64, input, input} in $double}\n'
    )
    (d,) = analyze(source)[1]
    assert (d.kind, d.text) == ('undeclared-word', '$double')
    assert d.hint == '`$double` is a local in the body of `$f`; a description refers only to entries'


def test_an_operation_works_in_the_functions_sort(monkeypatch: pytest.MonkeyPatch) -> None:
    # Only `i64` exists so far, so pretend `i32` does to reach the check.
    monkeypatch.setattr('mime.checker.SORTS', frozenset({'i64', 'i32'}))
    (d,) = analyze(NUMBER + function('let $r = add {i32, input, 1} in $r'))[1]
    assert (d.kind, d.text) == ('bad-value', 'i32')
    assert d.hint == '`$f` takes `$number`, whose sort is `i64`; write `i64`'
