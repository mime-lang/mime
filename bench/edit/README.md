# edit track

Each case is a folder `edit/<id>/` with:

- `before.py`, `before.ts`, `before.mime` (or `before.mime.todo`): a working program,
- `change.md`: a language-neutral change request,
- `tests.json`: tests for the program **after** the change. `before.*` must fail at least one of them,
- `after.py`, `after.ts`, `after.mime`: reference results of the change.

The model returns the whole modified program. For mime, this track checks that positional slots and IDs stay correct after an edit (Vera's slots "stop being obvious" after editing).
