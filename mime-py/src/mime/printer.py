"""The one layout of a program, its canonical form, and renaming (design/step-5.md, step-6.md)."""

import difflib
from collections.abc import Iterator
from dataclasses import dataclass, field

from mime.compiler import ToolError
from mime.diag import FatalError
from mime.lexer import Span, Tok, tokens
from mime.parser import Definition, Entry, Line, Module, Struct, Value


@dataclass
class Names:
    """A renaming: words by name, and each body's locals by name. A name missing from a map is kept."""

    words: dict[str, str] = field(default_factory=dict)
    locals: dict[int, dict[str, str]] = field(default_factory=dict)  # definition index -> local -> new

    def word(self, w: str) -> str:
        return self.words.get(w, w)

    def local(self, index: int, name: str) -> str:
        return self.locals.get(index, {}).get(name, name)


def _string(source: str, v: Value, rename: dict[str, str]) -> str:
    """The string as written, escapes included, with each reference renamed."""
    raw = source[v.span.start : v.span.end]
    for r in reversed(v.refs):
        if r.word is not None and r.stray is None and r.word in rename:
            at = r.span.start - v.span.start
            raw = raw[:at] + '@' + rename[r.word] + raw[at + 1 + len(r.word) :]
    return raw


def _value(source: str, v: Value | Struct, names: Names) -> str:
    if isinstance(v, Struct):
        return '{' + ', '.join(f'@{names.word(w.text)}' for w in v.words) + '}'
    if v.kind == Tok.WORD:
        return f'@{names.word(v.text)}'
    if v.kind == Tok.LOCAL:
        return f'%{v.text}'
    if v.kind == Tok.STRING:
        return _string(source, v, names.words)
    return v.text


def _entry(source: str, e: Entry, names: Names) -> str:
    fields = ', '.join(f'{f.key} = {_value(source, f.value, names)}' for f in e.fields)
    return f'@{names.word(e.word)} = {{{fields}}}'


def _definition(source: str, d: Definition, index: int, names: Names) -> str:
    def atom(v: Value) -> str:
        if v.kind == Tok.WORD:
            return f'@{names.word(v.text)}'
        if v.kind == Tok.LOCAL:
            return f'%{names.local(index, v.text)}'
        return v.text

    def line(x: Line) -> str:
        return f'  {atom(x.result)} = {x.operation.text} {x.type.text} {atom(x.left)}, {atom(x.right)}'

    inputs = ', '.join(f'@{names.word(x.text)}' for x in d.inputs)
    output = atom(d.output) if d.output.kind == Tok.WORD else d.output.text
    lines = [f'define @{names.word(d.word.text)} {{{inputs}}} -> {output} {{', *map(line, d.lines)]
    lines += [f'  ret {atom(d.ret)}', '}', f'abstract = {_string(source, d.abstract, names.words)}']
    return '\n'.join(lines)


def layout(module: Module, names: Names | None = None) -> str:
    """The program in its one layout (design/step-5.md section 2), with `names` applied."""
    names = names or Names()
    out = ''
    for i, x in enumerate(module.items):
        if i > 0:
            # One blank line around a definition; data words stand on consecutive lines.
            out += '\n\n' if isinstance(x, Definition) or isinstance(module.items[i - 1], Definition) else '\n'
        out += _definition(module.source, x, i, names) if isinstance(x, Definition) else _entry(module.source, x, names)
    return out + '\n' if out else ''


def _body_locals(d: Definition) -> list[Value]:
    """Every local in a body, as written, in source order: results and operands alike."""
    found = []
    for x in d.lines:
        found += [x.result, x.left, x.right]
    return [v for v in [*found, d.ret] if v.kind == Tok.LOCAL]


def local_numbers(d: Definition) -> dict[str, str]:
    """The body's locals numbered `0`, `1`, … in order of first appearance (design/step-6.md section 5).

    Blocks arrive with branches, and with them the rule that a pass-through parameter keeps its value's number.
    """
    numbers: dict[str, str] = {}
    for v in _body_locals(d):
        if v.text not in numbers:
            numbers[v.text] = str(len(numbers))
    return numbers


