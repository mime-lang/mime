"""Run a candidate program against test cases, in Python, TypeScript or (later) mime.

The program never sees expected values: only the arguments go to the subprocess, and the
harness compares the results.

Sandboxes:
  bwrap  bubblewrap: new user, pid, net, ipc, uts and cgroup namespaces, so no network; a
         read-only /usr and language runtime, a writable /work holding only this run's files,
         no home directory, an empty environment. Required for model-written code.
  none   a plain subprocess. Only for code we wrote ourselves (references, mutants, mocks).
Both get the same resource limits: CPU time, file size, memory, and a wall-clock timeout.
"""

from __future__ import annotations

import functools
import json
import os
import re
import resource
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from taskset import Spec

PY_DRIVER = """\
import copy, importlib.util, json, sys

def main():
    solution, cases_path, entry, out_path = sys.argv[1:5]
    out = {}
    try:
        spec = importlib.util.spec_from_file_location('solution', solution)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        fn = getattr(mod, entry)
        with open(cases_path) as f:
            cases = json.load(f)
        results = []
        for args in cases:
            try:
                value = fn(*copy.deepcopy(args))
                json.dumps(value)
                results.append({'value': value})
            except Exception as e:
                results.append({'error': f'{type(e).__name__}: {e}'})
        out['results'] = results
    except BaseException as e:
        out['load_error'] = f'{type(e).__name__}: {e}'
    with open(out_path, 'w') as f:
        json.dump(out, f)

main()
"""

TS_DRIVER = """\
import { readFileSync, writeFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const [solutionPath, casesPath, entry, outPath] = process.argv.slice(2);
const out: Record<string, unknown> = {};
try {
  const mod: any = await import(pathToFileURL(solutionPath).href);
  const fn = mod[entry];
  if (typeof fn !== 'function') throw new Error(`no exported function ${entry}`);
  const cases = JSON.parse(readFileSync(casesPath, 'utf8'));
  out.results = cases.map((args: unknown[]) => {
    try {
      const value = fn(...structuredClone(args));
      return value === undefined ? { error: 'returned undefined' } : { value };
    } catch (e) {
      return { error: String(e) };
    }
  });
} catch (e) {
  out.load_error = String(e);
}
writeFileSync(outPath, JSON.stringify(out));
"""


@dataclass
class Result:
    # pass | compile_error | runtime_error | wrong_answer | timeout | constraint | no_code | refusal | budget
    # | unavailable
    status: str
    message: str = ''
    passed: int = 0
    total: int = 0
    failures: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == 'pass'

    def to_json(self) -> dict:
        return {
            'status': self.status,
            'message': self.message,
            'passed': self.passed,
            'total': self.total,
            'failures': self.failures,
        }


