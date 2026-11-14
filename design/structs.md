# Structs A: struct values

> Status: draft for review. The first of two sub-steps of the structs step in the [roadmap](roadmap.md). It adds
> LLVM's first-class aggregates: a data word whose type is a list of field words, `extractvalue` and `insertvalue`
> to read and set a field, and `poison` to start from. Types are compared by their fields, as LLVM compares
> literal structs. **Structs B**, the next sub-step, makes them nominal, as LLVM's identified structs are. The note
> is renamed `step-N.md` when the sub-step is done.

```
@x = {type = i64, abstract = "how far across"}
@y = {type = i64, abstract = "how far up"}
@point = {type = {@x, @y}, abstract = "a place on the plane"}
@from = {type = @point, abstract = "where the move starts"}
@step = {type = i64, abstract = "how far to move"}

define @move {@from, @step} -> @point {
  %x = extractvalue @point @from, @x
  %moved = add i64 %x, @step
  %to = insertvalue @point @from, %moved, @x
  ret %to
}
abstract = "@from moved @step to the right"
symbol = "move"

define @origin {} -> @point {
  %p0 = insertvalue @point poison, 0, @x
  %p = insertvalue @point %p0, 0, @y
  ret %p
}
abstract = "the @point at 0 across and 0 up"
symbol = "origin"
```

## 1. Strictly LLVM, with one change: fields are words

A struct is LLVM's **first-class aggregate**: a value such as `{ i64, i64 }`, held like any other SSA value and never
in memory. mime adds no memory, no pointers and no new operation. Its lines are LLVM's `extractvalue` and
`insertvalue`, with LLVM's operand order, and a struct is built as clang builds one, from `poison`.

The one thing mime does differently is how a line names a field: **by its word, not its index.** LLVM writes
`extractvalue { i64, i64 } %p, 0`; mime writes `extractvalue @point %p, @x`, and lowering turns `@x` into its index.

- A model never counts positions, and a field added in the middle of a struct changes no line that reads another.
- It holds under renaming: `@x` is renamed with the program, and its index never changes.
- It is what [core.md](core.md) section 4 already set: a field is reached by its word.
- It lowers one to one, so it costs nothing on any backend.

## 2. The struct type

```
@point = {type = {@x, @y}, abstract = "a place on the plane"}
@from = {type = @point, abstract = "where the move starts"}
```

- **A field list makes a struct word.** `type = {@x, @y}` lists data words, each declared before the struct, each at
  most once. They are its **fields**, in that order. Field order is fixed: `{@y, @x}` is another type. A struct has at
  least one field.
- **A field's type** is `i64`, `i1` or a struct word, so structs nest: `@segment = {type = {@from, @to}}`.
- **A word typed by a struct word** has that struct's type: `@from`'s values are `@point`s. This is how a function
  takes two of one struct (`define @distance {@from, @to} -> @length`). A struct word may itself be an input, as
  `@point` is in `@move`.
- **A type names a struct word, never a word typed by one.** `@start = {type = @from}` is `bad-type`, with the hint
  "`@from` is a `@point`; write `type = @point`". So each type has one spelling. A type never names a scalar word
  either: `@count = {type = @number}` gets "write `type = i64`".
- **A field word is an ordinary data word.** It has its own abstract, it may be a field of several structs, and it
  may also be an input. `@x` in `@point` and in `@vector` is the same word, with the same meaning.
- **No struct holds itself,** directly or through another struct: `@node = {type = {@value, @node}}` is already a
  forward reference, since a declaration refers only to earlier entries. An LLVM struct cannot contain itself by
  value, because it would be infinitely large; data that refers to itself needs memory, which is put off until it is
  needed.

**Types are compared by their fields in this sub-step**, as LLVM compares literal structs: two struct words with the
same field list are the same type. [layout.md](layout.md) section 3 promises nominal types, so that `@point` and
`@vector` differ even with the same fields; Structs B builds that, and until it lands the checker does not tell them
apart.

## 3. The lines

| Line | Result | LLVM |
|---|---|---|
| `%v = extractvalue @point %p, @x` | the `@x` field of `%p`, typed as `@x` is | `extractvalue { i64, i64 } %p, 0` |
| `%q = insertvalue @point %p, %v, @x` | `%p` with its `@x` field replaced by `%v` | `insertvalue { i64, i64 } %p, i64 %v, 0` |
| `%q = insertvalue @point poison, %v, @x` | a `@point` with only `@x` set | `insertvalue { i64, i64 } poison, i64 %v, 0` |

- **The type slot** holds the struct word, as `add i64` holds `i64`, and the struct operand must have that type.
- **The value** given to `insertvalue` must have the field's type: an `i64` for `@x`, a `@point` for `@from`.
- **One field per line.** LLVM's index paths, `extractvalue %s, 0, 1`, are not mime: reading a field of a field takes
  two lines, each with its own local, as every operation in mime has.
- **`poison` is written only as the struct operand of `insertvalue`**, the start of a build. Anywhere else (an
  operand of `add`, an argument, a block argument, `ret`) it is `bad-value`: there it would only ever be read or
  passed on, and section 4 forbids both.
- **No comparison of structs.** LLVM's `icmp` takes integers only, and so does mime's; compare the fields.
- **Structs flow like any value:** as inputs, outputs, call arguments and results, block parameters, and fields of
  other structs.

## 4. Every field is set before it is read

A field that is still `poison` is LLVM's poison: reading it gives a poison scalar. Rather than trap at run time, the
**checker** proves that no run reads one, so neither mode ever meets it, and the backends need no shadow state.

- **The rule:** a field is read only where it is set on **every** path to that line. This is definite assignment,
  Java's "variable might not have been initialized" and Rust's E0381, applied to fields.
