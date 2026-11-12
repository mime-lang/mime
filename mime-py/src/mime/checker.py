"""Check a parsed module (design/step-1.md section 3, design/step-2.md). Reports every error it finds."""

import difflib
from dataclasses import dataclass

from mime.diag import Diagnostic
from mime.lexer import Span, Tok
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
        self.source = module.source
        self.entries = module.entries
        self.diags: list[Diagnostic] = []
        self.index: dict[str, int] = {}  # word -> index of its first entry
        self.kinds: dict[str, str | None] = {}  # word -> 'sort', 'function', or None when unclear
        self.fields: dict[str, dict[str, Field]] = {}  # word -> valid key -> first field with it

    def report(
        self,
        kind: str,
        message: str,
        at: Span,
        hint: str | None = None,
        *,
        entry: str,
        key: str | None = None,
        missing: bool = False,
    ) -> None:
        """Report a mistake at `at`, in the entry for `entry` and the field `key`. Something `missing` has no text."""
        text = None if missing else self.source[at.start : at.end]
        self.diags.append(Diagnostic(kind, message, at.line, at.column, hint, f'${entry}', key, text))

    def run(self) -> Program | None:
        # Index every word first, so a reference can tell a later entry from a missing one.
        for i, e in enumerate(self.entries):
            self.index.setdefault(e.word, i)
        valid_by_entry = []
        for i, e in enumerate(self.entries):
            kind, valid = self.entry(e)
            valid_by_entry.append(valid)
            if self.index[e.word] == i:
                self.kinds[e.word], self.fields[e.word] = kind, valid
            else:
                self.report(
                    'duplicate-word',
                    f'`${e.word}` already has an entry',
                    e.span,
                    'a word has one entry; merge the two or rename one',
                    entry=e.word,
                )
        for i, (e, valid) in enumerate(zip(self.entries, valid_by_entry, strict=True)):
            if 'description' in valid:
                self.description(e.word, i, valid['description'].value)
        for word, i in self.index.items():
            if self.kinds[word] == 'function':
                for key in ('takes', 'returns'):
                    if key in self.fields[word]:
                        self.reference(word, i, key, self.fields[word][key].value)
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
                self.report(
                    'duplicate-key',
                    f'`{f.key}` appears twice in the entry for `${e.word}`',
                    f.span,
                    entry=e.word,
                    key=f.key,
                )
            elif f.key not in KEYS:
                hint = (
                    'did you mean `sort`?'
                    if f.key == 'type'
                    else (f'a {kind} entry has the keys {_keys(expected)}' if kind else BOTH_KINDS)
                )
                self.report('unknown-key', f'`{f.key}` is not a key', f.span, hint, entry=e.word, key=f.key)
            elif kind and f.key not in expected:
                self.report(
                    'unknown-key',
                    f'`{f.key}` is not a key of a {kind} entry',
                    f.span,
                    f'a {kind} entry has the keys {_keys(expected)}',
                    entry=e.word,
                    key=f.key,
                )
            else:
                valid[f.key] = f
                self.value(e.word, f)
        if kind is None:
            if len(valid) < len(e.fields):
                return None, valid  # an unknown key was already reported, often the reason the kind is unclear
            self.report(
                'missing-key',
                f'the entry for `${e.word}` is neither a sort entry nor a function entry',
                e.span,
                BOTH_KINDS,
                entry=e.word,
                missing=True,
            )
            return None, valid
        missing = [k for k in expected if k not in valid]
        if missing:
            self.report(
                'missing-key',
                f'the entry for `${e.word}` is missing {_keys(tuple(missing))}',
                e.span,
                f'a {kind} entry has the keys {_keys(expected)}',
                entry=e.word,
                missing=True,
            )
        order = list(valid)
        want = [k for k in expected if k in valid]
        if order != want:
            first_wrong = next(valid[a] for a, b in zip(order, want, strict=True) if a != b)
            self.report(
                'key-order',
                f'the keys of `${e.word}` are out of order',
                first_wrong.span,
                f'write them in this order: {_keys(expected)}',
                entry=e.word,
                key=first_wrong.key,
            )
        return kind, valid

    def value(self, word: str, f: Field) -> None:
        v = f.value
        at = {'entry': word, 'key': f.key}
        if v.kind == Tok.NAME and v.text not in LANGUAGE_WORDS and f.key in ('takes', 'returns'):
            self.report(
                'unknown-language-word',
                f'`{v.text}` is not a language word',
                v.span,
                f'did you mean `${v.text}`?',
                **at,
            )
            return
        if f.key == 'description':
            if v.kind != Tok.STRING:
                self.report('bad-value', '`description` takes a string', v.span, 'write the meaning in `"…"`', **at)
            elif not v.text.strip():
                self.report('bad-value', 'a description cannot be empty', v.span, 'say what the word means', **at)
        elif f.key == 'sort':
            if v.kind != Tok.NAME or v.text not in SORTS:
                later = v.kind == Tok.NAME and v.text in LATER_SORTS
                hint = f'`{v.text}` arrives in a later step; ' if later else ''
                self.report(
                    'bad-value', f'`{_value_text(v)}` is not a sort', v.span, hint + 'the only sort is `i64`', **at
                )
        elif f.key in ('takes', 'returns') and v.kind != Tok.WORD:
            self.report('bad-value', f'`{f.key}` names a word', v.span, 'name a sort entry, such as `$number`', **at)
        elif f.key == 'body' and (v.kind != Tok.NAME or v.text != INPUT):
            self.report('bad-value', f'`{_value_text(v)}` is not a body', v.span, 'the only body is `input`', **at)

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

    def description(self, owner: str, owner_index: int, v: Value) -> None:
        """Check the `$` references inside a description (design/step-2.md)."""
        if v.kind != Tok.STRING:
            return
        at = {'entry': owner, 'key': 'description'}
        for r in v.refs:
            if r.word is None:
                self.report(
                    'bad-reference',
                    '`$` in a description must start a reference to a word',
                    r.span,
                    'write `\\$` for a dollar sign',
                    **at,
                )
            elif r.stray is not None:
                self.report(
                    'bad-reference',
                    f'`${r.word}` is followed by `{r.stray}`, which cannot appear in a name',
                    r.span,
                    'a name is lowercase letters, digits or `_`; put a space or punctuation other than `-` after it',
                    **at,
                )
            elif r.word not in self.index:
                self.report(
                    'undeclared-word',
                    f'no entry declares `${r.word}`',
                    r.span,
                    self.suggest(r.word, owner, owner_index),
                    **at,
                )
            elif r.word == owner and self.index[owner] == owner_index:
                self.report(
                    'forward-reference',
                    f'the description of `${owner}` refers to `${owner}` itself',
                    r.span,
                    f'a description may refer only to earlier entries; describe `${owner}` by its parts',
                    **at,
                )
            elif self.index[r.word] > owner_index:
                self.report(
                    'forward-reference',
                    f'`${r.word}` is declared after `${owner}`',
                    r.span,
                    f'a description may refer only to earlier entries; move the entry for `${r.word}` above `${owner}`',
                    **at,
                )

    def reference(self, owner: str, owner_index: int, key: str, v: Value) -> None:
        if v.kind != Tok.WORD:
            return
        at = {'entry': owner, 'key': key}
        if v.text not in self.index:
            self.report(
                'undeclared-word',
                f'no entry declares `${v.text}`',
                v.span,
                self.suggest(v.text, owner, owner_index),
                **at,
            )
        elif self.index[v.text] >= owner_index:
            self.report(
                'forward-reference',
                f'`${v.text}` is declared after `${owner}`',
                v.span,
                f'move the entry for `${v.text}` above `${owner}`',
                **at,
            )
        elif self.kinds[v.text] == 'function':
            self.report(
                'not-a-sort',
                f'`${v.text}` is a function entry, not a sort entry',
                v.span,
                'name a sort entry, such as `$number`',
                **at,
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
