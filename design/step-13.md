# Step 13: division and remainder

> Status: settled. The thirteenth step of the [roadmap](roadmap.md). It adds `sdiv`, `udiv`, `srem` and `urem` on `i64`,
> and `and`, `or` and `xor` on `i1`. Division is mime's first partial operation, so this step also builds the first trap
> on every backend ([backends.md](backends.md) section 1, [step-8.md](step-8.md) section 4).

```
@a = {type = i64, abstract = "one of two whole numbers"}
@b = {type = i64, abstract = "the other whole number"}

define @gcd {@a, @b} -> i64 {
  %done = icmp eq i64 @b, 0
  br %done, ^end{}, ^step{}
^end{}:
  ret @a
^step{}:
  %r = srem i64 @a, @b
  %g = call @gcd {@a = @b, @b = %r}
  ret %g
}
abstract = "the greatest common divisor of @a and @b, up to sign; it recurses about log @b times"
symbol = "gcd"
```

## 1. The operations

| Line | Type | Result |
|---|---|---|
| `%q = sdiv i64 %a, %b` | `i64` operands | `%a / %b` as signed numbers, rounded **toward zero** |
| `%r = srem i64 %a, %b` | `i64` operands | the remainder of `sdiv`: `%a - (%a sdiv %b) * %b`, with the **sign of `%a`** |
| `%q = udiv i64 %a, %b` | `i64` operands | `%a / %b` with both read as unsigned, from 0 to 2^64-1 |
| `%r = urem i64 %a, %b` | `i64` operands | the remainder of `udiv` |
| `%c = and i1 %x, %y` | `i1` operands | `true` when both are |
| `%c = or i1 %x, %y` | `i1` operands | `true` when either is |
| `%c = xor i1 %x, %y` | `i1` operands | `true` when exactly one is; `xor i1 %x, true` is "not `%x`" |

- These are LLVM's operations, spelled as in LLVM, with the type after the operation as for `add`.
- **Rounding toward zero** is LLVM's, C's, Java's and JavaScript's (`Math.trunc`). It is not Python's `//`, which
  rounds down: `-7 sdiv 2` is `-3`, where Python gives `-4`, and `-7 srem 2` is `-1`, where Python's `%` gives `1`.
  SKILL.md says so, since that is the mistake a model would make.
- An unsigned result is printed as an `i64`, as every value is: `-1 udiv 2` is 2^63-1.
- `and`, `or` and `xor` take only `i1`. mime has no bitwise operations on `i64`: `and i64` is `bad-value`, with the
  hint "`and` takes `i1`; mime has no bitwise operations on `i64`". There is no `not`; `xor i1 %x, true` is the one
  form, as in LLVM.

## 2. The domain

- **Division by zero traps,** for all four. Its message is "`sdiv` by zero" (and `udiv`, `srem`, `urem` alike),
  which says which domain was left, never the values ([step-8.md](step-8.md) section 4).
- **The smallest `i64` divided by `-1` wraps,** to the smallest `i64`, and its `srem` is `0`. The true quotient,
  2^63, does not fit, and mime already has one rule for a result that does not fit: it wraps
  ([step-3.md](step-3.md)). Trapping here alone would make `sdiv` the only operation whose overflow traps, a
  second rule for a model to learn. Two's complement hardware and the JVM give this value; LLVM's `sdiv` is
  undefined for it, so the LLVM backend guards it (section 4). This replaces [backends.md](backends.md) section 1's
  example of a partial `sdiv`, which listed this case before a step decided it.
- So `sdiv` and `srem` have one partial case each, zero, and `udiv` and `urem` the same. A total definition such as
  `x / 0 = 0` was rejected: a division by zero is almost always a missing check, and a silent `0` would move the
  failure away from its cause.

## 3. The trap

- `mime run` exits with `3` and prints one JSON object on stderr ([step-8.md](step-8.md) section 4):

  ```json
  {"kind": "trap", "entry": "@mean", "key": "body", "text": "%q = sdiv i64 %sum, %count", "message": "`sdiv` by zero", "hint": null}
  ```

- `text` is the line as written in the source that ran, so a model finds it the way it finds a diagnostic.
- **What every backend promises, and what only the interpreter does.** In checked mode, the default and the spec's
  meaning, every backend must trap: stop at that line, never give a value, never go on with undefined behavior. The
  later, opt-in unchecked mode ([backends.md](backends.md) section 1) is the one exception: there a backend may assume
  every divisor is nonzero and leave the guard out, so a division by zero is undefined behavior, the price of that mode.
  The interpreter is always checked, and so are the tests and the benchmark. The report above, with its message and its
  line, is promised by the **interpreter** only. A compiled program can run outside `mime run`, linked into a program
  mime never sees, where what a trap prints is not mime's to decide: that is past mime's border. So the spec enforces
  the report where mime runs the program itself, and only the stop everywhere else. A later step may promise the report
  on more backends, when it can be enforced there.
