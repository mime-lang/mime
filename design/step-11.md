# Step 11: canonical order

> Status: settled. The eleventh step of the [roadmap](roadmap.md).
> It gives `mime canon` one place for every data word and `declare`: just above the first `define` that needs it.
> The `define`s keep the order they are written in. It adds `unused-word`, and `mime canon --keep-words` replaces
> `mime canon --locals` ([step-6.md](step-6.md) section 6). The language does not change: any order that declares
> before use still checks.

```
@flag = {type = i1, abstract = "a truth value"}
@n = {type = i64, abstract = "a whole number, zero or more"}

declare @odd {@n} -> @flag

define @even {@n} -> @flag { … call @odd … }
abstract = "whether @n is even"
symbol = "even"

define @odd {@n} -> @flag { … call @even … }
abstract = "whether @n is odd, the opposite of @even"
symbol = "odd"
```

canon prints `@n` before `@flag`, since `@even` reads them in that order, and leaves the rest where it is:

```
@n, @flag, declare @odd, define @even, define @odd
```

## 1. The guarantee

Two clean programs have equal canonical forms exactly when they differ only in

1. the spelling of words, locals and labels ([step-5.md](step-5.md), [step-6.md](step-6.md)), and
2. where their data words and `declare`s stand, in any order that declares before use
   ([layout.md](layout.md) section 1).

**Only a `define` has a place of its own.** The order of the functions is how the writer tells the program, so
canon keeps it. A data word or a `declare` is there for the functions that need it, so it goes where the first of
them needs it.

## 2. The algorithm

```
out = []          # the new order
printed = {}      # the entries in out

def pull(e):                      # print e, after everything e needs
    if e in printed or e is a define:
        return
    printed.add(e)
    for r in refs(e):
        pull(r)
    out.append(e)

for d in the defines, in source order:
    for r in refs(d):
        pull(r)
    out.append(d)
    printed.add(d)
```

`refs(e)` is every entry `e` refers to, each once, at its first reference, in reading order:

| Entry | Reading order |
|---|---|
| `define` | its inputs in order, its output, its body line by line and each line left to right, its abstract |
| `declare` | its inputs in order, its output |
| data word | its type, its abstract |

- A call to the function's own word, or to a `define` already printed, pulls nothing.
- A call to a function defined later pulls its `declare`, which first pulls the words in its head.
- A data word's abstract that names a declared function pulls that `declare` above the data word.

## 3. Why it is sound

- **It is a stable sort.** The `define`s are visited in source order and printed in it.
- **It never reads where a data word or a `declare` was written**, only what refers to it, so any placement gives
  the same output. It follows references, never names, so renaming gives the same output.
- **No ties are left.** Each pulled entry's place is fixed by the reading order of its first user.
- **The output declares before use.** An entry is printed after everything it refers to. A `declare` is needed
  only by something above the `define` of its function (`redundant-declaration`, [step-9.md](step-9.md) section 4),
  so its first user is a `define` above that `define`, which is where a declaration may stand.
- **It is idempotent.** Its own output has the same `define`s in the same order and the same references.
- **A small edit makes a small move.** Only the entries whose references an edit adds or removes can move, each
  to its new first user.
- **It cannot loop.** In a clean program a data word refers only to earlier entries and a `declare` only to data
  words, so no pulled entries form a cycle. `pull` marks an entry before it follows its references, so a program
  with mistakes cannot make it loop either.

## 4. `unused-word`

Every pulled entry needs a first user, or it has no place:

| Kind | Message | Hint |
|---|---|---|
| `unused-word` | "nothing refers to `@count`" | "use it in a type, a body or an abstract, or remove it" |

- It is the rule [layout.md](layout.md) section 5 already states for locals and inputs, "every word is used",
  applied to data words.
- A `declare` nothing needs is already `redundant-declaration`.
- A `define` nothing calls is not reported: it keeps its place, and the modules step decides whether an unused
  internal function is a mistake ([step-9.md](step-9.md) section 7).
- `mime canon` still needs only a program that parses. **A program with mistakes keeps the order it is written
  in**; only its words, locals and labels are renamed. Moving entries could move a mistake away from what explains
  it, or change which mistakes the checker reports: a `declare` moved past a second one turns `duplicate-word`
  into `missing-definition`. So canon and the checker always agree, and the guarantee of section 1 is for clean
  programs only. (An earlier draft placed what the walk misses by a fallback rule; building it showed that rule
  changed the diagnostics of the mistakes goldens.)
- `unused-word` has no `key`: it is about the whole entry, as `duplicate-word` is.

## 5. The commands

Canon does three things: it places the data words and `declare`s (section 2), it numbers locals and labels
([step-6.md](step-6.md) section 5), and it renames words `@w0`, `@w1`, …. There are no flags to choose among
them, since every choice of flags would be another canonical form, and two outputs could only be compared when
made with the same flags.

- **`mime canon FILE`** prints the full canonical form, all three. It is for tools: comparing programs, lowering
  ([step-7.md](step-7.md) section 7), and the scrambled-words cell of the benchmark.
- **`mime canon --keep-words FILE`** rewrites the file with the first two and keeps every word as written, with
  the English unchanged, in the layout of `mime fmt`. It then prints the rewritten program. It replaces `--locals`,
  which numbered locals only. Words are kept because the file is the one a model goes on reading and editing, and
  `@w3` says nothing.
- Both are idempotent, and `--keep-words` then `canon` gives the same as `canon`.
- `mime fmt` still changes whitespace only.

This is what the benchmark needs: the plain cell is a program after `--keep-words`, the scrambled cell is its
`mime canon`, and the two differ in their words alone, with the same order and the same locals.

## 6. Easy for a model?

- **Familiar:** a formatter that sorts imports (`gofmt`, `isort`), here for the words a function uses; a C
  prototype written just above its first caller.
- **New:** canon moves data words and `declare`s. A model writes them anywhere above their users and runs
  `mime canon --keep-words prog.mime` when it is done, as it ran `--locals`. Every later read of the file, in this
  session or the next, has each function's words and declarations right above it. The functions stay where the
  model put them.
- **Mistakes surface** as `unused-word`, naming the word, and as the `declare` diagnostics of
  [step-9.md](step-9.md), which are unchanged.

## 7. What changes elsewhere

- [step-5.md](step-5.md) section 3 and [step-6.md](step-6.md) section 6: the placement, and `--keep-words` in place
  of `--locals`. "Two programs are the same up to renaming exactly when their canonical forms are equal" becomes
  "up to renaming and the placement of data words and declarations".
- [layout.md](layout.md) section 5: `unused-word` for data words.
- [spec/SKILL.md](../spec/SKILL.md): `--keep-words`, and `unused-word`.
- **Goldens.** A `.canon.mime` golden is approved again where its words move. Its `.ll` golden changes only where
  a move renumbers a word: the functions keep their order, and data words and declarations print nothing in LLVM
  IR, but inputs and internal functions are named by their canonical numbers (`%w0`, `@mime.w3`,
  [step-7.md](step-7.md) section 7). A placement test: for
  every clean golden, move each data word and `declare` to a random place that still declares before use, rename
  every word, and the canonical form is unchanged.
