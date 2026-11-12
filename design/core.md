# Core design: words, entries, modules, primitives, sorts, types

> Status: draft. The syntax in the examples is illustrative and is fixed by the grammar doc. It follows
> oymo's struct style (`{key = value}`, `let … in …`), with mime's `$` rule applied. This doc sets the direction.
> Each part is settled for real by its step in the [roadmap](roadmap.md).

## How decisions are judged

mime's main user is a model, so every decision answers two questions:

1. Does it keep meaning in the program's form (see [README](../README.md))?
2. Is it easy for a model to read and write?

Each section below ends with a **Model ease** note. It says what familiar pattern the decision leans on, what is new,
and how a model's mistakes surface. A pattern that is common in training data (JSON, tool definitions, namespaces,
SSA) is cheap. Something new is acceptable only when its mistakes are caught by the checker with a clear message.
Claims marked *to measure* go into the benchmark.

## 1. Two vocabularies

Every token belongs to one of two vocabularies:

| Vocabulary | Written | Meaning comes from | Renameable |
|---|---|---|---|
| **Domain** | `$` prefix: `$gcd`, `$pair` | the program's declarations | yes |
| **Language** | bare: `add`, `i64`, `description`, `let` | this spec | no |

- Strings are double-quoted: `"two whole numbers"`.
- The lexer alone decides which vocabulary a token belongs to. "Rename every `$` token" is a purely lexical rule, so
  the renaming invariant cannot be broken by accident.
- Adding a language word later never collides with a program's words.
- A bare token that is not a language word is an error, not a new word.

Oymo marks the other side: its language words are quoted (`'add'`, `'i32'`) and its labels are bare. Examples
borrowed from oymo are rewritten.

Why `$` and not single quotes: models have seen `'gcd'` as a string or char literal (Python, JS, SQL, C) far more
than as a name, so quotes would carry borrowed meaning. Quotes also come in pairs, so a closing quote can be
forgotten. `@` was the runner-up, but LLVM uses `@` for globals and `%` for locals, which fights mime's single class
of words.

**Model ease.** Familiar: `$x` reads as a name in shell, PHP, Perl, and template languages, and never as a string.
One character, nothing to close. New: every user word carries it. The expected mistake is a missing `$`, which shows
up as "unknown language word `gcd`; did you mean `$gcd`?", so the repair is easy. Small risk: `$` suggests a mutable
variable, and mime has no mutation. *To measure:* how often `$` is forgotten.

## 2. Words and entries

A word is declared by an **entry**: a struct of language keys, bound to the word at the top level of a module.

```
$first  = {description = "the first number",  sort = i64}
$second = {description = "the second number", sort = i64}
$pair   = {description = "two whole numbers, $first and $second", sort = {$first, $second}}
```

- Every entry has a `description`.
- **Words are unique in a module.** Each word has exactly one entry, at the top level. Entries do not nest. A local
  bound by a `let` (§6) is unique in its body and never reuses a module word.
- An entry's keys are all language words and a module's keys are all domain words, so the two never collide. (Oymo
  needs a rule that no symbol may be named `type`. mime does not.)
- A word means only what its entry says. Its spelling carries nothing.

**Model ease.** Familiar: each entry has the shape of a JSON object or a tool definition, and a flat list of
top-level declarations is how LLVM IR declares its types (`%pair = type { i64, i64 }`). Fixed keys are what models
produce most reliably. New: nothing structural. The expected mistake is listing a word before its entry, which is
reported as a forward reference (§3).

## 3. Descriptions

A description is a string written in a `description` slot. Inside it, a `$` token is a **checked reference** to a
word. The bare text around the references is connecting English.

```
description = "the greatest common divisor of the $first and $second of a $pair"
```

Descriptions sit on a spectrum:

```
free text            ──▶  text with checked references  ──▶  formal spec
(nothing is checked)      (every reference is checked)       (every claim is checked)
                          (mime is here)
```

Rules:

- A reference must name a word that is declared before this entry. A dangling or forward reference is an error,
  and so is a reference to the entry's own word, which would make the definition circular.
- References are renamed with the program. Renaming `$pair` updates every description that mentions it.
- A literal dollar sign in a description is written `\$`.
- Only a `description` slot is scanned. A string anywhere else is plain data. It is never scanned or renamed, so a
  string can never become a word reference.
- The checker reads only the references. The connecting English never changes what a program means, and canonical
  form ignores it.

A description is still borrowed meaning: its English can lie. Checked references limit how far it can drift from the
program, but not to zero. The evaluation therefore runs two extra ablations: one with descriptions removed and one
with descriptions that lie.

