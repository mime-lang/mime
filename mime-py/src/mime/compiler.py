"""The pipeline from source text to a checked program, a native executable, and its output."""

import re
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path

from mime.checker import Function, Program, check
from mime.diag import Diagnostic, FatalError, ToolError
from mime.interp import Scalar, StackOut, Timeout, interpret, trap
from mime.lower import runner, trap_sites
from mime.parser import parse

I64_MIN, I64_MAX = -(2**63), 2**63 - 1
NAME = re.compile(r'[a-z][a-z0-9_]*')
LOCAL = re.compile(r'[a-z0-9]+')


def analyze(source: str) -> tuple[Program | None, list[Diagnostic]]:
    try:
        module = parse(source)
    except FatalError as e:
        return None, [e.diagnostic]
    return check(module)


def domain_word(text: str) -> str:
    """The name of a word given on the command line, written as in the source: `@` and a name."""
    if text.startswith('$'):
        msg = f'words are written `@{text[1:]}` now, and need no quotes: @{text[1:]}'
        raise ToolError(msg)
    if not text.startswith('@'):
        msg = f'write the word as in the source, with its `@`: @{text}'
        raise ToolError(msg)
    if not NAME.fullmatch(text[1:]):
        msg = (
            f'`{text}` is not a word; a word is `@` and a lowercase letter followed by lowercase letters, digits or `_`'
        )
        raise ToolError(msg)
    return text[1:]


def name_arg(text: str) -> str:
    """A word (`@number`), a local (`%double`) or a label (`^loop`) on the command line, returned with its sigil."""
    if text.startswith(('%', '^')):
        if not LOCAL.fullmatch(text[1:]):
            kind = 'local' if text[0] == '%' else 'label'
            msg = f'`{text}` is not a {kind}; a {kind} is `{text[0]}` and lowercase letters or digits'
            raise ToolError(msg)
        return text
    return '@' + domain_word(text)


TRAPPED = 3  # the exit code of a trap, on every backend (design/step-8.md section 4)
BACKENDS = ('interp', 'llvm')  # `mime run --backend`; the first is the default (design/step-8.md section 3)


def exported(program: Program, name: str) -> Function:
    """The function exported as `name`. `mime run` names a function by its symbol, which no renaming changes."""
    f = next((f for f in program.functions if f.symbol == name), None)
    if f is not None:
        return f
    if name.startswith('@'):
        g = next((g for g in program.functions if g.word == name[1:]), None)
        if g is not None and g.symbol is not None:
            msg = f'`mime run` takes a symbol, not a word: write `{g.symbol}`'
            raise ToolError(msg)
        if g is not None:
            msg = f'`{name}` has no symbol; to run it, add `symbol = "{g.word}"` after its abstract'
            raise ToolError(msg)
    word = next((g for g in program.functions if g.word == name and g.symbol is None), None)
    if word is not None:
        msg = f'no function is exported as `{name}`; to run `@{name}`, add `symbol = "{name}"` after its abstract'
        raise ToolError(msg)
    if name in ('true', 'false'):
        msg = f'`{name}` looks like an input, so the symbol is missing: mime run FILE SYMBOL INPUT...'
        raise ToolError(msg)
    symbols = ', '.join(f'`{g.symbol}`' for g in program.functions if g.symbol is not None)
    exports = f'the program exports {symbols}' if symbols else 'the program exports nothing; give a function a `symbol`'
    msg = f'no function is exported as `{name}`; {exports}'
    raise ToolError(msg)


def inputs(f: Function, args: list[str]) -> list[Scalar]:
    """The values of `args`, one per input of `f`, read the same way for every backend."""
    if len(args) != len(f.inputs):
        names = ', '.join(f'`@{w}`' for w in f.inputs) or 'none'
        given = '1 was' if len(args) == 1 else f'{len(args)} were'
        plural = '' if len(f.inputs) == 1 else 's'
        msg = f'`{f.symbol}` takes {len(f.inputs)} input{plural} ({names}), but {given} given'
        raise ToolError(msg)
    values: list[Scalar] = []
    for name, arg in zip(f.inputs, args, strict=True):
        if f.input_types[name] == 'i1':
            if arg not in ('true', 'false'):
                msg = f'the input `{arg}` for `@{name}` is not `true` or `false`'
                raise ToolError(msg)
            values.append(arg == 'true')
            continue
        try:
            n = int(arg, 10)
        except ValueError:
            msg = f'the input `{arg}` is not a decimal integer'
            raise ToolError(msg) from None
        if not I64_MIN <= n <= I64_MAX:
            msg = f'the input {arg} does not fit in an i64'
            raise ToolError(msg)
        values.append(n)
    return values


def printed(value: Scalar) -> str:
    """What `mime run` prints for a result, on every backend: an `i64` in decimal, an `i1` as `true` or `false`."""
    if isinstance(value, bool):
        return 'true\n' if value else 'false\n'
    return f'{value}\n'


def run(program: Program, name: str, args: list[str], timeout: float = 10.0, backend: str = 'interp') -> str:
    """Run the function exported as `name` on `args` and return what it prints.

    A run that takes longer than `timeout` seconds is stopped: since step 7 a loop may never reach its exit.
    """
    f = exported(program, name)
    values = inputs(f, args)
    too_long = f'`{f.symbol}` did not finish within {timeout:g} s; a loop may never reach its exit (see --timeout)'
    # Running out of stack is the machine's limit, like time, not the program's meaning (design/step-9.md section 5).
    too_deep = (
        f'`{f.symbol}` ran out of stack: the machine could not hold that many nested calls, '
        'or a recursion never reaches its base case'
    )
    if backend == 'interp':
        try:
            return printed(interpret(program, f, values, time.monotonic() + timeout))
        except Timeout:
            raise ToolError(too_long) from None
        except StackOut:
            raise ToolError(too_deep) from None
    clang = shutil.which('clang')
    if clang is None:
        msg = '`clang` is not on PATH; `mime run --backend llvm` needs it to build the program'
        raise ToolError(msg)
    numbers = [str(int(v)) for v in values]  # the runner reads an `i1` as 1 or 0
    with tempfile.TemporaryDirectory(prefix='mime-') as tmp:
        ll, exe = Path(tmp) / 'program.ll', Path(tmp) / 'program'
        ll.write_text(runner(program, f.word))
        command = [clang, '-O0', '-w', str(ll), '-o', str(exe)]
        built = subprocess.run(command, capture_output=True, text=True, check=False)
        if built.returncode != 0:
            msg = f'clang failed; this is a mime bug:\n{built.stderr}'
            raise ToolError(msg)
        try:
            ran = subprocess.run([str(exe), *numbers], capture_output=True, text=True, check=False, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise ToolError(too_long) from None
        # A native stack that overflows kills the program with a signal; mime has no memory operations yet, so no other
        # mistake of a program raises one.
        if ran.returncode in (-signal.SIGSEGV, -signal.SIGBUS):
            raise ToolError(too_deep)
        if ran.returncode == TRAPPED:
            # The trap routine wrote the site of the guard that failed (design/step-13.md section 4, step-14.md section 2).
            sites = trap_sites(program)
            try:
                g, line, message = sites[int(ran.stderr.strip())]
            except (ValueError, IndexError):
                msg = f'the program trapped, but reported no site; this is a mime bug: {ran.stderr[:200]!r}'
                raise ToolError(msg) from None
            raise trap(program, g, line, message)
        if ran.returncode != 0:
            msg = f'the program exited with code {ran.returncode}'
            raise ToolError(msg)
        return ran.stdout
