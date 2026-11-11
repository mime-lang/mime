#!/usr/bin/env python3
"""Token accounting: spec + input + output tokens, across every retry, until passing.

Real providers report exact usage per call; adapters must pass those numbers to
Ledger.add. The approximate counter here is only for mock models and dry-run estimates.

CLI: python3 count_tokens.py FILE...   (prints approximate tokens per file)
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

TOKENIZER = 'approx-utf8-bytes/4'


def approx_tokens(text: str) -> int:
    return math.ceil(len(text.encode('utf-8')) / 4)


def messages_tokens(messages: list[dict]) -> int:
    return sum(approx_tokens(m['content']) for m in messages)


@dataclass
class Call:
    input_tokens: int  # everything sent, spec included
    output_tokens: int
    spec_tokens: int  # the part of input_tokens that is the skill file


@dataclass
class Ledger:
    """All model calls made for one sample."""

    calls: list[Call] = field(default_factory=list)

    def add(self, input_tokens: int, output_tokens: int, spec_tokens: int) -> None:
        if spec_tokens > input_tokens:
            raise ValueError('spec tokens cannot exceed input tokens')
        self.calls.append(Call(input_tokens, output_tokens, spec_tokens))

    @property
    def spec(self) -> int:
        return sum(c.spec_tokens for c in self.calls)

    @property
    def input(self) -> int:
        return sum(c.input_tokens for c in self.calls)

    @property
    def output(self) -> int:
        return sum(c.output_tokens for c in self.calls)

    @property
    def total(self) -> int:
        return self.input + self.output

    @property
    def retry(self) -> int:
        """Tokens spent after the first call."""
        return sum(c.input_tokens + c.output_tokens for c in self.calls[1:])

    def to_json(self) -> dict:
        return {
            'spec': self.spec,
            'input': self.input,
            'output': self.output,
            'retry': self.retry,
            'total': self.total,
            'calls': len(self.calls),
        }


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__.strip())
        return 2
    for name in argv:
        print(f'{approx_tokens(Path(name).read_text()):>8}  {name}')
    print(f'(tokenizer: {TOKENIZER})')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
