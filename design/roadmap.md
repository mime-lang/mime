# Roadmap

mime grows in small steps. Each step adds one new thing to the language and carries it all the way through:
design, parser, checker, lowering to LLVM IR, tests, and the compact spec that models read. A program written at
step N still works at step N+1.

**One step at a time.** Only the current step is designed in detail. A step is done when:

1. its design is settled in `design/` (no open question left that the step needs),
2. `hatch test` passes with programs that use the new thing and programs that misuse it,
3. every misuse gets a clear diagnostic, and
4. the compact spec, [spec/SKILL.md](../spec/SKILL.md), describes it. Models read this file, including in the benchmark.

Later steps stay rough on purpose. [core.md](core.md) is the direction, not a contract: a step may change it, and
when it does, core.md is updated in the same step.

## Steps

### 1. One entry, one function: the whole pipeline (done; see [step-1.md](step-1.md))

The smallest program that runs:

```
$number = {description = "a whole number", sort = i64}
$same   = {description = "the number it is given", takes = $number, returns = $number, body = input}
```

- **New:** the `$` lexer rule, entries, `description`, `sort = i64`, `takes`/`returns`, `input`, a module as a list
  of entries, JSON diagnostics.
- **Decide:** the grammar for this subset, how a program is run (entry point, how the input is given), and the
  diagnostic format.
- **Done when:** `mime run` on the program above prints its input, and a missing `$`, a missing `description`, an
  unknown key, and an undeclared word are each reported.

### 2. Checked references in descriptions (done; see [step-2.md](step-2.md))

- **New:** `$` references inside a `description`, the backward-only rule, `\$`.
- **Done when:** a forward or dangling reference in a description is reported, and plain text is never checked.

### 3. Arithmetic bodies

- **New:** `let … in …` in A-normal form, locals as `$` words, `add`, `sub`, `mul` with the sort as first operand,
  wrapping overflow.
- **Decide:** open question 1 (do locals get descriptions?).

### 4. Renaming and canonical form

- **New:** `mime canon`.
- **Also:** `mime rename FILE '$old' '$new'`, which rewrites a word and its references (see tools.md).
- **Done when:** the test suite renames every word in every test program and checks that behavior and canonical form
  are unchanged. This is mime's thesis turned into a test, so it comes early.

### 5. Calls and recursion

- **New:** `call`, bodies as a fixed point (a function may call itself and later functions).
- **Also:** `mime run` takes one argument written as a mime call, replacing `'$same' 7` (see step-1.md, section 4).

### 6. Comparisons and branches

- **New:** `icmp` with predicates, `i1`, control flow as regions.
- **Decide:** the region syntax, and open question 2 (how `input` works inside regions).

### 7. Division and remainder

- **New:** `sdiv`, `udiv`, `srem`, `urem`.
- **Decide:** what division by zero means. One operation has exactly one meaning, so it cannot be left undefined.

**Milestone: first benchmark run.** Integer tasks such as gcd can now be written in mime, so the benchmark's mime
cells stop being `unavailable` and the scrambled-words ablation can run on them.

### 8. Structs

- **New:** `sort = {$first, $second}`, field access `input.$first`, building a struct value.
- **Decide:** the syntax for building a struct value.

### 9. Integer widths

- **New:** `i8`, `i16`, `i32`, and conversions between widths.

### 10. Modules

- **New:** several files, `import` and export, renaming at import, headers.
- **Decide:** open question 3 (header format).

### 11. Opaque structs

- **New:** a struct exported without its fields.
- **Decide:** open question 5 (where an importer's compiler finds the struct's size).

### 12. Types

- **New:** the type checker: structural types made nominal by words.
- **Decide:** open question 4 (the checking layer).

### 13. Unions

- **New:** set-theoretic unions (`A | B`) and the checks that cover every case.

### Then

Submit mime to the [agentlanguages.dev](https://agentlanguages.dev/) catalogue, and start writing the mime compiler
in mime.
