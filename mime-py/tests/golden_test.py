"""Golden tests: each `goldens/NAME.mime` has its approved output next to it.

A program that checks clean approves `NAME.ll`, what `mime llvm` prints. A program with mistakes approves
`NAME.check.json`, what `mime check` prints. Only one of the two is kept for a golden; the other is deleted. A
program that parses also approves `NAME.canon.mime`, what `mime canon` prints.

Every golden that parses is kept in its one layout, as `mime fmt` writes it (design/step-5.md). A golden that is not
is rewritten in place, and its outputs must not change.

On a mismatch, approvaltests writes `NAME.ll.received` (or `NAME.check.json.received`) beside the approved file and the
test fails. Read the difference, then rename the received file over the approved one to accept it.
"""

from pathlib import Path

import pytest
from approvaltests.approvals import verify
from approvaltests.core.namer import Namer
from approvaltests.core.options import Options
from approvaltests.reporters.python_native_reporter import PythonNativeReporter

from mime import diag
from mime.compiler import analyze
from mime.diag import FatalError
from mime.lower import lower
from mime.parser import parse
from mime.printer import canon, layout

GOLDENS = Path(__file__).parent / 'goldens'
# Print the difference in the test output instead of opening a diff tool, so an agent sees it.
QUIET = Options().with_reporter(PythonNativeReporter())


class ApprovalNamer(Namer):
    """Name the approved file exactly `filename`, so it sits beside its source with its own extension."""

    def __init__(self, filename: Path) -> None:
        self.filename = str(filename)

    def get_received_filename(self, base: str | None = None) -> str:
        del base
        return self.filename + Namer.RECEIVED

    def get_approved_filename(self, base: str | None = None) -> str:
        del base
        return self.filename


def outputs(source: Path) -> tuple[str, str | None, str | None]:
    """The file name, the LLVM IR if the program checks clean, and `mime check`'s JSON if it does not."""
    program, diagnostics = analyze(source.read_text(encoding='utf-8'))
    if program is not None:
        return source.name, lower(program), None
    return source.name, None, diag.to_json(diagnostics)


def sources() -> list[str]:
    """The golden programs; `NAME.canon.mime` is an output, not a source."""
    return sorted(p.stem for p in GOLDENS.glob('*.mime') if '.' not in p.stem)


@pytest.mark.parametrize('name', sources())
def test_golden(name: str) -> None:
    source = GOLDENS / f'{name}.mime'
    text = source.read_text(encoding='utf-8')
    try:
        module = parse(text)
    except FatalError:
        module = None
    if module is not None and layout(module) != text:
        before = outputs(source)
        source.write_text(layout(module), encoding='utf-8')
        assert outputs(source)[1:] == before[1:]
        module = parse(layout(module))
    _, ir, check = outputs(source)
    form = canon(module) if module is not None else None
    for suffix, text in (('.ll', ir), ('.check.json', check), ('.canon.mime', form)):
        approved = GOLDENS / f'{name}{suffix}'
        if text is None:
            approved.unlink(missing_ok=True)
        else:
            verify(text, namer=ApprovalNamer(approved), options=QUIET)


def test_every_approved_file_has_a_source() -> None:
    names = set(sources())
    orphans = [p.name for p in GOLDENS.iterdir() if p.name.split('.', 1)[0] not in names]
    assert orphans == []
