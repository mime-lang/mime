# mime

**A programming language written and read by AI agents, where a word means only what the program says it means.**

> Status: thought experiment → early design. Nothing here is stable yet.

## The thesis

Today's languages rely on borrowed meaning. A function named `sort` or a variable named `user_count` carries meaning that comes from the model's training data, not from the program. A model reading the code trusts the name, and a name can lie.

mime makes a different bet: **a program should carry its own meaning, and that meaning should not depend on what any particular model has learned about words.** An agent should understand a mime program from its *form*: what is declared, how declarations relate, and how values flow. It should not need to recognize vocabulary.

Humans are not expected to read or write mime. They work through an agent, which writes the code and explains it.

## Why "mime"

<p align="center">
  <img src="assets/mime.webp" width="480" alt="A mime in a beret, striped shirt and suspenders leans far back on a braced leg, teeth clenched, both gloved fists closed around an invisible rope"><br>
  <sub>AI-generated image.</sub>
</p>

A mime tells a story without words. The audience understands a wall, a rope or a heavy box from shape and movement alone, with no vocabulary to lean on.

There is no rope in the picture above, and no word says "rope". You still see one, and even feel how heavy it is, from the body leaning far back on a braced leg, the clenched teeth, and two fists closed around nothing along one straight line. The meaning comes from form, not from an object or a word.

mime the language aims for the same thing. Its words are only labels, and the meaning is carried by form: declarations, the shapes of types, and how values flow from one step to the next.

(The name has nothing to do with MIME media types.)

## Words, the way mathematicians use them

mime borrows its discipline from mathematical writing. A mathematical text uses two kinds of words.

- **Logical words.** "Let", "suppose", "for every", "there exists" and "hence" are ordinary English. Nobody defines them, and every reader already shares their meaning. They give the text its flow and its logic.
- **Defined terms.** When a new concept appears, the mathematician gives it a name and a definition. Sometimes the name is a new word ("homeomorphism"). Often it is an everyday word with a new meaning ("group", "ring", "field", "compact"). Either way, the name is just a label. A ring has nothing to do with jewelry. All of its meaning sits in the definition, and the text uses a term only after defining it.

mime has the same two layers. The logical words are mime's **language words**: bare tokens such as `define`, `add`, `i64` and `abstract`, fixed by the spec and never renamed. Every other word is a defined term, written with an `@` (`@pair`, `@gcd`), and the lexer alone tells the two apart. Values inside a function body are locals, written with a `%` (`%0`); they have no entry and carry no meaning. A mime module treats its `@` words the way a mathematician treats defined terms:

1. **Declare before use.** Every `@` word a module uses is declared in that module or imported, by name, from another module that declares it.
2. **Meaning points backward.** A word's type and abstract mention only words declared before it, so a module read top to bottom is a chain of definitions with no undefined terms. Bodies are freer: a body may call later words and itself, so recursion needs no extra construct.
3. **Names carry no meaning.** Consistently renaming a word throughout a program (for example `@twice` → `@w7f3`) must never change what the program means. The checker treats words as opaque labels.
4. **One meaning, one form.** Where possible, the same computation is written exactly one way. Two agents solving the same problem should produce the same program, up to renaming.

Words may look like English, because that helps agents and humans talk about them. The language never relies on that, though, and rule 3 can be checked mechanically: `mime canon` replaces every `@` word with a fixed name, and two programs that differ only in naming get the same canonical form.

Every word also gets a short abstract, the way a mathematician adds a sentence of intuition after a definition. An abstract is not free text, though. Its `@` mentions may name only words that are already declared, and the checker verifies each mention and renames it along with the program:

```
free text            ──▶  text with checked references  ──▶  formal spec
(nothing is checked)      (every reference is checked)       (every claim is checked)
                          (mime is here)
```

The English that connects those mentions never changes what a program means. It is there to help an agent find its way, and the benchmark tests what happens when it is removed or made to lie.

## What it looks like

