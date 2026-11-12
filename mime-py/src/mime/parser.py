"""Parse tokens into a module (design/step-1.md, section 2). Stops at the first syntax error."""

from dataclasses import dataclass, replace

from mime.diag import Diagnostic, FatalError
from mime.lexer import Ref, Span, Tok, Token, tokens
from mime.words import LANGUAGE_WORDS


@dataclass(frozen=True)
class Value:
    kind: Tok  # WORD, NAME or STRING
    text: str
    span: Span
    refs: tuple[Ref, ...] = ()  # for a string, its `$` marks


@dataclass(frozen=True)
class Field:
    key: str
    value: Value
    span: Span  # the key


@dataclass(frozen=True)
class Entry:
    word: str
    fields: tuple[Field, ...]
    span: Span  # the word, with its `$`
    end: int  # the offset just after the entry's closing `}`, so `source[span.start:end]` is the whole entry


@dataclass(frozen=True)
class Module:
    entries: tuple[Entry, ...]
    source: str


def _show(t: Token) -> str:
    if t.kind == Tok.WORD:
        return f'`${t.text}`'
    if t.kind == Tok.NAME:
        return f'`{t.text}`'
    return t.kind.value


class _Parser:
    def __init__(self, source: str) -> None:
        self.source = source
        self.stream = tokens(source)
        self.ahead: Token | None = None
        # Where the parser is, for a diagnostic: the entry's word with its `$`, and the key of the field.
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

    def expect(self, kind: Tok, context: str) -> Token:
        t = self.take()
        if t.kind != kind:
            raise self.fail(t, f'expected {kind.value} {context}, found {_show(t)}')
        return t

    def module(self) -> Module:
        entries = []
        while self.peek().kind != Tok.END:
            entries.append(self.entry())
        return Module(tuple(entries), self.source)

    def entry(self) -> Entry:
        t = self.take()
        if t.kind == Tok.NAME and t.text not in LANGUAGE_WORDS:
            raise self.fail(
                t, f'`{t.text}` is not a language word', f'did you mean `${t.text}`?', kind='unknown-language-word'
            )
        if t.kind == Tok.COMMA:
            raise self.fail(t, 'entries are not separated by commas', 'remove the `,`')
        if t.kind != Tok.WORD:
            raise self.fail(t, f'expected an entry such as `$word = {{…}}`, found {_show(t)}')
        self.entry_word = f'${t.text}'
        self.expect(Tok.EQUALS, f'after `${t.text}`')
        self.expect(Tok.LBRACE, f'to start the entry for `${t.text}`')
        fields = []
        if self.peek().kind != Tok.RBRACE:
            while True:
                fields.append(self.field())
                sep = self.take()
                if sep.kind == Tok.RBRACE:
                    close = sep
                    break
                if sep.kind != Tok.COMMA:
                    raise self.fail(sep, f'expected `,` or `}}` after a field, found {_show(sep)}')
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
                f'entries do not nest, so `${k.text}` cannot be declared inside another entry',
                f'declare `${k.text}` as its own entry before this one',
                kind='nested-entry',
            )
        if k.kind != Tok.NAME:
            raise self.fail(k, f'expected a key such as `description`, found {_show(k)}')
        self.key = k.text
        self.expect(Tok.EQUALS, f'after the key `{k.text}`')
        v = self.take()
        if v.kind == Tok.LBRACE:
            raise self.fail(
                v,
                'entries do not nest, so a value cannot be a `{…}`',
                'declare the inner entry as its own entry and name its word here',
                kind='nested-entry',
            )
        if v.kind not in (Tok.STRING, Tok.WORD, Tok.NAME):
            raise self.fail(v, f'expected a value after `{k.text} =`, found {_show(v)}')
        self.key = None
        return Field(k.text, Value(v.kind, v.text, v.span, v.refs), k.span)


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
