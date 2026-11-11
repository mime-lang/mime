"""Loading benchmark tasks, names-track variants and edit cases. Stdlib only."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

HARNESS = Path(__file__).resolve().parent
BENCH = HARNESS.parent
REPO = BENCH.parent
TASKS = BENCH / 'tasks'
EDITS = BENCH / 'edit'
REPAIRS = BENCH / 'repair'
RESULTS = BENCH / 'results'
REPORTS = BENCH / 'reports'
PROMPTS = HARNESS / 'prompts'

TASK_ID = re.compile(r'^t(?P<tier>[123])-(?P<num>\d{3})-[a-z0-9]+(?:-[a-z0-9]+)*$')
EDIT_ID = re.compile(r'^e\d{3}-[a-z0-9]+(?:-[a-z0-9]+)*$')
TYPES = ('i64', 'bool', 'list<i64>')
LANGS = ('python', 'typescript', 'mime')
EXT = {'python': 'py', 'typescript': 'ts', 'mime': 'mime'}
STYLES = ('honest', 'none', 'misleading')

PY_TYPE = {'i64': 'int', 'bool': 'bool', 'list<i64>': 'list[int]'}
TS_TYPE = {'i64': 'number', 'bool': 'boolean', 'list<i64>': 'number[]'}


@dataclass
class Spec:
    """The contents of a tests.json file."""

    id: str
    entry: str
    params: list[str]
    returns: str
    cases: list[dict]
    tier: int | None = None

    @classmethod
    def load(cls, path: Path) -> Spec:
        data = json.loads(path.read_text())
        sig = data['signature']
        return cls(data['task'], data['entry'], sig['params'], sig['returns'], data['cases'], data.get('tier'))

    def neutral_signature(self) -> str:
        return f'{self.entry}({", ".join(self.params)}) -> {self.returns}'

    def native_signature(self, lang: str) -> str:
        names = [f'a{i}' for i in range(len(self.params))]
        if lang == 'python':
            ps = ', '.join(f'{n}: {PY_TYPE[t]}' for n, t in zip(names, self.params))
            return f'def {self.entry}({ps}) -> {PY_TYPE[self.returns]}'
        if lang == 'typescript':
            ps = ', '.join(f'{n}: {TS_TYPE[t]}' for n, t in zip(names, self.params))
            return f'export function {self.entry}({ps}): {TS_TYPE[self.returns]}'
        return self.neutral_signature()

    def examples(self) -> list[dict]:
        return [c for c in self.cases if c.get('example')]


@dataclass
class Variant:
    """One name style of a names-track library."""

    style: str
    dir: Path
    words: list[str]  # the library's words in this style

    def lib(self, lang: str) -> str | None:
        p = self.dir / f'lib.{EXT[lang]}'
        return p.read_text() if p.exists() else None

    def ref(self, lang: str) -> str | None:
        p = self.dir / f'ref.{EXT[lang]}'
        return p.read_text() if p.exists() else None


@dataclass
class Task:
    id: str
    dir: Path
    spec: Spec
    variants: dict[str, Variant] = field(default_factory=dict)

    @property
    def tier(self) -> int:
        m = TASK_ID.match(self.id)
        return int(m['tier']) if m else 0

    def description(self) -> str:
        return (self.dir / 'task.md').read_text()

    def ref(self, lang: str) -> str | None:
        p = self.dir / f'ref.{EXT[lang]}'
        return p.read_text() if p.exists() else None


@dataclass
class EditCase:
    id: str
    dir: Path
    spec: Spec

    def change(self) -> str:
        return (self.dir / 'change.md').read_text()

    def before(self, lang: str) -> str | None:
        p = self.dir / f'before.{EXT[lang]}'
        return p.read_text() if p.exists() else None

    def after(self, lang: str) -> str | None:
        p = self.dir / f'after.{EXT[lang]}'
        return p.read_text() if p.exists() else None


def load_variants(task_dir: Path) -> dict[str, Variant]:
    vdir = task_dir / 'variants'
    names = vdir / 'names.json'
    if not names.exists():
        return {}
    maps = json.loads(names.read_text())
    words = maps['words']
    out = {'honest': Variant('honest', vdir / 'honest', list(words))}
    for style in ('none', 'misleading'):
        out[style] = Variant(style, vdir / style, [maps[style][w] for w in words])
    return out


def load_tasks(only: list[str] | None = None) -> list[Task]:
    tasks = []
    for d in sorted(p for p in TASKS.iterdir() if p.is_dir()):
        if only and d.name not in only:
            continue
        tasks.append(Task(d.name, d, Spec.load(d / 'tests.json'), load_variants(d)))
    return tasks


def load_edits(only: list[str] | None = None) -> list[EditCase]:
    out = []
    for d in sorted(p for p in EDITS.iterdir() if p.is_dir()):
        if only and d.name not in only:
            continue
        out.append(EditCase(d.name, d, Spec.load(d / 'tests.json')))
    return out


def rename(text: str, mapping: dict[str, str]) -> str:
    """Apply a consistent, simultaneous renaming of whole identifiers."""
    if not mapping:
        return text
    pattern = re.compile(
        r'(?<![\w$])(' + '|'.join(re.escape(k) for k in sorted(mapping, key=len, reverse=True)) + r')(?![\w$])'
    )
    return pattern.sub(lambda m: mapping[m.group(1)], text)


# ---------------------------------------------------------------------------
# names track: "solve is one composition of library words"


def check_composition(code: str, lang: str, words: list[str], spec: Spec) -> str | None:
    """Return None if code obeys the composition rule, else a message saying why not."""
    if lang == 'python':
        return _check_composition_py(code, set(words), spec)
    if lang == 'typescript':
        return _check_composition_ts(code, set(words), spec)
    return f'composition rule not implemented for {lang}'


def _check_composition_py(code: str, words: set[str], spec: Spec) -> str | None:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f'SyntaxError: {e.msg} (line {e.lineno})'
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef) or tree.body[0].name != spec.entry:
        return f'the answer must be exactly one top-level definition, `def {spec.entry}`, and nothing else'
    fn = tree.body[0]
    a = fn.args
    if a.posonlyargs or a.vararg or a.kwonlyargs or a.kwarg or a.defaults or len(a.args) != len(spec.params):
        return f'`{spec.entry}` must take exactly {len(spec.params)} plain positional parameters'
    params = {p.arg for p in a.args}
    if len(fn.body) != 1 or not isinstance(fn.body[0], ast.Return) or fn.body[0].value is None:
        return f'the body of `{spec.entry}` must be a single `return` statement'

    def ok(node: ast.expr) -> str | None:
        if isinstance(node, ast.Name):
            return None if node.id in params else f'`{node.id}` is not a parameter'
        if isinstance(node, ast.Constant) and type(node.value) is int:
            return None
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            if node.func.id not in words:
                return f'`{node.func.id}` is not a library word'
            for arg in node.args:
                if err := ok(arg):
                    return err
            return None
        return f'`{ast.unparse(node)}` is not a call of a library word, a parameter, or an integer literal'

    return ok(fn.body[0].value)


_TS_FN = re.compile(r'^\s*export\s+function\s+(\w+)\s*\(([^)]*)\)\s*:\s*[^{]+\{(.*)\}\s*$', re.DOTALL)
_TS_TOKEN = re.compile(r'\s*(?:(?P<id>[A-Za-z_$][\w$]*)|(?P<int>\d+)|(?P<punct>[(),;]))')


def _check_composition_ts(code: str, words: set[str], spec: Spec) -> str | None:
    m = _TS_FN.match(code)
    if not m or m.group(1) != spec.entry:
        return f'the answer must be exactly one `export function {spec.entry}(...) {{ ... }}` and nothing else'
    raw_params = [p.strip() for p in m.group(2).split(',') if p.strip()]
    params = {p.split(':')[0].strip() for p in raw_params}
    if len(raw_params) != len(spec.params):
        return f'`{spec.entry}` must take exactly {len(spec.params)} parameters'
    body = m.group(3).strip()
    tokens: list[tuple[str, str]] = []
    pos = 0
    while pos < len(body):
        t = _TS_TOKEN.match(body, pos)
        if not t or t.end() == pos:
            return f'unexpected text in body: `{body[pos:].strip()[:20]}`'
        kind = t.lastgroup or ''
        tokens.append((kind, t.group(kind)))
        pos = t.end()
        while pos < len(body) and body[pos].isspace():
            pos += 1
    if not tokens or tokens[0] != ('id', 'return'):
        return f'the body of `{spec.entry}` must be a single `return` statement'
    rest = tokens[1:]
    if rest and rest[-1] == ('punct', ';'):
        rest = rest[:-1]
    for kind, text in rest:
        if kind == 'punct' and text == ';':
            return 'the body must be a single statement'
        if kind == 'id' and text not in words and text not in params:
            return f'`{text}` is not a library word or a parameter'
    return None


# ---------------------------------------------------------------------------
# hashing and git metadata


def sha256_files(paths: list[Path], root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(str(p.relative_to(root)).encode())
        h.update(b'\0')
        h.update(p.read_bytes())
        h.update(b'\0')
    return h.hexdigest()


def tree_files(root: Path) -> list[Path]:
    return [p for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts]


def git_info() -> dict:
    def git(*args: str) -> str | None:
        try:
            return subprocess.run(['git', *args], cwd=REPO, capture_output=True, text=True, check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return None

    commit = git('rev-parse', 'HEAD')
    # Results and reports are outputs, not the code that ran: earlier runs must not block the next one.
    status = git('status', '--porcelain', '--', '.', ':(exclude)bench/results', ':(exclude)bench/reports')
    return {'commit': commit, 'short': commit[:7] if commit else 'nogit', 'dirty': bool(status)}