**Model ease.** Familiar: string interpolation (`"Hello $name"`), where a `$name` inside a string points at something
outside it, and doc comments with checked links (Rust intra-doc links ``[`Foo`]``, JSDoc `{@link Foo}`). New:
references must point backward. The expected mistake is a forward reference, which the checker reports with the
entry that declares the word. *To measure:* whether agents read descriptions or definitions when the two disagree.

## 4. Fields

A struct is a sort that lists words: `sort = {$first, $second}`. Each listed word is a **field** of the struct.

- **Fields are ordered.** `{$first, $second}` and `{$second, $first}` are different sorts. Lowering needs an order,
  and one meaning has one form, so the checker never reorders.
- A struct lists each word at most once, and each field must be declared before the struct, like any reference.
- A field is reached by its word: `input.$first`. The dot is language syntax, with a value on its left and a field
  word on its right.
- A field needs no path, because words are unique in a module. The link from `$first` to `$pair` lives in `$pair`'s
  sort, which is checked, and not in the spelling of either word.
- Two structs may list the same word. Records that really mean the same thing share a field word. Two fields that
  mean different things need two words.

**Model ease.** Familiar: LLVM struct types (`{ i64, i64 }`) are ordered lists of members, and `value.field` access
is everywhere in training data. New: a field is a module-level word, not a name scoped to its struct. The expected
mistake is the scoped habit, `$pair.$first` or `$pair.first`, which the checker catches with a hint: "fields are
words; write `$first`". Declaring the struct before its fields is reported as a forward reference.

## 5. Functions

A function takes exactly one word and returns exactly one word. Both are checked references, and each referenced word
has its own entry and description.

```
$divisor = {description = "a whole number that divides another", sort = i64}

$gcd = {
  description = "the greatest common divisor of the two numbers in a $pair",
  takes   = $pair,
  returns = $divisor,
  body    = …,
}
```

- The single input is reached in the body through the language word `input`, as in `input.$first`. The parameter needs
  no name, so there is one fewer binder to name, rename, or get wrong.
- `takes` and `returns` always name a word. They are never written inline, so every parameter field and every result
  has exactly one declaration and one description. This also means a primitive is never returned directly. It is
  wrapped in a word.
- A function's signature is the pair (`takes`, `returns`). Two functions that take the same word visibly share an
  interface: their sameness is carried by form, not by spelling.

**Model ease.** Familiar: this is exactly a tool definition, with one input object, named fields, and a description on
every field. Current models are trained heavily on that shape. Also familiar: React props and single-argument record
functions. New: the result must be a named word. The cost is extra entries for one-off functions. *To measure:*
whether that cost shows up in total tokens.

## 6. Bodies

A body is a flat chain of `let`s in A-normal form: every intermediate value gets a name, and every operation takes
only names, literals, or types.

```
$twice = {
  description = "a $number added to itself",
  takes   = $number,
  returns = $number,
  body    = let $b = add {i64, input, input} in $b,
}
```

- Local names are domain words, so they carry `$` and are renameable. A local is unique in its body, is not a
  module word, has no description, and must be used ([step-3.md](step-3.md)).
- Following oymo, operations take their sort as an operand (`add {i64, …}`). Locals carry no annotation.
- Control flow follows oymo's regions (a struct of blocks that see each other). The grammar doc fixes how.

**Model ease.** Familiar: LLVM IR and SSA put the type (here, the sort) on the operation, and models have seen a lot
of LLVM IR. `let … in …` chains are familiar from ML and Haskell. New: `$` on locals. *To measure:* whether locals
should also get descriptions (see open questions).

## 7. Modules

One file is one module, and a module is a struct of entries. Its order matters.

- **Descriptions are ordered.** A description refers only to earlier entries. Read top to bottom, a module is a chain
  of meanings, like a mathematical text.
- **Bodies are a fixed point.** A body may use any entry in the module, including later ones and itself, as in
  oymo's unit (`fix (λg. {…})`). Recursion and mutual recursion need no extra construct.
- **Values must not be circular.** Only functions may refer to each other in a cycle. `$a = $b`, `$b = $a` is an
  error.
- **Imports name each word the module writes, and only those.** No glob imports and no re-exports. Every word in a
  module traces back to an entry. Importing `$point` does not pull in its fields `$x` and `$y`: a module imports
  `$x` only if it writes `$x`, for example to read that field. An import list is never a transitive closure, so it
  grows with what the module uses, not with the size of its libraries.
- **An import may rename.** Spelling carries nothing, so the importer picks each local name, and the renaming
  invariant (§10) guarantees that the meaning does not change. This is how two libraries that both export `$x` are
  used together:

  ```
  import $geo  {$x}            ; local $x is geo's $x
  import $grid {$col = $x}     ; local $col is grid's $x
  ```

  Two imports bound to one local name are a duplicate-word error that names both modules. There are no qualified
  paths such as `$geo.$x`, so each word is written one way inside a module.
