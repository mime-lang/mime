"""Calls, recursion and `declare` (design/step-9.md)."""

import json
from pathlib import Path

import pytest

from mime import interp
from mime.cli import main
from mime.compiler import analyze, run
from mime.parser import parse
from mime.printer import canon, layout, rename
from mime.tools import show, uses

N = '@n = {type = i64, abstract = "a whole number"}\n'
SAME = 'define @same {@n} -> i64 {\n  ret @n\n}\nabstract = "the @n it is given"\n'


def caller(body: str, word: str = '@f') -> str:
    return f'define {word} {{@n}} -> i64 {{\n{body}\n}}\nabstract = "x"\n'


def kinds(source: str) -> list[str]:
    return [d.kind for d in analyze(source)[1]]


@pytest.mark.parametrize(
    ('body', 'hint'),
    [
        ('%r = call @same(@n)\nret %r', 'write `call @same {@a = %x}`'),
        ('%r = call i64 @same {@n = @n}\nret %r', 'write `call @same {@a = %x}`; the type comes from `@same`'),
        ('%r = call @same {%x}\nret %r', 'an argument names an input of `@same`'),
        ('%r = call @same {@n %x}\nret %r', 'write `@n = %x`'),
        ('%r = add i64 call @same {@n = @n}, 1\nret %r', 'give the inner operation its own line'),
    ],
)
def test_call_syntax_hints(body: str, hint: str) -> None:
    (d,) = analyze(N + SAME + caller(body))[1]
    assert d.hint is not None
    assert hint in d.hint


@pytest.mark.parametrize(
    ('declaration', 'hint'),
    [
        ('declare @g {@n} -> i64 {\n  ret @n\n}\n', 'write the body in the `define` of `@g` below'),
        ('declare @g {@n} -> i64\nabstract = "x"\n', 'write `abstract = …` after the `define` of `@g`'),
    ],
)
def test_a_declaration_is_only_a_head(declaration: str, hint: str) -> None:
    (d,) = analyze(N + declaration)[1]
    assert d.kind == 'syntax'
    assert d.hint is not None
    assert hint in d.hint


def test_a_function_may_call_itself() -> None:
    assert kinds(N + caller('%r = call @f {@n = @n}\nret %r')) == []


def test_an_unread_call_is_an_unused_local() -> None:
    assert kinds(N + SAME + caller('%r = call @same {@n = @n}\nret @n')) == ['unused-local']


def test_a_call_of_a_missing_function_suggests_one() -> None:
    (d,) = analyze(N + SAME + caller('%r = call @sme {@n = @n}\nret %r'))[1]
    assert (d.kind, d.hint) == ('undeclared-word', 'did you mean `@same`?')


def test_an_argument_key_is_not_a_read_of_the_callers_input() -> None:
    # `@n = 1` names the callee's input; the caller's `@n` is still unread.
    assert kinds(N + SAME + caller('%r = call @same {@n = 1}\nret %r')) == ['unused-local']


def test_an_abstract_may_refer_to_a_declared_function() -> None:
    source = (
        N + 'declare @g {@n} -> i64\n'
        'define @f {@n} -> i64 {\n  %r = call @g {@n = @n}\n  ret %r\n}\nabstract = "like @g"\n'
        'define @g {@n} -> i64 {\n  %r = call @f {@n = @n}\n  ret %r\n}\nabstract = "like @f"\n'
    )
    assert kinds(source) == []


def test_a_declaration_mentioned_only_in_an_abstract_is_needed() -> None:
    source = (
        N + 'declare @g {@n} -> i64\n'
        '@m = {type = i64, abstract = "a number for @g"}\n'
        'define @g {@n} -> i64 {\n  ret @n\n}\nabstract = "the @n"\n'
    )
    assert kinds(source) == []


def test_a_declared_function_still_may_not_describe_itself() -> None:
    source = N + 'declare @g {@n} -> i64\n' + caller('%r = call @g {@n = @n}\nret %r')
    source += 'define @g {@n} -> i64 {\n  ret @n\n}\nabstract = "@g itself"\n'
    assert kinds(source) == ['forward-reference']


def test_layout_and_canon_keep_a_declaration() -> None:
    source = (Path(__file__).parent / 'goldens' / 'clean' / 'even_odd.mime').read_text()
    module = parse(source)
    assert layout(module) == source
    assert 'declare @w2 {@w0} -> @w1\n\ndefine @w3' in canon(module)


