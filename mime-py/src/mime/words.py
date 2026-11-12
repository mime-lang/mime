"""The language words of step 1. They are fixed by the spec and never renamed."""

SORT_KEYS = ('description', 'sort')
FUNCTION_KEYS = ('description', 'takes', 'returns', 'body')
KEYS = frozenset(SORT_KEYS + FUNCTION_KEYS)

SORTS = frozenset({'i64'})
INPUT = 'input'

LANGUAGE_WORDS = KEYS | SORTS | {INPUT}
