# Module layout and bodies

> Status: settled. Implemented by roadmap step 4, except where a section names a later step. It replaces the entry
> keys of [step-1.md](step-1.md) (`description`, `sort`, `takes`, `returns`) and the `let … in` bodies of
> [step-3.md](step-3.md), and it settles [core.md](core.md) open questions 2 and 3.
>
> From step 6 ([step-6.md](step-6.md)), words are written `@word` and locals `%local`. The examples here use the
> step 4 form, `$` for both.

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

## 1. Three sections

A module has three sections, always in this order:

1. **Imports:** the words it uses from other modules.
2. **Entries:** every word the module introduces. A data word is a declaration (section 3), and a function word
   is a definition, with its type, body and abstract in one place (section 4). The two kinds may come in any order.
3. **Exports:** the words other modules may import.

**Every entry refers only to earlier entries,** whatever their kind: a type, an input, an output or an abstract
names only words declared or defined above it. So a module reads top to bottom like a mathematical text, and the
hint for a word used too early is always the same: move its entry above. Two things are not entries that refer
backward ([step-9.md](step-9.md) section 4): a body may call its own function, which is recursion, and
`declare @f {inputs} -> output` gives a later function's head early, for mutual recursion. A word declared so
counts as declared from its `declare` on.

Imports and exports arrive with the modules step, which fixes their syntax. Until then a module has only
entries, and `mime run` runs a function by its `symbol` ([step-8.md](step-8.md) section 3).

## 2. Meaning

A word's meaning comes from three places, in a fixed order of authority:

| | 1. `type` | 2. definition | 3. `abstract` |
|---|---|---|---|
| Written | first | second | last |
| Checked | against every use | against the type | its references only |
| Role | the contract that always holds | the meaning | stands in for the definition where it is not in view |

When a body is in view, it wins over the English. When it is not, as for a word an importer uses, the abstract
stands in for it, and the linker eventually binds the word to its definition. Writing order, checking strength and
authority line up, and the unchecked English is always written last, after everything it describes. A model writing
an abstract can see exactly what it built.

## 3. Declarations

```
$first  = {type = i64, abstract = "the first number"}
$second = {type = i64, abstract = "the second number"}
$pair   = {type = {$first, $second}, abstract = "a $first and a $second"}
```

- A **data word** is `$w = {type = T, abstract = "…"}`, in that key order. It has no body, so its entry is its
  definition, and its abstract follows the type it describes.
- **`type` is the type of the word's values:** a primitive (`i64`) or a struct of words (`{$first, $second}`,
  which arrives with structs). A function type is written in its definition (section 4), never here: `type = {$n} -> $n` in a
  declaration gets "a function is written as a `define`".
- **A word in a type is nominal.** `$point` and `$vector` may both have type `{$x, $y}` and are still different
  types, because the word decides (core section 9). Type checking arrives with types.
- **The words in a type are data words.** A function word there would mean a function value, which mime cannot
  express yet.
- A word is declared once. A declaration refers only to earlier entries, never to itself. How a data word refers
  to itself, as a list does, is decided with structs.

## 4. Definitions

```
define $gcd {$first, $second} -> $number {
  …
}
abstract = "the greatest common divisor of a $first and a $second"
```

- A definition is `define`, the function's word, its type, its body in `{…}`, and then `abstract = "…"`.
- **`symbol = "name"`** may follow the abstract. It is the name the function is exported under, a C identifier
  unique in the module and not `main`. A function without one is internal to its module. A symbol is data, not a
  word: renaming and `mime canon` never change it, so what links to a function stays stable however its word is
  spelled. (Chosen over `link`, which also reads as a verb, a library or a URL.)
- **The type is `{inputs} -> output`.** The inputs are a struct of data words, and the output is one data word or a
  primitive. A function with no inputs is `{} -> $number`.
- **The inputs are the parameters.** In the body, `$first` is the value passed for `$first`. The type is written
  once and binds the parameters, so nothing is repeated, and each parameter is a declared word with its own
  abstract. That is how a function's inputs carry meaning.
- **The abstract follows the body directly,** so it does not name its word again. Like every entry, it refers
  only to earlier entries. It may not refer to its own word, nor to the body's results or blocks, which a reader of
  the abstract cannot see.
- A function word is defined once, and declared at most once, above its `define` and only where a call above the
  `define` needs it (`declare`, [step-9.md](step-9.md) section 4). It is never declared as a data word. An abstract or a type in a declaration whose word
  is defined below gets "a function's type and abstract belong to its `define`".

`$a -> $b`, without braces, gets "the inputs are a struct: write `{$a} -> $b`". `$a -> $b -> $c` gets "a function
returns one value". `=>`, `→` and `:` get "write `->`". Source stays ASCII.

