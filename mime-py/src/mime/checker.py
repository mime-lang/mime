"""Check a parsed module (design/step-4.md section 3, step-2.md for references). Reports every error it finds."""

import difflib
import re
from dataclasses import dataclass
from typing import TypedDict

from mime.diag import Diagnostic
from mime.lexer import Span, Tok
from mime.parser import (
    Block,
    Call,
    Declaration,
    Definition,
    Entry,
    Field,
    Item,
    Line,
    Module,
    Struct,
    Value,
    item_refs,
    item_word,
)
from mime.words import (
    FALSE,
    ICMP,
    KEYS,
    LANGUAGE_WORDS,
    LOGIC,
    OPERATION_HABITS,
    OPERATIONS,
    PREDICATES,
    RETIRED,
    TRUE,
    TYPES,
)

LATER_TYPES = frozenset({'i8', 'i16', 'i32'})
SYMBOL = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
LATER_OPERATIONS = frozenset({'get'})
I64_MIN, I64_MAX = -(2**63), 2**63 - 1
OPERAND_HINT = (
    'an operand is an input of the function, a local bound earlier in this block, an integer, or true or false'
)
OPERATIONS_HINT = (
    'the operations are `add`, `sub`, `mul`, `sdiv`, `udiv`, `srem`, `urem` and `icmp` on `i64`, '
    'and `and`, `or`, `xor` on `i1`'
)


def operand_type(operation: str) -> str:
    """The type an operation takes (design/step-13.md section 1): `i1` for `and`, `or`, `xor`, else `i64`."""
    return 'i1' if operation in LOGIC else 'i64'


def result_type(line: Line) -> str | None:
    """The type of a line's result, or None when its operation or the type after it is wrong: that line is already
    reported, and what it meant to give is unknown, so nothing that reads its result is reported for it."""
    op = line.operation.text
    if op not in OPERATIONS and op != ICMP:
        return None
    if line.type.text != operand_type(op):
        return None
    return 'i1' if op == ICMP or op in LOGIC else 'i64'


@dataclass(frozen=True)
class Function:
    word: str
    inputs: tuple[str, ...]
    output: str
    definition: Definition
    input_types: dict[str, str]  # input word -> `i64` or `i1`
    output_type: str
    local_types: dict[tuple[int, str], str]  # (block index, local) -> `i64` or `i1`
    symbol: str | None  # the name it is exported under, or None when it is internal to its module


@dataclass(frozen=True)
class Program:
    types: dict[str, str]  # data word -> its type
    functions: tuple[Function, ...]
    module: Module  # what the program was checked from, for backends that need its canonical names


@dataclass(frozen=True)
class Signature:
    """A function's type, from its `define` or its `declare`: what a call is checked against (step-9.md section 3)."""

    inputs: tuple[str, ...]
    input_types: dict[str, str]  # input word -> `i64` or `i1`, for the inputs that have one
    output_type: str | None
    rejected: frozenset[str] = frozenset()  # inputs of the head already reported; a call naming one is not reported


def _head(x: Definition | Declaration) -> str:
    inputs = ', '.join(f'@{v.text}' for v in x.inputs)
    output = f'@{x.output.text}' if x.output.kind == Tok.WORD else x.output.text
    return f'{{{inputs}}} -> {output}'


class Where(TypedDict):
    """Where a mistake is, as `report` takes it: the word with no `@`, and the key."""

    entry: str
    key: str | None


def _keys(names: tuple[str, ...]) -> str:
    return ', '.join(f'`{n}`' for n in names)


def _value_text(v: Value) -> str:
    sigil = {Tok.WORD: '@', Tok.LOCAL: '%', Tok.LABEL: '^'}.get(v.kind, '')
    return sigil + v.text


