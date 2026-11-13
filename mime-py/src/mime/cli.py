import argparse
import sys
from pathlib import Path

from mime import diag, printer, tools
from mime.__about__ import __version__
from mime.compiler import ToolError, analyze, domain_word, name_arg, run
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

    p = sub.add_parser('run', help='run one function of a program on one decimal integer per input')
    p.add_argument('file')
    p.add_argument('--positions', action='store_true', help=positions)
    # The word is optional to argparse so that a word the shell expanded away gets a hint, not a bare usage error.
    p.add_argument('word', nargs='?', help='the function to run, written as in the source: @same')
    p.add_argument('inputs', nargs='*', help='one decimal integer per input, in the order of the type')
    p.add_argument('--timeout', type=float, default=10.0, help='stop a run after this many seconds (default: 10)')

    word = 'the word, written as in the source: @number'
    p = sub.add_parser('show', help='print the entry for a word, exactly as written')
    p.add_argument('file')
    p.add_argument('word', nargs='?', help=word)

    p = sub.add_parser('uses', help='list every reference to a word, as a JSON array')
    p.add_argument('file')
    p.add_argument('--positions', action='store_true', help='add the line and column of each use')
    p.add_argument('word', nargs='?', help=word)

    p = sub.add_parser('fmt', help='rewrite a program in its one layout, keeping its words and English')
    p.add_argument('file')

    p = sub.add_parser('canon', help='print the canonical form: every word renamed @w0, @w1, ..., every local numbered')
    p.add_argument('file')
    p.add_argument('--locals', action='store_true', help='rewrite the file with only its locals numbered, and print it')

    p = sub.add_parser('rename', help='rename one word or local everywhere and rewrite the file')
    p.add_argument('file')
    p.add_argument('word', nargs='?', help='the word or local to rename: @number or %%double')
    p.add_argument('new', nargs='?', help='its new spelling, with the same sigil: @count or %%twice')
    return parser


def _check_run_args(word: str | None) -> None:
    """Explain a missing word."""
    if word is None or word == '':
        msg = 'mime run needs a word: mime run FILE @WORD INPUT...'
        raise ToolError(msg)
    if word.lstrip('-').isdigit():
        msg = f'`{word}` looks like an input, so the word is missing: mime run FILE @WORD INPUT...'
        raise ToolError(msg)


def _check_word_arg(command: str, word: str | None) -> str:
    """The word for `show` or `uses`."""
    if word is None or word == '':
        msg = f'mime {command} needs a word: mime {command} FILE @WORD'
        raise ToolError(msg)
    return domain_word(word)


def _query(args: argparse.Namespace) -> int:
    """`show` and `uses`, which need only a program that parses (design/tools.md). `uses` also takes a local."""
    if args.command == 'uses' and args.word and args.word.startswith('%'):
        local = name_arg(args.word)[1:]
        try:
            module = parse(_read(args.file))
        except FatalError as e:
            sys.stderr.write(diag.to_json([e.diagnostic], positions=args.positions))
            return PROGRAM_ERRORS
        sys.stdout.write(tools.uses_json(tools.local_uses(module, local), positions=args.positions))
        return OK
    if args.command == 'show' and args.word and args.word.startswith('%'):
        msg = f'`{args.word}` is a local, so it has no entry; `mime uses` lists its uses'
        raise ToolError(msg)
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


def _form(args: argparse.Namespace) -> int:
    """`fmt`, `canon` and `rename`, which need only a program that parses (design/step-5.md)."""
    if args.command == 'rename':
        if not args.word or not args.new:
            msg = 'mime rename needs the old and the new name: mime rename FILE @OLD @NEW'
            raise ToolError(msg)
        old, new = name_arg(args.word), name_arg(args.new)
    source = _read(args.file)
    try:
        module = parse(source)
    except FatalError as e:
        sys.stderr.write(diag.to_json([e.diagnostic]))
        return PROGRAM_ERRORS
    if args.command == 'canon' and args.locals:
        numbered = printer.canon_locals(module)
        _write(args.file, numbered)
        sys.stdout.write(numbered)
    elif args.command == 'canon':
        sys.stdout.write(printer.canon(module))
    elif args.command == 'fmt':
        _write(args.file, printer.layout(module))
    else:
        renamed = printer.rename(source, old, new)
        _write(args.file, renamed)
        found = tools.uses(parse(renamed), new[1:]) if new[0] == '@' else tools.local_uses(parse(renamed), new[1:])
        sys.stdout.write(tools.uses_json(found))
    return OK


def _write(path: str, text: str) -> None:
    try:
        Path(path).write_text(text, encoding='utf-8')
    except OSError as e:
        msg = f'cannot write {path}: {e}'
        raise ToolError(msg) from None


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
        if args.command in ('fmt', 'canon', 'rename'):
            return _form(args)
        if args.command == 'run':
            _check_run_args(args.word)
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
            sys.stdout.write(run(program, args.word, args.inputs, args.timeout))
    except ToolError as e:
        sys.stderr.write(f'mime: {e}\n')
        return USAGE
    return OK