def canonical_names(module: Module) -> Names:
    """Words become `w0`, `w1`, … in order of first occurrence, and each body's locals are numbered."""
    names = Names()

    def word(w: str) -> None:
        if w not in names.words:
            names.words[w] = f'w{len(names.words)}'

    def refs(v: Value) -> None:
        for r in v.refs:
            if r.word is not None and r.stray is None:
                word(r.word)

    for i, x in enumerate(module.items):
        if isinstance(x, Entry):
            word(x.word)
            for f in x.fields:
                for v in f.value.words if isinstance(f.value, Struct) else (f.value,):
                    if v.kind == Tok.WORD:
                        word(v.text)
                    elif v.kind == Tok.STRING:
                        refs(v)
            continue
        word(x.word.text)
        for v in (*x.inputs, x.output):
            if v.kind == Tok.WORD:
                word(v.text)
        for line in x.lines:
            for v in (line.left, line.right):
                if v.kind == Tok.WORD:
                    word(v.text)
        if x.ret.kind == Tok.WORD:
            word(x.ret.text)
        refs(x.abstract)
        names.locals[i] = local_numbers(x)
    return names


def canon(module: Module) -> str:
    return layout(module, canonical_names(module))


def canon_locals(module: Module) -> str:
    """The source with each body's locals numbered, and nothing else changed (design/step-6.md section 6)."""
    edits: list[tuple[Span, str]] = []
    for x in module.items:
        if isinstance(x, Definition):
            numbers = local_numbers(x)
            edits += [(v.span, '%' + numbers[v.text]) for v in _body_locals(x)]
    out = module.source
    for span, text in sorted(edits, key=lambda e: e[0].start, reverse=True):
        out = out[: span.start] + text + out[span.end :]
    return out


def _occurrences(source: str) -> Iterator[tuple[str, Span]]:
    """Every word and local in the source with its sigil (`@number`, `%double`), references in strings included.

    Stops at a lexer error.
    """
    try:
        for t in tokens(source):
            if t.kind == Tok.WORD:
                yield '@' + t.text, t.span
            elif t.kind == Tok.LOCAL:
                yield '%' + t.text, t.span
            for r in t.refs:
                if r.word is not None and r.stray is None:
                    yield '@' + r.word, Span(r.span.line, r.span.column, r.span.start, r.span.start + 1 + len(r.word))
    except FatalError:
        return


def words_in(source: str) -> list[str]:
    """Every distinct word and local in the source, with its sigil, in order of first occurrence."""
    return list(dict.fromkeys(w for w, _ in _occurrences(source)))


def rename_text(source: str, mapping: dict[str, str]) -> str:
    """`source` with each name in `mapping` replaced, sigils included (`'@number': '@count'`), and nothing else."""
    found = [(w, s) for w, s in _occurrences(source) if w in mapping]
    out = source
    for w, s in sorted(found, key=lambda x: x[1].start, reverse=True):
        out = out[: s.start] + mapping[w] + out[s.end :]
    return out


def rename(source: str, old: str, new: str) -> str:
    """Rename `old` to `new` everywhere, both with their sigil (design/step-5.md section 4, step-6.md section 6)."""
    if old[0] != new[0]:
        msg = f'`{old}` and `{new}` have different sigils; a word stays a word and a local stays a local'
        raise ToolError(msg)
    spellings = set(words_in(source))
    if old == new:
        msg = f'`{old}` is already called `{new}`'
        raise ToolError(msg)
    if new in spellings:
        msg = f'`{new}` is already used in this file; pick a new name, or rename that one first'
        raise ToolError(msg)
    if old not in spellings:
        close = difflib.get_close_matches(old, sorted(spellings), n=1)
        hint = f'; did you mean `{close[0]}`?' if close else ''
        msg = f'`{old}` does not appear in this file{hint}'
        raise ToolError(msg)
    return rename_text(source, {old: new})