- **Inside a function** the checker tracks, for each struct local, the fields that are set:
  - an input, a call's result and an `extractvalue` of a struct field have every field set;
  - `insertvalue … poison, %v, @x` has only `@x`; `insertvalue … %p, %v, @x` has `%p`'s fields and `@x`;
  - a block parameter has the fields set in every argument passed to it, on every jump. A loop's back edge is
    included, so the checker iterates until the sets stop changing.
- **At the edges, a struct is whole.** A struct passed to a call, returned by `ret`, or given as the value of an
  `insertvalue` must have every field set. So the analysis never crosses a function, a caller never meets a poison
  field, and `mime run` never prints one. Only a local, inside one function, is ever partly set.
- **`unset-field`**, the new diagnostic:

  ```
  %y = extractvalue @point %q, @y
  ```

  "`@y` may not be set here: a path reaches this line without setting it", with the hint "set `@y` on every path
  before reading it". A partial struct at a call or `ret` gets "`%q` is passed before `@y` is set on every path".
- **What it gives up.** The checker follows paths, not the values that choose them. A program that sets `@y` only
  when `%c` holds, and later reads it only when `%c` holds, never reads poison, but the checker rejects it, as Java
  and Rust do. Proving it would need a checker that reasons about values, and a model could not predict what it
  accepts. The fix is always the same: give the field a value on the other path too.
- **It changes nothing in the abstract machine.** A program the checker accepts never reads poison, so its meaning
  is LLVM's in both modes; the check only rejects more programs than LLVM does, as
  [abstract-machine.md](abstract-machine.md) section 2 allows. That section gains one sentence: a struct may hold
  poison fields that are never read.

## 5. Running

- **`mime run` reads and prints a struct by position,** as an LLVM constant is written: `{3, 4}`, nested as
  `{{0, 0}, {3, 4}}`, with `true` and `false` for `i1` fields. Printing field words would make the output change
  under renaming. An input is one argument: `mime run prog.mime move "{3, 4}" 2` prints `{5, 4}`.
- **A malformed struct argument** is a run error before the program starts, as a malformed integer is: "`move`'s
  first input is a `@point`, which takes 2 values, like `{1, 2}`".
- **Run cases** write a struct input or output the same way: `{"symbol": "move", "inputs": ["{3, 4}", "2"],
  "output": "{5, 4}"}`.

## 6. Backends

- **Interpreter.** A struct is a tuple of its field values; `poison` is a tuple of placeholders that section 4 ensures
  are never read. `extractvalue` and `insertvalue` take the field's index, found from its word while checking.
- **LLVM.** A struct word lowers to its literal type, `{ i64, i64 }`, and each field word to its index. Lines lower
  one to one: `%v1 = insertvalue { i64, i64 } poison, i64 0, 0`. Functions take and return structs by value, as
  LLVM allows. The runner builds each struct input with `insertvalue` from its parsed values and prints a result with
  `extractvalue`.
  - An exported function that takes or returns a struct uses LLVM's own way of passing aggregates, which is not the
    C calling convention clang uses for a C struct. Calling a mime function from C is a later concern (modules).
- **JavaScript and the JVM,** later: a struct is a frozen array or an object, and `insertvalue` makes a copy.

## 7. Hints for other habits

| Written | Hint |
|---|---|
| `extractvalue @point %p, 0` | "fields are words: write `@x`" |
| `extractvalue @segment %s, @from, @x` | "one field per line: read `@from`, then `@x` from it" |
| `%p.x`, `@point.@x`, `%p.@x` | "read a field with `%v = extractvalue @point %p, @x`" |
| `insertvalue @point %p, @x, %v` | "the value comes before the field: write `%v, @x`" |
| `extractvalue %p, @x` | "write the struct word after `extractvalue`: `extractvalue @point %p, @x`" |
| `extractvalue { i64, i64 } %p, @x` | "write the struct word, `@point`, not its fields" |
| `undef`, `zeroinitializer` | "start a struct from `poison`, and set every field before reading it" |
| `getelementptr`, `load`, `store`, `alloca` | "structs are values, not memory: use `extractvalue` and `insertvalue`" |
| `@x` read from a struct without it | "`@point` has no field `@x`; its fields are `@x` and `@y`" |

## 8. Easy for a model?

- **Familiar:** LLVM's `extractvalue` and `insertvalue`, with LLVM's operand order and clang's build from `poison`;
  definite assignment from Java and Rust; `{3, 4}` from LLVM constants.
- **New:** the field is a word, not an index, and the type slot is the struct word. A model writing LLVM habits gets
  a hint naming the word (section 7).
- **Mistakes surface** in the checker, before anything runs: a field read before it is set on every path is
  `unset-field` at that line, a wrong field or type names the struct's fields, and an index or a path gets the word
  form. None reaches a run as poison.

## 9. What changes elsewhere

- [abstract-machine.md](abstract-machine.md) section 2: a struct may hold poison fields that are never read; the
  checker ensures it.
- [layout.md](layout.md) section 2: `type` is a primitive, a field list, or a struct word. [core.md](core.md)
  section 4: a field is read with `extractvalue`, not `input.$first`.
- [roadmap.md](roadmap.md): structs split into A (this note) and B (nominal identity, as LLVM's identified structs).
- [spec/SKILL.md](../spec/SKILL.md): struct words, the two lines, `poison`, the set-before-read rule, and run I/O.
- Goldens: a clean `structs` golden (building, reading, replacing, nesting, a struct through a loop's block
  parameter, structs as inputs and outputs) with run cases, and a mistakes golden for section 7 and `unset-field`.
- `mime canon` and `rename` need nothing new: field words are words. Canonical order already pulls a struct's field
  words above it, since its type refers to them.
