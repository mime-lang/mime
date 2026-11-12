# Tools

> Status: settled. Adds `mime show` and `mime uses`; `mime rename` is planned with [roadmap](roadmap.md) step 5.

An agent working on a program does more than check and run it: it reads one entry, finds where a word is used,
and renames a word. With general text tools (`grep`, `sed`, `jq`), each of these is a little wrong for mime:

- `grep '\$number'` also matches `\$number` in an abstract, which is an escaped dollar sign, not a reference.
- `grep` can't tell which entry and key a match is in, and `sed -n` needs line numbers.
- A JSON filter is a query language of its own. A model can read a short list without one.

So the rule is: **every operation an agent needs on a mime program is a mime command**, and it uses the
language's own rules. mime does not clone general text tools. It adds a command when agents need one for a
mime-specific job.

## 1. Output

- A command that prints a **program or part of one** prints mime source, copied exactly from the file.
- A command that prints a **report** prints a JSON array, indented by two spaces. Each item has the location
  fields of a diagnostic ([diagnostics.md](diagnostics.md)): `entry`, `key` and `text`, and `line` and `column`
  with `--positions`.
- A word on the command line is written as in the source, with its `$` and in single quotes, as for `mime run`
  ([step-1.md](step-1.md) section 4).
- Exit codes are the same for every command: `0` success, `1` the program has errors (the diagnostics are printed
  on stderr), `2` the command line is wrong.

## 2. `mime show FILE '$word'`

Prints the entry for `$word`, from its word to its closing `}`, exactly as written, then a newline.

```
$ mime show prog.mime '$number'
$number = {type = i64, abstract = "a whole number"}
```

- It needs only a program that parses. A program with checker errors can still be shown, since showing an
  entry is often how an agent starts to fix one.
- When a word has two entries (`duplicate-word`), both are printed, in order, with a blank line between them.
- A word with no entry is a command-line error, with a "did you mean" hint.
- From step 4 ([layout.md](layout.md)), a function word's entry is its definition, from `define` through its
  `abstract`, so `show` prints all of it: type, body and abstract in one place.

## 3. `mime uses FILE '$word'`

Prints every reference to `$word` in source order: in a type, a function's inputs or output, a body, and an
abstract.

```
$ mime uses prog.mime '$number'
[
  {
    "entry": "$same",
    "key": "type",
    "text": "$number"
  },
  {
    "entry": "$same",
    "key": "body",
    "text": "$number"
  },
  ...
]
```

- The entry that declares the word is not a use.
- A reference is found by the reference rules of [step-2.md](step-2.md), so `\$number` is not a use and
  `$numbers` is a different word.
- It needs only a program that parses, like `show`. A word that no entry declares is allowed when something refers
  to it, which is how an agent finds every copy of a typo. A word with no entry and no uses is a command-line
  error, with a "did you mean" hint, so a misspelled word is never read as "unused".
- `text` is always the reference itself. It is kept so a use has the same shape as a diagnostic's location.

## 4. Model ease

- **Familiar:** "go to definition" and "find references" in an editor or language server, and `git grep`.
- **New:** the answer is in the program's own terms (entry and key), not lines.
- **How mistakes surface:** forgetting the single quotes is caught the same way as in `mime run`, with the
  hint "write '$name'". A misspelled word gets "did you mean" from both commands. `[]` from `uses` always means
  a declared word that nothing refers to.

## 5. Out of scope

- `mime rename FILE '$old' '$new'`, which rewrites a word and every reference to it. It comes with step 5
  (`mime canon`), which rewrites references anyway.
- When step 3 adds local words, `uses` will include their uses.
