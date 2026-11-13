# Step 10: loops with one way in

> Status: settled. The tenth step of the [roadmap](roadmap.md). It adds one rule to the blocks of
> [step-7.md](step-7.md): every loop has a single entry block, so a body's control flow is **reducible**. Nothing
> else in the language changes. This replaces "blocks stay general" in [backends.md](backends.md) section 6.

```
define @count {@n} -> i64 {
  br ^loop{0}
^loop{%i}:
  %more = icmp slt i64 %i, @n
  br %more, ^step{%i}, ^done{%i}
^step{%j}:
  %k = add i64 %j, 1
  br ^loop{%k}
^done{%r}:
  ret %r
}
```

Every jump into the cycle `^loop`, `^step` goes to `^loop`: from the entry block, and back from `^step`. `^loop` is
the loop's **header**, the one block that every way into the loop passes through.

## 1. The rule

- A **back edge** is a jump to a block that has already run on every path to the jumping block: its target
  dominates its source, in the words of compilers. A block that jumps to itself is a back edge.
- **Every jump that closes a cycle is a back edge.** Equivalently, each cycle can be entered at only one block,
  its header. A body that breaks this is `irreducible-loop`.
- This is what `while`, `for`, `break` and `continue` produce in every structured language, and what WebAssembly's
  `loop` and `br` can express directly.

```
define @bad {@flag} -> i64 {
  br @flag, ^a{0}, ^b{0}
^a{%x}:
  %y = add i64 %x, 1
  br ^b{%y}
^b{%z}:
  %w = add i64 %z, 1
  %c = icmp slt i64 %w, 10
  br %c, ^a{%w}, ^done{%w}
^done{%r}:
  ret %r
}
```

The cycle `^a`, `^b` is entered at `^a` and at `^b`, so neither block is its header. The checker reports the jump
that closes the cycle at the wrong block.

## 2. Checking

- The checker finds the blocks each block is dominated by, over the blocks that are reached, then walks the body
  depth first from the entry block, following each block's jumps in the order they are written. A jump to a block
  still on the walk's path closes a cycle; if that block does not dominate the jumping block, the jump is
  `irreducible-loop`, reported at the target's label in the `br`.
- Whether a body is reducible does not depend on the order of the walk, so the rule follows only the jumps, never
  a name: renaming keeps it.
- Each loop header is reported at most once.

| Kind | Message | Hint |
|---|---|---|
| `irreducible-loop` | "the loop through `^a` can also be entered without passing `^a`" | "give the loop one entry: every jump into it, from outside or from inside, goes to one block, which takes a parameter saying where to go and branches on it" |

## 3. Every irreducible body has a reducible form

Blocks are closed and take their values as arguments, so the fix is always mechanical: add a header that receives
the values and a flag, and branch on the flag. `@bad` becomes

```
define @good {@flag} -> i64 {
  br ^head{@flag, 0}
^head{%toa, %x}:
  br %toa, ^a{%x}, ^b{%x}
^a{%v}:
  %y = add i64 %v, 1
  br ^head{false, %y}
^b{%z}:
  %w = add i64 %z, 1
  %c = icmp slt i64 %w, 10
  br %c, ^head{true, %w}, ^done{%w}
^done{%r}:
  ret %r
}
```

(Here `^a` could also jump to `^b` directly, since `^head` dominates both. The canonical form is not decided by this
rule: both are clean.)

## 4. Why

- **JavaScript and WebAssembly map blocks onto structured loops.** Neither has `goto`. A reducible body lowers to
  labeled `while`, `break` and `continue` in JavaScript, and to `block`, `loop` and `br` in WebAssembly, so the
  loop-and-`switch` dispatcher of [backends.md](backends.md) section 4 is no longer needed. Engines optimize
  structured loops well, and the output can be read.
- **Loops are found from the jumps alone.** A loop is its header and the back edges to it. The types step, which
  may prove a value stays inside an operation's domain ([backends.md](backends.md) section 1), and any later
  reasoning about loops start from there.
- **It costs nothing now.** No golden or test program is irreducible, so no program changes form. Adding the rule
  after programs exist would break them.
- LLVM, the JVM and the interpreter handle any jumps, so they gain nothing and lose nothing.

## 5. Easy for a model?

- **Familiar:** every loop a model has learned from in a structured language has one way in, so a model writes
  reducible bodies without being told.
- **New:** one rule, and only `goto`-style state machines meet it.
- **Mistakes surface** as `irreducible-loop` at the jump into the loop's middle, naming the block that should be
  the header, with the mechanical fix of section 3 as the hint. A multi-entry loop is usually a jump wired to the
  wrong block, which the diagnostic also catches.

## 6. What changes elsewhere

- [backends.md](backends.md) section 6: blocks are reducible, and the JavaScript row of section 4 lowers them to
  structured loops.
- [layout.md](layout.md) section 5 and [spec/SKILL.md](../spec/SKILL.md): the rule.
- [roadmap.md](roadmap.md): the JavaScript backend no longer decides the loop-and-`switch` lowering.
- The mistakes goldens gain `irreducible_loop`.
