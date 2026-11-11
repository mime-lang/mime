# Agent guide for mime

mime is a language for AI agents to read and write. You, the agent, are its primary user. Read [README.md](README.md) for the thesis first.

## Ground rules of the language

- A word means only what its declaration says. Never infer meaning from how a word is spelled.
- Declare before use. Definitions refer only to earlier words or core primitives.
- Consistent renaming must never change meaning. Do not add features that break this, such as reflection on names or string-to-word lookup.
- Prefer one canonical form per computation over convenient alternatives.

## Repository

- `mime-py/`: the Python bootstrap toolchain (parser, checker, LLVM lowering, CLI). It will be deleted once mime compiles itself, so keep every Python-specific file inside it.
  - `mime-py/src/mime/`: toolchain source
  - `mime-py/tests/`: tests, named `*_test.py`
- `design/`: design documents that outlive the bootstrap (`docs/` is reserved for a future GitHub Pages site)
- `bench/`: the benchmark that tests mime's bet. Read [bench/README.md](bench/README.md) (the methodology card) before you change anything there.

## Commands

Run these from `mime-py/`:

```bash
hatch test        # all tests
hatch check       # lint, format, and type check
```

Run these from the repo root:

```bash
python3 bench/harness/validate.py     # benchmark format check (add --require-node to also run the TypeScript references)
python3 bench/harness/smoke.py        # the harness itself, on mock models
```

## Conventions

- Nothing outside `mime-py/` may depend on Python. One exception: `bench/` uses Python, because it runs Python baselines. Its harness uses only the standard library, except that a real model run imports the provider's SDK (`anthropic`).
- Python 3.12+, ruff, line length 120, single quotes.
- Every language feature gets a design note in `design/` before it gets an implementation.
- GitHub Actions is off until the owner says otherwise. Do not add or move files into `.github/workflows/`. The benchmark workflow waits in `bench/ci/bench.yml`.
