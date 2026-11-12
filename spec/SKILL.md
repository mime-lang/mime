# mime

mime is a language where a word means only what its type and definition say. Its spelling carries nothing:
renaming every word consistently never changes a program. This is the whole language as of roadmap step 4.

## Words

- A **domain word** is `$` plus a name: `$number`, `$affine`. You declare these.
- A **language word** is a bare name fixed by mime: `type`, `abstract`, `define`, `ret`, `add`, `sub`, `mul`,
  `i64`.
- A name is `[a-z][a-z0-9_]*`.

## A program

A program is a list of entries: data words and function definitions.

```
$number = {type = i64, abstract = "a whole number"}

define $affine {$number} -> $number {
  $double = add i64 $number, $number
  $triple = add i64 $double, $number
  $result = add i64 $triple, 1
  ret $result
}
abstract = "three times the $number it is given, plus one"
```

**Every entry refers only to earlier entries.** Declare a word above everything that uses it. Data words and
definitions may come in any order otherwise.

A **data word** is `$word = {type = i64, abstract = "…"}`, with exactly these two keys in this order. `i64` is the
only type so far.

A **function** is `define $f {$inputs} -> $output { … }` followed by `abstract = "…"`:

- The inputs are earlier data words, in braces: `{$number}`, `{$first, $second}`, or `{}` for none.
- The output is an earlier data word or `i64`.
- **The inputs are the parameters.** Inside the body, `$number` is the value passed for `$number`. There is no
  `input` and no parameter list.
- The abstract comes **after** the body, so you write it once you know what the body does.

A function's type and abstract belong to its `define`. Never write `type = {$a} -> $b` in a declaration.

## Bodies

A body is lines, then `ret`:

- A line is `$result = operation i64 left, right`. The operations are `add`, `sub` and `mul`.
- An operand, and the value after `ret`, is an input, a result bound **earlier** in the same body, or a decimal
  integer (`1`, `-7`; no leading zeros).
- **No nesting.** `$r = add i64 mul i64 $a, 2, 1` is an error: give `mul` its own line and use its result.
- No infix and no brackets: `$a + 1`, `add(i64, $a, 1)` and `add {i64, $a, 1}` are errors.
- A result has no abstract. It must be new in its body, must not be a declared word, and must be read later.
  Different functions may use the same result word.
- Every input must be read. If a function ignores an input, take it out of the type; a constant function has type
  `{} -> $number`.
- The body ends with exactly one `ret $value`. The type is not repeated: write `ret $x`, not `ret i64 $x`.
- Overflow wraps: `add i64 9223372036854775807, 1` is `-9223372036854775808`.
- Fields are separated by commas. No trailing comma. There are **no comments**: put English in an `abstract`.
- Strings are `"…"` on one line. Escapes: `\"`, `\\`, `\$`.

## Not LLVM

Bodies look like LLVM IR, with these differences: words are `$x` (never `%x` or `@f`), operands and `ret` carry no
type, there is no `phi`, `nsw` or `nuw` (overflow always wraps), and a definition's head is its mime type
(`define $f {$a} -> $r`), not `define i64 @f(i64 %a)`.

## References in abstracts

Inside an `abstract`, `$word` is a **checked reference**. The English around it is never read.

- An abstract may refer only to **earlier** entries, data words or functions.
- It may not refer to its own word, or to the results in a body.
- Every `$` in an abstract starts a reference. Write `\$` for a dollar sign: `"costs \$5"`.
- A reference follows the same name rule as in code: `"$number's"` and `"($number)"` are fine, but `"$numberX"` and
  `"$number-ish"` are errors, not `$number` followed by text.
- References are optional.

## Commands

```
mime check prog.mime                 # report every mistake, as a JSON array
mime run prog.mime '$affine' 5       # run $affine on 5: one decimal integer per input
mime llvm prog.mime                  # print the LLVM IR
mime show prog.mime '$affine'        # print the entry for $affine, exactly as written
mime uses prog.mime '$number'        # list every reference to $number, as a JSON array
```

Use `show` and `uses` instead of `grep` or `sed`: they follow mime's rules, so `\$number` in an abstract is not a
use, and each use names its `entry` and `key`. Both work on a program with checker errors. `show` prints a
function's whole definition, from `define` through its abstract.

On the command line, write the word as in the source and in **single quotes**: `'$affine'`. Without them, a shell
expands `$affine` as a variable before mime sees it.

Each diagnostic has a `kind`, the `entry` and `key` it is in (`type`, `abstract`, or `body`), the exact source
`text` at fault, a `message`, and usually a `hint` that names the fix. A field that does not apply is `null`. To
fix a mistake, find `text` inside that entry's field and replace it.

```json
[
  {
    "kind": "undeclared-word",
    "entry": "$affine",
    "key": "type",
    "text": "$numbr",
    "message": "no entry declares `$numbr`",
    "hint": "did you mean `$number`?"
  }
]
```
