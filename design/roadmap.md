# Roadmap

mime grows in small steps. Each step adds one new thing to the language and carries it all the way through:
design, parser, checker, lowering to LLVM IR, tests, and the compact spec that models read.

**One step at a time.** Only the current step is designed in detail. A step is done when:

1. its design is settled in `design/`, as `step-N.md` (no open question left that the step needs),
2. `hatch test` passes with programs that use the new thing and programs that misuse it, and the renaming test
   still holds for every golden,
3. every misuse gets a clear diagnostic,
4. it behaves the same on every backend that exists ([backends.md](backends.md)), and
5. the compact spec, [spec/SKILL.md](../spec/SKILL.md), describes it. Models read this file, including in the benchmark.

**Earlier programs may change form.** mime has no users yet, so a step may change how earlier programs are
written, as steps 4 and 6 did. When it does, the step says so and converts every test program, golden and doc.

**Steps are named, not numbered, until they are done.** A finished step gets the next number and its `step-N.md`.
Docs and diagnostics refer to a future step by its name ("arrives with structs"), so reordering or inserting a step
never renumbers anything.

Later steps stay rough on purpose. [core.md](core.md) is the direction, not a contract: a step may change it, and
when it does, core.md is updated in the same step.

## Done

| Step | Added | Note |
|---|---|---|
| 1 | the whole pipeline: one entry, one function, `mime run`, JSON diagnostics | [step-1.md](step-1.md) |
| 2 | checked references in descriptions (now abstracts) | [step-2.md](step-2.md) |
| 3 | arithmetic bodies: `add`, `sub`, `mul`, wrapping overflow, locals without descriptions | [step-3.md](step-3.md) |
| 4 | the module layout: `{type, abstract}` data words, `define` with LLVM-style lines | [step-4.md](step-4.md), [layout.md](layout.md) |
| 5 | renaming and canonical form: `fmt`, `canon`, `rename`, the renaming test | [step-5.md](step-5.md) |
| 6 | `@` words and `%` locals, numbered locals in canon | [step-6.md](step-6.md) |
| 7 | branches: `icmp`, `i1`, blocks with parameters, `br`, `^label`s | [step-7.md](step-7.md) |

Along the way: [diagnostics.md](diagnostics.md) (JSON only, `entry`/`key`/`text`) and [tools.md](tools.md)
(`show`, `uses`).

## Next steps, in order

### Reference interpreter

- **New:** a second backend, an interpreter in the bootstrap toolchain, and the conformance tests: every clean
  golden carries its run cases, and every backend must give the same answers ([backends.md](backends.md)).
- **Decide:** the checked form that backends share, how `mime run` chooses a backend, and how a trap is reported.
- **Why here:** with blocks, loops and branches (step 7), a body has real control flow, so a second backend starts
  paying for itself, while there is still little to implement twice.

### Calls and recursion

- **New:** `call`, and recursion.
- **Decide:** how a function refers to itself and to a later function, as mutual recursion needs: forward
  declarations, or definitions as a fixed point. Entries are ordered, like everything else, until this step.
- **Decide:** the call syntax. A function's inputs are words, so arguments can be passed by word,
  `call @gcd {@first = %a, @second = %b}`, which no argument swap can get wrong, or by position, `call @gcd(%a, %b)`,
  which is shorter and more familiar.

### Division and remainder

- **New:** `sdiv`, `udiv`, `srem`, `urem`, and `and`, `or`, `xor` on `i1`, as in LLVM. Step 7 left `i1` without
  operations, so combining two conditions or negating one takes extra blocks.
- **Decide:** the domain of each operation and what happens outside it: a trap, as [backends.md](backends.md)
  recommends, or a total definition such as `x / 0 = 0`. Never undefined behavior by default; an opt-in unchecked
  mode comes later ([backends.md](backends.md) section 1).

**Milestone: first benchmark run, on integers.** `clamp`, and integer programs such as gcd, can be written. The
benchmark's mime cells for those tasks stop being `unavailable`, and the scrambled-words ablation can run on them.

### Lists

- **New:** a list of `i64`: its length, reading an element, and building a new list.
- **Decide:** the syntax of the list type (a primitive type, not raw memory and pointers, so it maps onto
  JavaScript and the JVM; [backends.md](backends.md) section 6), what reading past the end means (a trap or a
  defined value, never undefined), and how `mime run` and the benchmark harness pass a list in and read one out.
- **Why here:** four of the benchmark's five tasks take or return a list (`sum-list`, `is-sorted`,
  `merge-sorted`, `shortest-k-distinct`), and two return a boolean, which `i1` covers.

**Milestone: the whole benchmark runs.** Every task can be written in mime.

### Structs

- **New:** `type = {@first, @second}`, reading a field, building a struct value.
- **Decide:** the syntax for both, and how a data word refers to itself, as a linked list does (`@list` holding a
  `@list`). That needs the same answer as the forward references of calls, and indirection, which lists may have
  brought.

### JavaScript backend

- **New:** `mime run --backend js`, through the conformance tests.
- **Decide:** `i64` as `BigInt` or as something faster, and the loop-and-`switch` lowering of blocks.
- **Why here:** lists and structs are the core data types; once they stop changing, a second compiled backend
  costs less in every later step.

### JVM backend

- **New:** `mime run --backend jvm`, through the conformance tests.
- **Decide:** JVM bytecode directly, or through Java source; how a module maps onto classes.

### Integer widths

- **New:** `i8`, `i16`, `i32`, and conversions between widths.

### Modules

- **New:** several files, `import` and export, renaming at import.
- **Decide:** the syntax of imports and exports. Link names are already settled: a function is exported under its
  `symbol` and is otherwise internal ([layout.md](layout.md) section 4). There is no header file: a module's
  declarations and abstracts are its interface ([layout.md](layout.md) section 7).

### Opaque structs

- **New:** a struct exported without its fields.
- **Decide:** core open question 5, where an importer's compiler finds the struct's size.

### Types

- **New:** the type checker: structural types made nominal by words.
- **Decide:** core open question 4, the checking layer.

### Unions

- **New:** set-theoretic unions (`A | B`) and the checks that cover every case.

### Then

Submit mime to the [agentlanguages.dev](https://agentlanguages.dev/) catalogue. Write an interpreter in mime, the
first large mime program, and make it a backend (`mime run --backend interp`), replacing the reference interpreter
([backends.md](backends.md) section 5). Then write the mime compiler in mime.
