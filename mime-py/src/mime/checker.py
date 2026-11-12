"""Check a parsed module against the step 1 rules (design/step-1.md, section 3). Reports every error it finds."""

import difflib
from dataclasses import dataclass

from mime.diag import Diagnostic
from mime.lexer import Tok
from mime.parser import Entry, Field, Module, Value
from mime.words import FUNCTION_KEYS, INPUT, KEYS, LANGUAGE_WORDS, SORT_KEYS, SORTS

KIND_KEYS = {'sort': SORT_KEYS, 'function': FUNCTION_KEYS}
LATER_SORTS = frozenset({'i1', 'i8', 'i16', 'i32'})
BOTH_KINDS = 'a sort entry has `description`, `sort`; a function entry has `description`, `takes`, `returns`, `body`'


@dataclass(frozen=True)
class Function:
    word: str
    takes: str
    returns: str
    sort: str  # the sort of both the input and the result; step 1 has only `i64`


@dataclass(frozen=True)
class Program:
    sorts: dict[str, str]  # word -> sort, for every sort entry
    functions: tuple[Function, ...]


def _keys(names: tuple[str, ...]) -> str:
    return ', '.join(f'`{n}`' for n in names)


def _value_text(v: Value) -> str:
    return f'${v.text}' if v.kind == Tok.WORD else v.text


