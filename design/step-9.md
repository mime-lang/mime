# Step 9: calls and recursion

> Status: settled. The ninth step of the [roadmap](roadmap.md). It adds `call`, recursion, and `declare` for a
> function that is called before its definition.

```
@first  = {type = i64, abstract = "one of two whole numbers"}
@second = {type = i64, abstract = "the other whole number"}

define @gcd {@first, @second} -> i64 {
  %done = icmp eq i64 @second, 0
  br %done, ^end{}, ^step{}
^end{}:
  ret @first
^step{}:
  %r = srem i64 @first, @second
  %g = call @gcd {@first = @second, @second = %r}
  ret %g
}
abstract = "the greatest common divisor of @first and @second"
symbol = "gcd"
```

(`srem` arrives with division; the example shows where this step leads.)

## 1. Lexical rules

- New language words: `call` and `declare`.
- Nothing else is new. A call's arguments are a group in braces, `{@first = %a}`, the bracket mime uses for
  everything a function or block receives.

## 2. Grammar

```
line        = local "=" "call" word "{" [argument ("," argument)*] "}"
            | …                                        (the lines of step 7)
argument    = word "=" atom
declaration = "declare" word "{" [word ("," word)*] "}" "->" output
```

- **A call is a line.** Its result is a `%` local, like every line's, and its type is the callee's output. No type is
  written: `call @gcd {…}`, not `call i64 @gcd(…)`, which gets the hint "write `call @gcd {@first = …}`; the type
  comes from `@gcd`".
- **Arguments are passed by word.** Each argument names the input it fills, `@first = %a`. The left side is the
  callee's input word, not a value; the right side is any atom of the caller: an input, a local, an integer, `true`
  or `false`. `{@n = @n}` passes the caller's own `@n` to the callee's `@n`.
- **The arguments are in the callee's input order**, every input exactly once, so a call has one canonical form.
- A function with no inputs is called with `{}`: `%s = call @seven {}`.
- No nesting, as before: `call @f {@n = add i64 %a, 1}` gets the nested-operation hint.

## 3. Checking a call

The arguments are a group of fields keyed by words, so the checker reports their mistakes with the kinds an
entry's fields already have ([diagnostics.md](diagnostics.md)), with `key` `body`:

| Mistake | Kind | Hint |
|---|---|---|
| an input of the callee left out | `missing-key` | "`@gcd` takes `@second`: add `@second = …`" |
| a word that is not one of its inputs | `unknown-key` | "`@gcd` takes `@first, @second`" |
| an input given twice | `duplicate-key` | |
| inputs out of order | `key-order` | "write the arguments in the order of `@gcd`'s type: `@first`, `@second`" |
| an argument of the wrong type | `wrong-type` | as for an operand |
| `call @number {}`, a data word | `bad-value` | "`@number` is a data word; only a function can be called" |
| a word not declared or defined above | `undeclared-word`, `forward-reference` | as today, and for a later function "declare it above: `declare @odd {@n} -> @flag`" |

- A call has no effect besides its result, so its result must be read, like every local (`unused-local`).
- A call is checked against the callee's type alone, never its body, so a call to a declared function checks
  before that function is defined.

## 4. Which function a body may call

Every entry still refers only to earlier entries ([layout.md](layout.md) section 1), with one exception and one new
entry:

- **A body may call its own word.** That is recursion, and needs nothing above it. The abstract still may not
  refer to its own word.
- **`declare` gives a later function's type early**, for mutual recursion:

```
@n    = {type = i64, abstract = "a whole number, zero or more"}
@flag = {type = i1, abstract = "a truth value"}

declare @odd {@n} -> @flag

define @even {@n} -> @flag {
  %zero = icmp eq i64 @n, 0
  br %zero, ^yes{}, ^no{}
^yes{}:
  ret true
^no{}:
  %m = sub i64 @n, 1
  %o = call @odd {@n = %m}
  ret %o
}
abstract = "whether @n is even"

define @odd {@n} -> @flag {
  %zero = icmp eq i64 @n, 0
  br %zero, ^no{}, ^yes{}
^no{}:
  ret false
^yes{}:
  %m = sub i64 @n, 1
  %e = call @even {@n = %m}
  ret %e
}
abstract = "whether @n is odd, the opposite of @even"
```

- A declaration is only the head of a later `define`: `declare @odd {@n} -> @flag`, with no body, abstract or
  symbol. Those stay on the `define`, the one place the function is written.
- After a declaration, the word counts as declared for everything below it: bodies call it, and abstracts may
  refer to it.
- **Each declaration has exactly one `define` below it, with the same type.** A type that differs is `wrong-type`
  on the `define`'s head, with the hint "`@odd` is declared above as `{@n} -> @flag`". A declaration with no
  `define` is `missing-definition`.
