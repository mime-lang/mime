import argparse
import sys
from pathlib import Path

from mime import diag, tools
from mime.__about__ import __version__
from mime.compiler import ToolError, analyze, domain_word, run
from mime.diag import FatalError
from mime.lower import lower
from mime.parser import parse

OK, PROGRAM_ERRORS, USAGE = 0, 1, 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='mime', description='mime language toolchain')
    parser.add_argument('--version', action='version', version=f'mime {__version__}')
    sub = parser.add_subparsers(dest='command')

    positions = 'add the line and column of each mistake to its diagnostic'
    p = sub.add_parser('check', help='report every mistake in a program, as a JSON array')
    p.add_argument('file')
    p.add_argument('--positions', action='store_true', help=positions)

    p = sub.add_parser('llvm', help='print the LLVM IR of a program')
    p.add_argument('file')
    p.add_argument('--positions', action='store_true', help=positions)

    p = sub.add_parser('run', help='run one function of a program on one input')
    p.add_argument('file')
    p.add_argument('--positions', action='store_true', help=positions)
    # Both are optional to argparse so that a word the shell expanded away gets a hint instead of a bare usage error.
    p.add_argument('word', nargs='?', help="the function to run, in single quotes so the shell keeps its `$`: '$same'")
    p.add_argument('input', nargs='?', help='a decimal integer')

    word = "the word, in single quotes so the shell keeps its `$`: '$number'"
    p = sub.add_parser('show', help='print the entry for a word, exactly as written')
    p.add_argument('file')
    p.add_argument('word', nargs='?', help=word)

    p = sub.add_parser('uses', help='list every reference to a word, as a JSON array')
    p.add_argument('file')
    p.add_argument('--positions', action='store_true', help='add the line and column of each use')
    p.add_argument('word', nargs='?', help=word)
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


def _check_word_arg(command: str, word: str | None) -> str:
    """The word for `show` or `uses`, explaining a missing one the way `mime run` does."""
    if word == '':
        msg = f'the word is empty; {SHELL_HINT}'
        raise ToolError(msg)
    if word is None:
        msg = f'mime {command} needs a word: mime {command} FILE WORD; {SHELL_HINT}'
        raise ToolError(msg)
    return domain_word(word)


def _query(args: argparse.Namespace) -> int:
    """`show` and `uses`, which need only a program that parses (design/tools.md)."""
    word = _check_word_arg(args.command, args.word)
    try:
        module = parse(_read(args.file))
    except FatalError as e:
        sys.stderr.write(diag.to_json([e.diagnostic], positions=getattr(args, 'positions', False)))
        return PROGRAM_ERRORS
    if args.command == 'show':
        sys.stdout.write(tools.show(module, word))
    else:
        sys.stdout.write(tools.uses_json(tools.uses(module, word), positions=args.positions))
    return OK


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
        if args.command in ('show', 'uses'):
            return _query(args)
        if args.command == 'run':
            _check_run_args(args.word, args.input)
        program, diagnostics = analyze(_read(args.file))
        if args.command == 'check':
            sys.stdout.write(diag.to_json(diagnostics, positions=args.positions))
            return PROGRAM_ERRORS if diagnostics else OK
        if program is None:
            sys.stderr.write(diag.to_json(diagnostics, positions=args.positions))
            return PROGRAM_ERRORS
        if args.command == 'llvm':
            sys.stdout.write(lower(program))
        else:
            sys.stdout.write(run(program, args.word, args.input))
    except ToolError as e:
        sys.stderr.write(f'mime: {e}\n')
        return USAGE
    return OK
