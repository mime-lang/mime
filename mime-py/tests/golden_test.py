"""Golden tests: each `goldens/NAME.mime` has its approved output next to it.

A program that checks clean approves `NAME.ll`, what `mime llvm` prints. A program with mistakes approves
`NAME.check.json`, what `mime check` prints. Only one of the two is kept for a golden; the other is deleted.

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
from mime.lower import lower

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


@pytest.mark.parametrize('name', sorted(p.stem for p in GOLDENS.glob('*.mime')))
def test_golden(name: str) -> None:
    source = GOLDENS / f'{name}.mime'
    _, ir, check = outputs(source)
    for suffix, text in (('.ll', ir), ('.check.json', check)):
        approved = GOLDENS / f'{name}{suffix}'
        if text is None:
            approved.unlink(missing_ok=True)
        else:
            verify(text, namer=ApprovalNamer(approved), options=QUIET)


def test_every_approved_file_has_a_source() -> None:
    sources = {p.stem for p in GOLDENS.glob('*.mime')}
    orphans = [p.name for p in GOLDENS.iterdir() if p.suffix != '.mime' and p.name.split('.', 1)[0] not in sources]
    assert orphans == []