- **Exports are explicit.** A struct exported without its field words is opaque: importers can pass it along but
  cannot read its fields.
- **The header is the module minus its bodies:** the (word, description, `takes`, `returns`, `sort`) rows of the
  exported entries. An agent writing a module loads the header row of every word it imports, so it reads each word's
  description while writing. The rows that those rows refer to are loaded on demand and never copied into the module.
- **The module graph is acyclic.** This is declare-before-use at the module level.

**Model ease.** Familiar: header files (`.h`, `.mli`), explicit imports (`from m import a, b`), renaming imports
(`from m import x as y`, `import {x as y}`), abstract types in an `.mli`, files as modules. New: two different scope
rules, ordered descriptions and unordered bodies, and fields imported as words of their own. The expected mistakes
are a description that refers forward and a field read without importing it. Both are cheap to report, the second
as "unknown word `$x`; `$geo` exports it". Loading only header rows keeps an agent's context small.

## 8. Primitives (v0)

Primitives are language words: bare, fixed by this spec, never renamed.

- **Sorts:** `i1`, `i8`, `i16`, `i32`, `i64`, and structs of words (§4). No floats or pointers yet.
- **Operations:** `add`, `sub`, `mul`, `sdiv`, `udiv`, `srem`, `urem`, `icmp` with predicates, `call`, branches,
  and return, following LLVM.
- **Overflow wraps.** Each operation has exactly one meaning.

**Model ease.** Familiar: these are LLVM's own names, so models already know their exact meaning.

## 9. Sorts and types

A **sort** says how the abstract machine sees a value: `i64` is 64 bits, with no alignment, padding or signedness.
An entry's `sort` slot and an operation's first operand name one. Sorts are values: `i64` is passed to operations
like any other operand. A sort is not a type. `$first` and `$second` in §2 have the same sort but are different
words, so they will be different types. Alignment and padding belong to a concrete target and are not part of the
language.

mime is untyped for now: `takes`/`returns` name words, and there is no type checker yet.

The planned direction, to be written up before it is built:

- **Structural, made nominal by words.** A type is a structure. Because the structure contains declared words, two
  types with different words are different types. No separate "newtype" construct is needed.
- **A struct's own word counts.** Two structs are the same type only when they are the same word, even when they
  list the same fields. A position and a displacement can share their components and stay apart:

  ```
  $x      = {description = "the x component", sort = i64}
  $y      = {description = "the y component", sort = i64}
  $point  = {description = "a position, at $x and $y",     sort = {$x, $y}}
  $vector = {description = "a displacement, by $x and $y", sort = {$x, $y}}
  ```
- **Unions as in TAPL.** Set-theoretic unions (`A | B`). Checks such as covering every case live in a separate
  checking layer, as in TAPL and oymo, not in a built-in exhaustiveness rule.

**Model ease.** Familiar: `sort` means what it means in SMT-LIB and Z3, where `(_ BitVec 64)` is a sort, and the
sort names are LLVM's. Structural types (TypeScript) and unions (TypeScript, Python) are familiar too. New: the slot
is called `sort`, not `type`, so a model may write `type = i64` out of habit. That is an unknown key in an entry, so
the checker reports it at once. Checking that runs as a separate layer is new as well, and is deferred until this
layer is designed.

## 10. Renaming and canonical form

- **Renaming invariant.** Consistently renaming domain words, including the references inside descriptions, never
  changes what a program means. Language words are never renamed.
- **Canonical form.** Replace every domain word by a fixed name in declaration order (`$w0`, `$w1`, …) and drop
  the connecting English of descriptions. Two programs are the same up to renaming when their canonical forms are
  equal.
- `mime canon` prints the canonical form. It tests the renaming invariant, checks "one meaning, one form", and
  produces the scrambled-words ablation.

**Model ease.** Models never write canonical form. It is a tool for the checker and the benchmark.

## Open questions

1. **Locals and descriptions.** Settled in [step-3.md](step-3.md): never. A local names an intermediate value, like
   a bound variable in a proof.
2. **Input reference.** Is `input` the right language word for the single parameter, and how does it work inside
   nested regions?
3. **Header format.** Is a header written by hand, generated, or both, as in oymo?
4. **Checking layer.** How TAPL-style layers apply to mime.
5. **Opaque structs in headers.** Lowering an importer needs the sort of an opaque struct, but its field words are
   not exported. Does the header show the struct's sort with its fields hidden, or only the compiled module carry it?
