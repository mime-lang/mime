import json
import shutil
from pathlib import Path

import pytest

from mime.cli import main

PROGRAM = (
    '@number = {type = i64, abstract = "a whole number"}\n'
    'define @same {@number} -> @number {\n  ret @number\n}\nabstract = "the @number it is given"\n'
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
    p.write_text(PROGRAM.replace('-> @number', '-> @numbr'))
    return p


def test_check_clean(prog: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(['check', str(prog)]) == 0
    assert capsys.readouterr().out == '[]\n'


UNDECLARED = {
    'kind': 'undeclared-word',
    'entry': '@same',
    'key': 'type',
    'text': '@numbr',
    'message': 'no entry declares `@numbr`',
    'hint': 'did you mean `@number`?',
}


def test_check_reports_json(broken: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(['check', str(broken)]) == 1
    out = capsys.readouterr().out
    assert json.loads(out) == [UNDECLARED]
    assert out.startswith('[\n  {\n    "kind": ')  # indented, one field per line


def test_positions_are_added_on_request(broken: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(['check', '--positions', str(broken)]) == 1
    assert json.loads(capsys.readouterr().out) == [UNDECLARED | {'line': 2, 'column': 27}]


def test_llvm_and_run_report_the_same_json(broken: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(['llvm', str(broken)]) == 1
    assert json.loads(capsys.readouterr().err) == [UNDECLARED]
    assert main(['run', '--positions', str(broken), '@same', '7']) == 1
    assert json.loads(capsys.readouterr().err) == [UNDECLARED | {'line': 2, 'column': 27}]


def test_llvm(prog: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(['llvm', str(prog)]) == 0
    assert capsys.readouterr().out == 'define internal i64 @mime.same(i64 %w0) {\n  ret i64 %w0\n}\n'


def test_llvm_refuses_a_broken_program(broken: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(['llvm', str(broken)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ''
    assert 'undeclared-word' in captured.err


@needs_clang
@pytest.mark.parametrize('n', ['7', '0', '-1', str(2**63 - 1), str(-(2**63))])
def test_run_prints_its_input(prog: Path, n: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(['run', str(prog), '@same', n]) == 0
    assert capsys.readouterr().out == f'{n}\n'


@needs_clang
def test_run_a_renamed_program(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / 'renamed.mime'
    p.write_text(PROGRAM.replace('@number', '@w0').replace('@same', '@w1'))
    assert main(['run', str(p), '@w1', '42']) == 0
    assert capsys.readouterr().out == '42\n'


@pytest.mark.parametrize(
    ('args', 'message'),
    [
        (['@nothere', '7'], 'no definition defines `@nothere`'),
        (['same', '7'], 'write the word as in the source, with its `@`: @same'),
        (['$same', '7'], 'words are written `@same` now, and need no quotes'),
        (['7'], '`7` looks like an input, so the word is missing'),
        (['-7'], '`-7` looks like an input, so the word is missing'),
        (['', '7'], 'mime run needs a word'),
        (['@same'], '`@same` takes 1 input (`@number`), but 0 were given'),
        (['@same', '1', '2'], '`@same` takes 1 input (`@number`), but 2 were given'),
        ([], 'mime run needs a word'),
        (['@number', '7'], 'no definition defines `@number`'),
        (['@same', 'seven'], 'is not a decimal integer'),
        (['@same', str(2**63)], 'does not fit in an i64'),
    ],
)
def test_run_usage_errors(prog: Path, args: list[str], message: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(['run', str(prog), *args]) == 2
    assert message in capsys.readouterr().err


def test_missing_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(['check', str(tmp_path / 'none.mime')]) == 2
    assert 'cannot read' in capsys.readouterr().err
