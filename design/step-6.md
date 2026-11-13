# Step 6: `@` words and `%` locals

> Status: settled. The sixth step of the [roadmap](roadmap.md). It splits domain words into two classes by sigil:
> `@word` for a word with an entry, and `%local` for a value bound in one body. It also lets `mime canon` replace
> local names with numbers that carry no meaning. It changes the form of every program once more, like step 4.

```
@number = {type = i64, abstract = "a whole number"}

define @affine {@number} -> @number {
  %double = add i64 @number, @number
  %triple = add i64 %double, @number
  %result = add i64 %triple, 1
  ret %result
}
abstract = "three times the @number it is given, plus one"
```

## 1. Three vocabularies

| Written | Is | Has | Renameable |
|---|---|---|---|
| `@word` | a word with an entry: a data word or a function | a type and an abstract | yes |
| `%local` | a value bound in one body: a result (later, block parameters; the form of labels is decided with branches) | nothing but its line | yes |
| bare `name` | a language word | its meaning in the spec | no |

The lexer alone tells the three apart, so renaming stays a purely lexical rule. A reader sees at once which words
carry meaning and must be looked up (`@`), and which are mechanical (`%`). A `@word` and a `%local` never clash,
because they are different tokens.

This replaces [core.md](core.md) section 1's single class of `$` words. Core chose `$` over `@` because LLVM's
`@`/`%` split "fights mime's single class of words". mime now has exactly those two classes, so the split fits.

## 2. Why `@` for words

- **No shell quoting.** `$` starts a variable in every Unix shell, so `mime run prog.mime '$affine' 5` needed single
  quotes and special hints for a word the shell ate. `mime run prog.mime @affine 5` works as typed in bash, zsh and
  fish. (PowerShell still needs quotes, because `@name` splats a variable there.)
- **A reference reads like a mention.** `"the @number it is given"` has the shape of an @-mention, the most familiar
  way to point at a named thing inside prose.
- **LLVM's split.** `@` for globals and `%` for locals, as in the IR that bodies already resemble.
- **The risk:** in LLVM, `@x` is a global symbol, so `add i64 @number, @number` may read as a global variable that
  needs a `load`. In mime it is the input's value. The checker reports any wrong use. *To measure.*

## 3. Abstracts

- A reference is `@` followed by a name. `\@` is an at sign. The step 2 rules carry over unchanged, with `@` for
  `$`: a reference names an earlier entry, never its own word, and a name with a stray character glued to it
  (`@numberX`) is a `bad-reference`.
- `%` in an abstract is plain text, so a local can never be referenced. That rule is now lexical, not a check.
- **Every `@` in an abstract starts a reference or is escaped.** An `@` that no name follows, as in `"@ 5 per
  unit"`, is a `bad-reference` with the hint "write `\@` for an at sign". This keeps one form, as step 2 did for
  `$`. An `@` glued to a letter or digit before it, as in an address (`"support@example"`), is still a reference,
  and its diagnostic gives the same hint.
- `$` is plain text in an abstract, with no rule of its own: `"costs $5"` needs no escape. `\$` is no longer an
  escape, so it is an unknown-escape `syntax` error with the hint "a `$` needs no escape now".

## 4. Locals

- A local is `%` followed by lowercase letters and digits, `%[a-z0-9]+`: `%double`, `%7`, `%07` and `%x2` are all
  locals, and `%7` and `%07` are two different ones. A local may start with a digit, unlike a word.
- The step 4 rules carry over, per block: a local is bound at most once in each block, read only after its line in
  that block, and read at least once. The same local may be bound in different blocks, as a pass-through parameter
  is (section 5), and two bodies may use the same local. In step 6 a body is a single block. A local cannot clash
  with a word, so step 4's rule that a result must not be a module word is gone.
- Inputs stay words. In `define @affine {@number}`, the body reads the input as `@number`, because an input is a
  declared word with an abstract.
- `%number` where `@number` is an input is an unbound local, with the hint "an input is its word: write
  `@number`". The input is still reported as unread. Only the hint relies on the two sharing a spelling, so what is
  reported cannot change under a renaming, which may rename the local and the word apart.

## 5. Numbered locals

A local's name is a hint for its writer, and it can mislead a reader: a `%sum` may hold a product. So a stored
program numbers its locals instead, and `mime canon` does the numbering.

```
define @affine {@number} -> @number {
  %v0 = add i64 @number, @number
  %v1 = add i64 %v0, @number
  %v2 = add i64 %v1, 1
  ret %v2
}
abstract = "three times the @number it is given, plus one"
```

