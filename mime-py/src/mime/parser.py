"""Parse tokens into a module (design/step-1.md, section 2). Stops at the first syntax error."""

from dataclasses import dataclass

from mime.diag import Diagnostic, FatalError
from mime.lexer import Ref, Tok, Token, lex
from mime.words import LANGUAGE_WORDS


@dataclass(frozen=True)
class Value:
    kind: Tok  # WORD, NAME or STRING
    text: str
    line: int
    column: int
    refs: tuple[Ref, ...] = ()  # for a string, its `$` marks


@dataclass(frozen=True)
class Field:
    key: str
    value: Value
    line: int
    column: int


@dataclass(frozen=True)
class Entry:
    word: str
    fields: tuple[Field, ...]
    line: int
    column: int


@dataclass(frozen=True)
class Module:
    entries: tuple[Entry, ...]


def _show(t: Token) -> str:
    if t.kind == Tok.WORD:
        return f'`${t.text}`'
    if t.kind == Tok.NAME:
        return f'`{t.text}`'
    return t.kind.value


class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> Token:
        return self.tokens[self.pos]

    def take(self) -> Token:
        t = self.tokens[self.pos]
        self.pos += 1
        return t

    def fail(self, t: Token, message: str, hint: str | None = None, kind: str = 'syntax') -> FatalError:
        return FatalError(Diagnostic(kind, message, t.line, t.column, hint))

    def expect(self, kind: Tok, context: str) -> Token:
        t = self.take()
        if t.kind != kind:
            raise self.fail(t, f'expected {kind.value} {context}, found {_show(t)}')
        return t

    def module(self) -> Module:
        entries = []
        while self.peek().kind != Tok.END:
            entries.append(self.entry())
        return Module(tuple(entries))

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
        self.expect(Tok.EQUALS, f'after `${t.text}`')
        self.expect(Tok.LBRACE, f'to start the entry for `${t.text}`')
        fields = []
        if self.peek().kind != Tok.RBRACE:
            while True:
                fields.append(self.field())
                sep = self.take()
                if sep.kind == Tok.RBRACE:
                    break
                if sep.kind != Tok.COMMA:
                    raise self.fail(sep, f'expected `,` or `}}` after a field, found {_show(sep)}')
                if self.peek().kind == Tok.RBRACE:
                    raise self.fail(sep, 'a trailing comma is not allowed', 'remove the `,`', kind='trailing-comma')
        else:
            self.take()
        return Entry(t.text, tuple(fields), t.line, t.column)

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
        return Field(k.text, Value(v.kind, v.text, v.line, v.column, v.refs), k.line, k.column)


def parse(source: str) -> Module:
    """Raises FatalError on a syntax error."""
    return _Parser(lex(source)).module()
