"""Branches: `icmp`, `i1`, blocks and `br` (design/step-7.md)."""

import json
from pathlib import Path

import pytest

from mime.cli import main
from mime.compiler import analyze
from mime.diag import Diagnostic
from mime.parser import parse
from mime.printer import canon, keep_words
from tests.run_cases import BACKENDS

CLEAN = Path(__file__).parent / 'goldens' / 'clean'
N = '@n = {type = i64, abstract = "a whole number"}\n@flag = {type = i1, abstract = "a truth value"}\n'


def mistakes(source: str) -> list[Diagnostic]:
    """The mistakes in `source` besides `unused-word`, which these programs are not about."""
    return [d for d in analyze(source)[1] if d.kind != 'unused-word']


def function(body: str, head: str = '{@n} -> i64') -> str:
    return N + f'define @f {head} {{\n{body}\n}}\nabstract = "x"\n'


def kinds(source: str) -> list[str]:
    # These programs test other mistakes, so a data word they leave unused is not reported here; `unused-word` has
    # tests of its own (check_test.py).
    return [d.kind for d in analyze(source)[1] if d.kind != 'unused-word']


def test_an_i1_input_must_be_true_or_false(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(['run', str(CLEAN / 'branches.mime'), 'pick', '1']) == 2
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
    unread, d = mistakes(source)  # %a is also unread in the entry block, which is true
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
        ('br ^loop{@n}\n^loop{%x}:\nbr ^loop{%x}', '{@n} -> i64', ['redundant-parameter']),
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
    (d,) = mistakes(function('ret 1', '{} -> @flag'))
    assert (d.kind, d.hint) == ('wrong-type', 'write `true` or `false`')


def test_canon_numbers_labels_and_keeps_a_carried_value() -> None:
    source = function(
        'br ^loop{@n, 0}\n^loop{%i, %acc}:\n%c = icmp eq i64 %i, 0\n%d = sub i64 %i, 1\n%e = add i64 %acc, %i\nbr %c, ^end{%acc}, ^loop{%d, %e}\n^end{%r}:\nret %r'
    )
    form = canon(parse(source))
    assert '^b0{%v0, %v1}:' in form
    assert '^b1{%v1}:\n  ret %v1' in form  # %r only ever receives %acc, so it keeps %acc's number


def test_canon_keep_words_numbers_labels_too(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / 'p.mime'
    p.write_text(
        function('br ^loop{@n}\n^loop{%x}:\n%c = icmp eq i64 %x, 0\nbr %c, ^done{}, ^loop{%x}\n^done{}:\nret 1')
    )
    assert main(['canon', '--keep-words', str(p)]) == 0
    text = p.read_text()
    assert '  br ^b0{@n}\n^b0{%v0}:\n  %v1 = icmp eq i64 %v0, 0\n  br %v1, ^b1{}, ^b0{%v0}\n^b1{}:' in text
    assert keep_words(parse(text)) == text  # idempotent
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


@pytest.mark.parametrize('backend', BACKENDS)
def test_a_run_that_never_finishes_is_stopped(backend: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / 'forever.mime'
    source = function('br ^loop{@n}\n^loop{%x}:\n%y = add i64 %x, 1\nbr ^loop{%y}') + 'symbol = "forever"\n'
    p.write_text(source.replace('@flag = {type = i1, abstract = "a truth value"}\n', ''))  # every word is used
    assert main(['run', '--backend', backend, '--timeout', '0.5', str(p), 'forever', '1']) == 2
    assert capsys.readouterr().err == (
        'mime: `forever` did not finish within 0.5 s; a loop may never reach its exit (see --timeout)\n'
    )


@pytest.mark.parametrize(
    ('body', 'expected'),
    [
        # one input or one constant, besides the parameter itself: a second way to read it
        ('br ^a{@n}\n^a{%x}:\nret %x', ['redundant-parameter']),
        ('br ^a{7}\n^a{%x}:\n%y = add i64 %x, @n\nret %y', ['redundant-parameter']),
        ('br ^a{true}\n^a{%x}:\nbr %x, ^b{}, ^b{}\n^b{}:\nret @n', ['redundant-parameter']),
        # one local is a pass-through, which is fine: the block could not read it otherwise
        ('%a = add i64 @n, 1\nbr ^b{%a}\n^b{%x}:\nret %x', []),
        # different values, or an input and a constant, are not one value
        ('%c = icmp eq i64 @n, 0\nbr %c, ^b{@n}, ^b{1}\n^b{%x}:\nret %x', []),
        ('%c = icmp eq i64 @n, 0\nbr %c, ^b{1}, ^b{2}\n^b{%x}:\nret %x', []),
    ],
)
def test_a_parameter_that_only_carries_an_input_or_a_constant(body: str, expected: list[str]) -> None:
    assert kinds(function(body)) == expected


def test_the_hint_says_what_to_write() -> None:
    (d,) = mistakes(
        function(
            'br ^loop{0, @n}\n^loop{%i, %limit}:\n%done = icmp sgt i64 %i, %limit\n%next = add i64 %i, 1\nbr %done, ^end{}, ^loop{%next, %limit}\n^end{}:\nret 0'
        )
    )
    assert (d.kind, d.text, d.hint) == (
        'redundant-parameter',
        '%limit',
        'drop the parameter and its arguments, and write `@n` where it is read',
    )


FLAG = '{@flag} -> i64'
BAD = (
    'br @flag, ^a{0}, ^b{0}\n^a{%x}:\n%y = add i64 %x, 1\nbr ^b{%y}\n'
    '^b{%z}:\n%w = add i64 %z, 1\n%c = icmp slt i64 %w, 10\nbr %c, ^a{%w}, ^done{%w}\n^done{%r}:\nret %r'
)


@pytest.mark.parametrize(
    'body',
    [
        # A self loop, a loop with a body block, and two nested loops each have one way in (design/step-10.md).
        'br ^loop{0}\n^loop{%i}:\n%j = add i64 %i, 1\n%c = icmp slt i64 %j, 10\nbr %c, ^loop{%j}, ^done{%j}\n'
        '^done{%r}:\nret %r',
        'br ^loop{0}\n^loop{%i}:\n%c = icmp slt i64 %i, 10\nbr %c, ^step{%i}, ^done{%i}\n'
        '^step{%j}:\n%k = add i64 %j, 1\nbr ^loop{%k}\n^done{%r}:\nret %r',
        'br ^outer{0}\n^outer{%i}:\n%c = icmp slt i64 %i, 3\nbr %c, ^inner{%i, 0}, ^done{%i}\n'
        '^inner{%a, %b}:\n%d = icmp slt i64 %b, 3\nbr %d, ^next{%a, %b}, ^back{%a}\n'
        '^next{%e, %f}:\n%g = add i64 %f, 1\nbr ^inner{%e, %g}\n'
        '^back{%h}:\n%k = add i64 %h, 1\nbr ^outer{%k}\n^done{%r}:\nret %r',
        # The fix of design/step-10.md section 3: one header that branches on a flag.
        'br ^head{@flag, 0}\n^head{%toa, %x}:\nbr %toa, ^a{%x}, ^b{%x}\n^a{%v}:\n%y = add i64 %v, 1\n'
        'br ^head{false, %y}\n^b{%z}:\n%w = add i64 %z, 1\n%c = icmp slt i64 %w, 10\n'
        'br %c, ^head{true, %w}, ^done{%w}\n^done{%r}:\nret %r',
    ],
)
def test_a_loop_with_one_way_in_checks(body: str) -> None:
    assert kinds(function(body, FLAG if '@flag' in body else NONE)) == []


def test_a_loop_with_two_ways_in_is_reported_once_whatever_the_jump_order() -> None:
    assert kinds(function(BAD, FLAG)) == ['irreducible-loop']
    swapped = BAD.replace('br @flag, ^a{0}, ^b{0}', 'br @flag, ^b{0}, ^a{0}')
    assert kinds(function(swapped, FLAG)) == ['irreducible-loop']
