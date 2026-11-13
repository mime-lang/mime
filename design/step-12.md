# Step 12: first benchmark run

> Status: settled. The twelfth step of the [roadmap](roadmap.md). It makes mime cells of the benchmark ([bench/README.md](../bench/README.md)) run, starting with `t1-002-clamp`, the
> one task mime can write today. The language does not change.

## 1. What runs

- **A mime cell runs when its task has a mime reference.** `ref.mime` replaces `ref.mime.todo`, and the harness
  treats a task with only the placeholder as it does now: `unavailable`, with the reason "no mime reference yet".
  Today that leaves `clamp` (`icmp` and `br`); `sum-list`, `is-sorted`, `merge-sorted` and
  `shortest-k-distinct` need lists.
- **Tracks.** `generate` runs. `names` needs a mime library in three name styles and `edit` a `before.mime`; no task
  has either yet, so those cells stay `unavailable`, as `repair` and `contracts` do.
- **The reference is the golden's program,** exported as `solve`: `tests/goldens/clean/clamp.mime` with
  `symbol = "solve"`. `validate.py` checks that it passes `tests.json`, as it does for `ref.py` and `ref.ts`.

## 2. How the harness finds mime

The harness depends on the `mime` command, never on how it is built:

- **`MIME_BIN`**, as `validate.py` already reads it, names a single self-contained file: a native program, or a
  Python zipapp (`.pyz`) that the harness runs with its own Python.
- **Otherwise, the bootstrap:** the harness packs `mime-py/src` into a zipapp in a temporary folder, with a
  `__main__.py` that calls `mime.cli:main`. The bootstrap toolchain uses only Python's standard library, so the
  archive needs nothing installed. This is the one place `bench/` knows where the bootstrap lives; once mime
  compiles itself, it is a `MIME_BIN` default instead.
- `execute.available('mime')` is `None` when either works. The manifest records the toolchain's version
  (`mime --version`) next to the compiler commit it already has.

## 3. How a mime cell runs

The same as a Python or TypeScript cell: one driver in `/work`, inside the same sandbox, with the same limits.

- **`/work` holds** `solution.mime`, `mime.pyz` (or the native `mime`), `cases.json` and a driver. A zipapp runs on
  the Python runtime the sandbox already binds for Python cells, so the sandbox needs no new mount. Model code is
  still run under bubblewrap: the toolchain is ours, but it runs the model's program.
- **The driver** is a small Python script, like the Python cells' driver, that only uses the CLI's contract: its
  arguments, its exit codes and what it prints ([step-8.md](step-8.md) section 3):
  1. `mime check solution.mime`. A diagnostic stops the cell: `compile_error`, with the first diagnostic's `kind`
     and `message`, so `self-repair` feedback carries the compiler's own words.
  2. For each case, `mime run --backend interp --timeout T solution.mime solve ARGS…`, with `true`/`false` for a
     `bool`. Exit `0` is the value: an integer, or `true`/`false`. Exit `3` is a trap, and exit `2` the timeout or
     running out of stack, each recorded as that case's error with mime's own message.
- **The interpreter, not LLVM,** since it needs no clang in the sandbox and every backend means the same
  ([backends.md](backends.md) section 3).
- **The entry is a symbol.** A model exports its function as `symbol = "solve"`; renaming never changes a symbol,
  so the harness finds the function whatever words the model chose.

## 4. What the model sees

- The system prompt already includes [spec/SKILL.md](../spec/SKILL.md), counted as spec tokens.
- **The signature is a skeleton,** in place of the neutral `solve(i64, i64, i64) -> i64`, since a mime function needs
  data words, an abstract and a symbol, and SKILL.md does not say how the harness calls it:

  ```
  @a0 = {type = i64, abstract = "…"}
  @a1 = {type = i64, abstract = "…"}
  @a2 = {type = i64, abstract = "…"}

  define @solve {@a0, @a1, @a2} -> i64 {
    …
  }
  abstract = "…"
  symbol = "solve"
  ```

  The words `@a0`, `@a1`, `@a2` match the Python and TypeScript signatures' `a0`, `a1`, `a2`. A `bool` is `i1`. A
  `list<i64>` has no skeleton yet, which is why such a task is `unavailable`.
- Examples are written as for TypeScript: `solve(5, 0, 10)` returns `5`.

## 5. What this step does not do

- **The scrambled-words ablation.** It belongs to the `names` track, which needs a mime library in three styles. The
  `none` style of a mime library is its `mime canon`, and its `honest` style its `mime canon --keep-words`
  ([step-11.md](step-11.md) section 5). That arrives with the first task that has a mime library, not here.
- **A real model run.** Choosing models and spending credit is the owner's decision ([bench/README.md](../bench/README.md),
  Running). This step makes the mime cells run on the mock models, through `smoke.py`, and shows the plan of a real
  run with `run.py --dry-run`.
- **The methodology card** changes in its own commit, as it requires: the known caveat "mime is not runnable yet"
  becomes what is runnable, and the layout's `ref.mime.todo` line names `ref.mime`.

## 6. Done when

- `validate.py` passes with `clamp`'s `ref.mime` checked against `tests.json`.
- `smoke.py` runs mime cells on the mock models: the reference passes, a broken program is a `compile_error` with
  mime's diagnostic, and the sandbox probes still hold.
- `run.py --mock --lang mime --task t1-002-clamp` writes scores, and `run.py --dry-run` lists mime cells for `clamp`
  only.
- `hatch test` still passes; nothing in `mime-py/` changes.
