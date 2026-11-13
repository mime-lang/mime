# Step 8: reference interpreter

> Status: settled. The eighth step of the [roadmap](roadmap.md). It adds the second backend, an interpreter in the
> bootstrap toolchain, and the conformance tests of [backends.md](backends.md) section 3. The language does not
> change: every program means what it meant in step 7.

```
mime run clamp.mime clamp 50 0 10                    # the interpreter, the default
mime run --backend llvm clamp.mime clamp 50 0 10     # a native program, built with clang
```

Both print `10`. `clamp` is the function's `symbol`, not its word: `mime run` calls a program from outside, the way
C or another module would, so it names the function as they do (section 3). From this step on, a step is done only
when both backends agree on every run case.

## 1. The checked form

The checker's output is the form every backend reads ([backends.md](backends.md) section 2). It is `Program`, and
this step names and documents it, without changing it:

- `Program.functions`: one `Function` per definition, in module order, with its `word`, its `inputs` in order,
  each input's type, its output type, the type of every block parameter and local, its `symbol`, and its
  `definition` (its blocks, lines and terminators, as parsed).
- `Program.module`: the module it was checked from, for a backend that prints names. LLVM copies the canonical
  names ([step-6.md](step-6.md)); the interpreter never prints a name.
- A backend is entered through a `symbol`. The checker already proves that symbols are unique C identifiers, so a
  symbol names at most one function on every backend.

A backend may assume everything the checker proves, and checks none of it again: every word and local is bound
before it is read, every operand has the type its operation takes, every jump passes as many arguments as its
target has parameters, and every block ends in exactly one terminator. A backend that finds one of these broken
has met a checker bug, and says so, as `mime llvm` does when clang fails.

A name is only a key in the checked form. The interpreter looks locals and inputs up by their spelling, so
renaming them consistently changes nothing it does, and the renaming test checks that on every run case
(section 5).

## 2. The interpreter

It walks the checked form block by block, in `mime-py/src/mime/interp.py`.

- **State.** The current block and one table of values, which holds the function's inputs, the block's parameters
  and the block's locals. Blocks are closed (step 7), so a jump starts a new table from the inputs and the jump's
  arguments: nothing else crosses a jump, and no value can leak from one block into another.
- **Values.** An `i64` is a Python integer kept in `[-2^63, 2^63)`; an `i1` is `True` or `False`.
- **Lines.** `add`, `sub`, `mul` compute exactly, then wrap to 64 bits in two's complement, as the spec says (step
  3), so `add i64 9223372036854775807, 1` is `-9223372036854775808`. `icmp` compares: the `s` predicates read both
  sides as signed, the `u` predicates read them as unsigned (`x mod 2^64`), so `icmp ult i64 -1, 0` is `false`.
- **Terminators.** `ret v` gives `v`. `br ^b{args}` evaluates the arguments in the current table, then jumps.
  `br %c, ^t{…}, ^f{…}` takes `^t` when `%c` is `true`.
- **Output.** `mime run` prints the result as the LLVM runner does: an `i64` in decimal, an `i1` as `true` or
  `false`, then a newline.

The interpreter has no edge blocks and no `phi`: those are LLVM's form of block parameters, not mime's.

## 3. `mime run --backend`

`mime run [--backend interp|llvm] [--timeout SECONDS] FILE SYMBOL INPUT...`

- **It runs an exported function, named by its symbol.** A word does not survive every renaming: `mime canon`
  renames every word on purpose, and a word in a script or a run case would then name nothing. A symbol is data,
  which no renaming touches ([step-7.md](step-7.md) section 7), so `mime run prog.mime clamp 5 0 10` names the same
  function before and after `rename`, in the canonical form, and in the benchmark harness, whatever the model
  called its words.
- **Only an exported function can be run.** To run a function, give it a `symbol`. An internal helper is run
  through an exported function that calls it, once calls arrive, as a C `static` function is.
- **Mistakes.** A word gets a hint: `@clamp` gives "`mime run` takes a symbol, not a word: write `clamp`" when
  `@clamp` is exported as `clamp`, and "`@clamp` has no symbol; to run it, add `symbol = "clamp"` after its
  abstract" when it is not (the suggested name is the word's own, which the model may change). An unknown symbol
  lists the symbols the program exports. A symbol is the first argument after the file, so an input in its place
  (`5`, `true`) is caught as today: "the symbol is missing".
- **The default is `interp`.** `mime run` then needs no clang, starts at once, and works wherever Python does,
  which is where a model tests what it wrote. `--backend llvm` builds a native program with clang, as `mime run`
  did until now. This changes [backends.md](backends.md) section 6, which said LLVM.