class _Checker:
    def __init__(self, module: Module) -> None:
        self.entries = module.entries
        self.diags: list[Diagnostic] = []
        self.index: dict[str, int] = {}  # word -> index of its first entry
        self.kinds: dict[str, str | None] = {}  # word -> 'sort', 'function', or None when unclear
        self.fields: dict[str, dict[str, Field]] = {}  # word -> valid key -> first field with it

    def report(self, kind: str, message: str, at: Entry | Field | Value, hint: str | None = None) -> None:
        self.diags.append(Diagnostic(kind, message, at.line, at.column, hint))

    def run(self) -> Program | None:
        for i, e in enumerate(self.entries):
            if e.word in self.index:
                first = self.entries[self.index[e.word]]
                self.report(
                    'duplicate-word', f'`${e.word}` already has an entry', e, f'the first entry is on line {first.line}'
                )
                self.entry(e)  # still check it, but nothing refers to it
            else:
                self.index[e.word] = i
                self.kinds[e.word], self.fields[e.word] = self.entry(e)
        for word, i in self.index.items():
            if self.kinds[word] == 'function':
                for key in ('takes', 'returns'):
                    if key in self.fields[word]:
                        self.reference(word, i, self.fields[word][key].value)
        self.diags.sort(key=lambda d: (d.line, d.column))
        if self.diags:
            return None
        return self.program()

    def entry(self, e: Entry) -> tuple[str | None, dict[str, Field]]:
        present = {f.key for f in e.fields}
        kind = 'sort' if 'sort' in present else 'function' if present & {'takes', 'returns', 'body'} else None
        expected = KIND_KEYS[kind] if kind else ()
        valid: dict[str, Field] = {}
        for f in e.fields:
            if f.key in valid:
                self.report('duplicate-key', f'`{f.key}` appears twice in the entry for `${e.word}`', f)
            elif f.key not in KEYS:
                hint = (
                    'did you mean `sort`?'
                    if f.key == 'type'
                    else (f'a {kind} entry has the keys {_keys(expected)}' if kind else BOTH_KINDS)
                )
                self.report('unknown-key', f'`{f.key}` is not a key', f, hint)
            elif kind and f.key not in expected:
                self.report(
                    'unknown-key',
                    f'`{f.key}` is not a key of a {kind} entry',
                    f,
                    f'a {kind} entry has the keys {_keys(expected)}',
                )
            else:
                valid[f.key] = f
                self.value(f)
        if kind is None:
            if len(valid) < len(e.fields):
                return None, valid  # an unknown key was already reported, often the reason the kind is unclear
            self.report(
                'missing-key', f'the entry for `${e.word}` is neither a sort entry nor a function entry', e, BOTH_KINDS
            )
            return None, valid
        missing = [k for k in expected if k not in valid]
        if missing:
            self.report(
                'missing-key',
                f'the entry for `${e.word}` is missing {_keys(tuple(missing))}',
                e,
                f'a {kind} entry has the keys {_keys(expected)}',
            )
        order = list(valid)
        want = [k for k in expected if k in valid]
        if order != want:
            first_wrong = next(valid[a] for a, b in zip(order, want, strict=True) if a != b)
            self.report(
                'key-order',
                f'the keys of `${e.word}` are out of order',
                first_wrong,
                f'write them in this order: {_keys(expected)}',
            )
        return kind, valid

    def value(self, f: Field) -> None:
        v = f.value
        if v.kind == Tok.NAME and v.text not in LANGUAGE_WORDS and f.key in ('takes', 'returns'):
            self.report('unknown-language-word', f'`{v.text}` is not a language word', v, f'did you mean `${v.text}`?')
            return
        if f.key == 'description':
            if v.kind != Tok.STRING:
                self.report('bad-value', '`description` takes a string', v, 'write the meaning in `"…"`')
            elif not v.text.strip():
                self.report('bad-value', 'a description cannot be empty', v, 'say what the word means')
        elif f.key == 'sort':
            if v.kind != Tok.NAME or v.text not in SORTS:
                later = v.kind == Tok.NAME and v.text in LATER_SORTS
                hint = f'`{v.text}` arrives in a later step; ' if later else ''
                self.report(
                    'bad-value', f'`{_value_text(v)}` is not a sort', v, hint + 'the only sort in step 1 is `i64`'
                )
        elif f.key in ('takes', 'returns') and v.kind != Tok.WORD:
            self.report('bad-value', f'`{f.key}` names a word', v, 'name a sort entry, such as `$number`')
        elif f.key == 'body' and (v.kind != Tok.NAME or v.text != INPUT):
            self.report('bad-value', f'`{_value_text(v)}` is not a body', v, 'the only body in step 1 is `input`')

    def suggest(self, typo: str, owner: str, owner_index: int) -> str | None:
        """A close word the reference could mean, preferring words it may already refer to."""
        earlier = [w for w, i in self.index.items() if i < owner_index]
        close = difflib.get_close_matches(typo, earlier, n=1)
        if close:
            return f'did you mean `${close[0]}`?'
        later = [w for w, i in self.index.items() if i > owner_index]
        close = difflib.get_close_matches(typo, later, n=1)
        if close:
            return f'did you mean `${close[0]}`? It is declared later, so also move its entry above `${owner}`'
        return None

    def reference(self, owner: str, owner_index: int, v: Value) -> None:
        if v.kind != Tok.WORD:
            return
        if v.text not in self.index:
            self.report(
                'undeclared-word', f'no entry declares `${v.text}`', v, self.suggest(v.text, owner, owner_index)
            )
        elif self.index[v.text] >= owner_index:
            self.report(
                'forward-reference',
                f'`${v.text}` is declared after `${owner}`',
                v,
                f'move the entry for `${v.text}` above `${owner}`',
            )
        elif self.kinds[v.text] == 'function':
            self.report(
                'not-a-sort',
                f'`${v.text}` is a function entry, not a sort entry',
                v,
                'name a sort entry, such as `$number`',
            )

    def program(self) -> Program:
        sorts = {w: self.fields[w]['sort'].value.text for w, k in self.kinds.items() if k == 'sort'}
        functions = []
        for w, k in self.kinds.items():
            if k == 'function':
                takes, returns = self.fields[w]['takes'].value.text, self.fields[w]['returns'].value.text
                functions.append(Function(w, takes, returns, sorts[takes]))
        return Program(sorts, tuple(functions))


def check(module: Module) -> tuple[Program | None, list[Diagnostic]]:
    checker = _Checker(module)
    program = checker.run()
    return program, checker.diags