### 4.1 What an abstract says

An abstract says **what** a function gives back, never **how** it computes it. It stands in for the definition
wherever the body is not in view (section 2), and the reader there is a caller, who needs the contract. Where the
body is in view, the body already says how.

- **The result, in terms of the inputs,** as a noun phrase, naming every input with `@`: `"the greatest common
  divisor of @first and @second"`. For an `i1` output, `"whether @n is even"`.
- **The edges a caller must know:** the inputs it does not handle (`"never returns when @n is zero or less"`), a
  result that wraps where a caller would not expect it (`"the smallest i64 stays negative"`), and the inputs it is
  undefined for, as LangRef says ([abstract-machine.md](abstract-machine.md)). That is one phrase after the result,
  `"; undefined when @b is 0"`, and it counts a callee's undefined inputs too, since a caller meets them the same
  way: `gcd` says `"undefined when one is the smallest i64 and the other -1"`, for its `srem`. It never says
  "traps": a trap is what checked mode does on those inputs, and unchecked mode does not, so it is not the
  function's meaning. Every abstract says it in full, never "as @gcd gives", since an abstract stands where the
  body is not in view. Overflow wraps everywhere ([step-3.md](step-3.md)), so an abstract does not say so for
  every `add`.
- **"How" only where a caller can observe it.** Today that is recursion depth, since a deep recursion runs out of
  stack ([step-9.md](step-9.md) section 5): `"…; it recurses @n times"`. Which blocks a body has, which helpers it
  calls, and in what order it does its steps are not in the abstract: they are in the body, and they change when the
  body is rewritten while the result stays the same.
- **Not the type.** The type is written once, in the head. A data word's abstract says what its values mean
  (`"the largest @x allowed"`), not that they are `i64`.
- A reference to another function is fine when it states the result, `"the opposite of @even"`, and not when it
  states the steps, `"by @odd"`.

| Writes | Instead of | Why |
|---|---|---|
| `"@x, moved into the range from @lo to @hi"` | `"compares @x with @lo, then with @hi"` | the steps, not the result |
| `"whether @n is even; it recurses @n times"` | `"whether @n is even, by @odd"` | a helper, not the contract |
| `"one more than @n"` | `"one more than @n, passed through two blocks"` | the blocks |
| `"four times @count, minus ten"` | `"an i64 computed from @count"` | the type, and no result |

**One part is checked: every input is named.** A function's abstract that does not refer to one of its inputs with
`@` is `unmentioned-input`, once for each input it leaves out, with `key` `abstract`:

| Kind | Message | Hint |
|---|---|---|
| `unmentioned-input` | "the abstract of `@gcd` does not name its input `@second`" | "say what the result is in terms of `@second`, and write it as `@second`" |

- A result that does not depend on an input is still a contract worth stating: `"@first, whatever @second is"`.
  But an input the body never reads is already `unused-local`, so this mostly catches an abstract that describes
  only part of the result.
- It follows references, never the English around them: `"twice the @number"` names `@number`; `"twice the
  number"` does not.
- A function with no inputs passes: `"always seven"`.
- A score of how good an abstract is, written next to it, was rejected: its writer would grade it, it would go stale
  with the body, and nothing could check it. What can be checked is checked here; the rest is judged by readers, and
  by the benchmark, never stored in the program.

*Easy for a model:* it is the first line of a docstring, which models write constantly: Go's "Foo returns …",
Python's "Return the …". *How mistakes surface:* an input left out is `unmentioned-input`; the rest do not, since
the English is never checked. An abstract that
describes steps reads fine until the body changes, and then it is wrong without a diagnostic. The benchmark's
scrambled-words cell, where the abstract is all that is left of a word's meaning, measures whether this guidance
pays.

## 5. Bodies

The body follows LLVM IR, the low-level code models know best, with five deliberate differences (section 6).

- **Lines.** A line is an instruction, `$x = add i64 $a, $b`, or a terminator. An instruction names its result, so
  the body stays in A-normal form: every operand is a word or an integer, never another instruction.
- **`ret $v`** ends the body and returns a value. Nothing follows it.
- **Visibility.** A body sees the function's parameters and its own earlier results.
- **Results** are domain words with no abstract. Each is bound once in its body and is not a module word. Two
  functions may use the same result word.
- **Every word is used.** A result that nothing reads is an error (`unused-local`), and so is a parameter: an input
  the body ignores should not be in the type. A function that needs no input has type `{} -> …`. A data word that
  nothing refers to is `unused-word` ([step-11.md](step-11.md)).
