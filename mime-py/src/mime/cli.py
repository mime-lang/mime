import argparse
import sys
from pathlib import Path

from mime import diag
from mime.__about__ import __version__
from mime.compiler import ToolError, analyze, run
from mime.lower import lower

OK, PROGRAM_ERRORS, USAGE = 0, 1, 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='mime', description='mime language toolchain')
    parser.add_argument('--version', action='version', version=f'mime {__version__}')
    sub = parser.add_subparsers(dest='command')

    p = sub.add_parser('check', help='report every mistake in a program')
    p.add_argument('file')
    p.add_argument('--json', action='store_true', help='print the diagnostics as a JSON array')

    p = sub.add_parser('llvm', help='print the LLVM IR of a program')
    p.add_argument('file')

    p = sub.add_parser('run', help='run one function of a program on one input')
    p.add_argument('file')
    # Both are optional to argparse so that a word the shell expanded away gets a hint instead of a bare usage error.
    p.add_argument('word', nargs='?', help="the function to run, in single quotes so the shell keeps its `$`: '$same'")
    p.add_argument('input', nargs='?', help='a decimal integer')
    return parser


SHELL_HINT = "if you wrote $name without single quotes, the shell expanded it as a variable; write '$name'"


def _check_run_args(word: str | None, arg: str | None) -> None:
    """Explain a missing argument, which most often means the shell ate a `$word`."""
    if word == '':
        msg = f'the word is empty; {SHELL_HINT}'
        raise ToolError(msg)
    if word is None:
        msg = 'mime run needs a word and an input: mime run FILE WORD INPUT'
        raise ToolError(msg)
    if arg is None:
        looks_like_input = word.lstrip('-').isdigit()
        reason = (
            f'`{word}` looks like the input, so the word is missing; {SHELL_HINT}'
            if looks_like_input
            else (f'mime run needs an input after `{word}`')
        )
        raise ToolError(reason)


def _read(path: str) -> str:
    try:
        return Path(path).read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError) as e:
        msg = f'cannot read {path}: {e}'
        raise ToolError(msg) from None


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return OK
    try:
        if args.command == 'run':
            _check_run_args(args.word, args.input)
        program, diagnostics = analyze(_read(args.file))
        if args.command == 'check':
            out = diag.to_json(diagnostics) if args.json else diag.to_text(args.file, diagnostics)
            sys.stdout.write(out)
            return PROGRAM_ERRORS if diagnostics else OK
        if program is None:
            sys.stderr.write(diag.to_text(args.file, diagnostics))
            return PROGRAM_ERRORS
        if args.command == 'llvm':
            sys.stdout.write(lower(program))
        else:
            sys.stdout.write(run(program, args.word, args.input))
    except ToolError as e:
        sys.stderr.write(f'mime: {e}\n')
        return USAGE
    return OK
