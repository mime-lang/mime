# Step 4: module layout and LLVM-style bodies

> Status: settled. The fourth step of the [roadmap](roadmap.md). It implements [layout.md](layout.md) for
> what exists so far: data words of type `i64`, and functions whose body is a list of lines ending in `ret`.
> Blocks, `br`, structs, calls, imports and exports come in the steps that layout.md names.

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

## 1. Lexical rules

- Language words: `type`, `abstract`, `define`, `ret`, `add`, `sub`, `mul`, `i64`. The words of steps 1 to 3 that
  this step replaces (`description`, `sort`, `takes`, `returns`, `body`, `input`, `let`, `in`) are no longer
  language words, and each gets a hint that names its replacement.
- New punctuation: `->`. The integer `-1` and the arrow `->` both start with `-`; the next character decides.
- `%` and `@`, LLVM's sigils, get "words are written `$x`". `=>` and `→` get "write `->`".
- Names, strings, integers and whitespace are as before. Whitespace never matters, so a line break is not a
  separator; each line is self-delimiting.

## 2. Grammar

```
module      = (declaration | definition)*
declaration = word "=" "{" field ("," field)* "}"
definition  = "define" word inputs "->" output "{" line* "ret" atom "}" "abstract" "=" string
inputs      = "{" [word ("," word)*] "}"
output      = word | name
line        = word "=" name name atom "," atom
atom        = word | integer
```

- Declarations and definitions may come in any order. Every entry refers only to earlier entries: a word used
  before its entry is a `forward-reference`, with the hint to move the entry above.
- A declaration's fields are `type` then `abstract`. Its values are a name, a word, a string, an integer, or a
  struct of words `{$a, $b}`, which the checker accepts or rejects.
- A line is `$result = operation type left, right`: `$x = add i64 $a, 1`.
- A body ends with exactly one `ret`. A line after `ret` is a `syntax` error, and so is a body without `ret`.

## 3. Checks

The diagnostic kinds are those of steps 1 to 3. `key` in a diagnostic is `type` or `abstract` for a declaration's
fields, and for a definition `type` (its head), `body`, or `abstract`.

| Where | Rule | Kind |
|---|---|---|
| declaration | keys are `type`, `abstract`, in that order, each once | `unknown-key`, `missing-key`, `key-order`, `duplicate-key` |
| declaration | `type` is `i64` | `bad-value` (a struct gets "arrives in step 10", a word gets "a type is a primitive such as `i64`") |
| declaration | `abstract` is a non-empty string; its references name earlier entries only (step 2) | `bad-value`, the step 2 kinds |
| any | a word has one declaration or one definition | `duplicate-word` |
| definition | each input is an earlier data word, listed once | `undeclared-word`, `forward-reference`, `bad-value`, `duplicate-word` |
| definition | the output is an earlier data word or `i64` | `undeclared-word`, `forward-reference`, `bad-value` |
| body | an operation is `add`, `sub` or `mul`, with type `i64` | `unknown-language-word`, `bad-value` |
| body | an operand is an input, an earlier result, or an integer that fits `i64` | `undeclared-word`, `forward-reference`, `not-a-value`, `bad-value` |
| body | a result is bound once and is not a module word | `duplicate-word` |
| body | every result and every input is read | `unused-local` |
| definition | its `abstract` refers to earlier entries, not to itself or its results | the step 2 kinds |

Each mistake gets one diagnostic where that does not depend on spelling: the body may read a rejected input, or an
input declared later, without a second report. An undeclared input or output with no close word gets the
declaration to write. (Step 6 removed the rule that a misspelled name whose hint names another counts as reading
it, because guessing what a typo means depends on spelling; see step-5.md section 1.)

## 4. Hints for old forms and LLVM habits

| Written | Hint |
|---|---|
| `description = …` | renamed: write `abstract` |
| `sort = …` | renamed: write `type` |
| `takes`, `returns`, `body` | a function is written as a `define` |
| `type = {$n} -> $n` | a function is written as a `define` |
| `let $x = add {i64, a, b} in` | write `$x = add i64 a, b` |
| `input` | the inputs are the words of the type, such as `$number` |
| `define $f($a)`, `define i64 @f(…)` | write the type: `define $f {$a} -> $r` |
| `%x`, `@f` | words are written `$x` |
| `phi` | use block parameters (step 8) |
| `nsw`, `nuw` | overflow always wraps |
| `ret i64 $x` | the type comes from the definition |
| `=>`, `→`, `:` in a type | write `->` |

## 5. Running and lowering

- `mime run FILE '$f' 3 4` passes one decimal integer per input, in the order of the type, and none for `{}`. A
  wrong count names the inputs.
- Each input becomes an LLVM parameter named after its word, and each line one instruction:

```llvm
define i64 @"$affine"(i64 %"$number") {
  %"$double" = add i64 %"$number", %"$number"
  %"$triple" = add i64 %"$double", %"$number"
  %"$result" = add i64 %"$triple", 1
  ret i64 %"$result"
}
```

## 6. Model ease

See [layout.md](layout.md) section 9. This step adds one thing to measure: the hints for old forms, since models
that have read earlier mime will write `description` and `let … in`.
