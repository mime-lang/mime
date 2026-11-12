"""`mime fmt`, `mime canon` and `mime rename` (design/step-5.md)."""

import json
from pathlib import Path

import pytest

from mime.cli import main
from mime.parser import parse
from mime.printer import canon, layout

MESSY = (
    '$number={type=i64,  abstract="a whole number, \\$5"}\n'
    '$count = {type = i64, abstract = "how many"}\n'
    'define $double {$number}->$number{$r=add i64 $number,$number\nret $r} abstract="twice the $number"\n'
    'define $seven {}->$count{ret 7}abstract="always seven"\n'
)
TIDY = (
    '$number = {type = i64, abstract = "a whole number, \\$5"}\n'
    '$count = {type = i64, abstract = "how many"}\n'
    '\n'
    'define $double {$number} -> $number {\n'
    '  $r = add i64 $number, $number\n'
    '  ret $r\n'
    '}\n'
    'abstract = "twice the $number"\n'
    '\n'
    'define $seven {} -> $count {\n'
    '  ret 7\n'
    '}\n'
    'abstract = "always seven"\n'
)


@pytest.fixture
def prog(tmp_path: Path) -> Path:
    p = tmp_path / 'prog.mime'
    p.write_text(MESSY)
    return p


def test_fmt_rewrites_the_file_in_its_one_layout(prog: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(['fmt', str(prog)]) == 0
    assert capsys.readouterr().out == ''
    assert prog.read_text() == TIDY


def test_fmt_is_idempotent() -> None:
    assert layout(parse(TIDY)) == TIDY


def test_a_data_word_after_a_definition_gets_a_blank_line() -> None:
    source = 'define $seven {} -> i64 {ret 7} abstract = "seven"\n$n = {type = i64, abstract = "x"}\n'
    assert layout(parse(source)).endswith('abstract = "seven"\n\n$n = {type = i64, abstract = "x"}\n')


def test_fmt_keeps_mistakes_the_checker_reports() -> None:
    # Fields keep their written order, so a `key-order` mistake is not hidden.
    assert layout(parse('$n = {abstract = "x", type = i64}')) == '$n = {abstract = "x", type = i64}\n'


def test_canon_renames_every_word_and_keeps_the_english(prog: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(['canon', str(prog)]) == 0
    out = capsys.readouterr().out
    assert out == TIDY.replace('$number', '$w0').replace('$count', '$w1').replace('$double', '$w2').replace(
        '$r', '$w3'
    ).replace('$seven', '$w4')
    assert prog.read_text() == MESSY  # canon only prints


def test_canon_numbers_results_per_body() -> None:
    n = '$n = {type = i64, abstract = "x"}\n'
    shared = n + 'define $f {$n} -> $n {$s = add i64 $n, 1 ret $s} abstract = "x"\n'
    shared += 'define $g {$n} -> $n {$s = add i64 $n, 2 ret $s} abstract = "x"\n'
    apart = shared.replace('$s = add i64 $n, 2 ret $s', '$t = add i64 $n, 2 ret $t')
    assert canon(parse(shared)) == canon(parse(apart))


def test_canon_keeps_differences_in_wording() -> None:
    a = '$n = {type = i64, abstract = "a whole number"}'
    assert canon(parse(a)) != canon(parse(a.replace('whole', 'round')))


def test_rename_changes_every_occurrence_and_nothing_else(prog: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(['rename', str(prog), '$number', '$amount']) == 0
    assert prog.read_text() == MESSY.replace('$number', '$amount')
    uses = json.loads(capsys.readouterr().out)
    assert [(u['entry'], u['key']) for u in uses] == [('$double', 'type')] * 2 + [('$double', 'body')] * 2 + [
        ('$double', 'abstract')
    ]


def test_rename_leaves_escapes_and_bad_references_alone(tmp_path: Path) -> None:
    p = tmp_path / 'p.mime'
    p.write_text('$n = {type = i64, abstract = "x"}\n$m = {type = i64, abstract = "a $n, not \\$n, nor $nX"}\n')
    assert main(['rename', str(p), '$n', '$k']) == 0
    assert (
        p.read_text() == '$k = {type = i64, abstract = "x"}\n$m = {type = i64, abstract = "a $k, not \\$n, nor $nX"}\n'
    )


def test_rename_renames_results_in_every_body(tmp_path: Path) -> None:
    p = tmp_path / 'p.mime'
    source = '$n = {type = i64, abstract = "x"}\n'
    source += 'define $f {$n} -> $n {$s = add i64 $n, 1 ret $s} abstract = "x"\n'
    source += 'define $g {$n} -> $n {$s = add i64 $n, 2 ret $s} abstract = "x"\n'
    p.write_text(source)
    assert main(['rename', str(p), '$s', '$sum']) == 0
    assert p.read_text() == source.replace('$s ', '$sum ').replace('ret $s}', 'ret $sum}')


@pytest.mark.parametrize(
    ('args', 'message'),
    [
        (['$number', '$double'], '`$double` is already used in this file'),
        (['$number', '$number'], '`$number` is already called `$number`'),
        (['$numbr', '$x'], '`$numbr` does not appear in this file; did you mean `$number`?'),
        (['$number'], 'mime rename needs a new word'),
        (['$number', 'count'], 'write the word as in the source'),
        (['', '$x'], 'the word is empty'),
    ],
)
def test_rename_refusals_change_nothing(
    prog: Path, args: list[str], message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(['rename', str(prog), *args]) == 2
    assert message in capsys.readouterr().err
    assert prog.read_text() == MESSY


@pytest.mark.parametrize('command', [['fmt'], ['canon'], ['rename', '$n', '$m']])
def test_a_program_that_does_not_parse(tmp_path: Path, command: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / 'broken.mime'
    p.write_text('$n = {type = i64, abstract = "x",}\n')
    name, *rest = command
    assert main([name, str(p), *rest]) == 1
    assert [d['kind'] for d in json.loads(capsys.readouterr().err)] == ['trailing-comma']
    assert p.read_text() == '$n = {type = i64, abstract = "x",}\n'
