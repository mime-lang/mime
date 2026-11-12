# Step 1: one entry, one function

> Status: settled. This is the first step of the [roadmap](roadmap.md). It fixes the smallest grammar that
> runs end to end, how a program is run, and how mistakes are reported.

The program this step must run:

```
$number = {description = "a whole number", sort = i64}
$same   = {description = "the number it is given", takes = $number, returns = $number, body = input}
```

## 1. Lexical rules

| Token | Form | Example |
|---|---|---|
| domain word | `$` then a name | `$number` |
| language word | a name | `sort`, `i64`, `input` |
| string | `"` … `"` on one line; escapes `\"`, `\\`, `\$` | `"a whole number"` |
| punctuation | `{` `}` `=` `,` | |

- A **name** is a lowercase ASCII letter followed by lowercase letters, digits, or `_`: `[a-z][a-z0-9_]*`.
- Whitespace (space, tab, newline) separates tokens and is otherwise ignored.
- **There are no comments.** English belongs in a `description`, where its references are checked (step 2). A
  comment would be English that nothing checks, which is exactly the borrowed meaning mime removes.
- An unescaped `$` inside a string is an error in this step. Step 2 makes it a reference, so reserving it now means
  no step 1 program changes meaning later.

**Model ease.** Familiar: lowercase identifiers and JSON strings. New: no comments. A model that writes `; note` or
`// note` gets "comments are not part of mime; put the English in a description".

## 2. Grammar

```
module = entry*
entry  = word "=" "{" field ("," field)* "}"
field  = name "=" value
value  = string | word | name
```

- A module is a sequence of entries, in order, with no separator between them. An entry ends at its `}`.
- Fields are separated by commas. **A trailing comma is an error**, as in JSON.

There are two kinds of entry, told apart by their keys. The keys must appear in this order:

| Kind | Keys, in order | Values in this step |
|---|---|---|
| sort entry | `description`, `sort` | a string; `i64` |
| function entry | `description`, `takes`, `returns`, `body` | a string; a word; a word; `input` |

Fixed order is one form: two agents writing the same entry write the same text. `description` comes first, so a
reader meets the meaning before the mechanics.

**Model ease.** Familiar: JSON objects and tool definitions, which models write with `description` first anyway. New:
key order is checked. A wrong order is reported with the expected order, so the repair is mechanical.

## 3. Checks

The parser stops at the first syntax error. The checker reports every error it finds.

| Kind | When | Hint |
|---|---|---|
| `syntax` | the text does not match the grammar | what was expected |
| `trailing-comma` | a `,` before `}` | remove it |
| `comment` | `;`, `//` or `#` | put the English in a description |
| `nested-entry` | a `$` key or a `{…}` value inside an entry | declare it as its own entry |
| `unknown-language-word` | a bare name that is not a language word, where a word belongs | did you mean `$name`? |
| `unknown-key` | a key that no entry kind has | `type` → did you mean `sort`? |
| `missing-key` | an entry lacks a key of its kind | the full key list |
| `key-order` | keys out of order | the expected order |
| `duplicate-key` | a key appears twice | |
| `duplicate-word` | a word has two entries | where the first one is |
| `undeclared-word` | a word with no entry | |
| `forward-reference` | `takes`/`returns` names a later entry | move the entry up |
| `not-a-sort` | `takes`/`returns` names a function entry | |
| `dollar-in-string` | an unescaped `$` in a string | references arrive in step 2; write `\$` for a dollar sign |
| `bad-value` | a value of the wrong form for its key, or an empty description | what the key takes |

`takes` and `returns` refer backward, like descriptions: they describe the function, they are not part of its body.

## 4. Running a program

```
mime check prog.mime
mime run prog.mime '$same' 7
```

- There is no `main`. A special name would give one spelling a meaning, which the ground rules forbid. The entry
  point is chosen on the command line.
- The word is written as in the source, with its `$`, so it can be copied from the file and found with grep. It
  goes in **single quotes**, because a shell treats `$same` as a variable and expands it before mime runs. A word
  without `$` is rejected with a hint, so there is one form.
- Forgetting the quotes fails loudly. Unquoted, the shell usually expands `$same` to nothing, so mime sees `7` where
  the word belongs. In double quotes, it sees an empty word. Both get the hint "write '$name'".
- This form is temporary. Step 5 adds calls, and then `mime run` takes one argument written as a mime call, so the
  command line and the language share one form.
- The input is a decimal integer argument. The result is printed as a decimal integer and a newline.
- `mime llvm prog.mime` prints the LLVM IR, for debugging and for tests.
- Exit codes: `0` success, `1` the program has errors, `2` the command line is wrong or `clang` is missing.

## 5. Diagnostics

`mime check` prints one line per diagnostic: `prog.mime:2:52: undeclared-word: no entry declares $numbr`, then the
hint, if any, on the next line. `mime check --json` prints a JSON array instead (`[]` when clean):

```json
[{"kind": "undeclared-word", "message": "no entry declares $numbr", "line": 2, "column": 52, "hint": null}]
```

`kind` is a stable code: tests and the benchmark's repair track match on it. Line and column are 1-based, and a
column counts characters.

## 6. Lowering

Each function entry becomes one LLVM function. A sort entry produces no code.

```llvm
define i64 @"$same"(i64 %input) {
  ret i64 %input
}
```

`mime run` adds a C `main` that parses the argument with `strtoll`, calls the function, and prints with `printf`. It
compiles with `clang`. Symbol names follow the source words, which keeps the IR readable. Renaming changes the
symbols but not the behavior, which is what the renaming invariant asks for.

## 7. Out of scope

Everything after step 1 in the roadmap: description references, `let`, operations, literals, calls, branches,
structs, imports.
