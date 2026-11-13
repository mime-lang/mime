"""The one layout of a program, its canonical form, and renaming (design/step-5.md, step-6.md)."""

import difflib
from collections.abc import Iterator
from dataclasses import dataclass, field

from mime.diag import FatalError, ToolError
from mime.lexer import Span, Tok, tokens
from mime.parser import Definition, Entry, Line, Module, Struct, Target, Terminator, Value, atoms


@dataclass
class Names:
    """A renaming: words by name, and each body's locals and labels. A name missing from a map is kept.

    A local is identified by its block and its name, `(block index, name)`, since blocks are closed and the same local
    may be bound in two of them (design/step-7.md section 3).
    """

    words: dict[str, str] = field(default_factory=dict)
    locals: dict[int, dict[tuple[int, str], str]] = field(default_factory=dict)  # definition -> local -> new
    labels: dict[int, dict[str, str]] = field(default_factory=dict)  # definition -> label -> new

    def word(self, w: str) -> str:
        return self.words.get(w, w)

    def local(self, index: int, block: int, name: str) -> str:
        return self.locals.get(index, {}).get((block, name), name)

    def label(self, index: int, name: str) -> str:
        return self.labels.get(index, {}).get(name, name)


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
    def atom(block: int, v: Value) -> str:
        if v.kind == Tok.WORD:
            return f'@{names.word(v.text)}'
        if v.kind == Tok.LOCAL:
            return f'%{names.local(index, block, v.text)}'
        return v.text

    def target(block: int, t: Target) -> str:
        return f'^{names.label(index, t.label.text)}{{' + ', '.join(atom(block, a) for a in t.args) + '}'

    def line(block: int, x: Line) -> str:
        op = f'icmp {x.predicate.text}' if x.predicate is not None else x.operation.text
        left, right = atom(block, x.left), atom(block, x.right)
        return f'  {atom(block, x.result)} = {op} {x.type.text} {left}, {right}'

    def end(block: int, x: Terminator) -> str:
        if x.keyword.text == 'ret' and x.value is not None:
            return f'  ret {atom(block, x.value)}'
        jumps = ', '.join(target(block, t) for t in x.targets)
        return f'  br {atom(block, x.value)}, {jumps}' if x.value is not None else f'  br {jumps}'

    inputs = ', '.join(f'@{names.word(x.text)}' for x in d.inputs)
    output = atom(0, d.output) if d.output.kind == Tok.WORD else d.output.text
    lines = [f'define @{names.word(d.word.text)} {{{inputs}}} -> {output} {{']
    for i, b in enumerate(d.blocks):
        if b.label is not None:
            params = ', '.join(atom(i, p) for p in b.params)
            lines.append(f'^{names.label(index, b.label.text)}{{{params}}}:')
        lines += [line(i, x) for x in b.lines]
        lines.append(end(i, b.end))
    lines += ['}', f'abstract = {_string(source, d.abstract, names.words)}']
    if d.symbol is not None:
        # A symbol is data, the name the function is exported under, so renaming and canon never change it.
        lines.append(f'symbol = {source[d.symbol.span.start : d.symbol.span.end]}')
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


def _body_names(d: Definition) -> list[tuple[int, Value]]:
    """Every local and label in a body, in source order, with the index of the block it is in."""
    found: list[tuple[int, Value]] = []
    for i, b in enumerate(d.blocks):
        if b.label is not None:
            found.append((i, b.label))
        found += [(i, p) for p in b.params]
        for x in b.lines:
            found += [(i, x.result), (i, x.left), (i, x.right)]
        if b.end.value is not None:
            found.append((i, b.end.value))
        for t in b.end.targets:
            found.append((i, t.label))
            found += [(i, a) for a in t.args]
    return [(i, v) for i, v in found if v.kind in (Tok.LOCAL, Tok.LABEL)]


def pass_throughs(d: Definition) -> dict[tuple[int, str], tuple[int, str]]:
    """Each block parameter that only ever receives one value, or that value and itself, mapped to that value."""
    blocks = {b.label.text: i for i, b in enumerate(d.blocks) if b.label is not None}
    incoming: dict[tuple[int, str], set[tuple[int, str] | None]] = {}
    for i, b in enumerate(d.blocks):
        for t in b.end.targets:
            j = blocks.get(t.label.text)
            if j is None or len(t.args) != len(d.blocks[j].params):
                continue
            for arg, p in zip(t.args, d.blocks[j].params, strict=True):
                source = (i, arg.text) if arg.kind == Tok.LOCAL else None  # an input or a constant is not a local
                incoming.setdefault((j, p.text), set()).add(source)
    found: dict[tuple[int, str], tuple[int, str]] = {}
    for param, sources in incoming.items():
        others = sources - {param}
        only = next(iter(others)) if len(others) == 1 else None
        if only is not None:
            found[param] = only
    return found


def local_numbers(d: Definition) -> tuple[dict[tuple[int, str], str], dict[str, str]]:
    """The body's locals named `v0`, `v1`, … and its labels `b0`, `b1`, … in order of first appearance
    (design/step-7.md section 6).

    A pass-through block parameter keeps the number of the value it carries (design/step-6.md section 5).
    """
    through = pass_throughs(d)
    locals_: dict[tuple[int, str], str] = {}
    labels: dict[str, str] = {}

    def source(local: tuple[int, str]) -> tuple[int, str]:
        seen = set()
        while local in through and local not in seen:
            seen.add(local)
            local = through[local]
        return local

    count = 0
    for i, v in _body_names(d):
        if v.kind == Tok.LABEL:
            labels.setdefault(v.text, f'b{len(labels)}')
            continue
        root = source((i, v.text))
        if root not in locals_:
            locals_[root] = f'v{count}'
            count += 1
        locals_[(i, v.text)] = locals_[root]
    return locals_, labels


def canonical_names(module: Module) -> Names:
    """Words become `w0`, `w1`, … in order of first occurrence, and each body's locals and labels are numbered."""
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
        for v in (*x.inputs, x.output, *atoms(x)):
            if v.kind == Tok.WORD:
                word(v.text)
        refs(x.abstract)
        names.locals[i], names.labels[i] = local_numbers(x)
    return names


def canon(module: Module) -> str:
    return layout(module, canonical_names(module))


def canon_locals(module: Module) -> str:
    """The source with each body's locals and labels numbered, and nothing else changed (design/step-6.md section 6)."""
    edits: list[tuple[Span, str]] = []
    for x in module.items:
        if isinstance(x, Definition):
            locals_, labels = local_numbers(x)
            for i, v in _body_names(x):
                new = '^' + labels[v.text] if v.kind == Tok.LABEL else '%' + locals_[(i, v.text)]
                edits.append((v.span, new))
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
            elif t.kind == Tok.LABEL:
                yield '^' + t.text, t.span
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