def same(a: object, b: object) -> bool:
    """Strict JSON equality: true is not 1."""
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def node_version() -> tuple[int, ...] | None:
    node = shutil.which('node')
    if not node:
        return None
    try:
        out = subprocess.run([node, '--version'], check=False, capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.match(r'v(\d+)\.(\d+)\.(\d+)', out.strip())
    return tuple(int(x) for x in m.groups()) if m else None


def runtime_versions() -> dict:
    nv = node_version()
    return {'python': sys.version.split()[0], 'node': '.'.join(map(str, nv)) if nv else None, 'mime': None}


def available(lang: str) -> str | None:
    """None if lang can run here, else the reason it can't."""
    if lang == 'python':
        return None
    if lang == 'typescript':
        nv = node_version()
        if nv is None:
            return 'node not found'
        if nv < (22, 6, 0):
            return f'node {".".join(map(str, nv))} is too old; type stripping needs 22.6+'
        return None
    if lang == 'mime':
        return 'the mime compiler does not exist yet'
    return f'unknown language {lang}'


SANDBOXES = ('bwrap', 'none')
MAX_FILE_BYTES = 16 << 20  # per file written by the program
MAX_TMPFS_BYTES = 64 << 20  # /tmp inside the sandbox
MAX_PY_ADDRESS_SPACE = 2 << 30  # Python only: V8 reserves far more virtual memory than it uses
NODE_HEAP_MB = 512


@functools.cache
def sandbox_available(name: str) -> str | None:
    """None if the sandbox can run here, else the reason it can't."""
    if name == 'none':
        return None
    if name != 'bwrap':
        return f'unknown sandbox {name!r}; choose one of {", ".join(SANDBOXES)}'
    if not shutil.which('bwrap'):
        return 'bwrap (bubblewrap) is not installed'
    probe = subprocess.run(
        [
            'bwrap',
            '--unshare-all',
            '--ro-bind',
            '/usr',
            '/usr',
            '--symlink',
            'usr/bin',
            '/bin',
            '--symlink',
            'usr/lib',
            '/lib',
            '/usr/bin/true',
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        return f'bwrap cannot create namespaces here: {probe.stderr.strip()[:200]}'
    return None


def sandbox_info(name: str) -> dict:
    info: dict = {'backend': name, 'network': 'host' if name == 'none' else 'none'}
    if name == 'bwrap':
        out = subprocess.run(['bwrap', '--version'], check=False, capture_output=True, text=True).stdout.strip()
        info['version'] = out
        info['mounts'] = 'ro /usr + runtime, rw /work (this run only), tmpfs /tmp; no home, empty env'
    info['limits'] = {
        'file_bytes': MAX_FILE_BYTES,
        'tmpfs_bytes': MAX_TMPFS_BYTES,
        'python_address_space': MAX_PY_ADDRESS_SPACE,
        'node_heap_mb': NODE_HEAP_MB,
    }
    return info


def _runtime(lang: str) -> tuple[str, list[str]]:
    """The interpreter's real path, and the directories it needs read-only."""
    if lang == 'python':
        exe = os.path.realpath(sys.executable)
        roots = {sys.base_prefix, os.path.dirname(os.path.dirname(exe))}
    else:
        exe = os.path.realpath(shutil.which('node') or 'node')
        roots = {os.path.dirname(os.path.dirname(exe))}
    return exe, sorted(r for r in roots if r and not (r == '/usr' or r.startswith('/usr/')))


def _bwrap(work: Path, lang: str, path_env: str) -> list[str]:
    args = ['bwrap', '--unshare-all', '--die-with-parent', '--new-session', '--clearenv']
    args += ['--ro-bind', '/usr', '/usr', '--proc', '/proc', '--dev', '/dev']
    for d in ('/bin', '/sbin', '/lib', '/lib32', '/lib64'):
        if os.path.islink(d):
            args += ['--symlink', os.readlink(d), d]
        elif os.path.isdir(d):
            args += ['--ro-bind', d, d]
    for f in ('/etc/ld.so.cache', '/etc/ld.so.conf', '/etc/ld.so.conf.d', '/etc/localtime'):
        args += ['--ro-bind-try', f, f]
    args += ['--size', str(MAX_TMPFS_BYTES), '--tmpfs', '/tmp']
    for root in _runtime(lang)[1]:
        args += ['--ro-bind', root, root]
    args += ['--bind', str(work), '/work', '--chdir', '/work']
    args += ['--setenv', 'PATH', path_env, '--setenv', 'HOME', '/work', '--setenv', 'LANG', 'C.UTF-8']
    return args + ['--']


def _limits(cpu_seconds: int, lang: str):
    def apply() -> None:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_FILE_BYTES, MAX_FILE_BYTES))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        if lang == 'python':
            resource.setrlimit(resource.RLIMIT_AS, (MAX_PY_ADDRESS_SPACE, MAX_PY_ADDRESS_SPACE))

    return apply


def _read_result(path: Path) -> dict | None:
    """Read the driver's output. The program may have replaced it with a symlink to a host
    file, a FIFO that would block, or garbage, so accept only a small regular JSON file."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return None
    with os.fdopen(fd, 'rb') as f:
        st = os.fstat(f.fileno())
        if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_FILE_BYTES:
            return None
        try:
            data = json.loads(f.read(MAX_FILE_BYTES))
        except (ValueError, UnicodeDecodeError):
            return None
    return data if isinstance(data, dict) else None


def run(source: str, lang: str, spec: Spec, timeout: float = 10.0, sandbox: str = 'none') -> Result:
    total = len(spec.cases)
    if reason := available(lang) or sandbox_available(sandbox):
        return Result('unavailable', reason, 0, total)
    if lang == 'python':
        try:
            compile(source, 'solution.py', 'exec')
        except SyntaxError as e:
            return Result('compile_error', f'SyntaxError: {e.msg} (line {e.lineno})', 0, total)
    with tempfile.TemporaryDirectory(prefix='mime-bench-') as tmp:
        t = Path(tmp)
        (t / 'cases.json').write_text(json.dumps([c['args'] for c in spec.cases]))
        exe, _ = _runtime(lang)
        if lang == 'python':
            (t / 'solution.py').write_text(source)
            (t / 'driver.py').write_text(PY_DRIVER)
            cmd = [exe, '-I', 'driver.py', 'solution.py', 'cases.json', spec.entry, 'out.json']
        else:
            (t / 'package.json').write_text('{"type": "module"}\n')
            (t / 'solution.ts').write_text(source)
            (t / 'driver.ts').write_text(TS_DRIVER)
            cmd = [exe, '--experimental-strip-types', '--no-warnings', f'--max-old-space-size={NODE_HEAP_MB}']
            cmd += ['driver.ts', './solution.ts', 'cases.json', spec.entry, 'out.json']
        path_env = os.path.dirname(exe) + ':/usr/bin:/bin'
        if sandbox == 'bwrap':
            cmd = _bwrap(t, lang, path_env) + cmd
            env = None
        elif sandbox == 'none':
            env = {'PATH': path_env, 'HOME': tmp, 'LANG': 'C.UTF-8'}
        else:
            raise ValueError(f'unknown sandbox {sandbox!r}')
        try:
            proc = subprocess.run(
                cmd,
                check=False,
                cwd=t,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                preexec_fn=_limits(int(timeout) + 1, lang),
            )
        except subprocess.TimeoutExpired:
            return Result('timeout', f'no result within {timeout:g}s', 0, total)
        out = _read_result(t / 'out.json')
        if out is None:
            err = (proc.stderr or proc.stdout).strip().splitlines()
            kind = 'compile_error' if any('SyntaxError' in line for line in err) else 'runtime_error'
            return Result(kind, '\n'.join(err[-5:]) or f'no valid result (exit code {proc.returncode})', 0, total)
    results = out.get('results')
    if 'load_error' not in out and (
        not isinstance(results, list) or len(results) != total or not all(isinstance(r, dict) for r in results)
    ):
        return Result('runtime_error', 'the driver output was malformed', 0, total)
    if 'load_error' in out:
        msg = out['load_error']
        kind = 'compile_error' if 'SyntaxError' in msg else 'runtime_error'
        return Result(kind, msg, 0, total)
    failures = []
    for case, got in zip(spec.cases, out['results']):
        if 'error' in got or 'value' not in got:
            failures.append({'args': case['args'], 'expected': case['expected'], 'error': str(got.get('error'))[:500]})
        elif not same(got['value'], case['expected']):
            failures.append({'args': case['args'], 'expected': case['expected'], 'actual': got['value']})
    passed = total - len(failures)
    if not failures:
        return Result('pass', f'{total} of {total} tests passed', passed, total)
    errors = [f for f in failures if 'error' in f]
    if errors:
        return Result('runtime_error', errors[0]['error'], passed, total, failures)
    return Result('wrong_answer', f'{len(failures)} of {total} tests failed', passed, total, failures)
