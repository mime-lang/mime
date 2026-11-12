# mime-py

The bootstrap toolchain for mime, written in Python. It exists only until mime can compile itself; after that, this whole folder is deleted.

Keep everything Python-specific inside this folder. Language docs, the spec, example programs and benchmarks live at the repo root so they outlive the bootstrap.

Requirements: Python 3.12+, [hatch](https://hatch.pypa.io/), and [clang](https://clang.llvm.org/) on `PATH` for `mime run`. Without clang, the tests that run programs are skipped.

```bash
cd mime-py
hatch test
hatch run mime --version
```
