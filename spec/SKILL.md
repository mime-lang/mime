# mime

mime is a language where a word means only what its entry says. Its spelling carries nothing: renaming every word
consistently never changes a program. This is the whole language as of roadmap step 3.

## Words

- A **domain word** is `$` plus a name: `$number`, `$same`. You declare these. Each module word has exactly one
  entry; a local is bound by a `let` (below).
- A **language word** is a bare name fixed by mime: `description`, `sort`, `takes`, `returns`, `body`, `i64`, `input`,
  `let`, `in`, `add`, `sub`, `mul`.
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
| function entry | `description` (a non-empty string), `takes` (a sort entry's word), `returns` (a sort entry's word), `body` (see Bodies) |

- `takes` and `returns` must name a sort entry declared **earlier** in the file.
- Fields are separated by commas. No trailing comma. Entries are not separated by anything.
- Entries never nest. Declare every word as its own top-level entry.
- There are **no comments**. Put English in a `description`.
- Strings are `"…"` on one line. Escapes: `\"`, `\\`, `\$`.

## Bodies

A body is a chain of `let`s that ends in one value. Each `let` names the result of one operation.

```
$affine = {
  description = "three times the $number it is given, plus one",
  takes = $number,
  returns = $number,
  body = let $double = add {i64, input, input} in
         let $triple = add {i64, $double, input} in
         let $result = add {i64, $triple, 1} in
         $result
}
```

- An operation is `add`, `sub` or `mul`, then `{sort, a, b}`. The sort comes first and is always `i64`.
- An operand, and the final value, is `input` (the value the function takes), a local bound **earlier** in the same
  body, or a decimal integer (`1`, `-7`; no leading zeros). `body = input` and `body = 7` are valid bodies.
- **No nesting.** `add {i64, mul {…}, 1}` is an error: bind `mul` with its own `let` and use its local. A bare
  `add {…}` as a body needs a `let` too.
- No infix and no parentheses: `input + 1` and `add(i64, input, 1)` are errors.
- A local has no description. It must be unique in its body, must not be a module word, and must be read by
  something later. Different functions may use the same local word.
- Overflow wraps: `add {i64, 9223372036854775807, 1}` is `-9223372036854775808`.

## References in descriptions

Inside a `description`, `$word` is a **checked reference**: it must name an entry declared **earlier** in the file.
The English around it is never read.

```
$number = {description = "a whole number", sort = i64}
$same   = {description = "the $number it is given", takes = $number, returns = $number, body = input}
```

- A description cannot refer to its own word, or to a later entry.
- Every `$` in a description starts a reference. Write `\$` for a dollar sign: `"costs \$5"`.
- A reference follows the same name rule as in code: `"$number's"` and `"($number)"` are fine, but `"$numberX"` and
  `"$number-ish"` are errors, not `$number` followed by text.
- References are optional.

## Commands

```
mime check prog.mime          # report every mistake, as a JSON array
mime run prog.mime '$same' 7  # run $same on 7
mime llvm prog.mime           # print the LLVM IR
mime show prog.mime '$same'   # print the entry for $same, exactly as written
mime uses prog.mime '$number' # list every reference to $number, as a JSON array
```

Use `show` and `uses` instead of `grep` or `sed`: they follow mime's rules, so `\$number` in a description is not
a use, and each use names its `entry` and `key`. Both work on a program with checker errors.

On the command line, write the word as in the source and in **single quotes**: `'$same'`. Without them, a shell
expands `$same` as a variable before mime sees it.

Each diagnostic has a `kind`, the `entry` and `key` it is in, the exact source `text` at fault, a `message`, and
usually a `hint` that names the fix. A field that does not apply is `null`. To fix a mistake, find `text` inside
that entry's field and replace it.

```json
[
  {
    "kind": "undeclared-word",
    "entry": "$same",
    "key": "takes",
    "text": "$numbr",
    "message": "no entry declares `$numbr`",
    "hint": "did you mean `$number`?"
  }
]
```
