"""Lower a checked program to textual LLVM IR (design/step-4.md section 5, step-6.md section 8, step-7.md section 7)."""

from mime.checker import Function, Program
from mime.lexer import Tok
from mime.parser import Block, Line, Value


def symbol(word: str) -> str:
    """`@"mime.affine"`: a `.` cannot appear in a C symbol, so no runtime symbol can clash, and an ELF linker reads
    an `@` inside a symbol as a version, so the word's own `@` is left out."""
    return f'@"mime.{word}"'


def _label(b: Block) -> str:
    return 'entry' if b.label is None else f'"^{b.label.text}"'


def _local(b: Block, name: str) -> str:
    """A local is named after its block, since the same local may be bound in two blocks."""
    return f'%"%{name}"' if b.label is None else f'%"^{b.label.text}%{name}"'


def _operand(b: Block, v: Value) -> str:
    """An input is `%"@number"` and a local `%"%0"`: quoted, because a bare `%0` is an unnamed LLVM value."""
    if v.kind == Tok.WORD:
        return f'%"@{v.text}"'
    if v.kind == Tok.LOCAL:
        return _local(b, v.text)
    return v.text  # an integer, `true` or `false`


def _line(b: Block, x: Line) -> str:
    # No `nsw` or `nuw` flag, so overflow wraps.
    op = f'icmp {x.predicate.text}' if x.predicate is not None else x.operation.text
    return f'  {_local(b, x.result.text)} = {op} i64 {_operand(b, x.left)}, {_operand(b, x.right)}'


def _function(f: Function) -> str:
    blocks = f.definition.blocks
    by_label = {b.label.text: b for b in blocks if b.label is not None}
    index = {id(b): i for i, b in enumerate(blocks)}
    # Every jump goes through its own edge block, so each `phi` has one entry per predecessor, even when a `br` jumps
    # to one block twice with different arguments (design/step-7.md section 7).
    incoming: dict[int, list[tuple[str, tuple[str, ...]]]] = {i: [] for i in range(len(blocks))}
    for i, b in enumerate(blocks):
        for k, t in enumerate(b.end.targets):
            incoming[index[id(by_label[t.label.text])]].append((f'"e{i}.{k}"', tuple(_operand(b, a) for a in t.args)))
    params = ', '.join(f'{f.input_types[w]} %"@{w}"' for w in f.inputs)
    out = [f'define {f.output_type} {symbol(f.word)}({params}) {{']
    for i, b in enumerate(blocks):
        out.append(f'{_label(b)}:')
        for k, p in enumerate(b.params):
            ty = f.local_types[(i, p.text)]
            pairs = ', '.join(f'[ {args[k]}, %{edge} ]' for edge, args in incoming[i])
            out.append(f'  {_local(b, p.text)} = phi {ty} {pairs}')
        out += [_line(b, x) for x in b.lines]
        end = b.end
        if end.keyword.text == 'ret' and end.value is not None:
            out.append(f'  ret {f.output_type} {_operand(b, end.value)}')
        elif end.value is not None:
            out.append(f'  br i1 {_operand(b, end.value)}, label %"e{i}.0", label %"e{i}.1"')
        else:
            out.append(f'  br label %"e{i}.0"')
        for k, t in enumerate(end.targets):
            out += [f'"e{i}.{k}":', f'  br label %{_label(by_label[t.label.text])}']
    return '\n'.join([*out, '}']) + '\n'


def lower(program: Program) -> str:
    return '\n'.join(_function(f) for f in program.functions)


def runner(program: Program, word: str) -> str:
    """IR for a C `main` that reads one argument per input, calls `word`, and prints the result.

    An `i1` input arrives as `1` or `0` (`mime run` turns `true` and `false` into them), and an `i1` result is printed
    as `true` or `false`.
    """
    f = next(f for f in program.functions if f.word == word)
    reads, args = [], []
    for i, w in enumerate(f.inputs):
        reads += [
            f'  %slot{i} = getelementptr ptr, ptr %argv, i64 {i + 1}',
            f'  %text{i} = load ptr, ptr %slot{i}',
            f'  %arg{i} = call i64 @strtoll(ptr %text{i}, ptr null, i32 10)',
        ]
        if f.input_types[w] == 'i1':
            reads.append(f'  %bit{i} = trunc i64 %arg{i} to i1')
            args.append(f'i1 %bit{i}')
        else:
            args.append(f'i64 %arg{i}')
    call = f'  %result = call {f.output_type} {symbol(f.word)}({", ".join(args)})'
    if f.output_type == 'i1':
        show = [
            '  %word = select i1 %result, ptr @.true, ptr @.false',
            '  %printed = call i32 (ptr, ...) @printf(ptr @.string, ptr %word)',
        ]
    else:
        show = ['  %printed = call i32 (ptr, ...) @printf(ptr @.format, i64 %result)']
    body = '\n'.join([*reads, call, *show])
    return f"""{lower(program)}
@.format = private unnamed_addr constant [6 x i8] c"%lld\\0A\\00"
@.string = private unnamed_addr constant [4 x i8] c"%s\\0A\\00"
@.true = private unnamed_addr constant [5 x i8] c"true\\00"
@.false = private unnamed_addr constant [6 x i8] c"false\\00"

declare i64 @strtoll(ptr, ptr, i32)
declare i32 @printf(ptr, ...)

define i32 @main(i32 %argc, ptr %argv) {{
{body}
  ret i32 0
}}
"""
