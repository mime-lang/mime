"""The language words (design/step-4.md). They are fixed by the spec and never renamed."""

KEYS = ('type', 'abstract')  # a declaration's keys, in this order
TYPES = frozenset({'i64'})
DEFINE, RET = 'define', 'ret'
OPERATIONS = frozenset({'add', 'sub', 'mul'})

LANGUAGE_WORDS = frozenset(KEYS) | TYPES | OPERATIONS | {DEFINE, RET}

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
    'phi': 'use block parameters; they arrive in step 8',
    'nsw': 'overflow always wraps, so there is no flag',
    'nuw': 'overflow always wraps, so there is no flag',
    'label': "write the block's word",
}
