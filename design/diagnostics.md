# Diagnostics

> Status: settled. Replaces the output format in [step-1.md](step-1.md) section 5. The kinds stay as each step
> defines them.

A diagnostic tells an agent what is wrong with a program and where. Its reader is a model, so its form follows
how a model reads and edits code, not how a terminal shows it.

```
mime check prog.mime
```

```json
[
  {
    "kind": "undeclared-word",
    "entry": "$same",
    "key": "type",
    "text": "$numbr",
    "message": "no entry declares `$numbr`",
    "hint": "did you mean `$number`?"
  }
]
```

## 1. One format

`mime check` prints a JSON array, indented by two spaces, with `[]` when the program is clean. `mime llvm` and
`mime run` print the same array on stderr when the program has errors. There is no text format and no `--json`
flag. Two formats for one report would break the rule of one canonical form, and a model, the reader mime is
for, reads JSON at least as well as `file:line:col:` lines. JSON also labels every part, so a message that itself
contains `:` or backticks can't be misread.

The golden tests approve exactly this output, so the goldens show what a model sees.

## 2. Fields

Every diagnostic has the same six fields, in this order. A field that does not apply is `null`, so the shape
never changes.

| Field | Value |
|---|---|
| `kind` | a stable code, such as `undeclared-word`; tests and the benchmark match on it |
| `entry` | the word of the entry the mistake is in, with its `$`, or `null` when the mistake is outside any entry or before its word is read |
| `key` | the key of the field the mistake is in, such as `type` or `body`, or `null` when it is in no one field |
| `text` | the exact source text at fault, or `null` when the mistake is something missing |
| `message` | what is wrong, in one sentence |
| `hint` | how to fix it, or `null` |

`text` is copied from the source, escapes and all, so it can be found by searching the file. For example:

- a misspelled word: `$numbr`
- a misplaced or unknown key: `type`
- a bad value: `i32`
- a bad `$` in an abstract: `$5`, `$numberX`
- a comment: the rest of its line

A missing key has no text; `entry` names the entry it is missing from.

## 3. Positions

`--positions` adds `line` and `column` after the six fields:

```
mime check --positions prog.mime
```

Both are 1-based. A column counts characters of the source line, so an escape such as `\"` counts as two. They are
off by default because they suit editors and people, not models:

- A model sees tokens, not characters, so it counts columns poorly.
- Line numbers go stale after the first fix, while a model is still working through the list.
- An agent edits by replacing exact text, which `text` gives it.

`entry` and `key` locate a mistake in the program's own terms. Words are unique in a module and keys come in a
fixed order, so the pair is exact, and fixing one entry does not move the location of a mistake in another.

## 4. Model ease

- **Familiar:** compiler diagnostics as JSON (rustc `--error-format=json`, the Language Server Protocol), and a
  `text` field, like the code snippet in a rustc error.
- **New:** the location is a word and a key, not a line and column. Nothing has to be counted.
- **How mistakes surface:** when `text` occurs more than once in a file, the model may edit the wrong copy.
  `entry` and `key` narrow it to one field. Words are unique, so a second copy can only be inside the same field,
  or in a `duplicate-word` entry, and `--positions` settles that.

## 5. Out of scope

- A machine-applicable `fix` (replace this text with that one), like rustc's suggestions. It needs its own design
  note.
- Command-line errors (exit code 2), such as a missing file. These are about the command, not the program, and
  stay plain `mime: …` lines on stderr.
