"""Lower a checked program to textual LLVM IR (design/step-4.md section 5, step-6.md section 8)."""

from mime.checker import Function, Program
from mime.lexer import Tok
from mime.parser import Value

LLVM_TYPE = {'i64': 'i64'}


def symbol(word: str) -> str:
    """`@"mime.affine"`: a `.` cannot appear in a C symbol, so no runtime symbol can clash, and an ELF linker reads
    an `@` inside a symbol as a version, so the word's own `@` is left out."""
    return f'@"mime.{word}"'


def _operand(v: Value) -> str:
    """An input is `%"@number"` and a local `%"%0"`: quoted, because a bare `%0` is an unnamed LLVM value."""
    if v.kind == Tok.WORD:
        return f'%"@{v.text}"'
    if v.kind == Tok.LOCAL:
        return f'%"%{v.text}"'
    return v.text


def _function(f: Function) -> str:
    t = LLVM_TYPE['i64']  # every data word is an `i64` so far
    params = ', '.join(f'{t} %"@{w}"' for w in f.inputs)
    lines = [f'define {t} {symbol(f.word)}({params}) {{']
    for line in f.definition.lines:
        # No `nsw` or `nuw` flag, so overflow wraps.
        left, right = _operand(line.left), _operand(line.right)
        lines.append(f'  {_operand(line.result)} = {line.operation.text} {t} {left}, {right}')
    lines.append(f'  ret {t} {_operand(f.definition.ret)}')
    return '\n'.join([*lines, '}']) + '\n'


def lower(program: Program) -> str:
    return '\n'.join(_function(f) for f in program.functions)


def runner(program: Program, word: str) -> str:
    """IR for a C `main` that reads one decimal argument per input, calls `word`, and prints the result."""
    f = next(f for f in program.functions if f.word == word)
    reads, args = [], []
    for i in range(len(f.inputs)):
        reads += [
            f'  %slot{i} = getelementptr ptr, ptr %argv, i64 {i + 1}',
            f'  %text{i} = load ptr, ptr %slot{i}',
            f'  %arg{i} = call i64 @strtoll(ptr %text{i}, ptr null, i32 10)',
        ]
        args.append(f'i64 %arg{i}')
    body = '\n'.join(reads)
    return f"""{lower(program)}
@.format = private unnamed_addr constant [6 x i8] c"%lld\\0A\\00"

declare i64 @strtoll(ptr, ptr, i32)
declare i32 @printf(ptr, ...)

define i32 @main(i32 %argc, ptr %argv) {{
{body}
  %result = call i64 {symbol(f.word)}({', '.join(args)})
  %printed = call i32 (ptr, ...) @printf(ptr @.format, i64 %result)
  ret i32 0
}}
"""
