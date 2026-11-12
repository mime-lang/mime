"""`mime show` and `mime uses` (design/tools.md)."""

import json
from pathlib import Path

import pytest

from mime.cli import main

PROGRAM = (
    '$number = {type = i64, abstract = "a whole number, \\$5 at most"}\n'
    '$count = {\n'
    '  type = i64,\n'
    '  abstract = "how many, as a $number"\n'
    '}\n'
    'define $same {$number} -> $number {\n'
    '  $twice = add i64 $number, $number\n'
    '  $back = sub i64 $twice, $number\n'
    '  ret $back\n'
    '}\n'
    'abstract = "the $number it is given"\n'
)


@pytest.fixture
def prog(tmp_path: Path) -> Path:
    p = tmp_path / 'prog.mime'
    p.write_text(PROGRAM)
    return p


def out(capsys: pytest.CaptureFixture[str]) -> str:
    return capsys.readouterr().out


def test_show_prints_a_data_word_as_written(prog: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(['show', str(prog), '$count']) == 0
    assert out(capsys) == '$count = {\n  type = i64,\n  abstract = "how many, as a $number"\n}\n'


def test_show_prints_a_whole_definition(prog: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(['show', str(prog), '$same']) == 0
    text = out(capsys)
    assert text.startswith('define $same {$number} -> $number {\n')
    assert text.endswith('}\nabstract = "the $number it is given"\n')


def test_show_prints_both_entries_of_a_duplicate_word(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / 'dup.mime'
    p.write_text('$n = {type = i64, abstract = "x"}\n$n = {type = i64, abstract = "y"}\n')
    assert main(['show', str(p), '$n']) == 0
    assert out(capsys) == '$n = {type = i64, abstract = "x"}\n\n$n = {type = i64, abstract = "y"}\n'


def test_show_works_on_a_program_with_checker_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / 'bad.mime'
    p.write_text('define $same {$numbr} -> $numbr {\n  ret $numbr\n}\nabstract = "x"\n')
    assert main(['show', str(p), '$same']) == 0
    assert out(capsys).startswith('define $same {')


def test_uses_lists_references_in_source_order(prog: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(['uses', str(prog), '$number']) == 0
    assert json.loads(out(capsys)) == [
        {'entry': '$count', 'key': 'abstract', 'text': '$number'},
        {'entry': '$same', 'key': 'type', 'text': '$number'},
        {'entry': '$same', 'key': 'type', 'text': '$number'},
        {'entry': '$same', 'key': 'body', 'text': '$number'},
        {'entry': '$same', 'key': 'body', 'text': '$number'},
        {'entry': '$same', 'key': 'body', 'text': '$number'},
        {'entry': '$same', 'key': 'abstract', 'text': '$number'},
    ]


def test_uses_adds_positions_on_request(prog: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(['uses', '--positions', str(prog), '$number']) == 0
    first = json.loads(out(capsys))[0]
    assert (first['line'], first['column']) == (4, 30)


def test_an_unused_word_has_no_uses(prog: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(['uses', str(prog), '$same']) == 0
    assert out(capsys) == '[]\n'


def test_uses_finds_a_word_with_no_entry(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / 'typo.mime'
    p.write_text('define $same {$numbr} -> $numbr {\n  ret $numbr\n}\nabstract = "a $numbr"\n')
    assert main(['uses', str(p), '$numbr']) == 0
    assert [u['key'] for u in json.loads(out(capsys))] == ['type', 'type', 'body', 'abstract']


def test_uses_skips_what_is_not_a_reference(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / 'p.mime'
    p.write_text(
        '$number = {type = i64, abstract = "x"}\n$numbers = {type = i64, abstract = "costs \\$number, unlike $numbers"}\n'
    )
    assert main(['uses', str(p), '$number']) == 0
    assert out(capsys) == '[]\n'


@pytest.mark.parametrize(
    ('args', 'message'),
    [
        (['show', '$cont'], 'no entry declares `$cont`; did you mean `$count`?'),
        (['uses', '$cont'], 'no entry declares `$cont` and nothing refers to it; did you mean `$count`?'),
        (['show', 'count'], "write the word as in the source, with its `$` and in single quotes: '$count'"),
        (['show', '$Count'], '`$Count` is not a word'),
        (['show', ''], 'the word is empty; if you wrote $name without single quotes'),
        (['uses'], 'mime uses needs a word: mime uses FILE WORD; if you wrote $name without single quotes'),
    ],
)
def test_word_mistakes(prog: Path, capsys: pytest.CaptureFixture[str], args: list[str], message: str) -> None:
    command, *rest = args
    assert main([command, str(prog), *rest]) == 2
    assert capsys.readouterr().err.startswith(f'mime: {message}')


def test_a_program_that_does_not_parse(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / 'broken.mime'
    p.write_text('$number = {type = i64, abstract = "x",}\n')
    assert main(['show', str(p), '$number']) == 1
    assert [d['kind'] for d in json.loads(capsys.readouterr().err)] == ['trailing-comma']
