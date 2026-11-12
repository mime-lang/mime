import json
import shutil
from pathlib import Path

import pytest

from mime.cli import main

PROGRAM = (
    '$number = {description = "a whole number", sort = i64}\n'
    '$same   = {description = "the number it is given", takes = $number, returns = $number, body = input}\n'
)
needs_clang = pytest.mark.skipif(shutil.which('clang') is None, reason='mime run needs clang')


@pytest.fixture
def prog(tmp_path: Path) -> Path:
    p = tmp_path / 'prog.mime'
    p.write_text(PROGRAM)
    return p


@pytest.fixture
def broken(tmp_path: Path) -> Path:
    p = tmp_path / 'broken.mime'
    p.write_text(PROGRAM.replace('returns = $number', 'returns = $numbr'))
    return p


def test_check_clean(prog: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(['check', str(prog)]) == 0
    assert capsys.readouterr().out == '[]\n'


UNDECLARED = {
    'kind': 'undeclared-word',
    'entry': '$same',
    'key': 'returns',
    'text': '$numbr',
    'message': 'no entry declares `$numbr`',
    'hint': 'did you mean `$number`?',
}


def test_check_reports_json(broken: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(['check', str(broken)]) == 1
    out = capsys.readouterr().out
    assert json.loads(out) == [UNDECLARED]
    assert out.startswith('[\n  {\n    "kind": ')  # indented, one field per line


def test_positions_are_added_on_request(broken: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(['check', '--positions', str(broken)]) == 1
    assert json.loads(capsys.readouterr().out) == [UNDECLARED | {'line': 2, 'column': 79}]


def test_llvm_and_run_report_the_same_json(broken: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(['llvm', str(broken)]) == 1
    assert json.loads(capsys.readouterr().err) == [UNDECLARED]
    assert main(['run', '--positions', str(broken), '$same', '7']) == 1
    assert json.loads(capsys.readouterr().err) == [UNDECLARED | {'line': 2, 'column': 79}]


def test_llvm(prog: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(['llvm', str(prog)]) == 0
    assert capsys.readouterr().out == 'define i64 @"$same"(i64 %input) {\n  ret i64 %input\n}\n'


def test_llvm_refuses_a_broken_program(broken: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(['llvm', str(broken)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ''
    assert 'undeclared-word' in captured.err


@needs_clang
@pytest.mark.parametrize('n', ['7', '0', '-1', str(2**63 - 1), str(-(2**63))])
def test_run_prints_its_input(prog: Path, n: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(['run', str(prog), '$same', n]) == 0
    assert capsys.readouterr().out == f'{n}\n'


@needs_clang
def test_run_a_renamed_program(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / 'renamed.mime'
    p.write_text(PROGRAM.replace('$number', '$w0').replace('$same', '$w1'))
    assert main(['run', str(p), '$w1', '42']) == 0
    assert capsys.readouterr().out == '42\n'


@pytest.mark.parametrize(
    ('args', 'message'),
    [
        (['$nothere', '7'], 'no function entry declares `$nothere`'),
        (['same', '7'], "write the word as in the source, with its `$` and in single quotes: '$same'"),
        (['7'], '`7` looks like the input, so the word is missing; if you wrote $name without single quotes'),
        (['-7'], '`-7` looks like the input, so the word is missing'),
        (['', '7'], 'the word is empty; if you wrote $name without single quotes'),
        (['$same'], 'mime run needs an input after `$same`'),
        ([], 'mime run needs a word and an input'),
        (['$number', '7'], 'no function entry declares `$number`'),
        (['$same', 'seven'], 'is not a decimal integer'),
        (['$same', str(2**63)], 'does not fit in an i64'),
    ],
)
def test_run_usage_errors(prog: Path, args: list[str], message: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(['run', str(prog), *args]) == 2
    assert message in capsys.readouterr().err


def test_missing_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(['check', str(tmp_path / 'none.mime')]) == 2
    assert 'cannot read' in capsys.readouterr().err
