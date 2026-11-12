"""Diagnostics: what the toolchain tells an agent about a program's mistakes."""

import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Diagnostic:
    kind: str
    message: str
    line: int
    column: int
    hint: str | None = None


class FatalError(Exception):
    """A mistake that stops parsing. The checker reports everything else without stopping."""

    def __init__(self, diagnostic: Diagnostic) -> None:
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


def to_text(path: str, diagnostics: list[Diagnostic]) -> str:
    lines = []
    for d in diagnostics:
        lines.append(f'{path}:{d.line}:{d.column}: {d.kind}: {d.message}')
        if d.hint:
            lines.append(f'  hint: {d.hint}')
    return ''.join(line + '\n' for line in lines)


def to_json(diagnostics: list[Diagnostic]) -> str:
    return json.dumps([asdict(d) for d in diagnostics]) + '\n'
