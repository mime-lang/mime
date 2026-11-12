"""Lower a checked program to textual LLVM IR (design/step-1.md, section 6)."""

from mime.checker import Function, Program

LLVM_SORT = {'i64': 'i64'}


def symbol(word: str) -> str:
    return f'@"${word}"'


def _function(f: Function) -> str:
    t = LLVM_SORT[f.sort]
    return f'define {t} {symbol(f.word)}({t} %input) {{\n  ret {t} %input\n}}\n'


def lower(program: Program) -> str:
    return '\n'.join(_function(f) for f in program.functions)


def runner(program: Program, word: str) -> str:
    """IR for a C `main` that reads one decimal argument, calls `word`, and prints the result."""
    f = next(f for f in program.functions if f.word == word)
    call = symbol(f.word)
    return f"""{lower(program)}
@.format = private unnamed_addr constant [6 x i8] c"%lld\\0A\\00"

declare i64 @strtoll(ptr, ptr, i32)
declare i32 @printf(ptr, ...)

define i32 @main(i32 %argc, ptr %argv) {{
  %slot = getelementptr ptr, ptr %argv, i64 1
  %text = load ptr, ptr %slot
  %arg = call i64 @strtoll(ptr %text, ptr null, i32 10)
  %result = call i64 {call}(i64 %arg)
  %printed = call i32 (ptr, ...) @printf(ptr @.format, i64 %result)
  ret i32 0
}}
"""