class _Checker:
    def __init__(self, module: Module) -> None:
        self.source = module.source
        self.items = module.items
        self.diags: list[Diagnostic] = []
        self.index: dict[str, int] = {}  # word -> position of its first entry or definition, in source order
        self.kinds: dict[str, str] = {}  # word -> 'data' or 'function'
        self.fields: dict[str, dict[str, Field]] = {}  # data word -> valid key -> first field with it
        self.locals: dict[str, list[str]] = {}  # result word -> the functions whose bodies bind it
        self.module = module
        self.symbols: dict[str, str] = {}  # symbol -> the function exported under it
        self.local_types: dict[str, dict[tuple[int, str], str]] = {}  # function -> (block, local) -> type
        self.signatures: dict[str, Signature] = {}  # function -> its type, once its head is checked
        self.declared: dict[str, int] = {}  # function -> position of its `declare`
        self.defined: dict[str, int] = {}  # function -> position of its `define`

    def report(self, kind: str, message: str, at: Span, hint: str | None = None, *, entry: str, key: str | None = None,
               missing: bool = False) -> None:  # fmt: skip
        """Report a mistake at `at`, in the entry for `entry` and the field `key`. Something `missing` has no text."""
        text = None if missing else self.source[at.start : at.end]
        self.diags.append(Diagnostic(kind, message, at.line, at.column, hint, f'@{entry}', key, text))

    def run(self) -> Program | None:
        # Index every word first, so a reference can tell a later word from a missing one. A function's word is
        # indexed at its `declare` when it has one, so everything below the declaration may use it.
        for i, x in enumerate(self.items):
            word = item_word(x)
            span = x.span if isinstance(x, Entry) else x.word.span
            if isinstance(x, Definition) and word in self.declared and word not in self.defined:
                self.defined[word] = i
            elif word in self.index:
                hint = 'a word has one entry; merge the two or rename one'
                if isinstance(x, Declaration) and word in self.defined:
                    hint = (
                        f'a declaration comes above the `define` of `@{word}`, and only when a call above it needs it'
                    )
                self.report('duplicate-word', f'`@{word}` already has an entry', span, hint, entry=word)
            else:
                self.index[word] = i
                self.kinds[word] = 'data' if isinstance(x, Entry) else 'function'
                if isinstance(x, Declaration):
                    self.declared[word] = i
                elif isinstance(x, Definition):
                    self.defined[word] = i
        for d in (x for x in self.items if isinstance(x, Definition)):
            for b in d.blocks:
                for v in (*b.params, *(line.result for line in b.lines)):
                    owners = self.locals.setdefault(v.text, [])
                    if d.word.text not in owners:
                        owners.append(d.word.text)
        for i, x in enumerate(self.items):
            if isinstance(x, Definition):
                self.definition(x, i)
                continue
            if isinstance(x, Declaration):
                self.declaration(x, i)
                continue
            valid = self.entry(x)
            if self.index[x.word] == i:
                self.fields[x.word] = valid
            if 'abstract' in valid:
                self.references(x.word, i, valid['abstract'].value)
        self.declarations()
        self.unused_words()
        self.diags.sort(key=lambda d: (d.line, d.column))
        if self.diags:
            return None
        return self.program()

    def unused_words(self) -> None:
        """A data word nothing refers to has no first user, so canon could not place it (design/step-11.md)."""
        used = {w for x in self.items for w in item_refs(x)}
        for i, x in enumerate(self.items):
            if isinstance(x, Entry) and x.word not in used and self.index.get(x.word) == i:
                self.report(
                    'unused-word',
                    f'nothing refers to `@{x.word}`',
                    x.span,
                    'use it in a type, a body or an abstract, or remove it',
                    entry=x.word,
                )

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
            self.report('bad-value', 'struct types arrive with structs', v.span, 'the types are `i64` and `i1`', **at)
        elif v.kind == Tok.NAME and v.text in TYPES:
            return
        elif v.kind == Tok.NAME and v.text in LATER_TYPES:
            self.report(
                'bad-value', f'`{v.text}` arrives in a later step', v.span, 'the types are `i64` and `i1`', **at
            )
        elif v.kind == Tok.WORD:
            self.report('bad-value', f'`@{v.text}` is not a type', v.span, 'a type is a primitive such as `i64`', **at)
        else:
            self.report('bad-value', f'`{_value_text(v)}` is not a type', v.span, 'the types are `i64` and `i1`', **at)

    # Definitions

    def declaration(self, d: Declaration, position: int) -> None:
        if self.declared.get(d.word.text) != position:
            return  # a duplicate, already reported
        self.head(d, position)

    def declarations(self) -> None:
        """Each `declare` has one `define` below it with the same type, and something between the two calls it."""
        for word, position in self.declared.items():
            d = self.items[position]
            if not isinstance(d, Declaration):
                continue
            at: Where = {'entry': word, 'key': 'type'}
            if word not in self.defined and any(item_word(x) == word for x in self.items[position + 1 :]):
                continue  # a later entry for the word, not a `define`, is already a duplicate-word
            if word not in self.defined:
                self.report(
                    'missing-definition',
                    f'`@{word}` is declared, but no `define` below defines it',
                    d.word.span,
                    f'write `define @{word} {_head(d)} {{…}}` below, or drop the declaration',
                    **at,
                )
                continue
            later = self.defined[word]
            x = self.items[later]
            if isinstance(x, Definition) and _head(x) != _head(d):
                self.report(
                    'wrong-type',
                    f'the type of `@{word}` differs from its declaration',
                    x.word.span,
                    f'`@{word}` is declared above as `{_head(d)}`',
                    **at,
                )
            if not any(self.mentions(self.items[i], word) for i in range(position + 1, later)):
                self.report(
                    'redundant-declaration',
                    f'nothing calls `@{word}` before its `define`',
                    d.word.span,
                    f'drop it: `@{word}` is defined before anything calls it',
                    **at,
                )

    @staticmethod
    def mentions(x: Item, word: str) -> bool:
        """Whether an entry calls `word` in its body or refers to it in its abstract."""
        if isinstance(x, Declaration):
            return False
        if isinstance(x, Definition):
            called = any(isinstance(line, Call) and line.callee.text == word for b in x.blocks for line in b.lines)
            return called or any(r.word == word for r in x.abstract.refs)
        abstract = next((f.value for f in x.fields if f.key == 'abstract'), None)
        return isinstance(abstract, Value) and any(r.word == word for r in abstract.refs)

    def head(self, d: Definition | Declaration, position: int) -> tuple[dict[str, Value], set[str], Signature]:
        """Check a function's inputs and output, and record its type for the calls that name it."""
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
                'the types are `i64` and `i1`',
                **head,
            )
        elif d.output.text not in TYPES:
            kind = 'bad-value' if d.output.text in LANGUAGE_WORDS else 'unknown-language-word'
            self.report(
                kind, f'`{d.output.text}` is not a type', d.output.span, 'the output is a word, `i64` or `i1`', **head
            )
        input_types = {w: t for w, v in inputs.items() if (t := self.word_type(w)) is not None}
        output_type = self.word_type(d.output.text) if d.output.kind == Tok.WORD else d.output.text
        signature = Signature(
            tuple(inputs), input_types, output_type if output_type in TYPES else None, frozenset(rejected)
        )
        if word not in self.signatures:  # a declaration's type stands; a define that differs is reported
            self.signatures[word] = signature
        return inputs, rejected, signature

    def definition(self, d: Definition, position: int) -> None:
        word = d.word.text
        inputs, rejected, signature = self.head(d, position)
        _Body(self, d, position, inputs, signature, rejected).check()
        if d.symbol is not None:
            self.symbol(d)
        self.references(word, position, d.abstract)
        self.mentions_inputs(d, inputs)

    def mentions_inputs(self, d: Definition, inputs: dict[str, Value]) -> None:
        """A function's abstract names every input with `@`, since it states the result in their terms (layout.md 4.1)."""
        if d.abstract.kind != Tok.STRING:
            return
        named = {r.word for r in d.abstract.refs if r.word is not None and r.stray is None}
        for w in inputs:
            if w not in named:
                self.report(
                    'unmentioned-input',
                    f'the abstract of `@{d.word.text}` does not name its input `@{w}`',
                    d.abstract.span,
                    f'say what the result is in terms of `@{w}`, and write it as `@{w}`',
                    entry=d.word.text,
                    key='abstract',
                )

    def symbol(self, d: Definition) -> None:
        """`symbol = "clamp"`: a C identifier, unique in the module, and not `main`, which `mime run` defines."""
        v = d.symbol
        if v is None:
            return
        at: Where = {'entry': d.word.text, 'key': 'symbol'}
        if not SYMBOL.fullmatch(v.text):
            self.report(
                'bad-value',
                f'`{v.text}` is not a symbol',
                v.span,
                'a symbol is a C name: a letter or `_`, then letters, digits or `_`',
                **at,
            )
        elif v.text == 'main':
            self.report(
                'bad-value', '`main` is taken by the program `mime run` builds', v.span, 'pick another symbol', **at
            )
        elif v.text in self.symbols:
            self.report(
                'duplicate-word',
                f'`{v.text}` is already the symbol of `@{self.symbols[v.text]}`',
                v.span,
                'each exported function needs its own symbol',
                **at,
            )
        else:
            self.symbols[v.text] = d.word.text

    def word_type(self, word: str) -> str | None:
        """The type of a data word (`i64` or `i1`), or None when it has no valid one."""
        f = self.fields.get(word, {}).get('type')
        if f is None or not isinstance(f.value, Value) or f.value.kind != Tok.NAME or f.value.text not in TYPES:
            return None
        return f.value.text

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
            elif r.word == owner and owner_index in (self.index[owner], self.defined.get(owner)):
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
        functions = []
        for d in self.items:
            if isinstance(d, Definition):
                inputs = tuple(x.text for x in d.inputs)
                output = types[d.output.text] if d.output.kind == Tok.WORD else d.output.text
                local_types = self.local_types[d.word.text]
                symbol = d.symbol.text if d.symbol is not None else None
                input_types = {w: types[w] for w in inputs}
                functions.append(
                    Function(d.word.text, inputs, d.output.text, d, input_types, output, local_types, symbol)
                )
        return Program(types, tuple(functions), self.module)


