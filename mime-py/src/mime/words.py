"""The language words. They are fixed by the spec and never renamed."""

SORT_KEYS = ('description', 'sort')
FUNCTION_KEYS = ('description', 'takes', 'returns', 'body')
KEYS = frozenset(SORT_KEYS + FUNCTION_KEYS)

SORTS = frozenset({'i64'})
INPUT = 'input'

LET, IN = 'let', 'in'
OPERATIONS = frozenset({'add', 'sub', 'mul'})  # step 3

LANGUAGE_WORDS = KEYS | SORTS | OPERATIONS | {INPUT, LET, IN}