def test_show_prints_the_define_not_the_declaration() -> None:
    source = N + 'declare @g {@n} -> i64\n' + caller('%r = call @g {@n = @n}\nret %r')
    assert show(parse(source), 'g') == 'declare @g {@n} -> i64\n'
    source += 'define @g {@n} -> i64 {\n  ret @n\n}\nabstract = "x"\n'
    assert show(parse(source), 'g').startswith('define @g {@n} -> i64 {')


def test_uses_lists_calls_and_argument_keys() -> None:
    module = parse(N + SAME + caller('%r = call @same {@n = @n}\nret %r'))
    assert [(u.entry, u.key, u.text) for u in uses(module, 'same')] == [('@f', 'body', '@same')]
    found = [(u.entry, u.key) for u in uses(module, 'n')]
    assert found.count(('@f', 'body')) == 2  # the callee's input `@n =` and the caller's `@n`


def test_renaming_an_input_renames_the_argument_keys() -> None:
    source = rename(N + SAME + caller('%r = call @same {@n = @n}\nret %r'), '@n', '@count')
    assert '%r = call @same {@count = @count}' in source
    assert kinds(source) == []


def test_the_interpreter_holds_a_limited_number_of_frames(monkeypatch: pytest.MonkeyPatch) -> None:
    program, _ = analyze(N + caller('%r = call @f {@n = @n}\nret %r') + 'symbol = "f"\n')
    assert program is not None
    monkeypatch.setattr(interp, 'FRAMES', 50)
    with pytest.raises(Exception, match='ran out of stack'):
        run(program, 'f', ['1'])


def test_a_deep_but_finite_recursion_needs_no_python_recursion() -> None:
    program, _ = analyze((Path(__file__).parent / 'goldens' / 'clean' / 'recursion.mime').read_text())
    assert program is not None
    assert run(program, 'sum', ['5000']) == f'{5000 * 5001 // 2}\n'


def test_running_out_of_stack_exits_with_2(capsys: pytest.CaptureFixture[str]) -> None:
    golden = Path(__file__).parent / 'goldens' / 'clean' / 'recursion.mime'
    assert main(['run', str(golden), 'forever', '1']) == 2
    assert capsys.readouterr().err == (
        'mime: `forever` ran out of stack: the machine could not hold that many nested calls, '
        'or a recursion never reaches its base case\n'
    )


def test_check_json_names_the_call(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / 'p.mime'
    p.write_text(N + SAME + caller('%r = call @same {}\n%s = add i64 %r, @n\nret %s'))
    assert main(['check', str(p)]) == 1
    (d,) = json.loads(capsys.readouterr().out)
    assert (d['kind'], d['entry'], d['key'], d['text']) == ('missing-key', '@f', 'body', '@same')


def report(source: str) -> list[tuple[str, str | None]]:
    return [(d.kind, d.hint) for d in analyze(source)[1]]


def test_a_rejected_input_of_the_callee_is_reported_once() -> None:
    source = N + 'define @g {@nn} -> i64 {\n  ret 1\n}\nabstract = "x"\n' + caller('%r = call @g {@nn = @n}\nret %r')
    assert report(source) == [('undeclared-word', 'did you mean `@n`?')]


def test_a_self_call_follows_its_own_head_when_the_declaration_differs() -> None:
    source = (
        N + '@m = {type = i64, abstract = "y"}\ndeclare @g {@n} -> i64\n' + caller('%r = call @g {@n = @n}\nret %r')
    )
    source += 'define @g {@m} -> i64 {\n  %r = call @g {@m = @m}\n  ret %r\n}\nabstract = "x"\n'
    assert report(source) == [('wrong-type', '`@g` is declared above as `{@n} -> i64`')]


def test_a_declaration_below_the_caller_is_moved_not_repeated() -> None:
    source = N + caller('%r = call @g {@n = @n}\nret %r') + 'declare @g {@n} -> i64\n'
    source += caller('%r = call @g {@n = @n}\nret %r', '@h') + 'define @g {@n} -> i64 {\n  ret @n\n}\nabstract = "x"\n'
    assert report(source) == [('forward-reference', 'move `declare @g {@n} -> i64` above `@f`')]


def test_a_declared_word_given_a_data_entry_is_one_mistake() -> None:
    assert kinds(N + 'declare @g {@n} -> i64\n@g = {type = i64, abstract = "x"}\n') == ['duplicate-word']
