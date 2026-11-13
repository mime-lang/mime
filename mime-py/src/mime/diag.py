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


class ToolError(Exception):
    """The program is fine, but the command or the machine is not (exit code 2)."""


class Trap(Exception):  # noqa: N818 - a trap is what the program did, not an error of the toolchain
    """A run left an operation's domain (exit code 3, design/step-8.md section 4). Nothing can trap yet: division,
    the first partial operation, raises it."""

    def __init__(self, diagnostic: Diagnostic) -> None:
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


class FatalError(Exception):
    """A mistake that stops parsing. The checker reports everything else without stopping."""

    def __init__(self, diagnostic: Diagnostic) -> None:
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


def _row(d: Diagnostic, *, positions: bool) -> dict[str, str | int | None]:
    row: dict[str, str | int | None] = {f: getattr(d, f) for f in FIELDS}
    if positions:
        row |= {'line': d.line, 'column': d.column}
    return row


def to_json(diagnostics: list[Diagnostic], *, positions: bool = False) -> str:
    """The one output form: a JSON array, indented by two spaces."""
    return json.dumps([_row(d, positions=positions) for d in diagnostics], indent=2, ensure_ascii=False) + '\n'


def trap_json(trap: Diagnostic, *, positions: bool = False) -> str:
    """A trap: one object with a diagnostic's fields, since a run stops at its first trap."""
    return json.dumps(_row(trap, positions=positions), indent=2, ensure_ascii=False) + '\n'
