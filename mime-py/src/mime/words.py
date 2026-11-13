"""The language words (design/step-4.md). They are fixed by the spec and never renamed."""

KEYS = ('type', 'abstract')  # a declaration's keys, in this order
TYPES = frozenset({'i64', 'i1'})
DEFINE, DECLARE, RET, BR, ICMP, CALL = 'define', 'declare', 'ret', 'br', 'icmp', 'call'
TRUE, FALSE = 'true', 'false'
PREDICATES = frozenset({'eq', 'ne', 'slt', 'sle', 'sgt', 'sge', 'ult', 'ule', 'ugt', 'uge'})
ARITHMETIC = frozenset({'add', 'sub', 'mul', 'sdiv', 'udiv', 'srem', 'urem'})  # on `i64`
DIVISIONS = frozenset({'sdiv', 'udiv', 'srem', 'urem'})  # partial: a zero divisor traps (design/step-13.md)
LOGIC = frozenset({'and', 'or', 'xor'})  # on `i1`
OPERATIONS = ARITHMETIC | LOGIC

LANGUAGE_WORDS = frozenset(KEYS) | TYPES | OPERATIONS | PREDICATES | {DEFINE, DECLARE, RET, BR, ICMP, CALL, TRUE, FALSE}

# Words of steps 1 to 3 that step 4 replaced, with the hint that names the replacement.
RETIRED = {
    'description': 'renamed: write `abstract`',
    'sort': 'renamed: write `type`',
    'takes': 'a function is written as a `define`: `define @f {@a} -> @r {…}`',
    'returns': 'a function is written as a `define`: `define @f {@a} -> @r {…}`',
    'body': 'a function is written as a `define`: `define @f {@a} -> @r {…}`',
    'input': 'the inputs are the words of the type, such as `@number`',
    'let': 'write `%x = add i64 %a, %b`',
    'in': 'write `%x = add i64 %a, %b`',
}
# LLVM words a model may bring along, with the mime form.
LLVM_HABITS = {
    'phi': 'use block parameters: `^loop{%a, %b}:`, and pass values with `br ^loop{%x, %y}`',
    'nsw': 'overflow always wraps, so there is no flag',
    'nuw': 'overflow always wraps, so there is no flag',
    'label': 'write the block: `br ^b{}`',
}
# Operations of other languages, with the mime operation (design/step-13.md section 5).
OPERATION_HABITS = {
    'div': 'write `sdiv i64` (signed) or `udiv i64` (unsigned)',
    'idiv': 'write `sdiv i64` (signed) or `udiv i64` (unsigned)',
    'mod': 'write `srem i64` (signed, with the sign of the dividend) or `urem i64`',
    'rem': 'write `srem i64` (signed, with the sign of the dividend) or `urem i64`',
    'not': 'write `xor i1 %c, true`',
}
