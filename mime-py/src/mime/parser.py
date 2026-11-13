"""Parse tokens into a module (design/step-4.md section 2, step-7.md section 2). Stops at the first syntax error."""

from dataclasses import dataclass, replace

from mime.diag import Diagnostic, FatalError
from mime.lexer import ARITHMETIC_HINT, ARROW_HINT, Ref, Span, Tok, Token, tokens
from mime.words import (
    BR,
    CALL,
    DECLARE,
    DEFINE,
    FALSE,
    ICMP,
    LANGUAGE_WORDS,
    LLVM_HABITS,
    OPERATIONS,
    RET,
    RETIRED,
    TRUE,
    TYPES,
)

DEFINE_HINT = 'write the type: `define @f {@a, @b} -> @r {…}`'
LINE_HINT = 'a line is `%x = add i64 %a, %b`, with `sub` or `mul` alike'
CALL_HINT = 'write `%r = call @f {@a = %x, @b = %y}`, naming each input of `@f`'


@dataclass(frozen=True)
class Value:
    kind: Tok  # WORD, LOCAL, NAME, STRING or INT
    text: str
    span: Span
    refs: tuple[Ref, ...] = ()  # for a string, its `@` references


@dataclass(frozen=True)
class Struct:
    """`{@a, @b}` as a declaration's value: a struct of words."""

    words: tuple[Value, ...]
    span: Span  # from `{` to `}`


@dataclass(frozen=True)
class Field:
    key: str
    value: Value | Struct
    span: Span  # the key


@dataclass(frozen=True)
class Entry:
    """A declaration: `@word = {type = …, abstract = "…"}`."""

    word: str
    fields: tuple[Field, ...]
    span: Span  # the word, with its `@`
    end: int  # the offset just after the closing `}`, so `source[span.start:end]` is the whole entry


@dataclass(frozen=True)
class Line:
    """`%result = operation type left, right`, or `%result = icmp predicate type left, right`."""

    result: Value
    operation: Value
    predicate: Value | None
    type: Value
    left: Value
    right: Value


@dataclass(frozen=True)
class Argument:
    """`@input = value` in a call: the callee's input it fills, and the caller's value (design/step-9.md section 2)."""

    key: Value  # the callee's input word
    value: Value


@dataclass(frozen=True)
class Call:
    """`%result = call @callee {@a = x, @b = y}`."""

    result: Value
    keyword: Value  # `call`
    callee: Value
    args: tuple[Argument, ...]


@dataclass(frozen=True)
class Target:
    """`^label{args}`: a block a `br` jumps to, and the values it passes to the block's parameters."""

    label: Value
    args: tuple[Value, ...]


@dataclass(frozen=True)
class Terminator:
    """`ret value`, `br ^b{args}`, or `br condition, ^t{args}, ^f{args}`."""

    keyword: Value  # `ret` or `br`
    value: Value | None  # the returned value, or the condition of a two-way `br`
    targets: tuple[Target, ...]


@dataclass(frozen=True)
class Block:
    """The entry block (no label), or `^label{params}:` and its lines, ending in one terminator."""

    label: Value | None
    params: tuple[Value, ...]
    lines: tuple[Line | Call, ...]
    end: Terminator


@dataclass(frozen=True)
class Definition:
    """`define @word {inputs} -> output {blocks} abstract = "…"`."""

    word: Value
    inputs: tuple[Value, ...]
    output: Value
    blocks: tuple[Block, ...]
    abstract: Value
    symbol: Value | None  # `symbol = "clamp"` after the abstract: the name the function is exported under
    span: Span  # the `define`
    end: int  # the offset just after the abstract, or after the symbol


@dataclass(frozen=True)
class Declaration:
    """`declare @word {inputs} -> output`: the head of a `define` further down (design/step-9.md section 4)."""

    word: Value
    inputs: tuple[Value, ...]
    output: Value
    span: Span  # the `declare`
    end: int  # the offset just after the output


