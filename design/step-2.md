# Step 2: checked references in descriptions

> Status: settled. The second step of the [roadmap](roadmap.md). It turns a `$` inside a description from a
> reserved character (step 1) into a checked reference, as [core.md](core.md) section 3 describes.

```
$number = {description = "a whole number", sort = i64}
$same   = {description = "the $number it is given", takes = $number, returns = $number, body = input}
```

In `$same`'s description, `$number` is a reference: the checker makes sure it names an entry declared earlier.
The English around it is never read.

## 1. What a reference is

- Inside a `description` string, `$` followed by a name is a reference: `$` then `[a-z][a-z0-9_]*`, the same rule as a
  word outside a string. The name ends at a space or at punctuation, so `$pair's`, `$number.` and `($number)` each
  refer to one word.
- A name followed directly by an uppercase or non-ASCII letter, or by `-`, is an error (`bad-reference`), as it is
  in code. So `"$numberX"`, `"$number-ish"` and `"$númber"` are mistakes, not `$number` followed by text. Without
  this, one shape would have two readings: a syntax error in code and a shorter word in a description.
- `\$` is a dollar sign, not a reference.
- A `$` that is not followed by a lowercase letter is an error (`bad-reference`), with the hint "write `\$` for a
  dollar sign". This catches `"costs $5"`, `"5$"` and `"$Pair"`. Reporting it, rather than reading it as text, keeps
  one form: every `$` in a description is either a reference or escaped.
- Only a `description` is scanned. No other key takes a string yet, and when one does, its strings are plain data.

## 2. Rules

- A reference names a word whose entry comes **before** the entry the description belongs to. This applies to every
  kind of entry, and to both sort and function words.
- A description cannot refer to its own word. A definition that uses the word it defines is circular, which a
  mathematical text does not allow either.
- References are optional. A description with none is valid, because the English can stand on its own. What a
  description must say is not something a checker can decide.
- When the same word has two entries (`duplicate-word`), references go to the first one.

## 3. Diagnostics

No new kinds are needed for a wrong reference. It is the same mistake as a wrong `takes` or `returns`, so it has the
same kind:

| Kind | When | Hint |
|---|---|---|
| `undeclared-word` | a reference names no entry | a close earlier word, or a later one with "move its entry above" |
| `forward-reference` | a reference names this entry or a later one | move the entry above, or describe the word by its parts |
| `bad-reference` | a `$` not followed by a lowercase letter | write `\$` for a dollar sign |
| `bad-reference` | a name followed by a letter or `-` | a name is lowercase letters, digits or `_` |

`bad-reference` replaces step 1's `dollar-in-string`. The diagnostic points at the `$` inside the string, counting
columns in the source text, so an escape such as `\"` before it counts as two characters.

## 4. Model ease

Familiar: string interpolation (`"Hello $name"`) and doc comments with checked links (Rust intra-doc links, JSDoc
`{@link}`). New: references must point backward, and a currency `$` must be escaped. The expected mistakes are a
forward reference, which is reported with the entry to move, a plural or misspelled word (`$numbers` for `$number`),
which gets a "did you mean" hint, and a bare `$5`, which gets the escape hint.

## 5. Out of scope

Renaming references along with their words is step 4 (`mime canon`). This step records each reference's position so
that step 4 can rewrite it.
