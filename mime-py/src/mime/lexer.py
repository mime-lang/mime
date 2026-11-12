"""Tokens of the grammar (design/step-1.md, section 1), and the `$` marks inside strings (design/step-2.md)."""

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
class Ref:
    """A `$` inside a string. `word` is the name after it, or None when no name follows.

    `stray` is a character glued to the end of the name that a name cannot hold, such as the `X` in `$numberX`.
    """

    word: str | None
    line: int
    column: int
    stray: str | None = None


@dataclass(frozen=True)
class Token:
    kind: Tok
    text: str  # a word without its `$`, a name, or a string's value after escapes
    line: int
    column: int
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


def lex(source: str) -> list[Token]:
    """Raises FatalError on the first mistake, which stops lexing."""
    tokens: list[Token] = []
    i, line, col = 0, 1, 1

    def fail(kind: str, message: str, hint: str | None = None, at: tuple[int, int] | None = None) -> NoReturn:
        ln, cl = at or (line, col)
        raise FatalError(Diagnostic(kind, message, ln, cl, hint))

    while i < len(source):
        c = source[i]
        if c == '\n':
            i, line, col = i + 1, line + 1, 1
        elif c in ' \t\r':
            i, col = i + 1, col + 1
        elif c in PUNCTUATION:
            tokens.append(Token(PUNCTUATION[c], c, line, col))
            i, col = i + 1, col + 1
        elif c in {';', '#'} or source.startswith('//', i):
            fail('comment', 'comments are not part of mime', COMMENT_HINT)
        elif c == '$':
            j = i + 1
            if j >= len(source) or not _name_start(source[j]):
                fail('syntax', 'expected a name after `$`', NAME_HINT)
            while j < len(source) and _name_char(source[j]):
                j += 1
            if j < len(source) and _glued(source[j]):
                fail('syntax', f'`{source[j]}` cannot appear in a name', NAME_HINT, (line, col + j - i))
            tokens.append(Token(Tok.WORD, source[i + 1 : j], line, col))
            col += j - i
            i = j
        elif _name_start(c):
            j = i
            while j < len(source) and _name_char(source[j]):
                j += 1
            if j < len(source) and _glued(source[j]):
                fail('syntax', f'`{source[j]}` cannot appear in a name', NAME_HINT, (line, col + j - i))
            tokens.append(Token(Tok.NAME, source[i:j], line, col))
            col += j - i
            i = j
        elif c == '"':
            start = (line, col)
            j, cl, value, refs = i + 1, col + 1, [], []
            while True:
                if j >= len(source) or source[j] == '\n':
                    fail('syntax', 'this string is not closed on its line', 'end it with `"`', start)
                ch = source[j]
                if ch == '"':
                    break
                if ch == '\\':
                    nxt = source[j + 1] if j + 1 < len(source) else ''
                    if nxt not in ESCAPES:
                        fail(
                            'syntax', f'unknown escape `\\{nxt}`', 'the escapes are `\\"`, `\\\\` and `\\$`', (line, cl)
                        )
                    value.append(ESCAPES[nxt])
                    j, cl = j + 2, cl + 2
                    continue
                if ch == '$':
                    k = j + 1
                    if k < len(source) and _name_start(source[k]):
                        while k < len(source) and _name_char(source[k]):
                            k += 1
                        stray = source[k] if k < len(source) and _glued(source[k]) else None
                        refs.append(Ref(source[j + 1 : k], line, cl, stray))
                    else:
                        refs.append(Ref(None, line, cl))
                value.append(ch)
                j, cl = j + 1, cl + 1
            tokens.append(Token(Tok.STRING, ''.join(value), *start, refs=tuple(refs)))
            col = cl + 1
            i = j + 1
        elif c.isalpha():
            fail('syntax', f'`{c}` cannot start a name', NAME_HINT)
        else:
            fail('syntax', f'unexpected character `{c}`')

    tokens.append(Token(Tok.END, '', line, col))
    return tokens
