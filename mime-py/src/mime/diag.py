"""Diagnostics: what the toolchain tells an agent about a program's mistakes (design/diagnostics.md)."""

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class Diagnostic:
    kind: str
    message: str
    line: int
    column: int
    hint: str | None = None
    entry: str | None = None  # the entry's word with its `@`, as in the source
    key: str | None = None
    text: str | None = None  # the exact source text at fault


# The fields every diagnostic prints, in order; `--positions` adds `line` and `column` after them.
FIELDS = ('kind', 'entry', 'key', 'text', 'message', 'hint')


class FatalError(Exception):
    """A mistake that stops parsing. The checker reports everything else without stopping."""

    def __init__(self, diagnostic: Diagnostic) -> None:
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


def to_json(diagnostics: list[Diagnostic], *, positions: bool = False) -> str:
    """The one output form: a JSON array, indented by two spaces."""
    rows = []
    for d in diagnostics:
        row: dict[str, str | int | None] = {f: getattr(d, f) for f in FIELDS}
        if positions:
            row |= {'line': d.line, 'column': d.column}
        rows.append(row)
    return json.dumps(rows, indent=2, ensure_ascii=False) + '\n'
