import argparse

from mime.__about__ import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='mime', description='mime language toolchain')
    parser.add_argument('--version', action='version', version=f'mime {__version__}')
    parser.parse_args(argv)
    parser.print_help()
    return 0
