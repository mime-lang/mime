"""Commands an agent uses on a program besides checking and running it (design/tools.md)."""

import difflib
import json
from dataclasses import dataclass

from mime.diag import ToolError
from mime.lexer import Span, Tok
from mime.parser import Declaration, Definition, Entry, Module, Struct, Value, atoms, item_word


@dataclass(frozen=True)
class Use:
    entry: str  # the word of the entry the use is in, with its `@`
    key: str
    text: str  # the reference as written, such as `@number`
    span: Span


def _words(module: Module) -> list[str]:
    return [item_word(x) for x in module.items]


def _did_you_mean(module: Module, word: str) -> str:
    close = difflib.get_close_matches(word, _words(module), n=1)
    return f'; did you mean `@{close[0]}`?' if close else ''


def show(module: Module, word: str) -> str:
    """The source text of every entry for `word`, in order, with a blank line between two.

    A function's entry is its whole definition, from `define` through its abstract. Its `declare` is shown only while
    there is no `define`, since the `define` repeats its type (design/step-9.md section 8).

    A function comes after the entries of the data words in its type, in source order (design/tools.md section 2.1).
    """
    found = [x for x in module.items if item_word(x) == word]
    if any(isinstance(x, Definition) for x in found):
        found = [x for x in found if not isinstance(x, Declaration)]
    if not found:
        msg = f'no entry declares `@{word}`{_did_you_mean(module, word)}'
        raise ToolError(msg)
    head = {
        v.text
        for x in found
        if isinstance(x, Definition | Declaration)
        for v in (*x.inputs, x.output)
        if v.kind == Tok.WORD
    }
    shown = [x for x in module.items if isinstance(x, Entry) and x.word in head] + found
    return '\n\n'.join(module.source[x.span.start : x.end] for x in shown) + '\n'


def _refs(v: Value, word: str) -> list[Span]:
    return [r.span for r in v.refs if r.word == word and r.stray is None] if v.kind == Tok.STRING else []


def uses(module: Module, word: str) -> list[Use]:
    """Every reference to `word`, in source order: in a type, an abstract, an input or output, and a body."""
    found: list[tuple[str, str, Span]] = []
    for d in module.items:
        if isinstance(d, Entry):
            for f in d.fields:
                v = f.value
                values = list(v.words) if isinstance(v, Struct) else [v]
                spans = [x.span for x in values if x.kind == Tok.WORD and x.text == word]
                if f.key == 'abstract' and isinstance(v, Value):
                    spans += _refs(v, word)
                found += [(d.word, f.key, s) for s in spans]
            continue
        head = [x.span for x in (*d.inputs, d.output) if x.kind == Tok.WORD and x.text == word]
        if isinstance(d, Declaration):
            found += [(d.word.text, 'type', s) for s in head]
            continue
        body = [a.span for a in atoms(d) if a.kind == Tok.WORD and a.text == word]
        found += [(d.word.text, 'type', s) for s in head]
        found += [(d.word.text, 'body', s) for s in body]
        found += [(d.word.text, 'abstract', s) for s in _refs(d.abstract, word)]
    if not found and word not in _words(module):
        msg = f'no entry declares `@{word}` and nothing refers to it{_did_you_mean(module, word)}'
        raise ToolError(msg)
    return [Use(f'@{w}', key, module.source[s.start : s.end], s) for w, key, s in found]


def local_uses(module: Module, local: str) -> list[Use]:
    """Every read of `%local` in every body that binds or reads it, in source order. Its bindings are not uses."""
    return [
        Use(f'@{d.word.text}', 'body', f'%{a.text}', a.span)
        for d in module.definitions
        for a in atoms(d)
        if a.kind == Tok.LOCAL and a.text == local
    ]


def uses_json(found: list[Use], *, positions: bool = False) -> str:
    """The uses as a JSON array, with the location fields of a diagnostic (design/diagnostics.md)."""
    rows = []
    for u in found:
        row: dict[str, str | int] = {'entry': u.entry, 'key': u.key, 'text': u.text}
        if positions:
            row |= {'line': u.span.line, 'column': u.span.column}
        rows.append(row)
    return json.dumps(rows, indent=2, ensure_ascii=False) + '\n'