class _Body:
    """Check one function body (design/step-4.md, step-7.md): blocks, jumps, locals, operations and types."""

    def __init__(
        self,
        checker: '_Checker',
        d: Definition,
        position: int,
        inputs: dict[str, Value],
        signature: Signature,
        rejected: set[str],
    ) -> None:
        self.c = checker
        self.d = d
        self.position = position
        self.inputs = inputs
        self.signature = signature
        self.input_types = signature.input_types
        self.output_type = signature.output_type
        self.callees: dict[int, Signature | None] = {}  # id of a call line -> its callee's type, resolved once
        self.rejected = rejected
        self.at: Where = {'entry': d.word.text, 'key': 'body'}
        self.labels: dict[str, int] = {}  # label -> index of its first block
        self.types: dict[tuple[int, str], str] = {}  # (block, local) -> type, params and results
        self.used_inputs: set[str] = set()
        self.miscounted: set[int] = set()  # blocks some jump passes the wrong number of arguments; reported once

    def report(self, kind: str, message: str, at: Span, hint: str | None = None) -> None:
        self.c.report(kind, message, at, hint, **self.at)

    def check(self) -> None:
        for i, b in enumerate(self.d.blocks):
            if b.label is None:
                continue
            if b.label.text in self.labels:
                self.report(
                    'duplicate-word', f'`^{b.label.text}` already labels a block', b.label.span, 'pick a new label'
                )
            else:
                self.labels[b.label.text] = i
        self.jumps()
        self.carried()
        self.reachable()
        self.reducible()
        self.infer_params()
        for i, b in enumerate(self.d.blocks):
            self.block(i, b)
        self.c.local_types[self.d.word.text] = self.types
        for word, v in self.inputs.items():
            if word not in self.used_inputs:
                self.c.report(
                    'unused-local',
                    f'nothing reads the input `@{word}`',
                    v.span,
                    f'remove `@{word}` from the type, or use it',
                    entry=self.d.word.text,
                    key='type',
                )

    def jumps(self) -> None:
        """Every jump names a block and passes as many arguments as it has parameters."""
        for b in self.d.blocks:
            for t in b.end.targets:
                if t.label.text not in self.labels:
                    close = difflib.get_close_matches(t.label.text, list(self.labels), n=1)
                    hint = f'did you mean `^{close[0]}`?' if close else 'every `br` jumps to a block of this body'
                    self.report('undeclared-word', f'no block is labelled `^{t.label.text}`', t.label.span, hint)
                    continue
                params = self.d.blocks[self.labels[t.label.text]].params
                if len(t.args) != len(params):
                    self.miscounted.add(self.labels[t.label.text])
                    names = ', '.join(f'%{p.text}' for p in params)
                    self.report(
                        'bad-value',
                        f'`^{t.label.text}` takes {len(params)} arguments, not {len(t.args)}',
                        t.label.span,
                        f'write `^{t.label.text}{{{names}}}` with a value for each parameter',
                    )

    def carried(self) -> None:
        """A parameter that only ever receives one input or one constant, besides itself, is a second way to read it.

        Every block reads the function's inputs and may write any constant, so the parameter is not needed
        (design/step-7.md section 3). This follows the values passed, not how anything is spelled.
        """
        incoming: dict[tuple[int, int], set[tuple[str, str] | None]] = {}
        for i, b in enumerate(self.d.blocks):
            for t in b.end.targets:
                j = self.labels.get(t.label.text)
                if j is None or len(t.args) != len(self.d.blocks[j].params):
                    continue
                for k, (arg, p) in enumerate(zip(t.args, self.d.blocks[j].params, strict=True)):
                    if arg.kind == Tok.LOCAL and i == j and arg.text == p.text:
                        continue  # the parameter passed to itself, on a loop's back edge
                    key = ('@', arg.text) if arg.kind == Tok.WORD and arg.text in self.inputs else None
                    if arg.kind in (Tok.INT, Tok.NAME):
                        key = ('', arg.text)
                    incoming.setdefault((j, k), set()).add(key)
        for (j, k), keys in incoming.items():
            if len(keys) == 1 and (key := next(iter(keys))) is not None:
                p = self.d.blocks[j].params[k]
                what = f'the input `@{key[1]}`, which every block reads' if key[0] == '@' else f'`{key[1]}`'
                use = f'`@{key[1]}`' if key[0] == '@' else f'`{key[1]}`'
                self.report(
                    'redundant-parameter',
                    f'`%{p.text}` only ever carries {what}',
                    p.span,
                    f'drop the parameter and its arguments, and write {use} where it is read',
                )

    def reachable(self) -> None:
        seen, todo = {0}, [0]
        while todo:
            for t in self.d.blocks[todo.pop()].end.targets:
                i = self.labels.get(t.label.text)
                if i is not None and i not in seen:
                    seen.add(i)
                    todo.append(i)
        for i, b in enumerate(self.d.blocks):
            if i not in seen and b.label is not None and self.labels.get(b.label.text) == i:
                self.report(
                    'unreachable-block',
                    f'no `br` reaches `^{b.label.text}`',
                    b.label.span,
                    'jump to it from a block that runs, or remove it',
                )

    def successors(self, i: int) -> list[tuple[int, Span]]:
        """The blocks block `i` jumps to, in the order its `br` names them, with the span of each target label."""
        out = []
        for t in self.d.blocks[i].end.targets:
            j = self.labels.get(t.label.text)
            if j is not None:
                out.append((j, t.label.span))
        return out

    def reducible(self) -> None:
        """Every cycle has one way in, its header, which dominates the jump that closes it (design/step-10.md)."""
        succ = {0: self.successors(0)}
        order, todo = [0], [0]
        while todo:
            for j, _ in succ[todo.pop()]:
                if j not in succ:
                    succ[j] = self.successors(j)
                    order.append(j)
                    todo.append(j)
        preds: dict[int, list[int]] = {i: [] for i in order}
        for i in order:
            for j, _ in succ[i]:
                preds[j].append(i)
        every = set(order)
        dom = {i: ({0} if i == 0 else set(every)) for i in order}
        changed = True
        while changed:
            changed = False
            for i in order[1:]:
                new = set.intersection(*(dom[p] for p in preds[i])) | {i}
                if new != dom[i]:
                    dom[i], changed = new, True
        reported: set[int] = set()
        on_path, done = {0}, {0}
        stack = [(0, iter(succ[0]))]
        while stack:
            i, it = stack[-1]
            step = next(it, None)
            if step is None:
                stack.pop()
                on_path.discard(i)
                continue
            j, span = step
            if j in on_path:
                if j not in dom[i] and j not in reported:
                    reported.add(j)
                    label = self.d.blocks[j].label
                    name = f'^{label.text}' if label is not None else 'the entry block'
                    self.report(
                        'irreducible-loop',
                        f'the loop through `{name}` can also be entered without passing `{name}`',
                        span,
                        'give the loop one entry: every jump into it, from outside or from inside, goes to one block, '
                        'which takes a parameter saying where to go and branches on it',
                    )
            elif j not in done:
                done.add(j)
                on_path.add(j)
                stack.append((j, iter(succ[j])))

    def infer_params(self) -> None:
        """Give each block parameter the type of the arguments jumps pass to it (design/step-7.md section 4)."""
        for i, b in enumerate(self.d.blocks):
            for line in b.lines:
                if isinstance(line, Call):
                    sig = self.callees[id(line)] = self.callee(line.callee)
                    if sig is not None and sig.output_type is not None:
                        self.types[(i, line.result.text)] = sig.output_type
                elif (t := result_type(line)) is not None:
                    self.types[(i, line.result.text)] = t
        changed = True
        while changed:
            changed = False
            for i, b in enumerate(self.d.blocks):
                for t in b.end.targets:
                    j = self.labels.get(t.label.text)
                    if j is None or len(t.args) != len(self.d.blocks[j].params):
                        continue
                    for arg, p in zip(t.args, self.d.blocks[j].params, strict=True):
                        known = self.value_type(i, arg)
                        if known is not None and (j, p.text) not in self.types:
                            self.types[(j, p.text)] = known
                            changed = True

    def value_type(self, block: int, v: Value) -> str | None:
        if v.kind == Tok.INT:
            return 'i64'
        if v.kind == Tok.NAME:
            return 'i1' if v.text in (TRUE, FALSE) else None
        if v.kind == Tok.WORD:
            return self.input_types.get(v.text)
        return self.types.get((block, v.text))

    def block(self, i: int, b: Block) -> None:
        bound: dict[str, Value] = {}
        used: set[str] = set()
        every = {p.text for p in b.params} | {line.result.text for line in b.lines}
        for p in b.params:
            if p.text in bound:
                self.report('duplicate-word', f'`%{p.text}` is already a parameter of this block', p.span)
            bound[p.text] = p
            if (i, p.text) not in self.types and i not in self.miscounted:
                self.report(
                    'wrong-type',
                    f'nothing gives the parameter `%{p.text}` a type',
                    p.span,
                    'pass it a value in some jump, other than itself',
                )
        for line in b.lines:
            if isinstance(line, Call):
                self.call(i, line, bound, every, used)
            else:
                # An unknown operation, or a wrong type after it, is one mistake: its operands are not judged by it.
                expected = operand_type(line.operation.text) if self.operation(line) else None
                for v in (line.left, line.right):
                    self.read(i, v, line.result.text, bound, every, used, expected, f'`{line.operation.text}`')
            if line.result.text in bound:
                self.report(
                    'duplicate-word',
                    f'`%{line.result.text}` is already bound in this block',
                    line.result.span,
                    'pick a new local for the result',
                )
            else:
                bound[line.result.text] = line.result
        end = b.end
        if end.keyword.text == 'ret' and end.value is not None:
            self.read(i, end.value, None, bound, every, used, self.output_type, '`ret`')
        elif end.value is not None:
            self.read(i, end.value, None, bound, every, used, 'i1', 'the condition of `br`')
        for t in end.targets:
            j = self.labels.get(t.label.text)
            params = self.d.blocks[j].params if j is not None else ()
            for k, arg in enumerate(t.args):
                expected = self.types.get((j, params[k].text)) if j is not None and k < len(params) else None
                self.read(i, arg, None, bound, every, used, expected, f'`^{t.label.text}`')
        for name, v in bound.items():
            if name not in used:
                self.report(
                    'unused-local',
                    f'nothing reads `%{name}`',
                    v.span,
                    'use it, or remove it; a block often returns the wrong local',
                )

    def callee(self, v: Value) -> Signature | None:
        """The type of the function a call names: an earlier one, a declared one, or this one, which is recursion.

        A call of this function is checked against its own head, even where a `declare` above says otherwise: the
        difference is reported once, on the head.
        """
        word = v.text
        c = self.c
        own = self.d.word.text
        if word == own:
            return self.signature
        if word not in c.index:
            functions = [w for w, k in c.kinds.items() if k == 'function']
            close = difflib.get_close_matches(word, functions, n=1)
            hint = f'did you mean `@{close[0]}`?' if close else 'define the function above this one'
            self.report('undeclared-word', f'no entry declares `@{word}`', v.span, hint)
            return None
        if c.kinds[word] != 'function':
            self.report(
                'bad-value',
                f'`@{word}` is a data word, so it cannot be called',
                v.span,
                f'only a function can be called; to read `@{word}`, list it in the inputs',
            )
            return None
        if c.index[word] > self.position:
            later = c.items[c.index[word]]
            if isinstance(later, Declaration):
                hint = f'move `declare @{word} {_head(later)}` above `@{own}`'
                message = f'`@{word}` is declared after `@{own}`'
            else:
                head = _head(later) if isinstance(later, Definition) else '{…} -> …'
                hint = f'declare it above `@{own}`: `declare @{word} {head}`, or move its `define` up'
                message = f'`@{word}` is defined after `@{own}`'
            self.report('forward-reference', message, v.span, hint)
            return None
        return c.signatures.get(word)

    def call(self, i: int, line: Call, bound: dict[str, Value], every: set[str], used: set[str]) -> None:
        """A call's arguments: one per input of the callee, in the callee's order (design/step-9.md section 3)."""
        sig = self.callees[id(line)]
        word = line.callee.text
        result = line.result.text
        if sig is None:
            for a in line.args:
                self.read(i, a.value, result, bound, every, used, None, f'`@{word}`')
            return
        takes = ', '.join(f'`@{w}`' for w in sig.inputs)
        given: list[str] = []
        unknown = False
        for a in line.args:
            key = a.key.text
            expected = None
            if key in sig.rejected:
                pass  # the callee's head already reports this input
            elif key not in sig.inputs:
                unknown = True
                hint = (
                    f'`@{word}` takes {takes}'
                    if sig.inputs
                    else f'`@{word}` takes no inputs: write `call @{word} {{}}`'
                )
                self.report('unknown-key', f'`@{key}` is not an input of `@{word}`', a.key.span, hint)
            elif key in given:
                self.report('duplicate-key', f'`@{key}` is given twice in this call of `@{word}`', a.key.span)
            else:
                given.append(key)
                expected = sig.input_types.get(key)
            self.read(i, a.value, result, bound, every, used, expected, f'`@{key}` of `@{word}`')
        missing = [w for w in sig.inputs if w not in given]
        if missing and not unknown:  # an unknown input is often the missing one, already reported
            fill = ', '.join(f'@{w} = …' for w in missing)
            self.report(
                'missing-key',
                f'this call of `@{word}` gives no {", ".join(f"`@{w}`" for w in missing)}',
                line.callee.span,
                f'`@{word}` takes {takes}: add `{fill}`',
            )
        want = [w for w in sig.inputs if w in given]
        if given != want:
            first = next(a for a, b in zip(given, want, strict=True) if a != b)
            span = next(a.key.span for a in line.args if a.key.text == first)
            self.report(
                'key-order',
                f'the arguments of this call of `@{word}` are out of order',
                span,
                f"write the arguments in the order of `@{word}`'s type: {takes}",
            )

    def operation(self, line: 'Line') -> bool:
        """Check the operation, its predicate and its type; true when its operands can be checked against it."""
        op, ty = line.operation, line.type
        if op.text not in OPERATIONS and op.text != ICMP:
            hint = OPERATION_HABITS.get(op.text, OPERATIONS_HINT)
            if op.text in LATER_OPERATIONS:
                self.report('bad-value', f'`{op.text}` arrives in a later step', op.span, hint)
            elif op.text in LANGUAGE_WORDS:
                self.report('bad-value', f'`{op.text}` is not an operation', op.span, hint)
            else:
                self.report('unknown-language-word', f'`{op.text}` is not a language word', op.span, hint)
            return False
        if line.predicate is not None and line.predicate.text not in PREDICATES:
            self.report(
                'bad-value',
                f'`{line.predicate.text}` is not a predicate',
                line.predicate.span,
                'the predicates are `eq`, `ne`, `slt`, `sle`, `sgt`, `sge`, `ult`, `ule`, `ugt` and `uge`',
            )
        if op.text in LOGIC and ty.text != 'i1':
            hint = f'`{op.text}` takes `i1`; mime has no bitwise operations on `i64`'
            self.report('bad-value', f'`{op.text}` does not take `{ty.text}`', ty.span, hint)
            return False
        if op.text not in LOGIC and ty.text != 'i64':
            later = f'`{ty.text}` arrives in a later step; ' if ty.text in LATER_TYPES else ''
            self.report(
                'bad-value', f'`{op.text}` does not take `{ty.text}`', ty.span, later + f'write `{op.text} i64`'
            )
            return False
        return True

    def read(
        self,
        i: int,
        v: Value,
        result: str | None,
        bound: dict[str, Value],
        every: set[str],
        used: set[str],
        expected: str | None,
        where: str,
    ) -> None:
        """Check a value a block reads, and that it has the `expected` type there."""
        if v.kind == Tok.INT:
            if not I64_MIN <= int(v.text) <= I64_MAX:
                self.report(
                    'bad-value', f'`{v.text}` does not fit in `i64`', v.span, 'an `i64` is from -2^63 to 2^63-1'
                )
        elif v.kind == Tok.WORD:
            if v.text in self.inputs:
                self.used_inputs.add(v.text)
            elif v.text not in self.rejected:
                self.word_operand(v)
                return
            else:
                return
        elif v.kind == Tok.LOCAL and not self.local(v, result, bound, every, used):
            return
        actual = self.value_type(i, v)
        if expected is not None and actual is not None and actual != expected:
            hint = (
                'write `true` or `false`'
                if v.kind == Tok.INT and expected == 'i1'
                else 'an `i1` is a truth value, not a number; branch on it with `br`'
                if actual == 'i1'
                else 'compare with `icmp` to get an `i1`'
            )
            self.report(
                'wrong-type', f'`{_value_text(v)}` is an `{actual}`, but {where} needs an `{expected}`', v.span, hint
            )

    def local(self, v: Value, result: str | None, bound: dict[str, Value], every: set[str], used: set[str]) -> bool:
        """Check a local a block reads; true when it is bound, so its type can be checked."""
        if v.text in bound:
            used.add(v.text)
            return True
        if v.text == result:
            used.add(v.text)
            self.report(
                'forward-reference',
                f'`%{v.text}` is bound by this line, so its own operation cannot read it',
                v.span,
                OPERAND_HINT,
            )
        elif v.text in every:
            used.add(v.text)
            self.report(
                'forward-reference',
                f'`%{v.text}` is bound later in this block',
                v.span,
                f'move the line for `%{v.text}` above this one',
            )
        elif v.text in self.inputs:
            self.report(
                'undeclared-word', f'nothing binds `%{v.text}`', v.span, f'an input is its word: write `@{v.text}`'
            )
        else:
            elsewhere = [
                b.label.text if b.label is not None else None
                for b in self.d.blocks
                if v.text in {p.text for p in b.params} | {line.result.text for line in b.lines}
            ]
            if elsewhere:
                place = 'the entry block' if elsewhere[0] is None else f'`^{elsewhere[0]}`'
                hint = f'`%{v.text}` is bound in {place}; a block sees only its own locals, so pass it as an argument'
            else:
                close = difflib.get_close_matches(v.text, list(bound), n=1)
                hint = f'did you mean `%{close[0]}`?' if close else OPERAND_HINT
            self.report('undeclared-word', f'nothing binds `%{v.text}` in this block', v.span, hint)
        return False

    def word_operand(self, v: Value) -> None:
        """A `@word` in a body that is not an input of the function."""
        if v.text in self.c.index:
            kind = 'function' if self.c.kinds[v.text] == 'function' else 'data word'
            self.report(
                'not-a-value',
                f'`@{v.text}` is a {kind} that is not an input of this function',
                v.span,
                "a body reads its inputs, its block's locals, and constants; to read it, list it in the inputs",
            )
        else:
            close = difflib.get_close_matches(v.text, list(self.inputs), n=1)
            hint = f'did you mean `@{close[0]}`?' if close else OPERAND_HINT
            self.report('undeclared-word', f'no entry declares `@{v.text}`', v.span, hint)


def check(module: Module) -> tuple[Program | None, list[Diagnostic]]:
    checker = _Checker(module)
    program = checker.run()
    return program, checker.diags
