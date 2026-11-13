"""The reference interpreter: the second backend, which walks the checked form block by block (design/step-8.md).

It assumes everything the checker proves (step-8.md section 1): every operand is bound and has its type, every jump
passes as many arguments as its target has parameters, and every call names a function and fills each of its inputs.
It never prints a name, so it reads every name as written.
"""

import time
from dataclasses import dataclass, field

from mime.checker import Function, Program
from mime.lexer import Tok
from mime.parser import Line, Value

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
OPERATE = {
    'add': lambda a, b: wrap(a + b),
    'sub': lambda a, b: wrap(a - b),
    'mul': lambda a, b: wrap(a * b),
}


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
    assert isinstance(left, int), 'checked: both sides are i64'  # noqa: S101
    assert isinstance(right, int), 'checked: both sides are i64'  # noqa: S101
    if x.predicate is not None:
        return COMPARE[x.predicate.text](left, right)
    return OPERATE[x.operation.text](left, right)


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
                frame.table[x.result.text] = _line(frame, x)
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
