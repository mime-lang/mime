"""Check a parsed module (design/step-4.md section 3, step-2.md for references). Reports every error it finds."""

import difflib
from dataclasses import dataclass
from typing import TypedDict

from mime.diag import Diagnostic
from mime.lexer import Span, Tok
from mime.parser import Definition, Entry, Field, Module, Struct, Value
from mime.words import KEYS, LANGUAGE_WORDS, OPERATIONS, RETIRED, TYPES

LATER_TYPES = frozenset({'i1', 'i8', 'i16', 'i32'})
LATER_OPERATIONS = frozenset({'sdiv', 'udiv', 'srem', 'urem', 'icmp', 'call', 'br', 'get'})
I64_MIN, I64_MAX = -(2**63), 2**63 - 1
OPERAND_HINT = 'an operand is an input of the function, a local bound earlier in this block, or an integer'
OPERATIONS_HINT = 'the operations are `add`, `sub` and `mul`'


@dataclass(frozen=True)
class Function:
    word: str
    inputs: tuple[str, ...]
    output: str
    definition: Definition


@dataclass(frozen=True)
class Program:
    types: dict[str, str]  # data word -> its type
    functions: tuple[Function, ...]


class Where(TypedDict):
    """Where a mistake is, as `report` takes it: the word with no `@`, and the key."""

    entry: str
    key: str | None


def _keys(names: tuple[str, ...]) -> str:
    return ', '.join(f'`{n}`' for n in names)


def _value_text(v: Value) -> str:
    return f'@{v.text}' if v.kind == Tok.WORD else v.text


