#!/usr/bin/env python3
"""Write the `none` and `misleading` styles of a names-track library from the `honest` one.

  python3 bench/harness/make_variants.py t1-001-sum-list

Edit only variants/honest/ and variants/names.json by hand; regenerate the rest with this.
validate.py checks that the three styles are the same program up to consistent renaming.
"""

from __future__ import annotations

import json
import sys

import taskset


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__.strip())
        return 2
    for task_id in argv:
        vdir = taskset.TASKS / task_id / 'variants'
        maps = json.loads((vdir / 'names.json').read_text())
        for style in ('none', 'misleading'):
            out = vdir / style
            out.mkdir(exist_ok=True)
            for src in sorted((vdir / 'honest').iterdir()):
                (out / src.name).write_text(taskset.rename(src.read_text(), maps[style]))
                print(f'wrote {out / src.name}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
