"""The pipeline from source text to a checked program, a native executable, and its output."""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from mime.checker import Program, check
from mime.diag import Diagnostic, FatalError
from mime.lower import runner
from mime.parser import parse

I64_MIN, I64_MAX = -(2**63), 2**63 - 1
NAME = re.compile(r'[a-z][a-z0-9_]*')


class ToolError(Exception):
    """The program is fine, but the command or the machine is not (exit code 2)."""


def analyze(source: str) -> tuple[Program | None, list[Diagnostic]]:
    try:
        module = parse(source)
    except FatalError as e:
        return None, [e.diagnostic]
    return check(module)


def domain_word(text: str) -> str:
    """The name of a word given on the command line, which is written as in the source: `$` and a name."""
    if not text.startswith('$'):
        msg = f"write the word as in the source, with its `$` and in single quotes: '${text}'"
        raise ToolError(msg)
    if not NAME.fullmatch(text[1:]):
        msg = (
            f'`{text}` is not a word; a word is `$` and a lowercase letter followed by lowercase letters, digits or `_`'
        )
        raise ToolError(msg)
    return text[1:]


def run(program: Program, word: str, arg: str) -> str:
    """Compile `program` with `word` as the entry point, run it on `arg`, and return what it prints."""
    word = domain_word(word)
    if not any(f.word == word for f in program.functions):
        msg = f'no function entry declares `${word}`'
        raise ToolError(msg)
    try:
        n = int(arg, 10)
    except ValueError:
        msg = f'the input `{arg}` is not a decimal integer'
        raise ToolError(msg) from None
    if not I64_MIN <= n <= I64_MAX:
        msg = f'the input {arg} does not fit in an i64'
        raise ToolError(msg)
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
        ran = subprocess.run([str(exe), str(n)], capture_output=True, text=True, check=False)
        if ran.returncode != 0:
            msg = f'the program exited with code {ran.returncode}'
            raise ToolError(msg)
        return ran.stdout
