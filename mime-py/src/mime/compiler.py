"""The pipeline from source text to a checked program, a native executable, and its output."""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from mime.checker import Program, check
from mime.diag import Diagnostic, FatalError, ToolError
from mime.lower import runner
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


def run(program: Program, word: str, args: list[str], timeout: float = 10.0) -> str:
    """Compile `program` with `word` as the entry point, run it on `args`, and return what it prints.

    A run that takes longer than `timeout` seconds is stopped: since step 7 a loop may never reach its exit.
    """
    word = domain_word(word)
    f = next((f for f in program.functions if f.word == word), None)
    if f is None:
        msg = f'no definition defines `@{word}`'
        raise ToolError(msg)
    if len(args) != len(f.inputs):
        names = ', '.join(f'`@{w}`' for w in f.inputs) or 'none'
        given = '1 was' if len(args) == 1 else f'{len(args)} were'
        plural = '' if len(f.inputs) == 1 else 's'
        msg = f'`@{word}` takes {len(f.inputs)} input{plural} ({names}), but {given} given'
        raise ToolError(msg)
    numbers = []
    for name, arg in zip(f.inputs, args, strict=True):
        if f.input_types[name] == 'i1':
            if arg not in ('true', 'false'):
                msg = f'the input `{arg}` for `@{name}` is not `true` or `false`'
                raise ToolError(msg)
            numbers.append('1' if arg == 'true' else '0')
            continue
        try:
            n = int(arg, 10)
        except ValueError:
            msg = f'the input `{arg}` is not a decimal integer'
            raise ToolError(msg) from None
        if not I64_MIN <= n <= I64_MAX:
            msg = f'the input {arg} does not fit in an i64'
            raise ToolError(msg)
        numbers.append(str(n))
    clang = shutil.which('clang')
    if clang is None:
        msg = '`clang` is not on PATH; mime run needs it to build the program'
        raise ToolError(msg)
    with tempfile.TemporaryDirectory(prefix='mime-') as tmp:
        ll, exe = Path(tmp) / 'program.ll', Path(tmp) / 'program'
        ll.write_text(runner(program, word))
        command = [clang, '-O0', '-w', str(ll), '-o', str(exe)]
        built = subprocess.run(command, capture_output=True, text=True, check=False)
        if built.returncode != 0:
            msg = f'clang failed; this is a mime bug:\n{built.stderr}'
            raise ToolError(msg)
        try:
            ran = subprocess.run([str(exe), *numbers], capture_output=True, text=True, check=False, timeout=timeout)
        except subprocess.TimeoutExpired:
            msg = f'`@{word}` did not finish within {timeout:g} s; a loop may never reach its exit (see --timeout)'
            raise ToolError(msg) from None
        if ran.returncode != 0:
            msg = f'the program exited with code {ran.returncode}'
            raise ToolError(msg)
        return ran.stdout