type Item = Entry | Definition | Declaration


@dataclass(frozen=True)
class Module:
    items: tuple[Item, ...]  # every entry in source order: data words, definitions and declarations
    source: str

    @property
    def entries(self) -> tuple[Entry, ...]:
        return tuple(x for x in self.items if isinstance(x, Entry))

    @property
    def definitions(self) -> tuple[Definition, ...]:
        return tuple(x for x in self.items if isinstance(x, Definition))


def item_word(x: Item) -> str:
    """The word an entry is for, without its `@`."""
    return x.word if isinstance(x, Entry) else x.word.text


def line_values(x: Line | Call) -> list[Value]:
    """Every word and value a line names besides its result, in source order: a call's callee and each argument's
    input word and value, or an operation's two operands."""
    if isinstance(x, Call):
        return [x.callee, *(v for a in x.args for v in (a.key, a.value))]
    return [x.left, x.right]


def block_values(b: Block) -> list[Value]:
    """Every value and word a block names, in source order, besides the locals it binds: operands, a call's callee and
    arguments, the `ret` value or `br` condition, and jump arguments."""
    found = []
    for line in b.lines:
        found += line_values(line)
    if b.end.value is not None:
        found.append(b.end.value)
    for t in b.end.targets:
        found += t.args
    return found


def atoms(d: Definition) -> list[Value]:
    """Every value and word a body names, in source order. Locals being bound are not included."""
    return [v for b in d.blocks for v in block_values(b)]


def _show(t: Token) -> str:
    if t.kind == Tok.WORD:
        return f'`@{t.text}`'
    if t.kind == Tok.LOCAL:
        return f'`%{t.text}`'
    if t.kind == Tok.NAME:
        return f'`{t.text}`'
    return t.kind.value


def _infix(t: Token) -> str | None:
    """The arithmetic hint for `%a -1`, where a value is followed by what reads as subtraction."""
    return ARITHMETIC_HINT if t.kind == Tok.INT and t.text.startswith('-') else None


def _value(t: Token) -> Value:
    return Value(t.kind, t.text, t.span, t.refs)


