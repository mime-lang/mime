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
| 8 | the reference interpreter, `mime run --backend`, running by symbol, conformance run cases | [step-8.md](step-8.md) |
| 9 | calls by word, recursion, `declare`, running out of stack as a machine limit | [step-9.md](step-9.md) |
| 10 | loops with one way in: reducible control flow, `irreducible-loop` | [step-10.md](step-10.md) |
| 11 | canonical order: data words and `declare`s above their first `define`, `unused-word`, `canon --keep-words` | [step-11.md](step-11.md) |
| 12 | first benchmark run: mime cells in the harness, `clamp`'s `ref.mime`, the mime signature skeleton | [step-12.md](step-12.md) |
| 13 | division and remainder: `sdiv udiv srem urem`, `and or xor` on `i1`, the first trap on every backend | [step-13.md](step-13.md) |

Along the way: [diagnostics.md](diagnostics.md) (JSON only, `entry`/`key`/`text`), [tools.md](tools.md)
(`show`, which prints a function after the words in its type, and `uses`), and what an abstract says
([layout.md](layout.md) section 4.1: the result, not the steps; `unmentioned-input`).

## Next steps, in order

### Lists

- **New:** a list of `i64`: its length, reading an element, and building a new list.
- **Decide:** the syntax of the list type (a primitive type, not raw memory and pointers, so it maps onto
  JavaScript and the JVM; [backends.md](backends.md) section 6), what reading past the end means (a trap or a
  defined value, never undefined), and how `mime run` and the benchmark harness pass a list in and read one out.
- **Why here:** four of the benchmark's five tasks take or return a list (`sum-list`, `is-sorted`,
  `merge-sorted`, `shortest-k-distinct`), and two return a boolean, which `i1` covers.

**Milestone: the whole benchmark runs.** Every task can be written in mime. The two `names`-track tasks
(`sum-list`, `is-sorted`) take lists, so this is also where the scrambled-words ablation first runs: a mime
library's `none` style is its `mime canon`, and its `honest` style its `mime canon --keep-words`
([step-12.md](step-12.md) section 5).

### Structs

- **New:** `type = {@first, @second}`, reading a field, building a struct value.
- **Decide:** the syntax for both, and how a data word refers to itself, as a linked list does (`@list` holding a
  `@list`). Calls answered this for functions with `declare` (step 9); a data word may need
  the same, and indirection, which lists may have brought.
- **Check nominal identity from the start.** [layout.md](layout.md) section 3 already promises that `@point` and
  `@vector` are different types even with the same fields. Until the types step, a `@vector` passed where a
  `@point` belongs would check clean, so this step checks that a struct value's word is the word expected, and
  leaves the rest of the type checker to the types step.

### JavaScript backend

- **New:** `mime run --backend js`, through the conformance tests.
- **Decide:** `i64` as `BigInt` or as something faster, and how reducible blocks lower to labeled loops
  ([step-10.md](step-10.md)).
- **Later, WebAssembly:** the same structured lowering, onto `block`, `loop` and `br`, with `i64` native. It is not
  a step yet: it earns one when a user needs it, since every backend multiplies the cost of every later step
  ([backends.md](backends.md) section 7).
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

**Before the bootstrap, decide whether positions are needed at all.** Every diagnostic, and from step 8 every trap,
already names its `entry`, `key` and `text`, which is enough to find a mistake and fix it. Line and column are only
printed with `--positions` ([diagnostics.md](diagnostics.md)). If no tool or model needs them by then, drop the
flag, and the mime compiler need not track a position for anything.
