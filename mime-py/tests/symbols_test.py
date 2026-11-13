"""`symbol = "name"`: the name a function is exported under (design/layout.md section 4, step-7.md section 7)."""

from pathlib import Path

import pytest

from mime.cli import main
from mime.compiler import analyze
from mime.diag import Diagnostic
from mime.lower import lower
from mime.parser import parse
from mime.printer import canon, rename
from tests.run_cases import BACKENDS, CONTEXT

N = '@n = {type = i64, abstract = "a whole number"}\n'


def mistakes(source: str) -> list[Diagnostic]:
    """The mistakes in `source` besides those in `CONTEXT`, which these programs are not about."""
    return [d for d in analyze(source)[1] if d.kind not in CONTEXT]


def function(symbol: str | None, word: str = '@f') -> str:
    line = f'symbol = "{symbol}"\n' if symbol is not None else ''
    return f'define {word} {{@n}} -> i64 {{\n  ret @n\n}}\nabstract = "x of @n"\n{line}'


def test_an_exported_function_takes_its_symbol() -> None:
    program, _ = analyze(N + function('next_number'))
    assert program is not None
    assert lower(program).startswith('define i64 @next_number(i64 %w0) {')


def test_a_function_without_a_symbol_is_internal() -> None:
    program, _ = analyze(N + function(None))
    assert program is not None
    assert lower(program).startswith('define internal i64 @mime.f(i64 %w0) {')


@pytest.mark.parametrize(
    ('source', 'expected'),
    [
        (N + function('ok_1'), []),
        (N + function('_private'), []),
        (N + function('2bad'), ['bad-value']),
        (N + function('has space'), ['bad-value']),
        (N + function('mime.f'), ['bad-value']),
        (N + function('main'), ['bad-value']),
        (N + function('dup') + function('dup', '@g'), ['duplicate-word']),
        (N + 'define @f {@n} -> i64 {\n  ret @n\n}\nabstract = "x"\nsymbol = f\n', ['syntax']),
    ],
)
def test_symbol_mistakes(source: str, expected: list[str]) -> None:
    assert [d.kind for d in analyze(source)[1]] == expected


def test_a_symbol_mistake_names_its_key() -> None:
    (d,) = mistakes(N + function('2bad'))
    assert (d.entry, d.key, d.text) == ('@f', 'symbol', '"2bad"')


def test_renaming_and_canon_keep_the_symbol() -> None:
    # A symbol is data, the name the function is exported under: renaming the word must not change what links to it.
    source = N + function('next_number')
    assert rename(source, '@f', '@g').endswith('symbol = "next_number"\n')
    assert canon(parse(source)).endswith('symbol = "next_number"\n')


def test_show_prints_the_symbol(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / 'p.mime'
    p.write_text(N + function('next_number'))
    assert main(['show', str(p), '@f']) == 0
    assert capsys.readouterr().out.endswith('abstract = "x of @n"\nsymbol = "next_number"\n')


@pytest.mark.parametrize('backend', BACKENDS)
def test_run_calls_an_exported_function(backend: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / 'p.mime'
    p.write_text(N + function('next_number'))
    assert main(['run', '--backend', backend, str(p), 'next_number', '7']) == 0
    assert capsys.readouterr().out == '7\n'
