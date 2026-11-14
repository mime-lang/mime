# The abstract machine

> Status: settled direction. mime's meaning is the LLVM abstract machine: an operation means what the
> [LLVM Language Reference](https://llvm.org/docs/LangRef.html) says it means. This note replaces
> [backends.md](backends.md) section 1's "the spec defines the meaning" and narrows step 13. [step-14.md](step-14.md)
> built it.

## 1. The rule

**mime is a subset of LLVM.** Every mime program lowers to an LLVM program with the same meaning; mime only takes
things away. Its checker rejects more programs than LLVM's verifier does, and checked mode rejects more runs than
LLVM does, trapping where LLVM would reach poison or undefined behavior. A program mime accepts and a run it
completes give exactly the result LLVM gives. mime never gives a different one.

- **A subset of meaning, not of text.** mime is spelled its own way: inputs are `@` words, blocks take parameters
  instead of `phi`, and abstracts sit beside the code. Each of these lowers one to one, so the subset is of the
  programs LLVM can express, through that lowering.
- **Running out of stack or time is not covered**: it is the machine's limit, not the program's meaning
  ([step-9.md](step-9.md)), and LLVM has it too.
- **A test for every step:** a feature that would let mime accept what LLVM rejects, or give a different result,
  breaks the rule.

**An operation means what LangRef says.** mime spells its operations as LLVM does (`add`, `sdiv`, `icmp`, `br`,
`phi`-like block parameters, `call`, `ret`), and each one keeps LLVM's meaning exactly. mime adds no meaning of its
own and picks no total definition where LLVM leaves a case open.

LangRef gives every operation, for every input, one of three outcomes. mime's two modes differ only in the last two:

| LangRef says | Example | Checked mode (the default) | Unchecked mode (later, opt-in) |
|---|---|---|---|
| **a value** | `add` wraps; `sdiv` rounds toward zero | that value, on every backend | that value |
| **poison** | `shl` by 64 or more; `add nsw` that overflows | **trap** at the line that makes it | as LLVM: the poison flows on |
| **undefined behavior** | `sdiv` by zero; the smallest `i64` `sdiv -1`; a load out of bounds | **trap** at that line | as LLVM: undefined |

- **Checked mode** is the spec's meaning for a model, the default everywhere, and the only mode of the interpreter,
  the tests and the benchmark. A program that runs clean in checked mode never reaches LLVM's poison or undefined
  behavior, so its result is the same in both modes and on every backend.
- **Unchecked mode** is LLVM itself: the same program, lowered with no guards, behaves exactly as the same IR does
  under LLVM, poison and undefined behavior included. It is for speed, and is never used to judge a program.
- **Checked mode is mime's, not LLVM's.** LLVM never checks for poison or undefined behavior as a program runs;
  it leaves that to front ends. The nearest pattern is clang's UBSan, which guards an operation with a compare, a
  branch and a trap call in the IR. Checked mode is the same shape at the IR level, with a wider reach: UBSan guards
  some of C's rules, and checked mode guards every case where LangRef gives poison or undefined behavior. Unchecked
  mode needs nothing of mime's: it is plain LLVM.
- **`undef`** is not in mime: no operation makes it, and no line can write it. So it needs no rule.

## 2. Poison traps where it is made

LLVM lets poison flow: it becomes undefined behavior only when it reaches a branch condition, a store address, a
division's divisor, a call that needs a defined value, and so on. Checked mode traps one step earlier, at the line
that **makes** the poison.

- **It keeps mime a subset of LLVM** (section 1). A program clean under this rule never makes poison, so LLVM's
  meaning holds for it unchanged.
- **It points at the cause.** The trap names the line a model must fix, not a later line the poison happened to
  reach. Tracking poison as it flows would report the use, far from the mistake.
- **It is simple for every backend:** one guard per line that can make poison, with no shadow state.

Today no mime line can make poison. Flags such as `nsw` and `nuw`, and shifts, will be the first, in their steps.

## 3. Traps

A trap is as [step-13.md](step-13.md) section 3 set it: in checked mode, every backend stops at that line and never
gives a value; `mime run` exits with `3`; the interpreter prints the report with its message and line, and other
backends promise only the stop. A trap's message names the rule LangRef sets, never the values: "`sdiv` by zero",
"`sdiv` overflow".

Running out of stack or time stays a machine limit ([step-9.md](step-9.md)), not a trap: LangRef gives a call no
depth limit, and a machine that cannot hold the stack stops with exit code `2`.

## 4. What changes in what exists

Steps 1 to 13 already follow LangRef, with one exception.

| Operation | LangRef | Steps 1 to 13 | From step 14 |
|---|---|---|---|
| `add`, `sub`, `mul` | wrap (no flags) | wrap | the same |
| `icmp`, `br`, `call`, `ret`, block parameters | defined | defined | the same |
| `and`, `or`, `xor` on `i1` | defined | defined | the same |
| `sdiv`, `srem`, `udiv`, `urem` by zero | undefined | trap | the same |
| smallest `i64` `sdiv -1`, `srem -1` | undefined | **wraps** to the smallest `i64`, and `0` | **trap**, "`sdiv` overflow" and "`srem` overflow" |

- [step-13.md](step-13.md) section 2 chose to wrap, so `sdiv` would not be "the only operation whose overflow
  traps". Under this rule it is LLVM that decides, and LLVM leaves the case undefined, so checked mode traps.
- In the LLVM backend, the overflow guard stops being a `select`: it becomes a second branch to its own trap block,
  with its own trap site. In unchecked mode, both guards go and the line is LLVM's `sdiv` alone.
- The interpreter traps on the case; the `division` and `gcd` goldens' run cases change from the wrapped values to
  the trap.

## 5. Other backends

Every backend implements LangRef's meaning in checked mode. JavaScript and the JVM add their own guards where their
operations differ (`BigInt.asIntN` for the wrap, a check before the JVM's division), as
[backends.md](backends.md) section 1 already says.

## 6. The step

[Step 14](step-14.md) builds the rule: the trap for the smallest `i64` divided by `-1` on the
interpreter and LLVM, the goldens, and the docs. Unchecked mode is not part of it; it arrives with `mime build`.

## 7. Easy for a model?

- **Familiar:** LangRef is the IR spec models have read most. Whatever a model knows about an LLVM operation is
  now true of mime's, with no mime-only exceptions to learn. Checked mode leans on UBSan: a guard and a trap
  before the operation that would break the rule.
- **New:** one rule, "in checked mode, poison and undefined behavior trap at their line", and that mime has no
  `undef`.
- **Mistakes surface** as a trap on the line that broke LangRef's rule, never as a silent value. A model that
  relies on the wrap of the smallest `i64` divided by `-1`, a hardware habit, gets a trap naming the line.

## 8. What changes elsewhere

- [backends.md](backends.md) section 1: the meaning is LangRef's; "the step that adds a partial operation decides
  its domain, and may choose a total definition" goes, since LangRef decides; the smallest `i64` divided by `-1`
  traps.
- [core.md](core.md): its header line on backends.md, and section 8's primitives, say the meaning is LangRef's.
- [step-13.md](step-13.md) section 2: its wrap of the edge case is replaced by section 4 above.
- [roadmap.md](roadmap.md): the step of section 6 is done.
- [spec/SKILL.md](../spec/SKILL.md): the rule of section 1 and the edge-case trap.
