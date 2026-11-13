# Step 7: branches

> Status: settled. The seventh step of the [roadmap](roadmap.md). It adds comparisons (`icmp`), the `i1` type, and
> the blocks and `br` of [layout.md](layout.md) section 5, with block labels written `^label` as in MLIR.

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

## 1. Lexical rules

- A **label** is `^` followed by lowercase letters and digits, `^[a-z0-9]+`, like a local: `^loop`, `^0`.
- New language words: `icmp`, `br`, `true`, `false`, `i1`, and the ten predicates `eq`, `ne`, `slt`, `sle`, `sgt`,
  `sge`, `ult`, `ule`, `ugt`, `uge`, LLVM's own.
- A block's parameters and a jump's arguments go in braces, `{…}`, as a function's inputs do: a block is a small
  function, so the same bracket means "the values this receives". `:` ends a block's label. `(` and `)` are still not
  in the grammar; `^loop(%a)` gets the hint "write `^loop{%a}`".

## 2. Grammar

```
body       = line* terminator block*
block      = label "{" [local ("," local)*] "}" ":" line* terminator
line       = local "=" name type atom "," atom
           | local "=" "icmp" predicate type atom "," atom
terminator = "ret" atom
           | "br" target
           | "br" atom "," target "," target
target     = label "{" [atom ("," atom)*] "}"
atom       = word | local | integer | "true" | "false"
```

- The lines after `{` are the **entry block**. It has no label, so nothing can jump to it, as in LLVM.
- The body keeps its braces, though the abstract that must follow it would be enough to end it. `define … {` is
  LLVM's form and every C-like language's, so a model writes the braces anyway; the `}` shows where a body of many
  blocks ends; and `{}` already means a group in mime: an entry's fields, a function's inputs, a block's parameters.
- Every other block starts with its label and parameters, `^loop{%a, %b}:`, or `^done{}:` with none.
- Every block ends with exactly one terminator, and nothing follows it in its block.
- `br ^b{args}` jumps to a block. `br %c, ^t{args}, ^f{args}` jumps to `^t` when `%c` is `true` and to `^f`
  otherwise. The arguments are bound to the target's parameters, in order.

## 3. Blocks

- **A block is closed.** It sees its own parameters, its own earlier results, and the function's inputs. Anything
  else must be passed as an argument. There are no dominance rules, so each block can be read and checked on its
  own, like a small function (layout.md section 5).
- A local is bound at most once in each block. The same local may be bound in different blocks ([step-6.md](step-6.md)
  section 4).
- Every label is unique in its body. Every block is reached by some `br` from a block that is reached, starting at
  the entry; a block that is not is `unreachable-block`.
- A jump passes exactly as many arguments as the target has parameters.
- Every parameter and every result is read, as before (`unused-local`).

## 4. Types: `i64` and `i1`

Every value now has one of two types. The checker works them out and reports a mismatch as `wrong-type`.

- `i1` is a new type, for truth values. Its two values are `true` and `false`. A data word may have type `i1`, and so
  may a function's output: `define @sorted {...} -> i1` or `-> @flag` with `@flag = {type = i1, ...}`.
- `add`, `sub` and `mul` take and give `i64`. `icmp` takes two `i64` and gives `i1`.
- An input has its data word's type. An integer is an `i64`; `true` and `false` are `i1`. An integer where an `i1`
  belongs gets the hint "write `true` or `false`".
- **A block parameter's type is inferred** from the arguments the jumps pass to it, and they must agree. Types stay
  on operations only, as in step 4. A parameter that no jump gives a type, because every jump passes it to itself,
  is a `wrong-type` with the hint to pass it a value.
- The condition of `br` is an `i1`. The value of `ret` has the function's output type.

## 5. Comparisons

`%c = icmp slt i64 %a, %b` compares two `i64`, as LLVM does. `s` predicates compare as signed numbers and `u`
predicates as unsigned ones: `-1` is the smallest signed `i64` but the largest unsigned one. Every predicate is
total, so `icmp` never traps.

## 6. Canonical form

`mime canon` and `mime canon --locals` number labels and locals per body, apart from each other:

- Labels become `^0`, `^1`, … in order of first appearance.
- Locals become `%0`, `%1`, … in order of first appearance, across all blocks, as step 6 says, with its
  pass-through rule: a block parameter whose every incoming argument is the same value, or the parameter itself on
  a back edge, gets that value's number. So a value that a loop carries unchanged keeps one name everywhere.

```
define @w3 {@w0, @w1, @w2} -> i64 {
  %0 = icmp slt i64 @w0, @w1
  br %0, ^0{}, ^1{}
^1{}:
  %1 = icmp sgt i64 @w0, @w2
  br %1, ^2{}, ^3{}
^0{}:
  ret @w1
^2{}:
  ret @w2
^3{}:
  ret @w0
}
```

`mime rename` takes labels too: `mime rename prog.mime ^low ^under`.

## 7. Running and lowering

- `mime run` takes `true` or `false` for an `i1` input, and prints `true` or `false` for an `i1` result.
- A loop may never reach its exit, so `mime run` stops a run after 10 seconds by default (`--timeout SECONDS`) and
  says so, rather than hanging the agent that called it.
- Each block becomes an LLVM basic block, and its parameters become `phi` nodes. Every jump goes through its own
  small edge block, so that a `br` whose two targets are the same block, with different arguments, still gives each
  `phi` one entry per predecessor.
- A local is named after its block in LLVM, `%"^loop%a"`, since the same local may be bound in two blocks.

## 8. Diagnostics

| Kind | When |
|---|---|
| `wrong-type` | an `i1` where an `i64` belongs or the reverse, in an operand, a condition, a `ret`, or a jump argument |
| `unreachable-block` | a block that no `br` from a reached block jumps to |
| `undeclared-word` | a `br` to a label that has no block |
| `duplicate-word` | two blocks with one label |
| `bad-value` | a jump with the wrong number of arguments, an unknown predicate, a type other than `i64` on an operation |
| `syntax` | a block without a terminator, a line after one, or a label without its `{}` |

LLVM habits get hints: `br label %b` ("write the block: `br ^b{}`"), `br i1 %c, …` ("the condition needs no type"),
`%loop:` and `loop:` ("a block label is written `^loop{}:`"), and `^loop:` ("write `^loop{}:`").

## 9. Model ease

- **Familiar:** LLVM's `icmp` and `br`, MLIR's `^label{%a, %b}` blocks with parameters, `true` and `false`.
- **New:** blocks are closed, so a value from another block must be passed as an argument; parameter types are
  inferred; the condition of `br` takes no type.
- **How mistakes surface:** a value read in the wrong block is reported as unbound, with the hint to pass it as an
  argument; an `i1` used as a number is `wrong-type`; a missing jump is `unreachable-block`. *To measure:* argument
  swaps in `br`, since two `i64` arguments in the wrong order are both valid.
