# mime bench: methodology card

This folder measures whether mime's bet works: **no word is trusted**. Names are optional labels, and meaning comes from forms. This card was written before the first result. Change it only in its own commit, and say why in that commit.

> Status: skeleton. No model has been run yet. The harness runs Python, TypeScript and mime on mock models, and one real model is configured but not yet run: `claude-haiku-5-5`. A mime cell runs only where its task has a mime reference, which today is `t1-002-clamp` on the `generate` track (see [Known caveats](#known-caveats)).

## What it measures

| Question | Track | Metric |
|---|---|---|
| Can a model write a correct program from a description? | `generate` | pass@1, pass@k, tokens until passing |
| Can a model fix a program from the compiler's own diagnostic? | `repair` | pass@1, attempts to green, tokens until passing |
| Does code stay correct after a change request? | `edit` | pass@1, tokens until passing |
| **Does meaning survive when names are removed or lie?** | `names` | pass@1 per name style, and the drop from `honest` to `none` and `misleading` |
| Does generated code carry contracts that reject wrong programs? | `contracts` | share of mutants rejected; `ensures true` scores 0 |

### Primary metric: tokens until passing

For one sample, **tokens until passing** is the sum over every model call in that sample of:

- spec/skill tokens in context (the mime skill file; 0 for Python and TypeScript, because models already know them),
- all other input tokens (task, examples, earlier turns, diagnostics), and
- all generated tokens,

counted until the tests pass or the per-sample budget runs out. Every retry sends the whole conversation again, so retries are counted at their full input cost.

Each cell reports:

- `tokens_per_success` = (tokens over **all** samples, passing or not) / (passing samples). This is the cost of one green program, failures included. It is infinite when nothing passed.
- the median tokens until passing, over passing samples only,
- the share of tokens that went to the spec.

We also report **pass@1** and **pass@k** (k = 5 by default, from n = 10 samples per cell), using the unbiased estimator `1 - C(n-c, k) / C(n, k)` (n samples, c passing).

### Modes (for `generate`, `names` and `edit`)

| Mode | Attempts | Feedback after a failed attempt |
|---|---|---|
| `zero-shot` | 1 | none |
| `self-repair` | up to `max_attempts` | the diagnostic kind and message, plus "N of M tests failed". The failing inputs are not shown. |
| `agentic` | up to `max_attempts` | as `self-repair`, plus up to 3 failing cases (inputs, expected, actual), the way an agent sees them when it runs the tests |

### The `names` track (the core bet)

Each task in this track has a small helper library in three styles. The styles are the same program up to consistent renaming, and CI checks this:

- `honest`: names say what the definition does,
- `none`: opaque names (`w1`, `w2`, ...),
- `misleading`: names are shuffled or swapped, so they lie about the definition.

The model must write `solve` as **one composition of library words**: a single `return` of calls to library functions, applied to the parameters and integer literals. Operators, loops and new definitions are not allowed. The harness enforces this rule, so the only way to pass is to pick helpers by their definitions.

**Prediction:** if the bet holds, mime scores the same on all three styles, and Python and TypeScript drop on `misleading`. If mime also drops, the bet is wrong (or our skill file is), and we publish that.

### The `contracts` track

The model writes code with contracts. Each task has `mutants/`: plausible wrong implementations (off-by-one errors, swapped bounds, a missing case). A contract scores by the share of mutants it rejects. Mutants are also checked against `tests.json` today, so every mutant must fail at least one test. This keeps the tests strong enough to separate right from wrong.

## What it does NOT measure

- **Human readability or ergonomics.** Humans are not mime's users.
- **Runtime performance.** The tests check results, not speed or complexity. An O(n²) answer passes.
- **Large programs.** Tasks are single functions. Whether the bet scales to modules and projects is an open question.
- **Cost in money.** Tokens are not dollars. Prompt caching, batch pricing and price per token differ by provider.
- **Tokens across models.** Each model has its own tokenizer, so compare tokens only within one model.
- **Whether a model "understands" a program.** We measure behavior on tests, nothing else.

## Known caveats

1. **mime runs on one task so far.** mime has a toolchain (`mime-py/`, until mime compiles itself) and a skill file (`spec/SKILL.md`), but no list type yet, so only `t1-002-clamp` has a mime reference (`ref.mime`); the other tasks keep a `ref.mime.todo` placeholder and their mime cells are `unavailable`. The `names` and `edit` tracks have no mime library or `before.mime` yet. The harness does not run the `repair` and `contracts` tracks yet. A mime cell runs `mime check`, then `mime run --backend interp` once per case, inside the same sandbox as the baselines; the harness takes the `mime` command from `MIME_BIN`, or packs the bootstrap toolchain into a zipapp ([design/step-12.md](../design/step-12.md)).
2. **Token counts.** Real runs record the provider's usage numbers, with thinking tokens counted as output. The mock models and `--dry-run` use an estimate, `ceil(utf8_bytes / 4)`. The split of input into spec and non-spec tokens is always that estimate.
3. **The baselines have a home advantage.** Models have seen huge amounts of Python and TypeScript, and none of mime. That gap is what we measure, not something we correct for.
4. **The `names` composition rule is strict.** It removes the escape hatch "ignore the library and write it yourself". It also makes `solve` unusually small, so these tasks test helper selection, not general coding.
5. **TypeScript is type-stripped, not type-checked.** We run it with `node --experimental-strip-types`, so type errors that don't affect runtime are not caught.
6. **The sandbox is namespaces, not a VM.** Model code runs under bubblewrap (`bwrap`). It gets new user, pid, network, ipc, uts and cgroup namespaces, so it has no network. It sees a read-only `/usr` and language runtime, and a writable `/work` that holds only that run's files. There is no home directory, the environment is empty, and CPU time, file size, memory and wall-clock time are limited. Every `smoke.py` run sends escape probes against it: network, host files, environment, writes, host processes, symlink and FIFO output swaps, a busy loop, and a 4 GB allocation. A kernel exploit could still escape, which a VM or gVisor would stop. Real runs refuse to start without a working sandbox. Our own references and mutants run unsandboxed.
7. **Contamination.** Once this repo is public, tasks and references can leak into training data. Hard tasks should rotate, and every report says which task set it used (`tasks_sha256` in the manifest).
8. **Small samples.** 10 samples per cell gives wide confidence intervals. Reports show n and c, so readers can judge for themselves.
9. **Sampling can't be controlled.** Current Claude models reject `temperature`, `top_p` and `top_k`, and the API has no seed. Samples vary through the provider's default sampling, so a rerun cannot reproduce outputs exactly. The archived raw outputs are the record. The manifest says this per model, and a model's thinking depth is fixed with `effort`.
10. **Refusals count as failures.** A provider refusal is recorded as status `refusal`, and we never fall back to another model, because a fallback would silently change the model being measured.

## Rules

1. **Tokens until passing is the primary metric.** pass@1 and pass@k come next.
2. **Archive everything.** Every prompt, raw output (the full provider response, too), diagnostic and score is kept, along with a manifest (model id, sampling settings, effort, seed, date, compiler commit, skill-file hash, task-set hash). A run that stops on a provider error is marked `aborted` and does not count. A result without its raw outputs doesn't count. `harness/validate.py` rejects a results folder with missing raw files.
3. **Avoid saturation.** Tasks come in 3 tiers. We keep adding tier-3 tasks until the best baseline scores **below 90%** pass@1 on tier 3. Reports flag a saturated tier.
4. **Baselines.** Every task also runs in Python and TypeScript, with the same `tests.json`.
5. **Small models count.** Every real run includes at least one small, cheap model. The runner refuses a real run without one.
6. **Failures feed the language.** Each failure class becomes a GitHub issue, a `tests/fail/` case and, where it helps, a new `examples/` file.
7. **Reports are generated.** `reports/` is written by `harness/report.py`, never by hand.
8. **Negative results are published.**

## Layout

```
bench/
├── README.md              this card
├── tasks/<tier>-<id>-<slug>/
│   ├── task.md            language-neutral description (no examples; those come from tests.json)
│   ├── tests.json         entry, signature, cases (some marked "example")
│   ├── ref.py  ref.ts     baseline references
│   ├── ref.mime           mime reference (ref.mime.todo: placeholder until mime can write the task)
│   ├── mutants/*.py       plausible wrong programs; each must fail a test
│   └── variants/          names track: names.json + honest/ none/ misleading/
├── repair/<id>/           broken.mime, diagnostic.json (verbatim), expected.mime
├── edit/<id>/             before.*, change.md, tests.json, after.* (reference)
├── harness/
│   ├── run.py             runner: --mock, --dry-run
│   ├── models.toml        settings + model list (only mocks until the owner picks models)
│   ├── count_tokens.py    token ledger: spec + input + output, across retries
│   ├── report.py          scores.jsonl → reports/*.md
│   ├── validate.py        CI check: task format, references, mutants, renaming, diagnostics, results
│   ├── smoke.py           CI check: the harness itself, on mock models
├── ci/bench.yml           the CI workflow, kept inactive (GitHub Actions is off for now)
│   └── prompts/           prompt templates (hashed into every manifest)
├── results/<YYYY-MM-DD>-<commit>/
│   ├── manifest.json
│   ├── raw/               every prompt + raw output + diagnostic, never deleted
│   └── scores.jsonl
└── reports/               generated
```

When results grow large, `results/` moves to a separate repo, `mime-lang/mime-bench`.

### Task format

`tests.json`:

```json
{
  "task": "t1-001-sum-list",
  "tier": 1,
  "entry": "solve",
  "signature": {"params": ["list<i64>"], "returns": "i64"},
  "cases": [{"args": [[1, 2, 3]], "expected": 6, "example": true}]
}
```

The types are `i64`, `bool` and `list<i64>`. Every integer in a case must fit in 32 bits, so no language overflows and no case depends on overflow behavior. Each task needs at least 5 cases, and at least one of them marked `example`.

## Running

From the repo root:

```bash
python3 bench/harness/validate.py                  # the CI checks (run them by hand: GitHub Actions is off)
python3 bench/harness/run.py --mock --dry-run      # show the plan, call nothing
python3 bench/harness/run.py --mock                # run mock models end to end
python3 bench/harness/report.py bench/results/<run>
```

Mock runs write to `results/<date>-<commit>-mock/`, which git ignores.

A real run (no `--mock`) needs the `anthropic` package, credentials, a clean, committed working tree, a working `bwrap` sandbox, and `--allow-spend`. Choosing models and spending API credit is the project owner's decision. Today `models.toml` lists only `claude-haiku-5-5` (small, effort `medium`). The first real run is staged:

```bash
python3 bench/harness/run.py --dry-run                                   # free: call count
python3 bench/harness/run.py --allow-spend --track generate --lang python --mode zero-shot --samples 1 --task t1-001-sum-list
```

## Prior art and what we changed

| Prior benchmark | What we copy | The flaw we avoid, and how |
|---|---|---|
| VeraBench (Vera) | Same problems in the new language and in Python/TS; the new language gets only a skill file | One run, no pass@k, saturated, results not checked in → n = 10 samples, pass@k, a saturation rule, archived raw results |
| RepairLoopBench (Lom) | Repair from verbatim live-compiler diagnostics; CI re-checks them | Raw outputs not archived → `raw/` is mandatory and validated |
| AILANG dashboard | 3 modes, many models, every release | No fixed comparison point → the manifest pins the task-set hash and the skill-file hash |
| ilo personas | Every confusion becomes a language bug, a regression test and an example | Spec loading cost left out of token counts → spec tokens are part of the primary metric |
| Codong Arena / NERD | Tokens per solution vs mainstream languages | Output tokens only, one task, no correctness → all tokens, until *passing*, over every task |
