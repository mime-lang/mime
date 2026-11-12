# Step 3: arithmetic bodies

> Status: settled. The third step of the [roadmap](roadmap.md). A body becomes a chain of `let`s in A-normal form
> over `add`, `sub` and `mul`, as [core.md](core.md) section 6 describes. It settles core open question 1: locals
> get no description.

```
$number = {description = "a whole number", sort = i64}
$affine = {
  description = "three times the $number it is given, plus one",
  takes = $number,
  returns = $number,
  body = let $double = add {i64, input, input} in
         let $triple = add {i64, $double, input} in
         let $result = add {i64, $triple, 1} in
         $result
}
```

## 1. Lexical rules

- New language words: `let`, `in`, `add`, `sub`, `mul`.
- New token, the **integer**: `0`, or an optional `-` followed by a digit `1`–`9` and more digits. `007`, `-0`
  and `+1` are errors, each with the one form to write instead, so every number has one spelling.
- A digit run glued to a letter, like `12a`, is an error, as a glued name is.
- `+`, `-` (when no digit follows), `*` and `(` are errors with the hint "arithmetic is written
  `add {i64, a, b}`", because infix and call syntax are the first things a model reaches for. Subtraction written
  without spaces gets the same hint: `input-1`, where `-` is glued to a name and a digit follows, and `input -1`,
  where a negative integer follows a value. A `-` glued to a name without a digit after it, as in `$my-word`, gets
  the name hint instead.

## 2. Grammar

```
body      = "let" word "=" operation "in" body
          | atom
operation = name "{" atom ("," atom)* "}"
atom      = name | word | integer
```

- `body` is the value of the `body` key. A body that is a single atom, like `input`, is still valid.
- An operation is an operation word and its operands in `{…}`. The first operand is the sort, then come the two
  values: `add {i64, a, b}`.
- **A-normal form.** An operand is an atom: `input`, a local, or an integer. An operation inside an operand is a
  syntax error, `nested-operation`, with the hint "bind the inner operation with its own `let`". So every
  intermediate value has a name, and one computation has one form.
- `let` and `in` may sit on any lines; whitespace never matters.

## 3. Locals

A local is the word a `let` binds: `$double` above.

- **A local has no description.** It names an intermediate value, like a bound variable in a proof, and the
  function's description says what the result means. "One form" means never, not sometimes. (This settles core
  open question 1.)
- **A local is unique in its body and is not a module word.** Two functions may each have a `$sum`, but one body
  cannot bind `$sum` twice, and a local cannot be `$number` when `$number` has an entry. There is no shadowing,
  so a word in a body always has exactly one binding.
- **A local is used after it is bound.** An operand or the final atom may name only a local bound earlier in the
  same body. A body reads `input`, its earlier locals, and integers. It does not read module words yet. Calls
  arrive in step 6.
- **Every local is used.** A `let` whose local nothing reads is an error, `unused-local`. Dead code would be a second
  form of the same computation, and an unused local is most often a sign that the body returns the wrong name.
- A local is a domain word, so the renaming invariant covers it. A description cannot refer to a local, because a
  reference names an entry.

## 4. Operations

| Operation | Result | On overflow |
|---|---|---|
| `add {s, a, b}` | a + b | wraps |
| `sub {s, a, b}` | a − b | wraps |
| `mul {s, a, b}` | a × b | wraps |

- The sort `s` comes first, as in LLVM, where the type sits on the operation. In this step it is `i64`, the only
  sort, and it must be the function's sort: the sort of the entry that `takes` names. While `i64` is the only sort
  this always holds, but the checker already checks it, so a second sort needs no new rule.
- The sort is a language word. A domain word there (`add {$number, …}`) is a `bad-value`, with the hint "the first
  operand is a sort, such as `i64`".
- An integer operand must fit in the sort: for `i64`, from −2⁶³ to 2⁶³−1.
- **Overflow wraps** modulo 2⁶⁴. Each operation has one meaning, with no undefined behavior and no traps, so
  `add {i64, 9223372036854775807, 1}` is `-9223372036854775808`.

## 5. Diagnostics

| Kind | When | Hint |
|---|---|---|
| `nested-operation` | an operation as an operand | bind it with its own `let` |
| `syntax` | a malformed `let`, a missing `in`, a bad integer, infix arithmetic, or an operation as a whole body | what was expected, or how to write it |
| `duplicate-word` | a local bound twice in a body, or a local that is a module word | pick a new word for the local |
| `undeclared-word` | an operand names no local and no entry, or a description names a local | a close local or word; for a local, that a description refers only to entries |
| `forward-reference` | an operand names a local bound later | move the `let` up |
| `not-a-value` | an operand names a module word | a body reads `input` and its locals |
| `unknown-language-word` | an operation word that mime does not have, such as `div` | the operations |
| `unused-local` | a local nothing reads | use it, or remove its `let` |
| `bad-value` | a wrong sort operand, a wrong operand count, an integer that does not fit, a language word that is not an operation or an atom, or a `let` outside `body` | what belongs there |

Each mistake gets one diagnostic, not a cascade. A local that clashes with a module word is still treated as bound,
a local read too early counts as read, and a misspelled local whose hint names a local counts as reading it, so none
of them is also reported as `unused-local`.

`sdiv`, `udiv`, `srem`, `urem` and `icmp` are language words of core section 8 that arrive later. Writing one now
gets "arrives in a later step". Every diagnostic in a body has `key` `body` and the offending text, as
[diagnostics.md](diagnostics.md) defines.

## 6. Lowering

Each `let` becomes one LLVM instruction, with the local as its name. Overflow wraps because the instructions carry
no `nsw` or `nuw` flag.

```llvm
define i64 @"$affine"(i64 %input) {
  %"$double" = add i64 %input, %input
  %"$triple" = add i64 %"$double", %input
  %"$result" = add i64 %"$triple", 1
  ret i64 %"$result"
}
```

## 7. Tools

`mime uses` includes uses of locals, with `key` `body`. The `let` that binds a local is not a use, as the entry that
declares a word is not ([tools.md](tools.md)).

## 8. Model ease

- **Familiar:** this is LLVM IR (`%b = add i64 %a, %a`) written as an ML `let … in` chain. The sort-first operand
  is LLVM's typed instruction, and `{…}` is the struct style of every entry.
- **New:** operands go in `{…}` and not `(…)`, the sort is an operand, and nested expressions are not allowed.
- **How mistakes surface:** `input + 1`, `add(i64, a, b)` and `add {i64, add {…}, 1}` are each reported with the
  form to write. A body that returns the wrong local leaves the right one unused, which `unused-local` reports.
  `add {$number, …}` gets the sort hint. *To measure:* how often models nest operations, and whether locals without
  descriptions cost accuracy.
