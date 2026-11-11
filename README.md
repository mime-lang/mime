# mime

**A programming language written and read by AI agents, where a word means only what the program says it means.**

> Status: thought experiment → early design. Nothing here is stable yet.

## The thesis

Today's languages rely on borrowed meaning. A function named `sort` or a variable named `user_count` carries meaning that comes from the model's training data, not from the program. A model reading the code trusts the name, and a name can lie.

mime makes a different bet: **a program should carry its own meaning, and that meaning should not depend on what any particular model has learned about words.** An agent should understand a mime program from its *form*: what is declared, how declarations relate, and how values flow. It should not need to recognize vocabulary.

Humans are not expected to read or write mime. They work through an agent, which writes the code and explains it.

## Words, the way mathematicians use them

mime borrows its discipline from mathematical writing. A mathematician does not assume the reader knows what "group" or "compact" means. They **define** the word first, and from then on they **use only words that are already defined**. The word itself is just a label. All of its meaning sits in the definition.

A mime module works the same way:

1. **Declare before use.** Every word a module uses is declared in that module, imported from another module that declares it, or is one of the small set of core primitives.
2. **A definition only uses earlier words.** A word is defined in terms of words that already exist, so a module reads as a chain of definitions with no forward references and no undefined terms.
3. **Names carry no meaning.** Consistently renaming a word throughout a program (for example `twice` → `w7f3`) must never change what the program means. The checker treats words as opaque labels.
4. **One meaning, one form.** Where possible, the same computation is written exactly one way. Two agents solving the same problem should produce the same program, up to renaming.

Words may look like English, because that helps agents and humans talk about them. The language never relies on that, though, and rule 3 can be checked mechanically.

## What it looks like

The surface is a flat, explicit, LLVM-IR-like text syntax in [A-normal form](https://en.wikipedia.org/wiki/A-normal_form) / SSA: every intermediate value gets its own name, every operation takes only names, and control flow is explicit. Nothing is nested or implicit, and there is no sugar. This style was inspired by [oymo](https://github.com/tapl-org/tapl/tree/main/oymo-py).

The sketch below shows the intended shape. It is **illustrative only**: the grammar is not designed yet.

```
module m

; words this module introduces, with their shapes
word twice  : (i64) -> i64
word quad   : (i64) -> i64

; definitions use only earlier words and core primitives (i64, add, ret)
define twice(%a : i64) -> i64 {
  %b = add i64 %a, %a
  ret %b
}

define quad(%a : i64) -> i64 {
  %b = twice %a
  %c = twice %b
  ret %c
}
```

Renaming `twice` to `w1` and `quad` to `w2` everywhere gives the same program.

## Architecture (planned)

```
mime text ──parse──▶ AST ──check──▶ checked module ──lower──▶ LLVM IR (.ll) ──clang──▶ native
```

- **Checker:** enforces declare-before-use, definition order, types, and the renaming invariant.
- **Backend:** emits textual LLVM IR. `clang` turns that into object files and executables.
- **Diagnostics:** structured (JSON) error messages written for agents, so an agent can repair its code in a loop.

## Testing the bet

The thesis is an empirical claim, so mime will be measured. The evaluation plan borrows from languages in the [agentlanguages.dev](https://agentlanguages.dev/) catalogue, especially VeraBench and Lom's RepairLoopBench, and also tries to avoid their known weak spots:

- **Task suite:** the same tasks implemented in mime and in baselines (Python, TypeScript, and other languages with no training data). The model gets the mime spec in context.
- **Metrics:** pass@k over several samples per task, a per-task pass matrix, attempts to green in a compile→diagnose→repair loop, and *total* token cost (spec + generation + retries), not just program length.
- **The key ablation:** run the same mime tasks with meaningful words and with consistently scrambled words. If the thesis holds, scrambling should cost an agent little in mime. In a conventional language it should cost much more.
- **Hygiene:** several models and providers, raw outputs archived, harder tasks added whenever a baseline saturates, and negative results published.

## Roadmap

- [ ] Core design doc: words, declarations, modules, primitives, types
- [ ] Grammar for the text syntax
- [ ] Parser and checker (declare-before-use, renaming invariant)
- [ ] Lowering to LLVM IR for a minimal subset (integers, functions, branches)
- [ ] Agent tooling: `AGENTS.md`, a compact spec for in-context use, JSON diagnostics
- [ ] First benchmark run and the scrambled-words ablation
- [ ] Submit to the [agentlanguages.dev](https://agentlanguages.dev/) catalogue

## Development

mime will be bootstrapped. The first toolchain is written in Python (3.12+, [hatch](https://hatch.pypa.io/)), and all of that code lives in [`mime-py/`](mime-py/). Once mime can compile itself, `mime-py/` is deleted. Everything that should outlive the bootstrap (design docs in [`design/`](design/), the spec, example programs, benchmarks) lives at the repo root.

```bash
cd mime-py
hatch test              # run tests
hatch run mime --version
```

## License

`SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception`. See [LICENSE](LICENSE).
