# repair track

Each case is a folder `repair/<id>/` with:

- `broken.mime`: a program with one mistake,
- `diagnostic.json`: the output of `mime check --json broken.mime`, captured **verbatim** from the live compiler, never written by hand,
- `expected.mime`: a fixed program that checks clean and passes `tests.json`,
- `tests.json`: same format as `tasks/*/tests.json`.

The model sees `broken.mime` and `diagnostic.json` and must return a fixed program. CI (`harness/validate.py`) runs `mime check --json` on every `broken.mime` and fails if the output no longer matches `diagnostic.json`. When the compiler's diagnostics change, recapture them and review the diff.

There are no cases yet: the compiler does not exist. A case added before then makes CI fail on purpose, since a diagnostic that no live compiler produced cannot be verbatim.
