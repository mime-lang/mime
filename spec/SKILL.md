# mime

mime is a language where a word means only what its entry says. Its spelling carries nothing: renaming every word
consistently never changes a program. This is the whole language as of roadmap step 1.

## Words

- A **domain word** is `$` plus a name: `$number`, `$same`. You declare these. Each has exactly one entry.
- A **language word** is a bare name fixed by mime: `description`, `sort`, `takes`, `returns`, `body`, `i64`, `input`.
- A name is `[a-z][a-z0-9_]*`.

## A program

A program is a list of entries. An entry is `$word = {key = value, …}`. There are two kinds, and their keys must
appear in exactly this order:

```
$number = {description = "a whole number", sort = i64}
$same   = {description = "the number it is given", takes = $number, returns = $number, body = input}
```

| Kind | Keys, in order |
|---|---|
| sort entry | `description` (a non-empty string), `sort` (`i64`) |
| function entry | `description` (a non-empty string), `takes` (a sort entry's word), `returns` (a sort entry's word), `body` (`input`) |

- `input` is the value the function takes. It is the only body that exists so far.
- `takes` and `returns` must name a sort entry declared **earlier** in the file.
- Fields are separated by commas. No trailing comma. Entries are not separated by anything.
- Entries never nest. Declare every word as its own top-level entry.
- There are **no comments**. Put English in a `description`.
- Strings are `"…"` on one line. Escapes: `\"`, `\\`, `\$`. A bare `$` in a string is an error for now.

## Commands

```
mime check prog.mime          # report every mistake; add --json for a JSON array
mime run prog.mime '$same' 7  # run $same on 7
mime llvm prog.mime           # print the LLVM IR
```

On the command line, write the word as in the source and in **single quotes**: `'$same'`. Without them, a shell
expands `$same` as a variable before mime sees it.

Each diagnostic has a `kind`, a `message`, a 1-based `line` and `column`, and usually a `hint` that names the fix.
