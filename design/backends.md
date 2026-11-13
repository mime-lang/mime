# Backends

> Status: settled direction. LLVM is the only backend today. This note says how more are added: a reference
> interpreter, JavaScript, the JVM, and an interpreter written in mime. Each arrives in its own roadmap step.

## 1. The spec defines the meaning

A mime program means what the spec says, not what one backend happens to do. Every backend implements the same
meaning, and a backend that disagrees has a bug.

- **Each operation has one meaning on every backend.** Overflow wraps because the spec says so, not because LLVM's
  `add` does. JavaScript's numbers do not wrap at 64 bits, so its backend must make them.
- **An operation may be partial; it is never undefined.** Mathematically, an operation that is not defined for some
  inputs is a partial function (`sdiv` by zero, or the smallest `i64` divided by `-1`). mime keeps partial
  operations, but outside its domain an operation **traps**: the program stops with a defined error, the same on
  every backend. It is never C's or LLVM's undefined behavior, where the compiler may assume the case never
  happens and change the meaning of the whole program, even code that ran before it. The step that adds a partial
  operation decides its domain, and may instead choose a total definition (such as `x / 0 = 0`) if the trap would
  hide nothing.
- **A trap is observable.** `mime run` reports it the same way on every backend, with its own exit code. Later,
  the types step can let the checker prove that a value is inside the domain, so a backend may leave the check out.
- **Backend habits become guards.** Where a target's own operation differs from mime's meaning, its backend adds
  the guard: LLVM's `sdiv` is undefined for the smallest `i64` divided by `-1`, JavaScript's `BigInt` division throws
  on zero, and the JVM throws on integer division by zero. Each is turned into mime's trap or value.

### Unchecked mode, later and opt-in

Traps cost a compare and a branch on the few partial operations (division, remainder, and later list indexing and
shifts); wrapping overflow costs nothing. When that matters, a later build command may offer an **unchecked mode**,
for example `mime build --unchecked`, in which a backend assumes that every partial operation stays inside its
domain and leaves out the check.

- A program that leaves the domain in unchecked mode has undefined behavior. That is the price of the mode, and
  the reason it is never the default.
- The spec's meaning is always the checked one. The conformance tests, the golden tests and the benchmark run only
  checked, so backends can always be compared, and a model always sees a trap where its mistake is.
- Where the checker can prove that an input is inside the domain (from the types step on), the check is left out
  in every mode, and that needs no unchecked mode at all.

The model is Rust's: integer overflow panics in a debug build, and the release behavior is an explicit choice.
Why checked is the default: mime's user is a model, and models make mistakes. Undefined behavior moves a failure
away from its cause, so a model could not repair it from a diagnostic, and backends could disagree without either
being wrong.

## 2. One checked form, many backends

The checker produces one backend-neutral form of a program: its functions, their inputs and outputs, their lines,
and later their blocks. Every backend reads that form, and nothing in it is specific to one target. Today the LLVM
lowering reads the checker's output directly. When the second backend arrives, that output is named and documented
as the form backends share.

```
mime text ──parse──▶ module ──check──▶ checked form ──┬─▶ LLVM IR ──clang──▶ native
                                                       ├─▶ interpreter
                                                       ├─▶ JavaScript
                                                       └─▶ JVM bytecode
```

## 3. Conformance tests

Every clean golden carries its run cases as data: inputs and the expected output, or the expected trap. Every
backend runs every case and must give the same answer. Backends check each other this way, which is differential
testing: a disagreement points at a bug in one of them. From the step that adds the second backend, a step is done
only when it behaves the same on every backend that exists.

## 4. The backends

| Backend | Maps easily | Hard parts |
|---|---|---|
| **LLVM** (today) | everything so far | guards for LLVM's undefined behavior, such as division edge cases |
| **Reference interpreter** | everything: it is the simplest backend | speed only |
| **JavaScript** | `i1` as a boolean; lists as arrays | `i64` needs `BigInt` with `BigInt.asIntN(64, …)` to wrap, which is exact but slow. JavaScript has no `goto`, so blocks lower to a loop around a `switch` on the next block. There are no guaranteed tail calls, so deep recursion can overflow the stack |
| **JVM** | `long` wraps natively; bytecode has `goto`, so blocks map directly | integer division by zero throws and needs a guard; modules map onto classes |

## 5. The interpreter, in two stages

1. **A reference interpreter in the bootstrap toolchain.** It is small, since it walks lines and blocks, and it
   is the second backend: the conformance tests can compare LLVM against it at once, and most tests can run
   without clang. Like everything in `mime-py/`, it is deleted once mime compiles itself.
2. **An interpreter written in mime.** An interpreter represents a program as data, so it needs lists, structs,
   unions and modules first. It is the first large mime program, and it replaces the reference interpreter as
   `mime run --backend interp`.

## 6. What this decides for other steps

- **Lists are a primitive type**, not built from raw memory and pointers. Arrays map directly onto JavaScript and
  the JVM; pointers would be costly on both.
- **Blocks stay general**: any block may jump to any other. The cost falls on the JavaScript backend's loop and
  `switch`, not on the language.
- **The backend is chosen on the command line**, as `mime run --backend llvm|interp|js|jvm`, with LLVM the default.
  Its exact form is decided with the reference interpreter.

## 7. The cost to keep in mind

Every backend multiplies the cost of every later step, since each new feature is built once per backend. So the
reference interpreter comes early, because it is cheap and catches bugs, and JavaScript and the JVM come once the
core data types (lists, structs) stop changing.
