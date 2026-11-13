# Tools

> Status: settled. Adds `mime show` and `mime uses`. `mime fmt`, `mime canon` and `mime rename` came with
> [roadmap](roadmap.md) step 5 ([step-5.md](step-5.md)).

An agent working on a program does more than check and run it: it reads one entry, finds where a word is used,
and renames a word. With general text tools (`grep`, `sed`, `jq`), each of these is a little wrong for mime:

- `grep '\@number'` also matches `\@number` in an abstract, which is an escaped dollar sign, not a reference.
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
- A word on the command line is written as in the source, with its `@`, as for `mime run`
  ([step-1.md](step-1.md) section 4).
- Exit codes are the same for every command: `0` success, `1` the program has errors (the diagnostics are printed
  on stderr), `2` the command line is wrong.

## 2. `mime show FILE @word`

Prints the entry for `@word`, from its word to its closing `}`, exactly as written, then a newline.

```
$ mime show prog.mime @number
@number = {type = i64, abstract = "a whole number"}
```

- It needs only a program that parses. A program with checker errors can still be shown, since showing an
  entry is often how an agent starts to fix one.
- When a word has two entries (`duplicate-word`), both are printed, in order, with a blank line between them.
- A word with no entry is a command-line error, with a "did you mean" hint.
- From step 4 ([layout.md](layout.md)), a function word's entry is its definition, from `define` through its
  `abstract`, so `show` prints all of it: type, body and abstract in one place.

### 2.1 A function's head words

A function's inputs and output are data words, declared at the top of the module and often far from the
`define`. A model shown only the `define` sees `{@n} -> @flag` without what `@n` and `@flag` mean. So for a
function, `show` first prints the entry of every data word in its type, then the function:

```
$ mime show even_odd.mime @odd
@n = {type = i64, abstract = "a whole number, zero or more"}

@flag = {type = i1, abstract = "a truth value"}

define @odd {@n} -> @flag {
  …
}
abstract = "whether @n is odd, the opposite of @even"
```

- **Only the head.** The words of the function's inputs and output, each once. Not the words its body or abstract
  name, nor the words inside a head word's own type: one level, so the output stays short and predictable.
- **In source order,** with a blank line between entries, as for a duplicate word. So the output keeps the rule of
  [layout.md](layout.md) section 1: every entry printed refers only to entries printed above it, or to words
  outside the head.
- A head word with no entry, such as a typo in a program with checker errors, or a primitive such as `i64`, is
  skipped. A function word in a head is skipped too; the checker reports it.
- The same applies to a `declare` shown while there is no `define`.
- A data word is still printed alone: its entry already holds its type and abstract.
- The words stay in one place in the module ([layout.md](layout.md) section 3), so they stay shared and nominal.
  Only what the tool prints gets closer.

*Easy for a model:* "go to definition" that also brings the hover text of each parameter, as an editor does. One
command gives everything needed to read or change a function, so a model need not chase words up the file, and
never edits a function without seeing what its inputs mean.

## 3. `mime uses FILE @word`

Prints every reference to `@word` in source order: in a type, a function's inputs or output, a body, and an
abstract.

```
$ mime uses prog.mime @number
[
  {
    "entry": "@same",
    "key": "type",
    "text": "@number"
  },
  {
    "entry": "@same",
    "key": "body",
    "text": "@number"
  },
  ...
]
```

- The entry that declares the word is not a use.
- A reference is found by the reference rules of [step-2.md](step-2.md), so `\@number` is not a use and
  `@numbers` is a different word.
- It needs only a program that parses, like `show`. A word that no entry declares is allowed when something refers
  to it, which is how an agent finds every copy of a typo. A word with no entry and no uses is a command-line
  error, with a "did you mean" hint, so a misspelled word is never read as "unused".
- `text` is always the reference itself. It is kept so a use has the same shape as a diagnostic's location.

## 4. Model ease

- **Familiar:** "go to definition" and "find references" in an editor or language server, and `git grep`.
- **New:** the answer is in the program's own terms (entry and key), not lines.
- **How mistakes surface:** a word written without its `@`, or with an old `$`, gets the form to write, as in
  `mime run`. A misspelled word gets "did you mean" from both commands. `[]` from `uses` always means
  a declared word that nothing refers to.

## 5. Out of scope

- `mime rename` is described in [step-5.md](step-5.md).
