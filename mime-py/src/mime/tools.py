"""Commands an agent uses on a program besides checking and running it (design/tools.md)."""

import difflib
import json
from dataclasses import dataclass

from mime.compiler import ToolError
from mime.lexer import Span, Tok
from mime.parser import Module


@dataclass(frozen=True)
class Use:
    entry: str  # the word of the entry the use is in, with its `$`
    key: str
    text: str  # the reference as written, such as `$number`
    span: Span


def _did_you_mean(module: Module, word: str) -> str:
    close = difflib.get_close_matches(word, [e.word for e in module.entries], n=1)
    return f'; did you mean `${close[0]}`?' if close else ''


def show(module: Module, word: str) -> str:
    """The source text of every entry for `word`, in order, with a blank line between two."""
    texts = [module.source[e.span.start : e.end] for e in module.entries if e.word == word]
    if not texts:
        msg = f'no entry declares `${word}`{_did_you_mean(module, word)}'
        raise ToolError(msg)
    return '\n\n'.join(texts) + '\n'


def uses(module: Module, word: str) -> list[Use]:
    """Every reference to `word`, in source order: as a value, and in a description."""
    found: list[Use] = []
    for e in module.entries:
        for f in e.fields:
            v = f.value
            spans = [v.span] if v.kind == Tok.WORD and v.text == word else []
            if f.key == 'description' and v.kind == Tok.STRING:
                spans += [r.span for r in v.refs if r.word == word and r.stray is None]
            found += [Use(f'${e.word}', f.key, module.source[s.start : s.end], s) for s in spans]
    if not found and all(e.word != word for e in module.entries):
        msg = f'no entry declares `${word}` and nothing refers to it{_did_you_mean(module, word)}'
        raise ToolError(msg)
    return found


def uses_json(found: list[Use], *, positions: bool = False) -> str:
    """The uses as a JSON array, with the location fields of a diagnostic (design/diagnostics.md)."""
    rows = []
    for u in found:
        row: dict[str, str | int] = {'entry': u.entry, 'key': u.key, 'text': u.text}
        if positions:
            row |= {'line': u.span.line, 'column': u.span.column}
        rows.append(row)
    return json.dumps(rows, indent=2, ensure_ascii=False) + '\n'