- **A writer uses any local, and canon numbers them.** While working, a model may write `%double`, `%7` or `%total`,
  and mix them, for example when it adds a line to a stored body. `mime canon --locals` then renumbers every local
  as `%v0`, `%v1`, … (and, from step 7, every label as `^b0`, `^b1`, …), so a writer never has to count. The
  letters keep canon's names apart from one another and from words (`@w0`), so a backend can use them as they are.
- **One counter per body.** The first local in a body is `%v0`, and the count continues through every block, in order
  of first appearance, so each number means one value everywhere in its function.
- **A pass-through keeps its number.** Once blocks arrive (with branches), a block parameter that receives the same value
  on every jump into its block, or that value and itself on a loop's back edge, is the value a dominance rule would
  have let the block read directly. Canon gives such a parameter the number of that value, so the name never
  changes inside the function, and a reader has less to re-map at block boundaries. A parameter that receives
  different values on different jumps, as a loop counter does, gets a number of its own.
- **Why numbers:** a positional name carries only its position, which is true by construction, so it cannot lie and
  cannot drift. A fixed list of codes would be a snapshot of today's words: any code could later become a product
  name, slang, or an acronym that models learn. Letters carry conventions already (`i` for an index, `n` for a
  count, `x` for an unknown). Numbers are the purest positional names, and they are what LLVM uses for unnamed
  values.
- **The known risk, accepted on purpose:** a slip to a neighbouring number (`%1` for `%2`) is a valid but wrong
  reference, and no checker reports it. A typo in a name is usually reported, since it rarely spells another local. This is an exception to "mistakes must
  surface", taken for names that cannot drift, and it is measured (section 10). If models confuse numbered locals
  much more often than named ones, this rule is revisited.
- Numbering depends only on position, never on spelling, so it is renaming-invariant. A duplicate is still caught:
  binding `%2` twice in one block is a `duplicate-word`.

## 6. The commands

- **`mime fmt FILE`** is unchanged: the one layout, every word and name kept.
- **`mime canon FILE`** prints the canonical form: words become `@w0`, `@w1`, … in order of first occurrence, and
  each body's locals are numbered (section 5). Abstracts keep their English, with their references renamed.
- **`mime canon --locals FILE`** (replaced by `--keep-words` in [step-11.md](step-11.md), which also places data
  words and declarations) rewrites the file with each local numbered, and nothing else changed:
  words, English and layout stay as written. It then prints the rewritten program, so an agent has the new text
  in front of it rather than a memory of the old names. It is idempotent.
- **`mime rename FILE @old @new`** renames a word. `mime rename FILE %old %new` renames a local, in every body that
  binds it. Either way it refuses to merge two names, and a word cannot become a local or the reverse.
- A word on the command line needs no quotes: `mime run prog.mime @affine 5`, `mime show prog.mime @number`.

## 7. Hints for the old forms

| Written | Hint |
|---|---|
| `$number` outside a string | words are written `@number`; locals are written `%name` |
| `@r = add …` | a result is a local: write `%r` |
| `%number` where `@number` is an input | an input is its word: `@number` |
| `\$` in a string | a `$` needs no escape now |
| `mime run prog.mime '$f' 5` | words are written `@f` |

## 8. Lowering

Since step 7, lowering copies the canonical form's names: inputs `%w0`, locals `%v0`, blocks `b0`. A function is
exported under its `symbol`, or is internal as `@mime.affine`: a `.` cannot appear in a C symbol, so an internal
name never clashes with an exported one or with the runner's, and the word's `@` is left out because an ELF linker
reads an `@` inside a symbol as a version. Step 7 section 7 has the details.

## 9. Workflow

An agent writes locals with names that help it think, finishes the function, then runs `mime canon --locals` once,
at the end of the task, so the stored program carries no local names into the next session. When a person wants to
read a body, a model can relabel the numbers on request. That is a view, never stored.

## 10. Model ease

- **Familiar:** LLVM's `@global` and `%local`, and @-mentions in prose.
- **New:** inputs are `@` words, not `%` parameters as in LLVM, and stored locals are numbers counted per body.
- **How mistakes surface:** every old `$` form, and the LLVM habit of `%` parameters, has a hint (section 7). A
  local bound twice is a `duplicate-word`. *To measure:* how often models make a wrong but valid reference with
  numbered locals compared with named ones (no checker catches it), and whether `@number` gets read as an LLVM
  global.