The surface is a flat, explicit, LLVM-IR-like text syntax in [A-normal form](https://en.wikipedia.org/wiki/A-normal_form) / SSA: every intermediate value gets its own name, every operation takes only names, and control flow is explicit. Nothing is nested or implicit, and there is no sugar. This style was inspired by [oymo](https://github.com/tapl-org/tapl/tree/main/oymo-py).

A program is a list of entries, each referring only to earlier ones ([design/layout.md](design/layout.md)). This one runs today:

```
@number = {type = i64, abstract = "a whole number"}

define @affine {@number} -> @number {
  %double = add i64 @number, @number
  %triple = add i64 %double, @number
  %result = add i64 %triple, 1
  ret %result
}
abstract = "three times the @number it is given, plus one"
symbol = "affine"
```

```bash
mime run prog.mime affine 5    # prints 16
```

`mime run` calls a function by its `symbol`, the name it is exported under. Renaming `@number` to `@w0` and `@affine` to `@w1` everywhere gives the same program, which still runs as `affine`, and `mime canon` numbers the locals `%v0`, `%v1`, `%v2`. A function's abstract comes after its body: the type is the contract, the body is the meaning, and the abstract, written last, stands in for the body wherever the body is not in view.

## Architecture (planned)

```
mime text ──parse──▶ module ──check──▶ checked form ──┬─▶ LLVM IR ──clang──▶ native
                                                       ├─▶ interpreter
                                                       ├─▶ JavaScript
                                                       └─▶ JVM bytecode
```

LLVM is the only backend today. The others are planned, and every backend must give the same answer for every
program: the spec defines what a program means, never one backend ([design/backends.md](design/backends.md)).

- **Checker:** enforces declare-before-use, definition order, types, and the renaming invariant.
- **Backends:** LLVM today, which emits textual LLVM IR for `clang` to turn into executables. A reference interpreter, JavaScript and the JVM follow, and later an interpreter written in mime.
- **Diagnostics:** structured (JSON) error messages written for agents, so an agent can repair its code in a loop.

## Testing the bet

The thesis is an empirical claim, so mime will be measured. The evaluation plan borrows from languages in the [agentlanguages.dev](https://agentlanguages.dev/) catalogue, especially VeraBench and Lom's RepairLoopBench, and also tries to avoid their known weak spots:

- **Task suite:** the same tasks implemented in mime and in baselines (Python, TypeScript, and other languages with no training data). The model gets the mime spec in context.
- **Metrics:** pass@k over several samples per task, a per-task pass matrix, attempts to green in a compile→diagnose→repair loop, and *total* token cost (spec + generation + retries), not just program length.
- **The key ablation:** run the same mime tasks with meaningful words and with consistently scrambled words. If the thesis holds, scrambling should cost an agent little in mime. In a conventional language it should cost much more.
- **Hygiene:** several models and providers, raw outputs archived, harder tasks added whenever a baseline saturates, and negative results published.

The benchmark lives in [`bench/`](bench/). Its methodology card says what it measures, what it does not, and the known caveats.

## Roadmap

mime grows in small steps, each adding one new thing to the language from design through LLVM lowering. The steps
are in [design/roadmap.md](design/roadmap.md).

## Development

mime will be bootstrapped. The first toolchain is written in Python (3.12+, [hatch](https://hatch.pypa.io/)), and all of that code lives in [`mime-py/`](mime-py/). Once mime can compile itself, `mime-py/` is deleted. Everything that should outlive the bootstrap (design docs in [`design/`](design/), the spec, example programs, benchmarks) lives at the repo root.

`mime run` also needs [clang](https://clang.llvm.org/) on `PATH`, which turns the emitted LLVM IR into an executable. Without it, `mime check` and `mime llvm` still work, and the tests that run programs are skipped.

```bash
cd mime-py
hatch test              # run tests
hatch run mime --version
```

## License

`SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception`. See [LICENSE](LICENSE).
