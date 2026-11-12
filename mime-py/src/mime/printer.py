"""The one layout of a program, its canonical form, and renaming (design/step-5.md)."""

import difflib
from collections.abc import Iterator
from dataclasses import dataclass, field

from mime.compiler import ToolError
from mime.diag import FatalError
from mime.lexer import Span, Tok, tokens
from mime.parser import Definition, Entry, Line, Module, Struct, Value


@dataclass
class Names:
    """A renaming: module words by spelling, and each body's results by spelling. A word missing is kept."""

    words: dict[str, str] = field(default_factory=dict)
    results: dict[int, dict[str, str]] = field(default_factory=dict)  # definition index -> result -> new

    def word(self, w: str) -> str:
        return self.words.get(w, w)

    def in_body(self, index: int, w: str) -> str:
        return self.results.get(index, {}).get(w) or self.word(w)


def _string(source: str, v: Value, rename: dict[str, str]) -> str:
    """The string as written, escapes included, with each reference renamed."""
    raw = source[v.span.start : v.span.end]
    for r in reversed(v.refs):
        if r.word is not None and r.stray is None and r.word in rename:
            at = r.span.start - v.span.start
            raw = raw[:at] + '$' + rename[r.word] + raw[at + 1 + len(r.word) :]
    return raw


def _value(source: str, v: Value | Struct, names: Names) -> str:
    if isinstance(v, Struct):
        return '{' + ', '.join(f'${names.word(w.text)}' for w in v.words) + '}'
    if v.kind == Tok.WORD:
        return f'${names.word(v.text)}'
    if v.kind == Tok.STRING:
        return _string(source, v, names.words)
    return v.text


def _entry(source: str, e: Entry, names: Names) -> str:
    fields = ', '.join(f'{f.key} = {_value(source, f.value, names)}' for f in e.fields)
    return f'${names.word(e.word)} = {{{fields}}}'


def _definition(source: str, d: Definition, index: int, names: Names) -> str:
    def atom(v: Value) -> str:
        return f'${names.in_body(index, v.text)}' if v.kind == Tok.WORD else v.text

    def line(x: Line) -> str:
        result = f'${names.in_body(index, x.result.text)}'
        return f'  {result} = {x.operation.text} {x.type.text} {atom(x.left)}, {atom(x.right)}'

    inputs = ', '.join(f'${names.word(x.text)}' for x in d.inputs)
    output = f'${names.word(d.output.text)}' if d.output.kind == Tok.WORD else d.output.text
    lines = [f'define ${names.word(d.word.text)} {{{inputs}}} -> {output} {{', *map(line, d.lines)]
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


def canonical_names(module: Module) -> Names:
    """`$w0`, `$w1`, … in order of first occurrence; each body's results get fresh names (step-5.md section 3)."""
    names = Names()
    count = 0

    def fresh() -> str:
        nonlocal count
        count += 1
        return f'w{count - 1}'

    def word(w: str) -> None:
        if w not in names.words:
            names.words[w] = fresh()

    def refs(v: Value) -> None:
        for r in v.refs:
            if r.word is not None and r.stray is None:
                word(r.word)

    # A result spelled like a module word is that word, as the checker reads it (a `duplicate-word` mistake), so canon
    # keeps the clash instead of hiding it behind a fresh name.
    module_words = {x.word if isinstance(x, Entry) else x.word.text for x in module.items}
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
        bound = {line.result.text for line in x.lines} - module_words
        body = names.results.setdefault(i, {})

        def use(v: Value, bound: set[str] = bound, body: dict[str, str] = body) -> None:
            if v.kind != Tok.WORD:
                return
            if v.text in bound:
                if v.text not in body:
                    body[v.text] = fresh()
            else:
                word(v.text)

        for line in x.lines:
            use(line.result)
            use(line.left)
            use(line.right)
        use(x.ret)
        refs(x.abstract)
    return names


def canon(module: Module) -> str:
    return layout(module, canonical_names(module))


def _occurrences(source: str) -> Iterator[tuple[str, Span]]:
    """Every domain word in the source, as written: words, and references in strings. Stops at a lexer error."""
    try:
        for t in tokens(source):
            if t.kind == Tok.WORD:
                yield t.text, t.span
            for r in t.refs:
                if r.word is not None and r.stray is None:
                    yield r.word, r.span
    except FatalError:
        return


def words_in(source: str) -> list[str]:
    """Every distinct domain word in the source, in order of first occurrence, as far as it lexes."""
    return list(dict.fromkeys(w for w, _ in _occurrences(source)))


def rename_text(source: str, mapping: dict[str, str]) -> str:
    """`source` with each word in `mapping` replaced, and nothing else changed. A word is given without its `$`."""
    found = [(w, s) for w, s in _occurrences(source) if w in mapping]
    out = source
    for w, s in sorted(found, key=lambda x: x[1].start, reverse=True):
        out = out[: s.start] + '$' + mapping[w] + out[s.start + 1 + len(w) :]
    return out


def rename(source: str, old: str, new: str) -> str:
    """Rename `$old` to `$new` everywhere (design/step-5.md section 4). Refuses to merge two words."""
    spellings = {w for w, _ in _occurrences(source)}
    if old == new:
        msg = f'`${old}` is already called `${new}`'
        raise ToolError(msg)
    if new in spellings:
        msg = f'`${new}` is already used in this file; pick a new word, or rename that one first'
        raise ToolError(msg)
    if old not in spellings:
        close = difflib.get_close_matches(old, sorted(spellings), n=1)
        hint = f'; did you mean `${close[0]}`?' if close else ''
        msg = f'`${old}` does not appear in this file{hint}'
        raise ToolError(msg)
    return rename_text(source, {old: new})
