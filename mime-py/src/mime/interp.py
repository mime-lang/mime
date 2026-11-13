"""The reference interpreter: the second backend, which walks the checked form block by block (design/step-8.md).

It assumes everything the checker proves (step-8.md section 1): every operand is bound and has its type, every jump
passes as many arguments as its target has parameters, and every call names a function and fills each of its inputs.
It never prints a name, so it reads every name as written.
"""

import time
from dataclasses import dataclass, field

from mime.checker import I64_MIN, Function, Program
from mime.diag import Diagnostic, Trap
from mime.lexer import Tok
from mime.parser import Line, Value
from mime.words import DIVISIONS, SIGNED_DIVISIONS

BITS = 64
MODULUS = 2**BITS
SIGN = 2 ** (BITS - 1)

type Scalar = int | bool  # an `i64` is a Python integer in [-2^63, 2^63), an `i1` is True or False


def wrap(n: int) -> int:
    """`n` modulo 2^64, as a signed `i64`: overflow wraps (design/step-3.md)."""
    n %= MODULUS
    return n - MODULUS if n >= SIGN else n


def unsigned(n: int) -> int:
    return n % MODULUS


COMPARE = {
    'eq': lambda a, b: a == b,
    'ne': lambda a, b: a != b,
    'slt': lambda a, b: a < b,
    'sle': lambda a, b: a <= b,
    'sgt': lambda a, b: a > b,
    'sge': lambda a, b: a >= b,
    'ult': lambda a, b: unsigned(a) < unsigned(b),
    'ule': lambda a, b: unsigned(a) <= unsigned(b),
    'ugt': lambda a, b: unsigned(a) > unsigned(b),
    'uge': lambda a, b: unsigned(a) >= unsigned(b),
}


def sdiv(a: int, b: int) -> int:
    """`a / b` rounded toward zero, as LLVM and C do, not down as Python's `//` does (design/step-13.md). The caller
    has ruled out the smallest i64 divided by -1, which traps (design/step-14.md)."""
    q = abs(a) // abs(b)
    return wrap(q if (a < 0) == (b < 0) else -q)


def srem(a: int, b: int) -> int:
    """The remainder of `sdiv`, with the sign of `a`."""
    return wrap(a - sdiv(a, b) * b)


OPERATE = {
    'add': lambda a, b: wrap(a + b),
    'sub': lambda a, b: wrap(a - b),
    'mul': lambda a, b: wrap(a * b),
    'sdiv': sdiv,
    'srem': srem,
    'udiv': lambda a, b: wrap(unsigned(a) // unsigned(b)),
    'urem': lambda a, b: wrap(unsigned(a) % unsigned(b)),
}
LOGIC = {
    'and': lambda a, b: a and b,
    'or': lambda a, b: a or b,
    'xor': lambda a, b: a != b,
}


def trap(program: Program, f: Function, line: Line, message: str) -> Trap:
    """The trap of `line` in `f`, reported the same way on every backend (design/step-8.md section 4): the line is
    named by its function and its text as written."""
    start, end = line.result.span, line.right.span
    text = program.module.source[start.start : end.end]
    return Trap(Diagnostic('trap', message, start.line, start.column, None, f'@{f.word}', 'body', text))


class _Domain(Exception):  # noqa: N818 - the line left its operation's domain; `interpret` names the line
    pass


# The interpreter's own limit on nested calls, not the spec's: the spec fixes no depth (design/step-9.md section 5).
# It ends an endless recursion at once, instead of filling memory until the timeout.
FRAMES = 100_000


class Timeout(Exception):  # noqa: N818 - it is what happened, not an error of the program
    """The run passed its deadline. Checked at every jump and call, since only they can repeat work."""


class StackOut(Exception):  # noqa: N818 - it is what happened, not an error of the program
    """More calls were nested than the interpreter holds."""


@dataclass
class _Frame:
    """One active call: its function, its inputs, and where it is."""

    f: Function
    inputs: dict[str, Scalar]
    block: int = 0
    line: int = 0  # the next line to run in the block
    table: dict[str, Scalar] = field(default_factory=dict)  # the block's parameters and locals, by name

    def read(self, v: Value) -> Scalar:
        if v.kind == Tok.WORD:
            return self.inputs[v.text]
        if v.kind == Tok.LOCAL:
            return self.table[v.text]
        if v.kind == Tok.NAME:
            return v.text == 'true'
        return int(v.text)


def _line(frame: _Frame, x: Line) -> Scalar:
    left, right = frame.read(x.left), frame.read(x.right)
    op = x.operation.text
    if op in LOGIC:
        return LOGIC[op](bool(left), bool(right))
    assert isinstance(left, int), 'checked: both sides are i64'  # noqa: S101
    assert isinstance(right, int), 'checked: both sides are i64'  # noqa: S101
    if x.predicate is not None:
        return COMPARE[x.predicate.text](left, right)
    if op in DIVISIONS and right == 0:
        msg = f'`{op}` by zero'
        raise _Domain(msg)
    if op in SIGNED_DIVISIONS and left == I64_MIN and right == -1:
        msg = f'`{op}` overflow'
        raise _Domain(msg)
    return OPERATE[op](left, right)


def interpret(program: Program, f: Function, values: list[Scalar], deadline: float) -> Scalar:
    """Run `f` on `values`, one per input in order, and return its result.

    Raises Timeout past `deadline`, and StackOut past FRAMES nested calls. The interpreter keeps its own stack of
    frames, so Python's recursion limit plays no part.
    """
    functions = {g.word: g for g in program.functions}
    labels = {g.word: {b.label.text: i for i, b in enumerate(g.definition.blocks) if b.label is not None}
              for g in program.functions}  # fmt: skip
    stack = [_Frame(f, dict(zip(f.inputs, values, strict=True)))]
    while True:
        frame = stack[-1]
        b = frame.f.definition.blocks[frame.block]
        if frame.line < len(b.lines):
            x = b.lines[frame.line]
            if isinstance(x, Line):
                try:
                    frame.table[x.result.text] = _line(frame, x)
                except _Domain as e:
                    raise trap(program, frame.f, x, str(e)) from None
                frame.line += 1
                continue
            # A call: the caller resumes at this line when the callee returns.
            if len(stack) >= FRAMES:
                raise StackOut
            if time.monotonic() > deadline:
                raise Timeout
            callee = functions[x.callee.text]
            stack.append(_Frame(callee, {a.key.text: frame.read(a.value) for a in x.args}))
            continue
        end = b.end
        if end.keyword.text == 'ret':
            assert end.value is not None  # noqa: S101
            value = frame.read(end.value)
            stack.pop()
            if not stack:
                return value
            caller = stack[-1]
            call = caller.f.definition.blocks[caller.block].lines[caller.line]
            caller.table[call.result.text] = value
            caller.line += 1
            continue
        target = end.targets[0] if end.value is None or frame.read(end.value) else end.targets[1]
        args = [frame.read(a) for a in target.args]
        frame.block = labels[frame.f.word][target.label.text]
        frame.line = 0
        # Blocks are closed: a jump starts a new table, from the target's parameters alone.
        params = frame.f.definition.blocks[frame.block].params
        frame.table = {p.text: a for p, a in zip(params, args, strict=True)}
        if time.monotonic() > deadline:
            raise Timeout
