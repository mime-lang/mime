# Step 5: renaming and canonical form

> Status: settled. The fifth step of the [roadmap](roadmap.md). It adds `mime fmt`, `mime canon` and
> `mime rename`, and the test that turns mime's thesis into a check: renaming every word never changes a program.

## 1. The invariant

Consistently renaming domain words, including the references inside abstracts, never changes what a program means
([core.md](core.md) section 10). Concretely, after a consistent renaming:

- the checker reports the same mistakes, of the same kinds, in the same entries and keys (with renamed words);
- a clean program stays clean, and every function gives the same output for every input;
- the canonical form is unchanged.

Language words are never renamed. A `\$` in an abstract is a dollar sign, not a reference, so it is never renamed,
and neither is a bad reference such as `$5` or `$numberX`.

**Hints that come from spelling are outside the invariant; what is reported is not.** "Did you mean `@number`?"
for `@numbr` exists because the two spellings are close, and closeness of spelling is exactly what a renaming
changes. After one, the hint may become a general one. But the kind, entry and key of every diagnostic stay the
same: that is what the invariant promises and the renaming test checks. So the checker never lets a guess based on
spelling change what it reports. A misspelled local is an `undeclared-word`, and the local it was probably meant to
be is still an `unused-local`; the hint on the first names the second. (Step 6 removed an earlier rule that hid the
second report: a renaming could make the two spellings unalike and bring the report back. Typo goldens now keep the
renaming test honest about this.) Likewise `%number` used for an input `@number` keeps its hint, but the input is
still reported as unread.

## 2. `mime fmt FILE`

Rewrites the file in its one layout, keeping every word and all the English. It prints nothing.

```
$number = {type = i64, abstract = "a whole number"}

define $double {$number} -> $number {
  $r = add i64 $number, $number
  ret $r
}
abstract = "twice the $number"
```

- A data word is one line: `$w = {key = value, key = value}`, with one space around `=` and after each `,`.
- A definition is `define $f {$a, $b} -> $out {` on one line, then each body line indented by two spaces, then
  `}`, then `abstract = "…"` on its own line. No inputs is `{}`.
- Consecutive data words have no blank line between them. A definition has one blank line before and after it.
- Strings are copied exactly as written, escapes included. The file ends with one newline.
- It needs only a program that parses, so a program with checker errors can be formatted. Fields are printed in
  the order they are written, so `fmt` never hides a `key-order` mistake.

`fmt` is idempotent: formatting a formatted file changes nothing. The golden tests keep every golden formatted, as
oymo does.

## 3. `mime canon FILE`

Prints the canonical form: the `fmt` layout with every domain word replaced by a fixed name.

```
$w0 = {type = i64, abstract = "a whole number"}

define $w1 {$w0} -> $w0 {
  $w2 = add i64 $w0, $w0
  ret $w2
}
abstract = "twice the $w0"
```

- **Names follow first occurrence.** Reading the source from the top, each word gets the next name, `$w0`, `$w1`,
  …, the first time it appears. The numbering depends only on where words appear, never on how they are spelled,
  so a renamed program gets the same names.
- **A result is numbered per body.** Results are bound in a body, and two bodies may reuse a result word, so each
  body's results get fresh names. Otherwise a program that reuses `$s` in two bodies and one that uses `$s` and
  `$t` would not compare equal, though they differ only in naming.
- **Abstracts keep their English,** with their references renamed. Changing an abstract's wording is not renaming,
  so `canon` does not hide it. This is also exactly the scrambled-words program the benchmark needs: the same code
  and the same English, with words that say nothing. (This replaces core.md's "drop the connecting English".)
- **A mention without `$` is plain English,** so canon keeps it as written: in `"doubles it, like double"`, the
  word `double` survives as it is and tells a reader what `$w1` means. The scrambled-words ablation is only clean
  when every mention of a word is marked with `$`. SKILL.md asks models to do that. No checker can enforce it
  without reading the English.
- The output of a clean program is itself a clean program with the same behavior, and `canon` is idempotent.
- Two programs are the same up to renaming exactly when their canonical forms are equal.

## 4. `mime rename FILE '$old' '$new'`

Renames one word everywhere and rewrites the file. It then prints the uses of `$new`, as `mime uses` would.

- Every occurrence of `$old` changes: its entry, every use in a type, input, output or body, and every reference
  in an abstract. Results with that spelling change in every body, since renaming a spelling consistently is still
  a renaming.
- It refuses, and changes nothing, when `$new` already appears anywhere in the file, so it can never merge two
  words. It also refuses when `$old` appears nowhere, with a "did you mean" hint.
- It needs only a program that parses. Everything outside the renamed words, layout and English included, is left
  exactly as it was.

## 5. Errors and exit codes

All three commands need a program that parses. When it does not, they print its diagnostic as JSON on stderr and
exit with `1`, as `mime show` does. A command-line mistake exits with `2`.

## 6. The renaming test

For every golden, the test suite renames every word to a scrambled name and checks the invariant of section 1:
same canonical form, same diagnostic kinds with the renamed entries, and, for the goldens that run, the same output
for the same inputs. This is the roadmap's "done when" for this step, and every later step keeps it passing.

## 7. Model ease

- **Familiar:** `gofmt`, `rustfmt` and `prettier` for `fmt`; "rename symbol" in an editor for `rename`.
- **New:** `canon`, which no mainstream language has. Models never write canonical form; it is for tools and the
  benchmark.
- **How mistakes surface:** a rename onto a word in use is refused with the word that collides. A rename by hand
  that misses an abstract reference is caught by the checker as an undeclared word.
