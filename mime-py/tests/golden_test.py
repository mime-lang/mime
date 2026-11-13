"""Golden tests: each golden program has its approved outputs next to it, in one of two folders.

- `goldens/clean/NAME.mime` must check clean. It approves `NAME.canon.mime`, what `mime canon` prints, and `NAME.ll`,
  the LLVM IR of that canonical form. Lowering the canonical form keeps the IR independent of how the golden names
  its words and locals, so a golden's `.ll` changes only when its structure or the lowering does. (`mime llvm` itself
  lowers a program as written, so its IR stays readable while debugging.)
  It also carries `NAME.runs.json`, its run cases, written by hand: every exported function has one, and every
  backend must print each case's `output`, for the golden and for its canonical form (design/step-8.md section 5).
- `goldens/mistakes/NAME.mime` must have mistakes. It approves `NAME.check.json`, what `mime check` prints.

Every golden that parses is kept in its one layout, as `mime fmt` writes it (design/step-5.md). A golden that is not
is rewritten in place, and its outputs must not change.

On a mismatch, approvaltests writes `NAME.ll.received` (or another `.received` file) beside the approved file and the
test fails. Read the difference, then rename the received file over the approved one to accept it.
"""

from pathlib import Path

import pytest
from approvaltests.approvals import verify
from approvaltests.core.namer import Namer
from approvaltests.core.options import Options
from approvaltests.reporters.python_native_reporter import PythonNativeReporter

from mime import diag
from mime.compiler import analyze, run
from mime.diag import FatalError
from mime.lower import lower
from mime.parser import parse
from mime.printer import canon, layout
from tests.run_cases import BACKENDS, every_case, load
from tests.run_cases import layout as runs_layout

GOLDENS = Path(__file__).parent / 'goldens'
CLEAN, MISTAKES = GOLDENS / 'clean', GOLDENS / 'mistakes'
OUTPUTS = {CLEAN: ('.ll', '.canon.mime', '.runs.json'), MISTAKES: ('.check.json',)}
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


def sources(folder: Path) -> list[str]:
    """The golden programs in `folder`; `NAME.canon.mime` is an output, not a source."""
    return sorted(p.stem for p in folder.glob('*.mime') if '.' not in p.stem)


def keep_formatted(source: Path) -> None:
    """Rewrite a golden that parses into its one layout; the check must not change."""
    text = source.read_text(encoding='utf-8')
    try:
        module = parse(text)
    except FatalError:
        return
    if layout(module) != text:
        before = analyze(text)[1]
        source.write_text(layout(module), encoding='utf-8')
        assert [d.kind for d in analyze(layout(module))[1]] == [d.kind for d in before]


@pytest.mark.parametrize('name', sources(CLEAN))
def test_clean_golden(name: str) -> None:
    source = CLEAN / f'{name}.mime'
    keep_formatted(source)
    text = source.read_text(encoding='utf-8')
    assert analyze(text)[1] == [], f'{name} is in goldens/clean but has mistakes; move it to goldens/mistakes'
    form = canon(parse(text))
    program, diagnostics = analyze(form)
    assert diagnostics == [], 'the canonical form of a clean program must check clean'
    assert program is not None
    verify(form, namer=ApprovalNamer(CLEAN / f'{name}.canon.mime'), options=QUIET)
    verify(lower(program), namer=ApprovalNamer(CLEAN / f'{name}.ll'), options=QUIET)


@pytest.mark.parametrize('name', sources(CLEAN))
def test_every_function_is_exported_and_run(name: str) -> None:
    text = (CLEAN / f'{name}.mime').read_text(encoding='utf-8')
    program, _ = analyze(text)
    assert program is not None
    internal = [f'@{f.word}' for f in program.functions if f.symbol is None]
    assert internal == [], f'give every function of {name} a `symbol`, so its run cases can name it'
    cases = load(name)
    assert (CLEAN / f'{name}.runs.json').read_text(encoding='utf-8') == runs_layout(cases), 'one case per line'
    assert {str(c['symbol']) for c in cases} == {f.symbol for f in program.functions}, 'every function needs a case'


@pytest.mark.parametrize('backend', BACKENDS)
@pytest.mark.parametrize(('name', 'symbol', 'inputs', 'output'), every_case())
def test_run_case(name: str, symbol: str, inputs: list[str], output: str, backend: str) -> None:
    text = (CLEAN / f'{name}.mime').read_text(encoding='utf-8')
    for form in (text, canon(parse(text))):
        program, _ = analyze(form)
        assert program is not None
        assert run(program, symbol, inputs, backend=backend) == output + '\n'


@pytest.mark.parametrize('name', sources(MISTAKES))
def test_mistakes_golden(name: str) -> None:
    source = MISTAKES / f'{name}.mime'
    keep_formatted(source)
    diagnostics = analyze(source.read_text(encoding='utf-8'))[1]
    assert diagnostics != [], f'{name} is in goldens/mistakes but checks clean; move it to goldens/clean'
    verify(diag.to_json(diagnostics), namer=ApprovalNamer(MISTAKES / f'{name}.check.json'), options=QUIET)


@pytest.mark.parametrize('folder', [CLEAN, MISTAKES], ids=['clean', 'mistakes'])
def test_every_file_is_a_source_or_one_of_its_outputs(folder: Path) -> None:
    names = set(sources(folder))
    expected = {f'{n}.mime' for n in names} | {f'{n}{suffix}' for n in names for suffix in OUTPUTS[folder]}
    assert sorted(p.name for p in folder.iterdir()) == sorted(expected)


def test_goldens_live_only_in_the_two_folders() -> None:
    assert sorted(p.name for p in GOLDENS.iterdir()) == ['clean', 'mistakes']
