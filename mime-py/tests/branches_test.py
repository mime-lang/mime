"""Branches: `icmp`, `i1`, blocks and `br` (design/step-7.md)."""

import json
import shutil
from pathlib import Path

import pytest

from mime.cli import main
from mime.compiler import analyze
from mime.parser import parse
from mime.printer import canon, canon_locals

CLEAN = Path(__file__).parent / 'goldens' / 'clean'
N = '@n = {type = i64, abstract = "a whole number"}\n@flag = {type = i1, abstract = "a truth value"}\n'
needs_clang = pytest.mark.skipif(shutil.which('clang') is None, reason='mime run needs clang')


def function(body: str, head: str = '{@n} -> i64') -> str:
    return N + f'define @f {head} {{\n{body}\n}}\nabstract = "x"\n'


def kinds(source: str) -> list[str]:
    return [d.kind for d in analyze(source)[1]]


@needs_clang
@pytest.mark.parametrize(
    ('golden', 'word', 'args', 'out'),
    [
        ('clamp', '@clamp', ['-5', '0', '10'], '0'),
        ('clamp', '@clamp', ['5', '0', '10'], '5'),
        ('clamp', '@clamp', ['50', '0', '10'], '10'),
        ('branches', '@sum', ['0'], '0'),
        ('branches', '@sum', ['10'], '55'),
        ('branches', '@positive', ['3'], 'true'),
        ('branches', '@positive', ['-3'], 'false'),
        ('branches', '@pick', ['true'], '1'),
        ('branches', '@pick', ['false'], '2'),
        ('branches', '@negate', ['true'], 'false'),
    ],
)
def test_run(golden: str, word: str, args: list[str], out: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(['run', str(CLEAN / f'{golden}.mime'), word, *args]) == 0
    assert capsys.readouterr().out == out + '\n'


def test_an_i1_input_must_be_true_or_false(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(['run', str(CLEAN / 'branches.mime'), '@pick', '1']) == 2
    assert 'is not `true` or `false`' in capsys.readouterr().err


@pytest.mark.parametrize(
    ('signed', 'unsigned'),
    [('slt', 'ult')],
)
def test_signed_and_unsigned_predicates_check(signed: str, unsigned: str) -> None:
    for p in (signed, unsigned):
        assert kinds(function(f'%c = icmp {p} i64 @n, -1\nbr %c, ^a{{}}, ^b{{}}\n^a{{}}:\nret 1\n^b{{}}:\nret 0')) == []


def test_a_block_sees_only_its_own_locals() -> None:
    source = function('%a = add i64 @n, 1\nbr ^next{}\n^next{}:\nret %a')
    unread, d = analyze(source)[1]  # %a is also unread in the entry block, which is true
    assert (unread.kind, unread.text) == ('unused-local', '%a')
    assert (d.kind, d.text) == ('undeclared-word', '%a')
    assert d.hint == '`%a` is bound in the entry block; a block sees only its own locals, so pass it as an argument'
    # The fix the hint names is clean, and an unread %a in the entry block is then read by the jump.
    assert kinds(function('%a = add i64 @n, 1\nbr ^next{%a}\n^next{%b}:\nret %b')) == []


def test_the_same_local_may_be_bound_in_two_blocks() -> None:
    source = function(
        '%c = icmp eq i64 @n, 0\nbr %c, ^a{}, ^b{}\n^a{}:\n%r = add i64 @n, 1\nret %r\n^b{}:\n%r = sub i64 @n, 1\nret %r'
    )
    assert kinds(source) == []


NONE = '{} -> i64'


@pytest.mark.parametrize(
    ('body', 'head', 'expected'),
    [
        ('ret 1', NONE, []),
        ('ret true', NONE, ['wrong-type']),
        ('%c = icmp eq i64 @n, 0\nret %c', '{@n} -> i64', ['wrong-type']),
        ('br @n, ^a{}, ^a{}\n^a{}:\nret 1', '{@n} -> i64', ['wrong-type']),
        ('br true, ^a{1}, ^a{false}\n^a{%x}:\nret %x', NONE, ['wrong-type']),
        ('br ^loop{@n}\n^loop{%x}:\nbr ^loop{%x}', '{@n} -> i64', []),
        ('br ^a{}\n^a{}:\nret 1\n^b{}:\nret 2', NONE, ['unreachable-block']),
        ('br ^a{1, 2}\n^a{%x}:\nret %x', NONE, ['bad-value']),
        ('br ^b{}\n^a{}:\nret 1', NONE, ['undeclared-word', 'unreachable-block']),
        ('%c = icmp less i64 @n, 0\nbr %c, ^a{}, ^a{}\n^a{}:\nret 1', '{@n} -> i64', ['bad-value']),
        ('%c = icmp eq i1 @n, 0\nbr %c, ^a{}, ^a{}\n^a{}:\nret 1', '{@n} -> i64', ['bad-value']),
    ],
)
def test_types_and_jumps(body: str, head: str, expected: list[str]) -> None:
    assert kinds(function(body, head)) == expected


def test_a_parameter_no_jump_gives_a_type() -> None:
    # The entry passes nothing typed: only the loop's own back edge reaches %x.
    assert kinds(function('br ^loop{%y}\n^loop{%x}:\nbr ^loop{%x}', NONE)) == ['undeclared-word', 'wrong-type']


def test_an_integer_where_an_i1_belongs() -> None:
    (d,) = analyze(function('ret 1', '{} -> @flag'))[1]
    assert (d.kind, d.hint) == ('wrong-type', 'write `true` or `false`')


def test_canon_numbers_labels_and_keeps_a_carried_value() -> None:
    source = function(
        'br ^loop{@n, 0}\n^loop{%i, %acc}:\n%c = icmp eq i64 %i, 0\n%d = sub i64 %i, 1\n%e = add i64 %acc, %i\nbr %c, ^end{%acc}, ^loop{%d, %e}\n^end{%r}:\nret %r'
    )
    form = canon(parse(source))
    assert '^0{%0, %1}:' in form
    assert '^1{%1}:\n  ret %1' in form  # %r only ever receives %acc, so it keeps %acc's number


def test_canon_locals_numbers_labels_too(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / 'p.mime'
    p.write_text(
        function('br ^loop{@n}\n^loop{%x}:\n%c = icmp eq i64 %x, 0\nbr %c, ^done{}, ^loop{%x}\n^done{}:\nret 1')
    )
    assert main(['canon', '--locals', str(p)]) == 0
    text = p.read_text()
    assert 'br ^0{@n}\n^0{%0}:\n%1 = icmp eq i64 %0, 0\nbr %1, ^1{}, ^0{%0}\n^1{}:' in text
    assert canon_locals(parse(text)) == text  # idempotent
    capsys.readouterr()


def test_rename_a_label(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / 'p.mime'
    p.write_text(function('br ^a{}\n^a{}:\nret 1'))
    assert main(['rename', str(p), '^a', '^next']) == 0
    assert 'br ^next{}\n^next{}:' in p.read_text()
    capsys.readouterr()
    assert main(['rename', str(p), '^next', '%x']) == 2
    assert 'different sigils' in capsys.readouterr().err


def test_uses_lists_a_local_read_in_a_jump(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / 'p.mime'
    p.write_text(function('%a = add i64 @n, 1\nbr ^b{%a}\n^b{%x}:\nret %x'))
    assert main(['uses', str(p), '%a']) == 0
    assert json.loads(capsys.readouterr().out) == [{'entry': '@f', 'key': 'body', 'text': '%a'}]


@needs_clang
def test_a_run_that_never_finishes_is_stopped(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / 'forever.mime'
    p.write_text(function('br ^loop{@n}\n^loop{%x}:\n%y = add i64 %x, 1\nbr ^loop{%y}'))
    assert main(['run', '--timeout', '0.5', str(p), '@f', '1']) == 2
    assert capsys.readouterr().err == (
        'mime: `@f` did not finish within 0.5 s; a loop may never reach its exit (see --timeout)\n'
    )