- **Run cases** gain `"trap"` in place of `"output"`, holding the message: `{"symbol": "mean", "inputs": ["4", "0"],
  "trap": "`sdiv` by zero"}`. On the interpreter, the run must trap with that message; on any other backend, it must
  trap.
- This narrows [step-8.md](step-8.md) section 4, which said every backend reports the same object.

## 4. Backends

- **Interpreter.** `sdiv` divides the absolute values and gives the quotient the sign of the product, so it rounds
  toward zero whatever Python's `//` does; `srem` follows from it. Both wrap. `udiv` and `urem` work on the values
  modulo 2^64. A zero divisor raises the trap with the line it is on.
- **LLVM.** Each division is guarded:

  ```
    %v2.zero = icmp eq i64 %v1, 0
    br i1 %v2.zero, label %b0.t0, label %b0.d0
  b0.t0:
    call void @mime.trap(i64 3)
    unreachable
  b0.d0:
    %v2.edge = and i1 (icmp eq i64 %v0, -9223372036854775808), (icmp eq i64 %v1, -1)    ; sdiv and srem only
    %v2.by = select i1 %v2.edge, i64 1, i64 %v1
    %v2 = sdiv i64 %v0, %v2.by
  ```

  (written with its compares inlined here; the IR has one line each). Dividing the smallest `i64` by `1` instead
  of `-1` gives exactly the wrapped quotient and the zero remainder, so the overflow guard is a `select`, with no
  branch. The block after a guard continues the line's block, so a jump out of that block, and the `phi` that
  receives it, names the last continuation (`b0.d0`), not `b0`.
- **The trap routine.** `@mime.trap` takes the trap's site, a number for each guarded line in the program, in the
  order of `mime llvm`, and never returns. A module only declares it, so `mime llvm` stays a library: whoever links
  the module defines what a trap does there. The runner of `mime run --backend llvm` defines it to write the site
  to stderr and exit with `3`, and the toolchain looks the site up in a table it built while lowering, so `mime
  run` shows the interpreter's report here too. That is a convenience, not a promise (section 3): the tests check
  only that the LLVM backend traps.
- **JavaScript and the JVM,** later, guard the same two cases: `BigInt` division throws on zero and the JVM's on
  zero; both need `asIntN` or nothing for the wrap.

## 5. Hints for other habits

| Written | Hint |
|---|---|
| `div`, `idiv`, `/` as an operation | "write `sdiv i64` (signed) or `udiv i64` (unsigned)" |
| `mod`, `rem`, `%` as an operation | "write `srem i64` (signed, the sign of the dividend) or `urem i64`" |
| `not` | "write `xor i1 %c, true`" |
| `sdiv i1` | "write `sdiv i64`", as for `add` |
| `and i64` | "`and` takes `i1`; mime has no bitwise operations on `i64`" |
| `fdiv` | as an unknown word, with the list of operations |

## 6. Easy for a model?

- **Familiar:** LLVM's names and C's meaning. `and`, `or`, `xor` on `i1` are LLVM's, and every language has them.
- **New:** rounding toward zero, for a model that thinks in Python; and `xor … true` for "not". SKILL.md states both.
- **Mistakes surface** as a trap with the line that divided by zero, on every backend, never as a wrong value or
  undefined behavior. A Python habit (`//` rounding down) does not surface by itself; it shows as a wrong answer on
  negative inputs, which is why SKILL.md names it.

## 7. What changes elsewhere

- [backends.md](backends.md) section 1: the smallest `i64` divided by `-1` wraps.
- [step-3.md](step-3.md)'s overflow rule now covers `sdiv` too; [spec/SKILL.md](../spec/SKILL.md): the operations,
  rounding, the trap, and `xor … true`.
- Goldens: a clean `division` golden (signed and unsigned, both remainders, the wrapped edge, a trap per operation,
  and `and`, `or`, `xor`) and a clean `gcd`; a mistakes golden for the hints of section 5. The checker's hint "the
  operations are `add`, `sub`, `mul` and `icmp`" lists the new ones.
- The benchmark: a `gcd` task can now be written; adding one is a change to the task set, outside this step.