class _Parser:
    def __init__(self, source: str) -> None:
        self.source = source
        self.stream = tokens(source)
        self.ahead: Token | None = None
        # Where the parser is, for a diagnostic: the word with its `@`, and the key (`type`, `body`, `abstract`).
        self.entry_word: str | None = None
        self.key: str | None = None

    def peek(self) -> Token:
        if self.ahead is None:
            self.ahead = next(self.stream)  # the stream ends with END, and nothing reads past it
        return self.ahead

    def take(self) -> Token:
        t = self.peek()
        if t.kind != Tok.END:
            self.ahead = None
        return t

    def fail(self, t: Token, message: str, hint: str | None = None, kind: str = 'syntax') -> FatalError:
        text = self.source[t.span.start : t.span.end] or None
        diagnostic = Diagnostic(kind, message, t.span.line, t.span.column, hint, self.entry_word, self.key, text)
        return FatalError(diagnostic)

    def expect(self, kind: Tok, context: str, hint: str | None = None) -> Token:
        t = self.take()
        if t.kind != kind:
            raise self.fail(t, f'expected {kind.value} {context}, found {_show(t)}', hint)
        return t

    def module(self) -> Module:
        items: list[Item] = []
        while self.peek().kind != Tok.END:
            t = self.peek()
            if t.kind == Tok.NAME and t.text == DEFINE:
                items.append(self.definition())
            elif t.kind == Tok.NAME and t.text == DECLARE:
                items.append(self.declaration())
            else:
                items.append(self.entry())
        return Module(tuple(items), self.source)

    # Declarations

    def entry(self) -> Entry:
        t = self.take()
        if t.kind == Tok.NAME and t.text not in LANGUAGE_WORDS:
            raise self.fail(
                t, f'`{t.text}` is not a language word', f'did you mean `@{t.text}`?', kind='unknown-language-word'
            )
        if t.kind == Tok.COMMA:
            raise self.fail(t, 'entries are not separated by commas', 'remove the `,`')
        if t.kind != Tok.WORD:
            raise self.fail(t, f'expected an entry such as `@word = {{…}}`, found {_show(t)}')
        self.entry_word = f'@{t.text}'
        self.expect(Tok.EQUALS, f'after `@{t.text}`')
        self.expect(Tok.LBRACE, f'to start the entry for `@{t.text}`')
        fields = []
        if self.peek().kind != Tok.RBRACE:
            while True:
                fields.append(self.field())
                sep = self.take()
                if sep.kind == Tok.RBRACE:
                    close = sep
                    break
                if sep.kind == Tok.ARROW:
                    self.key = 'type'
                    raise self.fail(sep, 'a function is written as a `define`', DEFINE_HINT)
                if sep.kind != Tok.COMMA:
                    raise self.fail(sep, f'expected `,` or `}}` after a field, found {_show(sep)}', _infix(sep))
                if self.peek().kind == Tok.RBRACE:
                    raise self.fail(sep, 'a trailing comma is not allowed', 'remove the `,`', kind='trailing-comma')
        else:
            close = self.take()
        self.entry_word = None
        return Entry(t.text, tuple(fields), t.span, close.span.end)

    def field(self) -> Field:
        k = self.take()
        if k.kind == Tok.WORD:
            raise self.fail(
                k,
                f'entries do not nest, so `@{k.text}` cannot be declared inside another entry',
                f'declare `@{k.text}` as its own entry before this one',
                kind='nested-entry',
            )
        if k.kind != Tok.NAME:
            raise self.fail(k, f'expected a key such as `type`, found {_show(k)}')
        self.key = k.text
        if k.text == 'body':
            raise self.fail(k, '`body` is not a key', RETIRED['body'], kind='unknown-key')
        self.expect(Tok.EQUALS, f'after the key `{k.text}`')
        value: Value | Struct
        if self.peek().kind == Tok.LBRACE:
            value = self.struct()
        else:
            v = self.take()
            if v.kind not in (Tok.STRING, Tok.WORD, Tok.NAME, Tok.INT):
                raise self.fail(v, f'expected a value after `{k.text} =`, found {_show(v)}')
            value = _value(v)
        if self.peek().kind != Tok.ARROW:
            self.key = None
        return Field(k.text, value, k.span)

    def struct(self) -> Struct:
        """`{@a, @b}`. A key inside it means a nested entry, which mime does not have."""
        open_ = self.take()
        words = []
        while self.peek().kind != Tok.RBRACE:
            w = self.take()
            if w.kind in (Tok.NAME, Tok.WORD) and self.peek().kind == Tok.EQUALS:
                raise self.fail(
                    w,
                    'entries do not nest, so a value cannot be a `{…}` of keys',
                    'declare the inner entry as its own entry and name its word here',
                    kind='nested-entry',
                )
            if w.kind != Tok.WORD:
                raise self.fail(w, f'expected a word in the struct, found {_show(w)}')
            words.append(_value(w))
            if self.peek().kind == Tok.COMMA:
                comma = self.take()
                if self.peek().kind == Tok.RBRACE:
                    raise self.fail(comma, 'a trailing comma is not allowed', 'remove the `,`', kind='trailing-comma')
            elif self.peek().kind != Tok.RBRACE:
                raise self.fail(self.peek(), f'expected `,` or `}}` in the struct, found {_show(self.peek())}')
        close = self.take()
        return Struct(tuple(words), Span(open_.span.line, open_.span.column, open_.span.start, close.span.end))

    # Definitions

    def head(self, keyword: Token) -> tuple[Token, tuple[Value, ...], Token]:
        """`@word {inputs} -> output` after `define` or `declare`."""
        w = self.take()
        if w.kind != Tok.WORD:
            raise self.fail(w, f'expected the function word after `{keyword.text}`, found {_show(w)}', DEFINE_HINT)
        self.entry_word, self.key = f'@{w.text}', 'type'
        inputs = self.inputs()
        arrow = self.take()
        if arrow.kind != Tok.ARROW:
            hint = ARROW_HINT if arrow.kind in (Tok.COLON, Tok.EQUALS) else DEFINE_HINT
            raise self.fail(arrow, f'expected `->` after the inputs, found {_show(arrow)}', hint)
        out = self.take()
        if out.kind not in (Tok.WORD, Tok.NAME):
            raise self.fail(
                out, f'expected the output after `->`, found {_show(out)}', 'name a word, such as `@number`'
            )
        if self.peek().kind == Tok.ARROW:
            raise self.fail(self.peek(), 'a function returns one value', 'put the inputs in a struct: `{@a, @b} -> @c`')
        return w, inputs, out

    def declaration(self) -> Declaration:
        keyword = self.take()
        w, inputs, out = self.head(keyword)
        nxt = self.peek()
        if nxt.kind == Tok.LBRACE:
            raise self.fail(
                nxt,
                'a declaration has no body',
                f'write the body in the `define` of `@{w.text}` below, or make this the `define`',
            )
        if nxt.kind == Tok.NAME and nxt.text in ('abstract', 'symbol'):
            raise self.fail(
                nxt, f'a declaration has no {nxt.text}', f'write `{nxt.text} = …` after the `define` of `@{w.text}`'
            )
        self.entry_word = self.key = None
        return Declaration(_value(w), inputs, _value(out), keyword.span, out.span.end)

    def definition(self) -> Definition:
        keyword = self.take()
        w, inputs, out = self.head(keyword)
        self.key = 'body'
        self.expect(Tok.LBRACE, 'to start the body')
        blocks = [self.block(None, ())]
        while self.peek().kind != Tok.RBRACE:
            label = self.take()
            if label.kind != Tok.LABEL:
                raise self.fail(
                    label, 'nothing follows a terminator in its block', 'start a new block with `^label{}:`'
                )
            blocks.append(self.block(_value(label), self.params(label)))
        self.take()
        self.key = 'abstract'
        a = self.take()
        if a.kind != Tok.NAME or a.text != 'abstract':
            raise self.fail(a, 'a definition ends with its abstract', 'write `abstract = "…"` right after the body')
        self.expect(Tok.EQUALS, 'after `abstract`')
        s = self.take()
        if s.kind != Tok.STRING:
            raise self.fail(s, f'expected the abstract as a string, found {_show(s)}', 'write the meaning in `"…"`')
        symbol, end = None, s.span.end
        if self.peek().kind == Tok.NAME and self.peek().text == 'symbol':
            self.key = 'symbol'
            self.take()
            self.expect(Tok.EQUALS, 'after `symbol`')
            v = self.take()
            if v.kind != Tok.STRING:
                raise self.fail(v, f'expected the symbol as a string, found {_show(v)}', 'write `symbol = "name"`')
            symbol, end = _value(v), v.span.end
        self.entry_word = self.key = None
        return Definition(_value(w), inputs, _value(out), tuple(blocks), _value(s), symbol, keyword.span, end)

    def block(self, label: Value | None, params: tuple[Value, ...]) -> Block:
        """Lines up to and including the block's one terminator."""
        lines = []
        while True:
            t = self.peek()
            if t.kind == Tok.NAME and t.text in (RET, BR):
                end = self.terminator()
                after = self.peek()
                if after.kind == Tok.NAME and after.text == 'abstract':
                    raise self.fail(
                        after,
                        'the abstract goes after the body',
                        'close the body with `}`, then write `abstract = "…"`',
                    )
                if after.kind not in (Tok.RBRACE, Tok.LABEL):
                    hint = _infix(after) or 'a terminator ends its block; start a new block with `^label{}:`'
                    raise self.fail(after, 'nothing follows a terminator in its block', hint)
                return Block(label, params, tuple(lines), end)
            if t.kind == Tok.RBRACE:
                where = 'a body' if label is None else f'the block `^{label.text}`'
                raise self.fail(
                    t, f'{where} ends with `ret` or `br`', 'return a value with `ret %x`, or jump with `br`'
                )
            if t.kind == Tok.LABEL:
                where = 'the entry block' if label is None else f'the block `^{label.text}`'
                hint = (
                    'the lines after `{` are the entry block, which has no label'
                    if label is None and not lines
                    else 'end it with `ret` or `br` before the next block'
                )
                raise self.fail(t, f'{where} has no terminator', hint)
            lines.append(self.line())

    def params(self, label: Token) -> tuple[Value, ...]:
        """`{%a, %b}:` after a block's label: its inputs, in braces like a function's."""
        hint = f'write `^{label.text}{{}}:`, or `^{label.text}{{%a, %b}}:` with parameters'
        found = self.group(label, 'a parameter such as `%a`', f'^{label.text}{{}}:', parameters=True)
        self.expect(Tok.COLON, f'after the parameters of `^{label.text}`', hint)
        return found

    def group(self, label: Token, what: str, form: str, *, parameters: bool) -> tuple[Value, ...]:
        """`{…}` after a label: a block's parameters, or the arguments a jump passes to it."""
        if self.peek().kind == Tok.LPAREN:
            raise self.fail(
                self.peek(),
                'a block takes its values in braces, as a function does',
                f'write `^{label.text}{{…}}`, not `^{label.text}(…)`',
            )
        if self.peek().kind != Tok.LBRACE:
            raise self.fail(self.peek(), f'expected `{{` after `^{label.text}`', f'write `{form}`')
        self.take()
        found = []
        while self.peek().kind != Tok.RBRACE:
            if parameters:
                p = self.take()
                if p.kind != Tok.LOCAL:
                    raise self.fail(p, f'expected {what}, found {_show(p)}', 'a parameter is a local')
                found.append(_value(p))
            else:
                found.append(self.atom(f'in the arguments of `^{label.text}`'))
            if self.peek().kind == Tok.COMMA:
                comma = self.take()
                if self.peek().kind == Tok.RBRACE:
                    raise self.fail(comma, 'a trailing comma is not allowed', 'remove the `,`', kind='trailing-comma')
            elif self.peek().kind != Tok.RBRACE:
                raise self.fail(self.peek(), f'expected `,` or `}}` after {what}, found {_show(self.peek())}')
        self.take()
        return tuple(found)

    def terminator(self) -> Terminator:
        keyword = _value(self.take())
        if keyword.text == RET:
            return Terminator(keyword, self.atom('after `ret`'), ())
        if self.peek().kind == Tok.LABEL:
            return Terminator(keyword, None, (self.target(),))
        nxt = self.peek()
        if nxt.kind == Tok.NAME and nxt.text == 'label':
            raise self.fail(nxt, '`label` is not a language word', 'write the block: `br ^b{}`')
        if nxt.kind == Tok.NAME and nxt.text in TYPES:
            raise self.fail(nxt, 'the condition of `br` takes no type', 'write `br %c, ^then{}, ^else{}`')
        condition = self.atom('after `br`')
        self.expect(Tok.COMMA, 'after the condition of `br`', 'write `br %c, ^then{}, ^else{}`')
        first = self.target()
        self.expect(Tok.COMMA, 'between the two blocks of `br`', 'write `br %c, ^then{}, ^else{}`')
        return Terminator(keyword, condition, (first, self.target()))

    def target(self) -> Target:
        label = self.take()
        if label.kind == Tok.LOCAL:
            raise self.fail(label, f'`%{label.text}` is a local, not a block', f'write `^{label.text}{{}}`')
        if label.kind != Tok.LABEL:
            raise self.fail(label, f'expected a block such as `^next{{}}`, found {_show(label)}')
        return Target(_value(label), self.group(label, 'an argument', f'^{label.text}{{}}', parameters=False))

    def inputs(self) -> tuple[Value, ...]:
        t = self.take()
        if t.kind == Tok.LPAREN:
            raise self.fail(t, "a function's inputs are a struct of words", DEFINE_HINT)
        if t.kind != Tok.LBRACE:
            raise self.fail(t, f'expected the inputs, `{{…}}`, found {_show(t)}', DEFINE_HINT)
        found = []
        while self.peek().kind != Tok.RBRACE:
            x = self.take()
            if x.kind != Tok.WORD:
                hint = (
                    f'an input is a declared word; declare one with `type = {x.text}`'
                    if x.kind == Tok.NAME and x.text in TYPES
                    else 'an input is a declared word, such as `@number`'
                )
                raise self.fail(x, f'expected an input word, found {_show(x)}', hint)
            found.append(_value(x))
            if self.peek().kind == Tok.COMMA:
                comma = self.take()
                if self.peek().kind == Tok.RBRACE:
                    raise self.fail(comma, 'a trailing comma is not allowed', 'remove the `,`', kind='trailing-comma')
            elif self.peek().kind != Tok.RBRACE:
                raise self.fail(self.peek(), f'expected `,` or `}}` in the inputs, found {_show(self.peek())}')
        self.take()
        return tuple(found)

    def line(self) -> Line | Call:
        r = self.take()
        if r.kind in (Tok.NAME, Tok.LOCAL) and self.peek().kind == Tok.COLON:
            raise self.fail(r, 'a block label is written with `^`', f'write `^{r.text}{{}}:`')
        if r.kind == Tok.NAME and (r.text in RETIRED or r.text in LLVM_HABITS):
            raise self.fail(r, f'`{r.text}` is not a language word', RETIRED.get(r.text) or LLVM_HABITS[r.text])
        if r.kind == Tok.WORD:
            raise self.fail(r, 'a result is a local, not a word', f'write `%{r.text}`; a `@` word has an entry')
        if r.kind != Tok.LOCAL:
            raise self.fail(r, f'expected a line or `ret`, found {_show(r)}', LINE_HINT)
        eq = self.take()
        if eq.kind != Tok.EQUALS:
            raise self.fail(eq, f'expected `=` after `%{r.text}`, found {_show(eq)}', LINE_HINT)
        op = self.take()
        if op.kind != Tok.NAME:
            raise self.fail(op, f'expected an operation after `%{r.text} =`, found {_show(op)}', ARITHMETIC_HINT)
        if op.text in LLVM_HABITS:
            raise self.fail(op, f'`{op.text}` is not a language word', LLVM_HABITS[op.text])
        if op.text == CALL:
            return self.call(_value(r), _value(op))
        nxt = self.peek()
        if nxt.kind in (Tok.LBRACE, Tok.LPAREN):
            raise self.fail(nxt, f'the operands of `{op.text}` take no brackets', LINE_HINT)
        predicate = None
        if op.text == ICMP:
            p = self.take()
            if p.kind != Tok.NAME:
                raise self.fail(
                    p, f'expected a predicate after `icmp`, found {_show(p)}', 'write `icmp slt i64 %a, %b`'
                )
            predicate = _value(p)
        ty = self.take()
        if ty.kind != Tok.NAME:
            raise self.fail(ty, f'expected a type after `{op.text}`, found {_show(ty)}', LINE_HINT)
        if ty.text in LLVM_HABITS:
            raise self.fail(ty, f'`{ty.text}` is not a language word', LLVM_HABITS[ty.text])
        left = self.atom(f'after `{op.text} {ty.text}`')
        self.expect(Tok.COMMA, 'between the two operands', LINE_HINT)
        right = self.atom('after `,`')
        if self.peek().kind == Tok.COMMA:
            raise self.fail(self.peek(), f'`{op.text}` takes two operands', LINE_HINT)
        return Line(_value(r), _value(op), predicate, _value(ty), left, right)

    def call(self, result: Value, keyword: Value) -> Call:
        """`call @f {@a = x, @b = y}` after `%result =`."""
        t = self.take()
        if t.kind == Tok.NAME and t.text in TYPES:
            f = self.peek()
            hint = (
                f'write `call @{f.text} {{@a = %x}}`; the type comes from `@{f.text}`'
                if f.kind == Tok.WORD
                else 'the type comes from the function; ' + CALL_HINT
            )
            raise self.fail(t, 'a call takes no type', hint)
        if t.kind != Tok.WORD:
            raise self.fail(t, f'expected the function after `call`, found {_show(t)}', CALL_HINT)
        callee = _value(t)
        if self.peek().kind == Tok.LPAREN:
            raise self.fail(
                self.peek(),
                'a call takes its arguments in braces, each named by its input',
                f'write `call @{t.text} {{@a = %x}}`',
            )
        self.expect(Tok.LBRACE, f'after `call @{t.text}`', CALL_HINT)
        args = []
        while self.peek().kind != Tok.RBRACE:
            k = self.take()
            if k.kind != Tok.WORD:
                raise self.fail(
                    k,
                    f'expected the input an argument fills, found {_show(k)}',
                    f'an argument names an input of `@{t.text}`: `@a = {self.source[k.span.start : k.span.end]}`',
                )
            self.expect(Tok.EQUALS, f'after the input `@{k.text}`', f'write `@{k.text} = %x`')
            args.append(Argument(_value(k), self.atom(f'for `@{k.text}`')))
            if self.peek().kind == Tok.COMMA:
                comma = self.take()
                if self.peek().kind == Tok.RBRACE:
                    raise self.fail(comma, 'a trailing comma is not allowed', 'remove the `,`', kind='trailing-comma')
            elif self.peek().kind != Tok.RBRACE:
                raise self.fail(self.peek(), f'expected `,` or `}}` after an argument, found {_show(self.peek())}')
        self.take()
        return Call(result, keyword, callee, tuple(args))

    def atom(self, context: str) -> Value:
        t = self.take()
        if t.kind in (Tok.WORD, Tok.LOCAL, Tok.INT):
            return _value(t)
        if t.kind != Tok.NAME:
            raise self.fail(
                t, f'expected an operand {context}, found {_show(t)}', 'an operand is a word, a local or an integer'
            )
        if t.text in (TRUE, FALSE):
            return _value(t)
        if t.text in TYPES:
            raise self.fail(t, f'`{t.text}` is a type, not an operand', 'the type comes from the definition')
        if t.text in OPERATIONS or t.text in (ICMP, CALL):
            raise self.fail(
                t,
                f'`{t.text}` is an operation inside an operand',
                'give the inner operation its own line, and use its result here',
                kind='nested-operation',
            )
        if t.text in RETIRED:
            raise self.fail(t, f'`{t.text}` is not a language word', RETIRED[t.text])
        kind = 'syntax' if t.text in LANGUAGE_WORDS else 'unknown-language-word'
        raise self.fail(t, f'`{t.text}` is not an operand', f'did you mean `%{t.text}` or `@{t.text}`?', kind=kind)


def parse(source: str) -> Module:
    """Raises FatalError on a syntax error, naming the entry and key it is in when the parser knows them."""
    parser = _Parser(source)
    try:
        return parser.module()
    except FatalError as e:
        d = e.diagnostic
        if d.entry is None and parser.entry_word is not None:
            # A mistake the lexer found, inside an entry the parser had started.
            raise FatalError(replace(d, entry=parser.entry_word, key=parser.key)) from None
        raise
