# Step 14: LLVM's abstract machine

> Status: settled. The fourteenth step of the [roadmap](roadmap.md). It makes LLVM's Language Reference the meaning of
> every mime operation ([abstract-machine.md](abstract-machine.md)), and builds the one change that follows for what
> exists: `sdiv` and `srem` of the smallest `i64` by `-1`, which LLVM leaves undefined, trap in place of wrapping.

## 1. The change

| Line | Before (step 13) | Now |
|---|---|---|
| `sdiv i64 -9223372036854775808, -1` | wraps to `-9223372036854775808` | traps: "`sdiv` overflow" |
| `srem i64 -9223372036854775808, -1` | `0` | traps: "`srem` overflow" |

Everything else in steps 1 to 13 already means what LangRef says ([abstract-machine.md](abstract-machine.md)
section 4). A line of `sdiv` or `srem` now has two guards, in this order: a zero divisor, then the overflow. A zero
divisor with the smallest `i64` as the dividend traps as "by zero", since that guard runs first.

## 2. Backends

- **Interpreter.** After the zero check, `sdiv` and `srem` check for the smallest `i64` divided by `-1` and raise
  the trap with "`sdiv` overflow" or "`srem` overflow".
- **LLVM.** Each guard branches to its own trap block, with its own trap site; step 13's `select`, which replaced
  the divisor by `1`, is gone:

  ```
    %v2.zero = icmp eq i64 %v1, 0
    br i1 %v2.zero, label %b0.t0, label %b0.d0
  b0.t0:
    call void @mime.trap(i64 3)
    unreachable
  b0.d0:
    %v2.min = icmp eq i64 %v0, -9223372036854775808
    %v2.neg = icmp eq i64 %v1, -1
    %v2.over = and i1 %v2.min, %v2.neg
    br i1 %v2.over, label %b0.t1, label %b0.d1
  b0.t1:
    call void @mime.trap(i64 4)
    unreachable
  b0.d1:
    %v2 = sdiv i64 %v0, %v1
  ```

  A trap site is now a guard, not a line: the sites are numbered by function, block, line and guard, and the table
  the toolchain builds while lowering holds each site's line and message. The blocks of a guard are numbered by the
  guards above it in its block, and a jump out of the block, with the `phi` that receives it, names the last
  continuation (`b0.d1`), as in step 13.
- **JavaScript and the JVM**, later: the JVM's `ldiv` and `lrem` give the wrapped value for this case, and `BigInt`
  gives 2^63; both need the guard.

## 3. Run cases and goldens

- `division`: the two edge cases change from their wrapped values to the traps, and the abstracts of `@quotient`
  and `@remainder` say when they trap.
- `gcd`: a trap case for each function, since `srem` reaches the edge when one input is the smallest `i64` and the
  other `-1`, in either order for the loop.

## 4. Easy for a model?

- **Familiar:** LLVM's meaning, as LangRef states it; C's too, where this case is undefined.
- **New:** a hardware habit (x86 faults, the JVM wraps) no longer holds; SKILL.md says so.
- **Mistakes surface** as a trap naming the line and "overflow", never as a value that looks right.

## 5. What changes elsewhere

- [backends.md](backends.md) section 1: LangRef defines the meaning; checked mode traps where it says poison or
  undefined behavior; no step chooses a total definition.
- [step-13.md](step-13.md) section 2: the wrap is replaced by this step. [core.md](core.md): the header and the
  primitives say the meaning is LangRef's.
- [spec/SKILL.md](../spec/SKILL.md): the rule, under "Not LLVM", and the edge-case trap under division.
