"""Lower a checked program to textual LLVM IR (design/step-4.md section 5, step-7.md section 7).

Lowering copies the names of the canonical form (design/step-5.md, step-6.md): an input is `%w0`, a local `%v0`, a
block `b0`. Each kind has its own prefix, so no name needs quoting, renumbering, or a check for clashes, and the IR
reads with the same names as `mime canon`. A function is exported under its `symbol`, or is internal to its module
as `@mime.word`.
"""

from mime.checker import Function, Program
from mime.lexer import Tok
from mime.parser import Block, Call, Line, Value
from mime.printer import Names, canonical_names, pass_throughs


def symbol(f: Function) -> str:
    """The function's LLVM name: its `symbol`, or `mime.word`. A `.` cannot appear in a C symbol, so an internal name
    never clashes with an exported one or with the runner's own, and the word's `@` is left out because an ELF linker
    reads an `@` inside a symbol as a version."""
    return f'@{f.symbol}' if f.symbol is not None else f'@mime.{f.word}'


class _Function:
    def __init__(self, f: Function, names: Names, index: int, functions: dict[str, Function]) -> None:
        self.f = f
        self.functions = functions
        self.names = names
        self.index = index
        self.blocks = f.definition.blocks
        self.by_label = {b.label.text: i for i, b in enumerate(self.blocks) if b.label is not None}
        # A parameter that only carries one value is that value: its block's dominator defines it, so it needs no `phi`.
        self.through = set(pass_throughs(f.definition))

    def label(self, i: int) -> str:
        b = self.blocks[i]
        return 'entry' if b.label is None else self.names.label(self.index, b.label.text)

    def operand(self, i: int, v: Value) -> str:
        if v.kind == Tok.WORD:
            return f'%{self.names.word(v.text)}'
        if v.kind == Tok.LOCAL:
            return f'%{self.names.local(self.index, i, v.text)}'
        return v.text  # an integer, `true` or `false`

    def needs_edges(self, i: int) -> bool:
        """A two-way `br` whose arms reach the same block with parameters goes through two edge blocks, so each `phi`
        has one entry per predecessor (design/step-7.md section 7)."""
        end = self.blocks[i].end
        if end.keyword.text != 'br' or end.value is None:
            return False
        first, second = end.targets
        target = self.blocks[self.by_label[first.label.text]]
        return first.label.text == second.label.text and any(
            (self.by_label[first.label.text], p.text) not in self.through for p in target.params
        )

    def edge(self, i: int, k: int) -> str:
        return f'{self.label(i)}.e{k}'

    def text(self) -> str:
        incoming: dict[int, list[tuple[str, list[str]]]] = {j: [] for j in range(len(self.blocks))}
        for i, b in enumerate(self.blocks):
            for k, t in enumerate(b.end.targets):
                source = self.edge(i, k) if self.needs_edges(i) else self.label(i)
                incoming[self.by_label[t.label.text]].append((source, [self.operand(i, a) for a in t.args]))
        params = ', '.join(f'{self.f.input_types[w]} %{self.names.word(w)}' for w in self.f.inputs)
        linkage = '' if self.f.symbol is not None else 'internal '
        out = [f'define {linkage}{self.f.output_type} {symbol(self.f)}({params}) {{']
        for i, b in enumerate(self.blocks):
            if b.label is not None:
                canonical = self.label(i)
                note = f'{" " * 40}; ^{b.label.text}' if b.label.text != canonical else ''
                out.append(f'{canonical}:{note}'.rstrip() if note else f'{canonical}:')
            elif any(self.by_label.get(t.label.text) is not None for t in b.end.targets):
                out.append('entry:')
            for k, p in enumerate(b.params):
                if (i, p.text) in self.through:
                    continue
                ty = self.f.local_types[(i, p.text)]
                pairs = ', '.join(f'[ {args[k]}, %{source} ]' for source, args in incoming[i])
                out.append(f'  %{self.names.local(self.index, i, p.text)} = phi {ty} {pairs}')
            out += [self.line(i, x) for x in b.lines]
            out += self.end(i, b)
        return '\n'.join([*out, '}']) + '\n'

    def line(self, i: int, x: Line | Call) -> str:
        result = f'%{self.names.local(self.index, i, x.result.text)}'
        if isinstance(x, Call):
            # The arguments are in the callee's input order, which the checker ensures, so they are passed as written.
            # No check guards the depth: a native stack that overflows stops the program (design/step-9.md section 6).
            g = self.functions[x.callee.text]
            args = ', '.join(f'{g.input_types[a.key.text]} {self.operand(i, a.value)}' for a in x.args)
            return f'  {result} = call {g.output_type} {symbol(g)}({args})'
        # No `nsw` or `nuw` flag, so overflow wraps.
        op = f'icmp {x.predicate.text}' if x.predicate is not None else x.operation.text
        left, right = self.operand(i, x.left), self.operand(i, x.right)
        return f'  {result} = {op} i64 {left}, {right}'

    def end(self, i: int, b: Block) -> list[str]:
        e = b.end
        if e.keyword.text == 'ret' and e.value is not None:
            return [f'  ret {self.f.output_type} {self.operand(i, e.value)}']
        edges = self.needs_edges(i)
        labels = [
            f'label %{self.edge(i, k) if edges else self.label(self.by_label[t.label.text])}'
            for k, t in enumerate(e.targets)
        ]
        head = (
            f'  br i1 {self.operand(i, e.value)}, {", ".join(labels)}' if e.value is not None else f'  br {labels[0]}'
        )
        out = [head]
        if edges:
            for k, t in enumerate(e.targets):
                out += [f'{self.edge(i, k)}:', f'  br label %{self.label(self.by_label[t.label.text])}']
        return out


def lower(program: Program) -> str:
    names = canonical_names(program.module)
    index = {id(x): i for i, x in enumerate(program.module.items)}
    functions = {f.word: f for f in program.functions}
    return '\n'.join(_Function(f, names, index[id(f.definition)], functions).text() for f in program.functions)


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
    call = f'  %result = call {f.output_type} {symbol(f)}({", ".join(args)})'
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