- Both backends share everything before the run: the program is checked, the symbol and the inputs are read and
  checked the same way, with the same messages.
- **Timeout.** A run stops after `--timeout` seconds (10 by default) on both backends, with the same message. The
  interpreter checks the clock at every jump, since only a jump can repeat work.
- **Exit codes.** `0` a result was printed; `1` the program has mistakes (JSON diagnostics on stderr); `2` a usage
  or tool error, the timeout included; `3` a trap (section 4).

## 4. Traps

No operation can trap yet: `add`, `sub`, `mul` and `icmp` are total. This step fixes how a trap is reported, so
that division, the first partial operation, only adds its kinds.

A trap exits with code `3`, prints nothing on stdout, and prints one JSON object on stderr, with the fields of a
diagnostic ([diagnostics.md](diagnostics.md)):

```json
{
  "kind": "trap",
  "entry": "@mean",
  "key": "body",
  "text": "%q = sdiv i64 %sum, %count",
  "message": "`sdiv` by zero",
  "hint": null
}
```

- `entry` is the function whose line trapped, `key` is `body`, and `text` is that line exactly as written, so a
  model finds and fixes it the way it fixes a diagnostic. `--positions` adds its line and column, as for `check`
  (the roadmap asks, before the bootstrap, whether positions are needed at all).
- Every backend reports the same object. The interpreter knows the line at once. A compiled backend passes the
  line's index to a trap routine of its runner, and the toolchain looks the line up; the step that adds the first
  trap builds that routine.
- The `message` says which domain was left (`by zero`, `overflows`), never the values: a value can be large, and
  the line already names what to check.

## 5. Conformance tests

Every clean golden carries its run cases beside it, in `goldens/clean/NAME.runs.json`, written by hand:

```json
[
  {"symbol": "clamp", "inputs": ["-5", "0", "10"], "output": "0"},
  {"symbol": "clamp", "inputs": ["50", "0", "10"], "output": "10"}
]
```

- `inputs` are what `mime run` takes on the command line, `output` is what it prints, without the newline. A later
  step adds `"trap": "…"` in place of `output`, for a case that must trap.
- The golden test runs every case on every backend, on both the golden and its canonical form, and compares it
  with `output`. The LLVM cases are skipped where clang is missing; the interpreter's never are.
- **Every exported function has a case**, and every function of a clean golden is exported, until calls let a
  golden keep an internal helper. A golden whose function has no run case fails the test, so a new golden cannot
  skip its conformance. This step gives a `symbol` to every function of the clean goldens, so their `.ll` changes
  from `define internal … @mime.word` to `define … @symbol`.
- The renaming test runs each scrambled golden on the **same** run cases, unchanged: a symbol is not renamed, so
  the cases need no mapping, and that is the invariant itself.
- `runs.json` is a source, not an approved output: it is the answer the program must give, so nothing rewrites it.
  It is kept in the layout above, one case per line.
- The run cases now spread over `run_test.py`, `branches_test.py`, `symbols_test.py` and the renaming test move
  into the goldens. Tests of `mime run` itself (its argument checks, its messages, the timeout) stay where they are,
  and run on both backends.

## 6. Easy for a model?

- **Familiar:** `mime run` is `python prog.py` or `node prog.js`: run a program, read what it prints. Calling a
  function by its exported name is how C's `main`, `dlsym` and a test runner find one. `--backend` is a flag a
  model needs only to compare backends; the default needs no setup.
- **New:** nothing in the language. A model must export a function before running it, and the hint says so in the
  form to paste. The trap report is a diagnostic with `kind` `trap`, so a model reads it with what it already knows.
- **Mistakes surface** as before: a program with mistakes gives its diagnostics and runs on no backend. A backend
  that disagrees with another is a toolchain bug, caught by the conformance tests before a model sees it.

## 7. What changes elsewhere

- [backends.md](backends.md) section 6: the default backend is the interpreter; section 2 points to section 1 of
  this note for the checked form.
- [spec/SKILL.md](../spec/SKILL.md): the `run` command by symbol, "export a function to run it", `--backend`, and
  exit code `3`.
- The benchmark harness, from its first mime run: each task names the symbol its function must be exported under,
  so the harness never depends on how a model spells its words.
- Every test that runs a program by word, and every golden function, gains a symbol.
- [AGENTS.md](../AGENTS.md): the golden layout gains `NAME.runs.json`.

Not in this step: a step budget in place of the wall clock (runs that are deterministic across machines), and the
unchecked mode of [backends.md](backends.md) section 1.
