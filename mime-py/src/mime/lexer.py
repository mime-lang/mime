"""Tokens of the grammar (design/step-1.md, section 1), and the `$` marks inside strings (design/step-2.md)."""

from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum
from typing import NoReturn

from mime.diag import Diagnostic, FatalError


class Tok(Enum):
    WORD = 'domain word'
    NAME = 'language word'
    STRING = 'string'
    LBRACE = '`{`'
    RBRACE = '`}`'
    EQUALS = '`=`'
    COMMA = '`,`'
    END = 'end of file'


@dataclass(frozen=True)
class Span:
    """Where something is in the source: its 1-based line and column, and `source[start:end]` is its text."""

    line: int
    column: int
    start: int
    end: int


@dataclass(frozen=True)
class Ref:
    """A `$` inside a string. `word` is the name after it, or None when no name follows.

    `stray` is a character glued to the end of the name that a name cannot hold, such as the `X` in `$numberX`.
    The span covers the `$`, the name, and any glued characters.
    """

    word: str | None
    span: Span
    stray: str | None = None


@dataclass(frozen=True)
class Token:
    kind: Tok
    text: str  # a word without its `$`, a name, or a string's value after escapes
    span: Span
    refs: tuple[Ref, ...] = ()  # for a string, every unescaped `$` in it, in order


PUNCTUATION = {'{': Tok.LBRACE, '}': Tok.RBRACE, '=': Tok.EQUALS, ',': Tok.COMMA}
ESCAPES = {'"': '"', '\\': '\\', '$': '$'}
NAME_HINT = 'a name is a lowercase letter followed by lowercase letters, digits or `_`'
COMMENT_HINT = 'mime has no comments; put the English in a `description`'


def _name_start(c: str) -> bool:
    return 'a' <= c <= 'z'


def _name_char(c: str) -> bool:
    return 'a' <= c <= 'z' or '0' <= c <= '9' or c == '_'


def _glued(c: str) -> bool:
    """A character right after a name that looks like more of it, so the name is a mistake rather than cut short."""
    return c.isalnum() or c == '-'


def _run_end(source: str, k: int) -> int:
    """The end of the name-like run at `k`: what a reader would take as one word, right or wrong."""
    while k < len(source) and (_glued(source[k]) or source[k] == '_'):
        k += 1
    return k


def tokens(source: str) -> Iterator[Token]:
    """Yields tokens one at a time, ending with END. Raises FatalError on the first mistake, which stops lexing."""
    i, line, col = 0, 1, 1

    def fail(kind: str, message: str, hint: str | None, start: int, end: int, column: int | None = None) -> NoReturn:
        text = source[start:end] or None
        raise FatalError(Diagnostic(kind, message, line, column or col, hint, text=text))

    def name_end(j: int) -> int:
        """The end of the name starting at `j`, failing if a character a name cannot hold is glued to it."""
        k = j
        while k < len(source) and _name_char(source[k]):
            k += 1
        if k < len(source) and _glued(source[k]):
            fail('syntax', f'`{source[k]}` cannot appear in a name', NAME_HINT, i, _run_end(source, k), col + k - i)
        return k

    while i < len(source):
        c = source[i]
        if c == '\n':
            i, line, col = i + 1, line + 1, 1
        elif c in ' \t\r':
            i, col = i + 1, col + 1
        elif c in PUNCTUATION:
            yield Token(PUNCTUATION[c], c, Span(line, col, i, i + 1))
            i, col = i + 1, col + 1
        elif c in {';', '#'} or source.startswith('//', i):
            eol = source.find('\n', i)
            end = len(source) if eol < 0 else eol
            fail('comment', 'comments are not part of mime', COMMENT_HINT, i, len(source[i:end].rstrip()) + i)
        elif c == '$':
            if i + 1 >= len(source) or not _name_start(source[i + 1]):
                fail('syntax', 'expected a name after `$`', NAME_HINT, i, _run_end(source, i + 1))
            j = name_end(i + 1)
            yield Token(Tok.WORD, source[i + 1 : j], Span(line, col, i, j))
            col += j - i
            i = j
        elif _name_start(c):
            j = name_end(i)
            yield Token(Tok.NAME, source[i:j], Span(line, col, i, j))
            col += j - i
            i = j
        elif c == '"':
            j, cl, value, refs = i + 1, col + 1, [], []
            while True:
                if j >= len(source) or source[j] == '\n':
                    fail('syntax', 'this string is not closed on its line', 'end it with `"`', i, j)
                ch = source[j]
                if ch == '"':
                    break
                if ch == '\\':
                    nxt = source[j + 1] if j + 1 < len(source) else ''
                    if nxt not in ESCAPES:
                        hint = 'the escapes are `\\"`, `\\\\` and `\\$`'
                        fail('syntax', f'unknown escape `\\{nxt}`', hint, j, j + 1 + len(nxt), cl)
                    value.append(ESCAPES[nxt])
                    j, cl = j + 2, cl + 2
                    continue
                if ch == '$':
                    refs.append(_ref(source, j, line, cl))
                value.append(ch)
                j, cl = j + 1, cl + 1
            yield Token(Tok.STRING, ''.join(value), Span(line, col, i, j + 1), tuple(refs))
            col = cl + 1
            i = j + 1
        elif c.isalpha():
            fail('syntax', f'`{c}` cannot start a name', NAME_HINT, i, _run_end(source, i))
        else:
            fail('syntax', f'unexpected character `{c}`', None, i, i + 1)

    yield Token(Tok.END, '', Span(line, col, i, i))


def _ref(source: str, j: int, line: int, column: int) -> Ref:
    """The reference whose `$` is at `source[j]`, inside a string."""
    k = j + 1
    if k < len(source) and _name_start(source[k]):
        while k < len(source) and _name_char(source[k]):
            k += 1
        stray = source[k] if k < len(source) and _glued(source[k]) else None
        return Ref(source[j + 1 : k], Span(line, column, j, _run_end(source, k)), stray)
    return Ref(None, Span(line, column, j, _run_end(source, k)))


def lex(source: str) -> list[Token]:
    """Every token at once. Raises FatalError on the first mistake."""
    return list(tokens(source))
