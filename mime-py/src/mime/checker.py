"""Check a parsed module (design/step-1.md section 3, step-2.md, step-3.md). Reports every error it finds."""

import difflib
from dataclasses import dataclass
from typing import TypedDict

from mime.diag import Diagnostic
from mime.lexer import Span, Tok
from mime.parser import Entry, Field, Let, Module, Operation, Value
from mime.words import FUNCTION_KEYS, INPUT, KEYS, LANGUAGE_WORDS, OPERATIONS, SORT_KEYS, SORTS

KIND_KEYS = {'sort': SORT_KEYS, 'function': FUNCTION_KEYS}
LATER_SORTS = frozenset({'i1', 'i8', 'i16', 'i32'})
LATER_OPERATIONS = frozenset({'sdiv', 'udiv', 'srem', 'urem', 'icmp', 'call'})
I64_MIN, I64_MAX = -(2**63), 2**63 - 1
OPERANDS = 3  # an operation takes its sort and two values
OPERAND_HINT = 'an operand is `input`, a local bound earlier in this body, or an integer'
BOTH_KINDS = 'a sort entry has `description`, `sort`; a function entry has `description`, `takes`, `returns`, `body`'


@dataclass(frozen=True)
class Function:
    word: str
    takes: str
    returns: str
    sort: str  # the sort of both the input and the result; there is only `i64` so far
    body: Value | Let


@dataclass(frozen=True)
class Program:
    sorts: dict[str, str]  # word -> sort, for every sort entry
    functions: tuple[Function, ...]


