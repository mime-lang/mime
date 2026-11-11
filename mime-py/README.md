# mime-py

The bootstrap toolchain for mime, written in Python. It exists only until mime can compile itself; after that, this whole folder is deleted.

Keep everything Python-specific inside this folder. Language docs, the spec, example programs and benchmarks live at the repo root so they outlive the bootstrap.

```bash
cd mime-py
hatch test
hatch run mime --version
```
