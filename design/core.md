# Core design: words, entries, modules, primitives, types

> Status: draft. The syntax in the examples is illustrative and is fixed by the grammar doc. It follows
> oymo's struct style (`{key = value}`, `let … in …`), with mime's `$` rule applied.

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

A word is declared by an **entry**: a struct whose bare keys are language words and whose `$` keys are child words.

```
$pair = {
  description = "two whole numbers",
  $a = {description = "the first number of a $pair",  type = i64},
  $b = {description = "the second number of a $pair", type = i64},
}
```

- Every entry has a `description`.
- Language keys and child words share one struct without colliding, because the `$` rule separates them. (Oymo
  needs a rule that no symbol may be named `type`. mime does not.)
- A word means only what its entry says. Its spelling carries nothing.

**Model ease.** Familiar: this has the shape of a JSON object or a tool definition. Fixed keys and nesting are what
models produce most reliably. New: nothing structural.

## 3. Descriptions

A description is a string written in a `description` slot. Inside it, a `$` token is a **checked reference** to a
word. The bare text around the references is connecting English.

```
description = "the greatest common divisor of $pair.$a and $pair.$b"
```

Descriptions sit on a spectrum:

```
free text            ──▶  text with checked references  ──▶  formal spec
(nothing is checked)      (every reference is checked)       (every claim is checked)
                          (mime is here)
```

Rules:

- A reference must name a word that is declared before this entry, or a child of this entry. A dangling or forward
  reference is an error.
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

## 4. Nested words

A child word is declared inside its parent entry and is written as a path: `$pair.$a`.

- `$pair.$a` and `$vector.$a` are different words with their own descriptions.
- Renaming works per segment: renaming `$pair` moves the whole path, and renaming `$pair.$a` leaves `$vector.$a`
  alone. Each segment carries `$`, and the dot is language syntax.
- Two records that really mean the same thing share a top-level word instead.

**Model ease.** Familiar: namespaces, struct fields, and `Type.field` paths are everywhere in training data. New: `$`
on each segment. The expected mistake, `$pair.a`, can be caught with a specific hint.

## 5. Functions

A function takes exactly one word and returns exactly one word. Both are checked references, and each referenced word
has its own entry and description.

```
$divisor = {description = "a whole number that divides another", type = i64}

$gcd = {
  description = "the greatest common divisor of the two numbers in a $pair",
  takes   = $pair,
  returns = $divisor,
  body    = …,
}
```

- The single input is reached in the body through the language word `input`, as in `input.$a`. The parameter needs
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

- Local names are domain words, so they carry `$` and are renameable.
- Following oymo, operations take their type as an operand (`add {i64, …}`). Locals carry no annotation.
- Control flow follows oymo's regions (a struct of blocks that see each other). The grammar doc fixes how.

**Model ease.** Familiar: LLVM IR and SSA put the type on the operation, and models have seen a lot of LLVM IR. `let …
in …` chains are familiar from ML and Haskell. New: `$` on locals. *To measure:* whether locals should also get
descriptions (see open questions).

## 7. Modules

One file is one module, and a module is a struct of entries. Its order matters.

- **Descriptions are ordered.** A description refers only to earlier entries. Read top to bottom, a module is a chain
  of meanings, like a mathematical text.
- **Bodies are a fixed point.** A body may use any entry in the module, including later ones and itself, as in
  oymo's unit (`fix (λg. {…})`). Recursion and mutual recursion need no extra construct.
- **Values must not be circular.** Only functions may refer to each other in a cycle. `$a = $b`, `$b = $a` is an
  error.
- **Imports name each word.** No glob imports and no re-exports. Every word in a module traces back to an entry.
- **Exports are explicit.**
- **The header is the module minus its bodies:** the (word, description, `takes`, `returns`, `type`) rows of the
  exported entries. An agent writing a module loads the header of every word it imports, so it reads each word's
  description while writing.
- **The module graph is acyclic.** This is declare-before-use at the module level.

**Model ease.** Familiar: header files (`.h`, `.mli`), explicit imports (`from m import a, b`), files as modules.
New: two different scope rules, ordered descriptions and unordered bodies. The expected mistake is a description
that refers forward, which is cheap to report. Loading only headers keeps an agent's context small.

## 8. Primitives (v0)

Primitives are language words: bare, fixed by this spec, never renamed.

- **Types:** `i1`, `i8`, `i16`, `i32`, `i64`. No floats or pointers yet.
- **Operations:** `add`, `sub`, `mul`, `sdiv`, `udiv`, `srem`, `urem`, `icmp` with predicates, `call`, branches,
  and return, following LLVM.
- **Overflow wraps.** Each operation has exactly one meaning.

**Model ease.** Familiar: these are LLVM's own names, so models already know their exact meaning.

## 9. Types

mime is untyped for now. Types are values: `i64` is a value passed to operations, and `takes`/`returns` name words.
There is no type checker yet.

The planned direction, to be written up before it is built:

- **Structural, made nominal by words.** A type is a structure. Because the structure contains declared words, two
  types with different words are different types. No separate "newtype" construct is needed.
- **Unions as in TAPL.** Set-theoretic unions (`A | B`). Checks such as covering every case live in a separate
  checking layer, as in TAPL and oymo, not in a built-in exhaustiveness rule.

**Model ease.** Familiar: structural types (TypeScript) and unions (TypeScript, Python). New: checking that runs as a
separate layer. Deferred until this layer is designed.

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

1. **Locals and descriptions.** Do local `let` names need descriptions? Bound variables in a math proof usually get
   none. "One form" means it must be always or never.
2. **Input reference.** Is `input` the right language word for the single parameter, and how does it work inside
   nested regions?
3. **Header format.** Is a header written by hand, generated, or both, as in oymo?
4. **Checking layer.** How TAPL-style layers apply to mime.