class Where(TypedDict):
    """Where a mistake is, as `report` takes it: the entry's word and the key of the field."""

    entry: str
    key: str | None


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
        self.locals: dict[str, list[str]] = {}  # local -> the functions whose bodies bind it

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
        for e in self.entries:
            for f in e.fields:
                b = f.value
                while f.key == 'body' and isinstance(b, Let):
                    owners = self.locals.setdefault(b.local.text, [])
                    if e.word not in owners:
                        owners.append(e.word)
                    b = b.rest
        for i, (e, valid) in enumerate(zip(self.entries, valid_by_entry, strict=True)):
            if 'description' in valid:
                self.description(e.word, i, valid['description'].value)
        for word, i in self.index.items():
            if self.kinds[word] == 'function':
                for key in ('takes', 'returns'):
                    if key in self.fields[word]:
                        self.reference(word, i, key, self.fields[word][key].value)
                self.operation_sorts(word)
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
        at: Where = {'entry': word, 'key': f.key}
        if f.key == 'body':
            self.body(word, v)
            return
        if isinstance(v, Let):
            self.report('bad-value', '`let` belongs in a `body`', v.span, f'`{f.key}` takes a single value', **at)
            return
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

    def body(self, word: str, body: Value | Let) -> None:
        """Check a `let` chain (design/step-3.md): its locals, its operations, and that every local is used."""
        at: Where = {'entry': word, 'key': 'body'}
        lets = []
        b = body
        while isinstance(b, Let):
            lets.append(b)
            b = b.rest
        # A local that clashes with a module word is reported once, at its `let`; before it, the word is the entry.
        every_local = {x.local.text for x in lets if x.local.text not in self.index}
        bound: dict[str, Value] = {}  # local -> the `let` word that binds it
        used: set[str] = set()
        for x in lets:
            self.operation(x.operation, x.local.text, bound, every_local, used, at)
            local = x.local
            if local.text in self.index:
                self.report(
                    'duplicate-word',
                    f'`${local.text}` already has an entry, so a local cannot use it',
                    local.span,
                    'pick a new word for the local',
                    **at,
                )
                bound[local.text] = local  # later uses read it, so they are not reported again
                used.add(local.text)
            elif local.text in bound:
                self.report(
                    'duplicate-word',
                    f'`${local.text}` is already bound in this body',
                    local.span,
                    'pick a new word for the local',
                    **at,
                )
            else:
                bound[local.text] = local
        self.atom(b, None, bound, every_local, used, at)
        for local, v in bound.items():
            if local not in used:
                self.report(
                    'unused-local',
                    f'nothing reads `${local}`',
                    v.span,
                    'use it, or remove its `let`; a body often returns the wrong local',
                    **at,
                )

    def operation(
        self, op: Operation, local: str, bound: dict[str, Value], every: set[str], used: set[str], at: Where
    ) -> None:
        name = op.name.text
        if name not in OPERATIONS:
            if name in LATER_OPERATIONS:
                self.report(
                    'bad-value',
                    f'`{name}` arrives in a later step',
                    op.name.span,
                    'the operations are `add`, `sub` and `mul`',
                    **at,
                )
            elif name in LANGUAGE_WORDS:
                self.report(
                    'bad-value',
                    f'`{name}` is not an operation',
                    op.name.span,
                    'the operations are `add`, `sub` and `mul`',
                    **at,
                )
            else:
                self.report(
                    'unknown-language-word',
                    f'`{name}` is not a language word',
                    op.name.span,
                    'the operations are `add`, `sub` and `mul`',
                    **at,
                )
        if len(op.operands) != OPERANDS:
            self.report(
                'bad-value',
                f'`{name}` takes a sort and two operands, not {len(op.operands)} operands',
                op.span,
                f'write `{name} {{i64, a, b}}`',
                **at,
            )
        sort, *values = op.operands
        if sort.kind != Tok.NAME or sort.text not in SORTS:
            later = sort.kind == Tok.NAME and sort.text in LATER_SORTS
            hint = 'the first operand is a sort, such as `i64`'
            if sort.kind == Tok.WORD:
                hint += f'; `${sort.text}` is a word, not a sort'
            elif later:
                hint = f'`{sort.text}` arrives in a later step; the only sort is `i64`'
            self.report('bad-value', f'`{_value_text(sort)}` is not a sort', sort.span, hint, **at)
        for v in values:
            self.atom(v, local, bound, every, used, at)

    def atom(
        self,
        v: Value,
        local: str | None,
        bound: dict[str, Value],
        every: set[str],
        used: set[str],
        at: Where,
    ) -> None:
        """Check an operand, or the final value of a body. `local` is the word the enclosing `let` binds."""
        if v.kind == Tok.INT:
            if not I64_MIN <= int(v.text) <= I64_MAX:
                self.report(
                    'bad-value', f'`{v.text}` does not fit in `i64`', v.span, 'an `i64` is from -2^63 to 2^63-1', **at
                )
        elif v.kind == Tok.NAME:
            if v.text == INPUT:
                return
            if v.text in LANGUAGE_WORDS:
                self.report('bad-value', f'`{v.text}` is not a value', v.span, OPERAND_HINT, **at)
            else:
                self.report(
                    'unknown-language-word',
                    f'`{v.text}` is not a language word',
                    v.span,
                    f'did you mean `${v.text}`?',
                    **at,
                )
        elif v.kind == Tok.STRING:
            self.report('bad-value', 'a body is not a string', v.span, OPERAND_HINT, **at)
        elif v.text in bound:
            used.add(v.text)
        elif v.text == local:
            used.add(v.text)  # reported here, not again as unused
            self.report(
                'forward-reference',
                f'`${v.text}` is bound by this `let`, so its own operation cannot read it',
                v.span,
                OPERAND_HINT,
                **at,
            )
        elif v.text in every:
            used.add(v.text)
            self.report(
                'forward-reference',
                f'`${v.text}` is bound later in this body',
                v.span,
                f'move the `let` for `${v.text}` above this one',
                **at,
            )
        elif v.text in self.index:
            self.report(
                'not-a-value',
                f'`${v.text}` is a {self.kinds[v.text] or "module"} entry, not a value',
                v.span,
                'a body reads `input`, its earlier locals, and integers',
                **at,
            )
        else:
            close = difflib.get_close_matches(v.text, list(bound), n=1)
            hint = f'did you mean `${close[0]}`?' if close else OPERAND_HINT
            used.update(close)  # the local the typo most likely means is not reported again as unused
            self.report('undeclared-word', f'nothing binds `${v.text}`', v.span, hint, **at)

    def operation_sorts(self, word: str) -> None:
        """Every operation in a body works in the function's sort: the sort of the entry its `takes` names."""
        fields = self.fields[word]
        if 'takes' not in fields or 'body' not in fields:
            return
        takes = fields['takes'].value
        if (
            not isinstance(takes, Value)
            or self.kinds.get(takes.text) != 'sort'
            or 'sort' not in self.fields[takes.text]
        ):
            return  # a wrong `takes` is reported on its own
        sort = self.fields[takes.text]['sort'].value
        if not isinstance(sort, Value) or sort.text not in SORTS:
            return
        b = fields['body'].value
        while isinstance(b, Let):
            first = b.operation.operands[0]
            if first.kind == Tok.NAME and first.text in SORTS and first.text != sort.text:
                self.report(
                    'bad-value',
                    f'`{first.text}` is not the sort of `${word}`',
                    first.span,
                    f'`${word}` takes `${takes.text}`, whose sort is `{sort.text}`; write `{sort.text}`',
                    entry=word,
                    key='body',
                )
            b = b.rest

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

    def description(self, owner: str, owner_index: int, v: Value | Let) -> None:
        """Check the `$` references inside a description (design/step-2.md)."""
        if not isinstance(v, Value) or v.kind != Tok.STRING:
            return
        at: Where = {'entry': owner, 'key': 'description'}
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
                if r.word in self.locals:
                    owners = ', '.join(f'`${w}`' for w in self.locals[r.word])
                    hint = f'`${r.word}` is a local in the body of {owners}; a description refers only to entries'
                else:
                    hint = self.suggest(r.word, owner, owner_index)
                self.report('undeclared-word', f'no entry declares `${r.word}`', r.span, hint, **at)
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

    def reference(self, owner: str, owner_index: int, key: str, v: Value | Let) -> None:
        if not isinstance(v, Value) or v.kind != Tok.WORD:
            return
        at: Where = {'entry': owner, 'key': key}
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
        def text(word: str, key: str) -> str:
            v = self.fields[word][key].value
            if not isinstance(v, Value):
                msg = f'`{key}` of `${word}` is not a single value in a checked program'
                raise TypeError(msg)
            return v.text

        sorts = {w: text(w, 'sort') for w, k in self.kinds.items() if k == 'sort'}
        functions = []
        for w, k in self.kinds.items():
            if k == 'function':
                takes, returns = text(w, 'takes'), text(w, 'returns')
                functions.append(Function(w, takes, returns, sorts[takes], self.fields[w]['body'].value))
        return Program(sorts, tuple(functions))


def check(module: Module) -> tuple[Program | None, list[Diagnostic]]:
    checker = _Checker(module)
    program = checker.run()
    return program, checker.diags