- **Types on operations only.** An operation names its type, `add i64`, as in LLVM. Operands and `ret` carry none,
  because the definition gives the function's type.
- **Overflow wraps,** as in step 3.

**Blocks (step 7, [step-7.md](step-7.md)).** Control flow adds blocks, which step 4 does not implement. The lines after `{` are the entry
block, which has no label. Every other block starts with a label, `^name{%x, %y}:`, or `^name{}:` with no
parameters. `br ^block{args}` jumps to a block, and `br %c, ^then{args}, ^else{args}` jumps to one of two. A block
sees its own parameters, its own earlier results and the function's parameters. Anything else is passed as a block
argument, so there are no dominance rules: each block can be checked and read on its own, like a small function. A
block that no `br` reaches is an error (`unreachable-block`), and nothing can jump to the entry block, as in LLVM.
Every loop has one way in, its header, so control flow is reducible (`irreducible-loop`, [step-10.md](step-10.md)).

## 6. Differences from LLVM IR

| LLVM | mime | Why |
|---|---|---|
| `%x` locals, `@f` globals | `$x` for every word | one class of words, so renaming stays lexical |
| `phi` | block parameters | a `phi` needs every predecessor tracked; the compiler writes the phis |
| dominance | a block sees only its parameters, its results and the function's parameters | errors stay where their cause is, and the fix is mechanical |
| `ret i64 %x`, `br label %b`, `define i64 @f(i64 %x)` | `ret $x`, `br $b()`, `define $f {$x} -> $r` | the definition gives the types once |
| undefined behavior, poison | one defined meaning per operation | each operation has exactly one meaning |

LLVM habits get hints:

- `%x` and `@f`: "words are written `$x`".
- `define $f($a, $b)` and `define i64 @f(…)`: "write the type: `define $f {$a, $b} -> $r`".
- `phi`: "use block parameters".
- `nsw` and `nuw`: "overflow always wraps".
- `label %b`: "write the block's word".
- A label without parentheses, `$done:` or `done:`: "write `$done():`".
- `ret i64 $x`: "the type comes from the definition".

**The main risk** is that a syntax that looks like LLVM invites LLVM's semantics. Where LLVM leaves behavior
undefined (division by zero, shifts that are too wide), a model will assume LLVM's rules. Each such operation gets
its meaning in the step that adds it, and SKILL.md lists every difference. *To measure:* how often models assume
LLVM semantics.

## 7. No header file

There is no generated header. The declarations, the definitions' types and the abstracts are the module's
interface, written in the module itself, so there is one form and nothing to keep in sync. An importer reads them
and skips the bodies. A tool may print that view on demand without storing it. This settles core open question 3.

## 8. What changes for existing programs

Steps 1 to 3 change form. This step breaks the roadmap's rule that a program keeps working in the next step, once:
mime has no users yet, and every later step depends on this layout. The step 1 program becomes

```
$number = {type = i64, abstract = "a whole number"}

define $same {$number} -> $number {
  ret $number
}
abstract = "the $number it is given"
```

- `description` becomes `abstract`, which is still a checked reference string (step 2's rules apply to it).
- `sort` becomes `type`. `takes` and `returns` become the definition's type.
- `body = input` and `let … in` become a definition with lines and `ret`. `input` is retired, which settles core
  open question 2: a parameter is its word.
- `mime run FILE '$f' 7` passes one decimal integer per input, in the type's order, and none for `{}`.
- Lowering gives each input its LLVM parameter: `define i64 @"$gcd"(i64 %"$first", i64 %"$second")`.

## 9. Model ease

- **Familiar:** declarations have the shape of JSON Schema and tool definitions (`type` plus a description). A
  definition's head is a function signature, as in `fn gcd(first, second) -> Number`. Bodies are LLVM IR, with
  Cranelift-style block parameters to come.
- **New:** a function's abstract comes after its body, parameters are declared words rather than fresh names,
  operands carry no types, and blocks will be closed.
- **How mistakes surface:** LLVM habits are reported with the mime form (section 6). Putting a function's type or
  abstract in a declaration gets "a function's type and abstract belong to its `define`". An ignored input gets
  `unused-local` with the hint to remove it from the type. *To measure:* whether abstract-last makes abstracts more
  accurate, and, once blocks arrive, argument swaps in `br` (both values are `i64`, so nothing catches them before
  the types step).

## 10. Out of scope

- The syntax of imports and exports, and link names for imported words: the modules step.
- Calls, and how a function refers to itself or to a later function: the calls step.
- Struct values, `get`, and data words that refer to themselves, such as a list: the structs step.
- Blocks, `br`, `icmp` and `i1`: the branches step. Step 4 implements a single body with `ret`.