class _Checker:
    def __init__(self, module: Module) -> None:
        self.source = module.source
        self.items = module.items
        self.diags: list[Diagnostic] = []
        self.index: dict[str, int] = {}  # word -> position of its first entry or definition, in source order
        self.kinds: dict[str, str] = {}  # word -> 'data' or 'function'
        self.fields: dict[str, dict[str, Field]] = {}  # data word -> valid key -> first field with it
        self.locals: dict[str, list[str]] = {}  # result word -> the functions whose bodies bind it

    def report(self, kind: str, message: str, at: Span, hint: str | None = None, *, entry: str, key: str | None = None,
               missing: bool = False) -> None:  # fmt: skip
        """Report a mistake at `at`, in the entry for `entry` and the field `key`. Something `missing` has no text."""
        text = None if missing else self.source[at.start : at.end]
        self.diags.append(Diagnostic(kind, message, at.line, at.column, hint, f'@{entry}', key, text))

    def run(self) -> Program | None:
        # Index every word first, so a reference can tell a later word from a missing one.
        words = [
            (x.word, x.span, 'data') if isinstance(x, Entry) else (x.word.text, x.word.span, 'function')
            for x in self.items
        ]
        for i, (word, span, kind) in enumerate(words):
            if word in self.index:
                self.report(
                    'duplicate-word',
                    f'`@{word}` already has an entry',
                    span,
                    'a word has one entry; merge the two or rename one',
                    entry=word,
                )
            else:
                self.index[word], self.kinds[word] = i, kind
        for d in (x for x in self.items if isinstance(x, Definition)):
            for line in d.lines:
                owners = self.locals.setdefault(line.result.text, [])
                if d.word.text not in owners:
                    owners.append(d.word.text)
        for i, x in enumerate(self.items):
            if isinstance(x, Definition):
                self.definition(x, i)
                continue
            valid = self.entry(x)
            if self.index[x.word] == i:
                self.fields[x.word] = valid
            if 'abstract' in valid:
                self.references(x.word, i, valid['abstract'].value)
        self.diags.sort(key=lambda d: (d.line, d.column))
        if self.diags:
            return None
        return self.program()

    # Declarations

    def entry(self, e: Entry) -> dict[str, Field]:
        valid: dict[str, Field] = {}
        for f in e.fields:
            if f.key in valid:
                self.report(
                    'duplicate-key',
                    f'`{f.key}` appears twice in the entry for `@{e.word}`',
                    f.span,
                    entry=e.word,
                    key=f.key,
                )
            elif f.key not in KEYS:
                hint = RETIRED.get(f.key, f'a declaration has the keys {_keys(KEYS)}')
                self.report('unknown-key', f'`{f.key}` is not a key', f.span, hint, entry=e.word, key=f.key)
            else:
                valid[f.key] = f
                self.value(e.word, f)
        missing = [k for k in KEYS if k not in valid]
        if missing and len(valid) == len(e.fields):  # an unknown key often is the missing one, already reported
            self.report(
                'missing-key',
                f'the entry for `@{e.word}` is missing {_keys(tuple(missing))}',
                e.span,
                f'a declaration has the keys {_keys(KEYS)}',
                entry=e.word,
                missing=True,
            )
        order = list(valid)
        want = [k for k in KEYS if k in valid]
        if order != want:
            first_wrong = next(valid[a] for a, b in zip(order, want, strict=True) if a != b)
            self.report(
                'key-order',
                f'the keys of `@{e.word}` are out of order',
                first_wrong.span,
                f'write them in this order: {_keys(KEYS)}',
                entry=e.word,
                key=first_wrong.key,
            )
        return valid

    def value(self, word: str, f: Field) -> None:
        v = f.value
        at: Where = {'entry': word, 'key': f.key}
        if f.key == 'abstract':
            if not isinstance(v, Value) or v.kind != Tok.STRING:
                self.report('bad-value', '`abstract` takes a string', v.span, 'write the meaning in `"…"`', **at)
            elif not v.text.strip():
                self.report('bad-value', 'an abstract cannot be empty', v.span, 'say what the word means', **at)
            return
        if isinstance(v, Struct):
            self.report('bad-value', 'struct types arrive with structs', v.span, 'the only type is `i64`', **at)
        elif v.kind == Tok.NAME and v.text in TYPES:
            return
        elif v.kind == Tok.NAME and v.text in LATER_TYPES:
            self.report('bad-value', f'`{v.text}` arrives in a later step', v.span, 'the only type is `i64`', **at)
        elif v.kind == Tok.WORD:
            self.report('bad-value', f'`@{v.text}` is not a type', v.span, 'a type is a primitive such as `i64`', **at)
        else:
            self.report('bad-value', f'`{_value_text(v)}` is not a type', v.span, 'the only type is `i64`', **at)

    # Definitions

    def definition(self, d: Definition, position: int) -> None:
        word = d.word.text
        head: Where = {'entry': word, 'key': 'type'}
        inputs: dict[str, Value] = {}
        rejected: set[str] = set()  # inputs already reported; the body reading one is not reported again
        for x in d.inputs:
            if x.text in inputs:
                self.report('duplicate-word', f'`@{x.text}` is listed twice', x.span, 'list each input once', **head)
            elif self.data_word(x, word, position, head, 'an input'):
                inputs[x.text] = x
            else:
                # The input is already reported, so the body reading the same word is not reported again. This follows
                # the word, not its spelling's closeness to another, so a renaming cannot change it (step-5.md).
                rejected.add(x.text)
        if d.output.kind == Tok.WORD:
            self.data_word(d.output, word, position, head, 'the output')
        elif d.output.text in LATER_TYPES:
            self.report(
                'bad-value',
                f'`{d.output.text}` arrives in a later step',
                d.output.span,
                'the only type is `i64`',
                **head,
            )
        elif d.output.text not in TYPES:
            kind = 'bad-value' if d.output.text in LANGUAGE_WORDS else 'unknown-language-word'
            self.report(
                kind, f'`{d.output.text}` is not a type', d.output.span, 'the output is a word or `i64`', **head
            )
        self.body(d, inputs, rejected)
        self.references(word, position, d.abstract)

    def data_word(self, v: Value, owner: str, position: int, at: Where, role: str) -> bool:
        """Check that `v` names an earlier data word; true when the body may read it as an input.

        A data word declared later is reported, and the body may still read it, so the move is the only fix needed.
        """
        if v.text not in self.index:
            hint = self.suggest(v.text, owner, position)
            if hint is None:
                hint = f'declare it above `@{owner}`: `@{v.text} = {{type = i64, abstract = "…"}}`'
            self.report('undeclared-word', f'no entry declares `@{v.text}`', v.span, hint, **at)
            return False
        if self.kinds[v.text] != 'data':
            self.report(
                'bad-value',
                f'`@{v.text}` is a function, so it cannot be {role}',
                v.span,
                f'{role} is a data word, declared with `{{type = …, abstract = "…"}}`',
                **at,
            )
            return False
        if self.index[v.text] > position:
            self.report(
                'forward-reference',
                f'`@{v.text}` is declared after `@{owner}`',
                v.span,
                f'move the entry for `@{v.text}` above `@{owner}`',
                **at,
            )
            return True
        return True

    def body(self, d: Definition, inputs: dict[str, Value], rejected: set[str]) -> None:
        """Check the lines of a body (design/step-4.md, step-6.md): operations, operands, locals, and every read."""
        at: Where = {'entry': d.word.text, 'key': 'body'}
        every = {line.result.text for line in d.lines}  # every local this body binds
        bound: dict[str, Value] = {}  # local -> where it is bound
        used: set[str] = set()  # inputs and locals read, by kind and name: '@number', '%double'
        for line in d.lines:
            self.operation(line.operation, line.type, at)
            for v in (line.left, line.right):
                self.atom(v, line.result.text, inputs, rejected, bound, every, used, at)
            r = line.result
            if r.text in bound:
                self.report(
                    'duplicate-word',
                    f'`%{r.text}` is already bound in this block',
                    r.span,
                    'pick a new local for the result',
                    **at,
                )
            else:
                bound[r.text] = r
        self.atom(d.ret, None, inputs, rejected, bound, every, used, at)
        for local, v in bound.items():
            if f'%{local}' not in used:
                self.report(
                    'unused-local',
                    f'nothing reads `%{local}`',
                    v.span,
                    'use it, or remove its line; a body often returns the wrong local',
                    **at,
                )
        for word, v in inputs.items():
            if f'@{word}' not in used:
                self.report(
                    'unused-local',
                    f'nothing reads the input `@{word}`',
                    v.span,
                    f'remove `@{word}` from the type, or use it',
                    entry=d.word.text,
                    key='type',
                )

    def operation(self, op: Value, ty: Value, at: Where) -> None:
        name = op.text
        if name not in OPERATIONS:
            if name in LATER_OPERATIONS:
                self.report('bad-value', f'`{name}` arrives in a later step', op.span, OPERATIONS_HINT, **at)
            elif name in LANGUAGE_WORDS:
                self.report('bad-value', f'`{name}` is not an operation', op.span, OPERATIONS_HINT, **at)
            else:
                self.report('unknown-language-word', f'`{name}` is not a language word', op.span, OPERATIONS_HINT, **at)
        if ty.text not in TYPES:
            hint = f'`{ty.text}` arrives in a later step; ' if ty.text in LATER_TYPES else ''
            self.report('bad-value', f'`{ty.text}` is not a type', ty.span, hint + 'the only type is `i64`', **at)

    def atom(
        self,
        v: Value,
        result: str | None,
        inputs: dict[str, Value],
        rejected: set[str],
        bound: dict[str, Value],
        every: set[str],
        used: set[str],
        at: Where,
    ) -> None:
        """Check an operand or the returned value. `result` is the local the enclosing line binds."""
        if v.kind == Tok.INT:
            if not I64_MIN <= int(v.text) <= I64_MAX:
                self.report(
                    'bad-value', f'`{v.text}` does not fit in `i64`', v.span, 'an `i64` is from -2^63 to 2^63-1', **at
                )
            return
        if v.kind == Tok.WORD:
            self.word_operand(v, inputs, rejected, used, at)
            return
        if v.text in bound:
            used.add(f'%{v.text}')
        elif v.text == result:
            used.add(f'%{v.text}')  # reported here, not again as unused
            self.report(
                'forward-reference',
                f'`%{v.text}` is bound by this line, so its own operation cannot read it',
                v.span,
                OPERAND_HINT,
                **at,
            )
        elif v.text in every:
            used.add(f'%{v.text}')
            self.report(
                'forward-reference',
                f'`%{v.text}` is bound later in this block',
                v.span,
                f'move the line for `%{v.text}` above this one',
                **at,
            )
        elif v.text in inputs:
            # Only the hint uses the shared spelling. The input stays unread, so what is reported does not depend on
            # how a local and a word happen to be spelled (design/step-5.md section 1).
            self.report(
                'undeclared-word',
                f'nothing binds `%{v.text}`',
                v.span,
                f'an input is its word: write `@{v.text}`',
                **at,
            )
        else:
            close = difflib.get_close_matches(v.text, list(bound), n=1)
            hint = f'did you mean `%{close[0]}`?' if close else OPERAND_HINT
            self.report('undeclared-word', f'nothing binds `%{v.text}`', v.span, hint, **at)

    def word_operand(self, v: Value, inputs: dict[str, Value], rejected: set[str], used: set[str], at: Where) -> None:
        """A `@word` in a body: one of the function's inputs."""
        if v.text in inputs:
            used.add(f'@{v.text}')
        elif v.text in rejected:
            return  # a rejected input, or the word it most likely means; the input is already reported
        elif v.text in self.index:
            kind = 'function' if self.kinds[v.text] == 'function' else 'data word'
            self.report(
                'not-a-value',
                f'`@{v.text}` is a {kind} that is not an input of this function',
                v.span,
                'a body reads its inputs, its earlier locals, and integers; to read it, list it in the inputs',
                **at,
            )
        else:
            close = difflib.get_close_matches(v.text, list(inputs), n=1)
            hint = f'did you mean `@{close[0]}`?' if close else OPERAND_HINT
            self.report('undeclared-word', f'no entry declares `@{v.text}`', v.span, hint, **at)

    # References in abstracts

    def suggest(self, typo: str, owner: str, owner_index: int) -> str | None:
        """A close word the reference could mean, preferring words it may already refer to."""
        earlier = [w for w, i in self.index.items() if i < owner_index]
        close = difflib.get_close_matches(typo, earlier, n=1)
        if close:
            return f'did you mean `@{close[0]}`?'
        later = [w for w, i in self.index.items() if i > owner_index]
        close = difflib.get_close_matches(typo, later, n=1)
        if close:
            return f'did you mean `@{close[0]}`? It is declared later, so also move its entry above `@{owner}`'
        return None

    def references(self, owner: str, owner_index: int, v: Value | Struct) -> None:
        """Check the `@` references inside an abstract (design/step-2.md)."""
        if not isinstance(v, Value) or v.kind != Tok.STRING:
            return
        at: Where = {'entry': owner, 'key': 'abstract'}
        for r in v.refs:
            if r.word is None:
                self.report(
                    'bad-reference',
                    '`@` in an abstract must start a reference to a word',
                    r.span,
                    'write `\\@` for an at sign',
                    **at,
                )
            elif r.stray is not None:
                self.report(
                    'bad-reference',
                    f'`@{r.word}` is followed by `{r.stray}`, which cannot appear in a name',
                    r.span,
                    'a name is lowercase letters, digits or `_`; put a space or punctuation other than `-` after it',
                    **at,
                )
            elif r.word not in self.index:
                if r.word in self.locals:
                    owners = ', '.join(f'`@{w}`' for w in self.locals[r.word])
                    hint = f'`%{r.word}` is a local in the body of {owners}; an abstract refers only to entries'
                elif r.span.start > 0 and self.source[r.span.start - 1].isalnum():
                    hint = 'write `\\@` for an at sign, as in an address'
                else:
                    hint = self.suggest(r.word, owner, owner_index)
                self.report('undeclared-word', f'no entry declares `@{r.word}`', r.span, hint, **at)
            elif r.word == owner and self.index[owner] == owner_index:
                self.report(
                    'forward-reference',
                    f'the abstract of `@{owner}` refers to `@{owner}` itself',
                    r.span,
                    f'an abstract may refer only to earlier entries; describe `@{owner}` by its parts',
                    **at,
                )
            elif self.index[r.word] > owner_index:
                self.report(
                    'forward-reference',
                    f'`@{r.word}` is declared after `@{owner}`',
                    r.span,
                    f'an abstract may refer only to earlier entries; move the entry for `@{r.word}` above `@{owner}`',
                    **at,
                )

    def program(self) -> Program:
        types = {}
        for w, fields in self.fields.items():
            v = fields['type'].value
            if not isinstance(v, Value):
                msg = f'the type of `@{w}` is not a primitive in a checked program'
                raise TypeError(msg)
            types[w] = v.text
        functions = tuple(
            Function(d.word.text, tuple(x.text for x in d.inputs), d.output.text, d)
            for d in self.items
            if isinstance(d, Definition)
        )
        return Program(types, functions)


def check(module: Module) -> tuple[Program | None, list[Diagnostic]]:
    checker = _Checker(module)
    program = checker.run()
    return program, checker.diags
