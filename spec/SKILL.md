# mime

mime is a language where a word means only what its type and definition say. Its spelling carries nothing:
renaming every word consistently never changes a program. This is the whole language as of roadmap step 8.

## Names

- A **word** is `@` plus a name: `@number`, `@affine`. Every word has an entry, and you declare it. A name is
  `[a-z][a-z0-9_]*`.
- A **local** is `%` plus lowercase letters and digits: `%double`, `%0`. A local is a value inside one function
  body. It has no entry and no abstract.
- A **label** is `^` plus lowercase letters and digits: `^loop`, `^0`. It names a block in a body.
- A **language word** is a bare name fixed by mime: `type`, `abstract`, `define`, `ret`, `br`, `add`, `sub`, `mul`,
  `icmp`, the predicates `eq ne slt sle sgt sge ult ule ugt uge`, the types `i64` and `i1`, and `true`, `false`.

`@` marks what carries meaning and must be looked up; `%` marks what is mechanical. mime has no `$`.

## A program

A program is a list of entries: data words and function definitions.

```
@number = {type = i64, abstract = "a whole number"}

define @affine {@number} -> @number {
  %double = add i64 @number, @number
  %triple = add i64 %double, @number
  %result = add i64 %triple, 1
  ret %result
}
abstract = "three times the @number it is given, plus one"
```

**Every entry refers only to earlier entries.** Declare a word above everything that uses it. Data words and
definitions may come in any order otherwise.

A **data word** is `@word = {type = i64, abstract = "…"}`, with exactly these two keys in this order. The types are
`i64` (a 64-bit integer) and `i1` (a truth value, `true` or `false`).

A **function** is `define @f {@inputs} -> @output { … }` followed by `abstract = "…"`:

- The inputs are earlier data words, in braces: `{@number}`, `{@first, @second}`, or `{}` for none.
- The output is an earlier data word, `i64` or `i1`.
- **The inputs are the parameters.** Inside the body, `@number` is the value passed for `@number`. An input is
  always its `@` word, never a `%` local, and there is no parameter list.
- The abstract comes **after** the body, so you write it once you know what the body does.
- An optional `symbol = "name"` after the abstract exports the function under that name, for C, other modules and
  `mime run` to call. It must be a C identifier and unique, and renaming never changes it. Without it, the function
  is internal. **To run a function, export it.**

A function's type and abstract belong to its `define`. Never write `type = {@a} -> @b` in a declaration.

## Bodies

A body is lines, then `ret`:

- A line is `%result = operation i64 left, right`. The result is always a `%` local. The operations are `add`,
  `sub` and `mul`.
- An operand, and the value after `ret`, is an input (`@number`), a local bound **earlier** in the body (`%double`),
  or a decimal integer (`1`, `-7`; no leading zeros).
- **No nesting.** `%r = add i64 mul i64 @a, 2, 1` is an error: give `mul` its own line and use its local.
- No infix and no brackets: `@a + 1`, `add(i64, @a, 1)` and `add {i64, @a, 1}` are errors.
- A local is bound once and must be read later. Name locals however helps you think; different functions may use
  the same local.
- Every input must be read. If a function ignores an input, take it out of the type; a constant function has type
  `{} -> @number`.
- The body ends with exactly one `ret %value`. The type is not repeated: write `ret %x`, not `ret i64 %x`.
- Overflow wraps: `add i64 9223372036854775807, 1` is `-9223372036854775808`.
- Fields are separated by commas. No trailing comma. There are **no comments**: put English in an `abstract`.
- Strings are `"…"` on one line. Escapes: `\"`, `\\`, `\@`. A `$` needs no escape.

## Blocks and branches

```
@x  = {type = i64, abstract = "a whole number"}
@lo = {type = i64, abstract = "the smallest @x allowed"}
@hi = {type = i64, abstract = "the largest @x allowed"}

define @clamp {@x, @lo, @hi} -> i64 {
  %below = icmp slt i64 @x, @lo
  br %below, ^low{}, ^check{}
^check{}:
  %above = icmp sgt i64 @x, @hi
  br %above, ^high{}, ^keep{}
^low{}:
  ret @lo
^high{}:
  ret @hi
^keep{}:
  ret @x
}
abstract = "@x, moved into the range from @lo to @hi"
```

- The lines after `{` are the **entry block**, which has no label. Every other block starts with `^label{%a, %b}:`,
  or `^label{}:` with no parameters.
- Every block ends with exactly one terminator: `ret %v`, `br ^next{args}`, or `br %c, ^then{args}, ^else{args}`.
  Nothing follows a terminator in its block.