- **A declaration must be needed.** One that nothing between it and its `define` uses is `redundant-declaration`,
  with the hint "drop it: `@odd` is defined before anything calls it". So a module has one form: a function is
  declared only where mutual recursion needs it.
- A data word is never declared this way; `declare` is for functions only.
- **Not LLVM:** in LLVM, `declare` is a function defined elsewhere, outside the module. In mime it is a function
  defined later in the same module. The modules step decides how an imported function is written.

## 5. Meaning

- A call evaluates its arguments, runs the callee on them from its entry block, and binds the callee's result to
  its local. Calls have no other effect, since mime has no state yet.
- **The result is guaranteed if the machine can hold the calls.** The spec fixes no depth. A recursion that ends
  means its result on every backend; if a backend runs out of stack first, it stops and says so, and never gives
  another result. Running out of stack is the machine's limit, not the program's meaning, as running out of time
  is ([step-8.md](step-8.md) section 3). WebAssembly and the JVM define stack exhaustion the same way.
- So it is not a trap. A trap is an operation leaving the domain the spec gives it, the same on every backend;
  how deep a stack goes depends on the machine. `mime run` reports it like the timeout, with exit code `2`:

```
mime: `sum` ran out of stack: the machine could not hold that many nested calls, or a recursion never reaches its base case
```

- An endless loop ends in the timeout, and an endless recursion ends here. The message names both causes, since
  a backend cannot tell them apart.
- No tail calls are promised. A loop is a block that jumps back to itself, which never nests.

## 6. Backends

- **Interpreter.** It keeps its own stack of frames, a block and a table each, rather than Python's recursion, so
  Python's limit plays no part. It stops at a limit of its own (100000 frames), so an endless recursion ends at
  once instead of filling memory until the timeout. The limit is the interpreter's, not the spec's.
- **LLVM.** A call lowers to `call i64 @mime.w3(i64 %v1, i64 %v2)`, its arguments in the callee's input order,
  with no check: a call costs what a C call costs. A native stack that overflows kills the program with a signal
  (`SIGSEGV`, or `SIGBUS` on macOS), and `mime run` reports that signal as running out of stack. mime has no memory
  operations yet, so no other mistake of a program can raise it; a crash from a lowering bug would look the same,
  which the conformance tests guard against.
- **JavaScript and the JVM**, later, turn their own stack errors (`RangeError`, `StackOverflowError`) into the
  same report.
- **Run cases** keep their recursion shallow, a few hundred calls, which every machine holds. A case may hold
  `"limit": "stack"` in place of `"output"`, but only for a recursion that never ends, where every backend runs out:

```json
{"symbol": "forever", "inputs": ["1"], "limit": "stack"}
```

## 7. Internal functions

Calls make internal functions useful: a helper without a `symbol` is reached through an exported function that
calls it ([step-8.md](step-8.md) section 3).

- In a clean golden, every exported function has a run case, and every internal function is called by some
  function, so each is run through the cases.
- Outside the goldens, an internal function that nothing calls is not a mistake yet: until the modules step, every
  function without a symbol is internal. The modules step decides whether an unused internal function is reported.

## 8. Tools

- `mime uses @gcd` lists every call of `@gcd`, with `key` `body`. A call's argument keys are uses of the callee's
  inputs: renaming `@first` renames `@first = …` in every call of `@gcd`.
- `mime canon` numbers a declared word at its declaration, its first appearance.
- `mime show @odd` prints the `define`, and the declaration only when there is no `define` yet.

## 9. Easy for a model?

- **Familiar:** `call` is LLVM's, and the arguments are keyword arguments, as in Python, Swift or a JSON tool call:
  `{@first = %a}` reads like `gcd(first=a)`. Forward declarations are C prototypes, and the error for a missing
  one names the line to paste.
- **New:** arguments must be in the callee's input order, though they are named. A model that writes them in
  another order gets `key-order` with the order to write. Running out of stack is reported as the timeout is,
  naming the usual cause.
- **Mistakes surface** as the diagnostics of an entry's fields, which a model already knows, each naming the input
  at fault. A swapped pair of `i64` arguments, which a positional call would check clean, cannot be written.

## 10. What changes elsewhere

- [layout.md](layout.md) sections 1 and 4: the self-call exception, `declare`, and "a function word is defined once,
  and declared at most once, above its `define`". Section 1 also loses "`mime run` may run any function word",
  which step 8 replaced with symbols.
- [spec/SKILL.md](../spec/SKILL.md): `call`, `declare`, and running out of stack.
- The goldens gain `calls` (a helper called by an exported function, an argument passed by word), `recursion`
  (`@sum` by recursion, and a recursion that never ends), and `even_odd`; the mistakes goldens gain the call and declaration
  mistakes of sections 3 and 4.
