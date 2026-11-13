import json
import shutil
from pathlib import Path

import pytest

from mime import cli
from mime.cli import main
from mime.diag import Diagnostic, Trap
from tests.run_cases import BACKENDS

PROGRAM = (
    '@number = {type = i64, abstract = "a whole number"}\n'
    'define @same {@number} -> @number {\n  ret @number\n}\nabstract = "the @number it is given"\nsymbol = "same"\n'
)


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
    assert main(['run', '--positions', str(broken), 'same', '7']) == 1
    assert json.loads(capsys.readouterr().err) == [UNDECLARED | {'line': 2, 'column': 27}]


def test_llvm(prog: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(['llvm', str(prog)]) == 0
    assert capsys.readouterr().out == 'define i64 @same(i64 %w0) {\n  ret i64 %w0\n}\n'


def test_llvm_refuses_a_broken_program(broken: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(['llvm', str(broken)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ''
    assert 'undeclared-word' in captured.err


@pytest.mark.parametrize('backend', BACKENDS)
@pytest.mark.parametrize('n', ['7', '0', '-1', str(2**63 - 1), str(-(2**63))])
def test_run_prints_its_input(prog: Path, n: str, backend: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(['run', '--backend', backend, str(prog), 'same', n]) == 0
    assert capsys.readouterr().out == f'{n}\n'


INTERNAL = PROGRAM.removesuffix('symbol = "same"\n')


@pytest.mark.parametrize(
    ('source', 'args', 'message'),
    [
        (PROGRAM, ['nothere', '7'], 'no function is exported as `nothere`; the program exports `same`'),
        (PROGRAM, ['@same', '7'], '`mime run` takes a symbol, not a word: write `same`'),
        (PROGRAM, ['@number', '7'], 'no function is exported as `@number`; the program exports `same`'),
        (INTERNAL, ['@same', '7'], '`@same` has no symbol; to run it, add `symbol = "same"` after its abstract'),
        (INTERNAL, ['same', '7'], 'no function is exported as `same`; to run `@same`, add `symbol = "same"`'),
        (INTERNAL, ['other', '7'], 'the program exports nothing; give a function a `symbol`'),
        (PROGRAM, ['7'], '`7` looks like an input, so the symbol is missing'),
        (PROGRAM, ['-7'], '`-7` looks like an input, so the symbol is missing'),
        (PROGRAM, ['true'], '`true` looks like an input, so the symbol is missing'),
        (PROGRAM, ['', '7'], 'mime run needs a symbol'),
        (PROGRAM, [], 'mime run needs a symbol'),
        (PROGRAM, ['same'], '`same` takes 1 input (`@number`), but 0 were given'),
        (PROGRAM, ['same', '1', '2'], '`same` takes 1 input (`@number`), but 2 were given'),
        (PROGRAM, ['same', 'seven'], 'is not a decimal integer'),
        (PROGRAM, ['same', str(2**63)], 'does not fit in an i64'),
    ],
)
def test_run_usage_errors(
    tmp_path: Path, source: str, args: list[str], message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    p = tmp_path / 'prog.mime'
    p.write_text(source)
    assert main(['run', str(p), *args]) == 2
    assert message in capsys.readouterr().err


def test_the_default_backend_needs_no_clang(
    prog: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(shutil, 'which', lambda _: None)
    assert main(['run', str(prog), 'same', '7']) == 0
    assert capsys.readouterr().out == '7\n'
    assert main(['run', '--backend', 'llvm', str(prog), 'same', '7']) == 2
    assert '`clang` is not on PATH' in capsys.readouterr().err


def test_a_trap_is_one_json_object_with_exit_code_3(
    prog: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Nothing traps until division arrives, so this raises the trap the interpreter would (design/step-8.md section 4).
    trap = Diagnostic('trap', '`sdiv` by zero', 4, 3, entry='@mean', key='body', text='%q = sdiv i64 %sum, %count')

    def trapping(*_: object) -> str:
        raise Trap(trap)

    monkeypatch.setattr(cli, 'run', trapping)
    assert main(['run', '--positions', str(prog), 'same', '7']) == 3
    captured = capsys.readouterr()
    assert captured.out == ''
    assert json.loads(captured.err) == {
        'kind': 'trap',
        'entry': '@mean',
        'key': 'body',
        'text': '%q = sdiv i64 %sum, %count',
        'message': '`sdiv` by zero',
        'hint': None,
        'line': 4,
        'column': 3,
    }


def test_missing_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(['check', str(tmp_path / 'none.mime')]) == 2
    assert 'cannot read' in capsys.readouterr().err
