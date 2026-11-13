"""The reference interpreter: the second backend, which walks the checked form block by block (design/step-8.md).

It assumes everything the checker proves (step-8.md section 1): every operand is bound and has its type, and every
jump passes as many arguments as its target has parameters. It never prints a name, so it reads every name as written.
"""

import time

from mime.checker import Function
from mime.lexer import Tok
from mime.parser import Value

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


class Timeout(Exception):  # noqa: N818 - it is what happened, not an error of the program
    """The run passed its deadline. Checked at every jump, since only a jump can repeat work."""


def interpret(f: Function, values: list[Scalar], deadline: float) -> Scalar:
    """Run `f` on `values`, one per input in order, and return its result; raise Timeout past `deadline`."""
    blocks = f.definition.blocks
    by_label = {b.label.text: i for i, b in enumerate(blocks) if b.label is not None}
    inputs = dict(zip(f.inputs, values, strict=True))
    block, table = 0, {}  # table: the current block's parameters and locals, by name
    while True:
        b = blocks[block]

        def read(v: Value, table: dict[str, Scalar] = table) -> Scalar:
            if v.kind == Tok.WORD:
                return inputs[v.text]
            if v.kind == Tok.LOCAL:
                return table[v.text]
            if v.kind == Tok.NAME:
                return v.text == 'true'
            return int(v.text)

        for x in b.lines:
            left, right = read(x.left), read(x.right)
            assert isinstance(left, int), 'checked: both sides are i64'  # noqa: S101
            assert isinstance(right, int), 'checked: both sides are i64'  # noqa: S101
            if x.predicate is not None:
                table[x.result.text] = COMPARE[x.predicate.text](left, right)
            else:
                table[x.result.text] = OPERATE[x.operation.text](left, right)
        end = b.end
        if end.keyword.text == 'ret':
            assert end.value is not None  # noqa: S101
            return read(end.value)
        target = end.targets[0] if end.value is None or read(end.value) else end.targets[1]
        args = [read(a) for a in target.args]
        block = by_label[target.label.text]
        # Blocks are closed: a jump starts a new table, from the target's parameters alone.
        table = {p.text: a for p, a in zip(blocks[block].params, args, strict=True)}
        if time.monotonic() > deadline:
            raise Timeout
