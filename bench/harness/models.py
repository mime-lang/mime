"""Model adapters: deterministic mocks, and real providers.

The project owner chooses the models and approves any API spend (see bench/README.md).
Real adapters report the provider's exact token usage, never an estimate, and import their
SDK only when a real run starts, so validate.py, smoke.py and --dry-run stay stdlib-only.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Protocol

from count_tokens import approx_tokens, messages_tokens
from taskset import Spec

FENCE = {'python': 'python', 'typescript': 'typescript', 'mime': 'mime'}
DEFAULT = {'i64': {'python': '0', 'typescript': '0'}, 'bool': {'python': 'False', 'typescript': 'false'}}
DEFAULT['list<i64>'] = {'python': '[]', 'typescript': '[]'}

# What the manifest records about sampling, per provider.
SAMPLING = {
    'mock': 'deterministic mock; the sample seed picks its behavior',
    'anthropic': 'provider default: the API rejects temperature, top_p and top_k, and has no seed parameter',
}


@dataclass
class Completion:
    text: str  # the reply's visible text
    input_tokens: int  # everything billed as input, spec included
    output_tokens: int  # everything billed as output, thinking included
    stop_reason: str | None = None
    native: list[dict] | None = None  # provider content blocks, replayed unchanged on the next turn
    raw: dict | None = None  # the full provider response, archived as-is


@dataclass
class Oracle:
    """What a mock model may 'know' about the job. Real models never see this."""

    lang: str
    spec: Spec
    reference: str  # a passing answer
    trusting_reference: str | None = None  # names track: the honest answer, whatever the style


class Model(Protocol):
    id: str

    def complete(self, messages: list[dict], *, seed: int, attempt: int, oracle: Oracle) -> Completion: ...


class ProviderError(RuntimeError):
    """The provider failed (after its own retries). The run stops: an outage is not a model failure."""


def fenced(code: str, lang: str) -> str:
    return f'```{FENCE[lang]}\n{code.rstrip()}\n```\n'


def broken(code: str, lang: str) -> str:
    return code.rstrip() + ('\n)\n' if lang == 'python' else '\n}\n')


def constant(spec: Spec, lang: str) -> str:
    value = DEFAULT[spec.returns][lang]
    sig = spec.native_signature(lang)
    if lang == 'python':
        return f'{sig}:\n    return {value}\n'
    return f'{sig} {{\n  return {value};\n}}\n'


@dataclass
class MockModel:
    """Deterministic stand-in for a model, to test the harness end to end.

    behaviors:
      reference     always the reference answer (should pass everything)
      constant      always returns the return type's zero value (should fail)
      flaky         a syntax error first with probability 1/2, the reference after any feedback
      name-truster  names track: writes the honest-names answer whatever the style; else reference
    """

    id: str
    behavior: str

    def complete(self, messages: list[dict], *, seed: int, attempt: int, oracle: Oracle) -> Completion:
        code = self._code(seed, attempt, oracle)
        text = 'Here is the program.\n\n' + fenced(code, oracle.lang)
        return Completion(text, messages_tokens(messages), approx_tokens(text), 'end_turn')

    def _code(self, seed: int, attempt: int, oracle: Oracle) -> str:
        if self.behavior == 'reference':
            return oracle.reference
        if self.behavior == 'constant':
            return constant(oracle.spec, oracle.lang)
        if self.behavior == 'flaky':
            if attempt == 1 and random.Random(f'{self.id}:{seed}').random() < 0.5:
                return broken(oracle.reference, oracle.lang)
            return oracle.reference
        if self.behavior == 'name-truster':
            return oracle.trusting_reference or oracle.reference
        raise ValueError(f'unknown mock behavior {self.behavior!r}')


@dataclass
class AnthropicModel:
    """Claude through the official `anthropic` SDK (Messages API, non-streaming).

    Thinking is adaptive and its depth is fixed by `effort`, recorded in the manifest.
    No refusal fallback: a fallback would switch to another model and corrupt the cell,
    so a refusal is recorded as its own status instead.
    """

    id: str
    effort: str
    max_tokens: int = 16000
    client: Any = field(default=None, repr=False)

    def connect(self) -> None:
        """Import the SDK and build the client. Called once before a real run starts."""
        if self.client is not None:
            return
        try:
            import anthropic
        except ImportError as e:
            raise ProviderError('the `anthropic` package is not installed (pip install anthropic)') from e
        self.client = anthropic.Anthropic(max_retries=4)

    def describe(self) -> dict:
        """SDK version and endpoint, for the manifest. Call after connect()."""
        try:
            import anthropic

            sdk = anthropic.__version__
        except ImportError:
            sdk = None
        return {'sdk': f'anthropic {sdk}' if sdk else None, 'endpoint': str(getattr(self.client, 'base_url', ''))}

    def complete(self, messages: list[dict], *, seed: int, attempt: int, oracle: Oracle) -> Completion:
        try:
            import anthropic

            api_error: type[Exception] | tuple = anthropic.APIError
        except ImportError:  # only possible with an injected client (tests)
            api_error = ()
        self.connect()
        system = '\n\n'.join(m['content'] for m in messages if m['role'] == 'system')
        turns = [
            {'role': m['role'], 'content': m.get('native') or m['content']} for m in messages if m['role'] != 'system'
        ]
        try:
            resp = self.client.messages.create(
                model=self.id,
                max_tokens=self.max_tokens,
                system=system,
                thinking={'type': 'adaptive'},
                output_config={'effort': self.effort},
                messages=turns,
            )
        except api_error as e:
            raise ProviderError(f'{self.id}: {type(e).__name__}: {e}') from e
        except Exception as e:  # e.g. no credentials: the SDK raises TypeError before any request
            raise ProviderError(f'{self.id}: the request could not be sent: {type(e).__name__}: {e}') from e
        u = resp.usage
        input_tokens = u.input_tokens + (u.cache_creation_input_tokens or 0) + (u.cache_read_input_tokens or 0)
        text = ''.join(b.text for b in resp.content if b.type == 'text')
        native = [b.model_dump(mode='json', exclude_none=True) for b in resp.content]
        return Completion(text, input_tokens, u.output_tokens, resp.stop_reason, native, resp.model_dump(mode='json'))


def make(cfg: dict) -> MockModel | AnthropicModel:
    if cfg['provider'] == 'mock':
        return MockModel(cfg['id'], cfg['behavior'])
    if cfg['provider'] == 'anthropic':
        return AnthropicModel(cfg['id'], cfg['effort'], cfg.get('max_tokens', 16000))
    raise ValueError(f'{cfg["id"]}: no adapter for provider {cfg["provider"]!r}')
