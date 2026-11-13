# Backends

> Status: settled direction. LLVM (step 4) and the reference interpreter (step 8) are the backends today. This note
> says how more are added: JavaScript, the JVM, and an interpreter written in mime. Each arrives in its own roadmap
> step.

## 1. LLVM's abstract machine defines the meaning

A mime program means what the [LLVM Language Reference](https://llvm.org/docs/LangRef.html) says its operations mean,
not what one backend happens to do ([abstract-machine.md](abstract-machine.md)). Every backend implements that
meaning, and a backend that disagrees has a bug.

- **Each operation has one meaning on every backend: LLVM's.** Overflow wraps because LLVM's `add` without `nsw`
  does. JavaScript's numbers do not wrap at 64 bits, so its backend must make them.
- **Where LLVM says poison or undefined behavior, checked mode traps.** `sdiv` by zero, and the smallest `i64`
  divided by `-1`, are undefined in LLVM, so in checked mode the program stops at that line with a defined error, the
  same on every backend ([step-14.md](step-14.md)). It never goes on with undefined behavior, where the compiler may
  assume the case never happens and change the meaning of the whole program, even code that ran before it. mime
  adds no meaning of its own: no step picks a total definition, such as `x / 0 = 0`, where LLVM leaves a case open.
- **A trap is observable.** In checked mode, every backend stops at a trap and never gives a value; under `mime run`
  it exits with its own code. Only the opt-in unchecked mode below may leave the check out. The full report, its
  message and its line, is promised by the interpreter, where mime runs the program itself; a compiled program can
  run outside mime, where what it prints is not mime's to decide ([step-13.md](step-13.md) section 3). Later,
  the types step can let the checker prove that a value is inside the domain, so a backend may leave the check out.
- **Backend habits become guards.** Where a target's own operation differs from LLVM's meaning, or LLVM's leaves a
  case undefined, its backend adds the guard: the LLVM backend guards its own `sdiv`, JavaScript's `BigInt` division
  throws on zero, and the JVM's division wraps the smallest `i64` divided by `-1` where mime must trap. Each is
  turned into mime's trap or value.

### Unchecked mode, later and opt-in

Traps cost a compare and a branch on the few partial operations (division, remainder, and later
shifts); wrapping overflow costs nothing. When that matters, a later build command may offer an **unchecked mode**,
for example `mime build --unchecked`, in which a backend assumes that every partial operation stays inside its
domain and leaves out the check. There the same program behaves exactly as LLVM says, poison and undefined
behavior included.

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
lowering and the reference interpreter read it, as `Program`; [step-8.md](step-8.md) section 1 documents it.

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
| **LLVM** (step 4) | everything so far | guards for LLVM's undefined behavior, such as division edge cases |
| **Reference interpreter** (step 8) | everything: it is the simplest backend | speed only |
| **JavaScript** | `i1` as a boolean; lists as arrays | `i64` needs `BigInt` with `BigInt.asIntN(64, …)` to wrap, which is exact but slow. JavaScript has no `goto`, but blocks are reducible ([step-10.md](step-10.md)), so they lower to labeled `while`, `break` and `continue`. There are no guaranteed tail calls, so deep recursion can overflow the stack |
| **JVM** | `long` wraps natively; bytecode has `goto`, so blocks map directly | integer division by zero throws and needs a guard; modules map onto classes |

## 5. The interpreter, in two stages

1. **A reference interpreter in the bootstrap toolchain.** It is small, since it walks lines and blocks, and it
   is the second backend: the conformance tests can compare LLVM against it at once, and most tests can run
   without clang. Like everything in `mime-py/`, it is deleted once mime compiles itself.
2. **An interpreter written in mime.** An interpreter represents a program as data, so it needs lists, structs,
   unions and modules first. It is the first large mime program, and it replaces the reference interpreter as
   `mime run --backend interp`.

## 6. What this decides for other steps

- **Blocks are reducible**: every loop has one way in, its header ([step-10.md](step-10.md)). This replaced
  "blocks stay general", which left JavaScript a loop around a `switch` on the next block. Structured targets,
  JavaScript and WebAssembly, lower blocks to their own loops; LLVM and the JVM take any jumps anyway.
- **The backend is chosen on the command line**, as `mime run --backend interp|llvm|js|jvm`, with the interpreter
  the default, so `mime run` needs no clang ([step-8.md](step-8.md) section 3). A run names its function by its
  `symbol`, which no renaming changes.

## 7. The cost to keep in mind

Every backend multiplies the cost of every later step, since each new feature is built once per backend. So the
reference interpreter comes early, because it is cheap and catches bugs, and JavaScript and the JVM come once the
core data types (lists, structs) stop changing.