- **Blocks are closed.** A block sees only its own parameters, its own earlier locals, and the function's inputs.
  To use a value from another block, pass it as an argument: `br ^next{%a}` and `^next{%b}:`. A loop is a block
  that jumps back to itself, passing its new values.
- A jump passes exactly as many arguments as the block has parameters, and every block must be reached by some jump.
- `%c = icmp slt i64 %a, %b` compares two `i64` and gives an `i1`. `s` predicates are signed, `u` unsigned.
- **Types are checked.** `add`, `sub`, `mul` take `i64`; `br`'s condition is an `i1`; `ret` gives the output's type. A
  block parameter's type comes from the arguments passed to it. An `i1` is `true` or `false`, never `1` or `0`.
- The same local may be bound in two different blocks.
- Don't pass an input or a constant through a block parameter: every block can read `@n` and write `1` directly.
  A parameter that only ever carries one of them is a `redundant-parameter`.

When a function is finished, run `mime canon --locals prog.mime`. It renumbers every local `%v0`, `%v1`, … in order
of appearance, and every label `^b0`, `^b1`, …, so the stored program carries no local names. A stored body you edit later may mix numbered locals
with new named ones; run the command again when you are done.

## Not LLVM

Bodies look like LLVM IR, with these differences: an input is its `@` word (LLVM would use a `%` parameter),
operands and `ret` carry no type, there is no `phi`, `nsw` or `nuw` (overflow always wraps), and a definition's
head is its mime type (`define @f {@a} -> @r`), not `define i64 @f(i64 %a)`. `@number` in a body is a value, not a
global that needs a `load`. Labels are `^loop` (not `%loop` or `loop:`), a jump is `br ^loop{%x}` (not
`br label %loop`), and the condition of `br` takes no type (`br %c, …`, not `br i1 %c, …`).

## References in abstracts

Inside an `abstract`, `@word` is a **checked reference**. The English around it is never read.

- An abstract may refer only to **earlier** entries, data words or functions.
- It may not refer to its own word. A `%` local can never be referenced: `%` in an abstract is plain text.
- Every `@` in an abstract starts a reference. Write `\@` for an at sign: `"at \@ 5 each"`, `"help\@example"`.
- A reference follows the same name rule as in code: `"@number's"` and `"(@number)"` are fine, but `"@numberX"` and
  `"@number-ish"` are errors, not `@number` followed by text.
- References are optional, but **mark every mention of a word with `@`**, even in passing: `"like @double"`, not
  `"like double"`. An unmarked mention is plain English: it is not checked, and renaming does not change it.

## Commands

```
mime check prog.mime                 # report every mistake, as a JSON array
mime run prog.mime affine 5          # run the function exported as `affine` on 5, by its symbol, not its
                                     # word: one argument per input; true or false for an i1
                                     # a run stops after 10 s (--timeout SECONDS), in case a loop never exits
mime run --backend llvm prog.mime affine 5   # the same, built natively with clang; the default, interp, needs none
mime llvm prog.mime                  # print the LLVM IR
mime show prog.mime @affine          # print the entry for @affine, exactly as written
mime uses prog.mime @number          # list every reference to @number (or to a local, %double), as JSON
mime rename prog.mime @a @b          # rename @a to @b everywhere, abstracts included; also %x %y and ^a ^b
mime fmt prog.mime                   # rewrite the file in its one layout
mime canon --locals prog.mime        # rewrite the file with its locals numbered, and print it
mime canon prog.mime                 # print the canonical form: words @w0, @w1, ..., locals numbered
```

Words need no quotes on the command line. Use `show`, `uses` and `rename` instead of `grep` or `sed`: they follow
mime's rules, so `\@number` in an abstract is not a use, and each use names its `entry` and `key`. They work on a
program with checker errors. `show` prints a function's whole definition, from `define` through its abstract.

`mime run` exits with 0 and prints the result, or exits with 1 and prints the program's diagnostics on stderr. A
trap, when an operation leaves its domain (none can yet), exits with 3 and prints one JSON object on stderr, with
the fields below and `kind` `trap`: its `text` is the line that trapped.

Each diagnostic has a `kind`, the `entry` and `key` it is in (`type`, `abstract`, or `body`), the exact source
`text` at fault, a `message`, and usually a `hint` that names the fix. A field that does not apply is `null`. To
fix a mistake, find `text` inside that entry's field and replace it.

```json
[
  {
    "kind": "undeclared-word",
    "entry": "@affine",
    "key": "type",
    "text": "@numbr",
    "message": "no entry declares `@numbr`",
    "hint": "did you mean `@number`?"
  }
]
```
