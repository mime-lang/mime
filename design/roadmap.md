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

### 3. Arithmetic bodies (done; see [step-3.md](step-3.md))

- **New:** `let … in …` in A-normal form, locals as `$` words, `add`, `sub`, `mul` with the sort as first operand,
  wrapping overflow.
- **Decide:** open question 1 (do locals get descriptions?).

### 4. Module layout and LLVM-style bodies

- **New:** the layout of [layout.md](layout.md): data words `{type, abstract}`, then definitions
  `define $f {$inputs} -> $output { … }` followed by their `abstract`. A body is LLVM-style lines with typed
  operations, ending in `ret`. `description`, `sort`, `takes`, `returns`, `input` and `let … in` are replaced.
- **Note:** the one step that changes the form of earlier programs (layout.md section 8).

### 5. Renaming and canonical form

- **New:** `mime canon`.
- **Also:** `mime rename FILE '$old' '$new'`, which rewrites a word and its references (see tools.md).
- **Done when:** the test suite renames every word in every test program and checks that behavior and canonical form
  are unchanged. This is mime's thesis turned into a test, so it comes early.

### 6. Calls and recursion

- **New:** `call`, and recursion.
- **Decide:** how a function refers to itself and to a later function, as mutual recursion needs: forward
  declarations, or definitions as a fixed point. Definitions are ordered, like everything else, until this step.
- **Also:** `mime run` takes one argument written as a mime call, replacing `'$same' 7` (see step-1.md, section 4).

### 7. Comparisons and branches

- **New:** `icmp` with predicates, `i1`, and the blocks and `br` of layout.md section 5.

### 8. Division and remainder

- **New:** `sdiv`, `udiv`, `srem`, `urem`.
- **Decide:** what division by zero means. One operation has exactly one meaning, so it cannot be left undefined.

**Milestone: first benchmark run.** Integer tasks such as gcd can now be written in mime, so the benchmark's mime
cells stop being `unavailable` and the scrambled-words ablation can run on them.

### 9. Structs

- **New:** `type = {$first, $second}`, reading a field, building a struct value.
- **Decide:** the syntax for both, and how a data word refers to itself, as a list does (`$list` holding a `$list`).
  That needs the same answer as step 6's forward references, and it needs indirection, which mime does not have
  yet.

### 10. Integer widths

- **New:** `i8`, `i16`, `i32`, and conversions between widths.

### 11. Modules

- **New:** several files, `import` and export, renaming at import, headers.
- **Decide:** open question 3 (header format).

### 12. Opaque structs

- **New:** a struct exported without its fields.
- **Decide:** open question 5 (where an importer's compiler finds the struct's size).

### 13. Types

- **New:** the type checker: structural types made nominal by words.
- **Decide:** open question 4 (the checking layer).

### 14. Unions

- **New:** set-theoretic unions (`A | B`) and the checks that cover every case.

### Then

Submit mime to the [agentlanguages.dev](https://agentlanguages.dev/) catalogue, and start writing the mime compiler
in mime.
