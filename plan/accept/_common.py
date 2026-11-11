"""Shared helpers for governor acceptance scripts (factory PLAN.md §4 contract).

Stdlib only at import time, so every script fails cleanly (JSON last line) on an empty repo.
Project code runs in subprocesses with the project's interpreter (`uv run python plan/accept/...`).
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_checks: list[dict] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    _checks.append({"name": name, "ok": bool(ok), "detail": str(detail)[:240]})
    return bool(ok)


def run(args: list[str], timeout: float = 600, env: dict | None = None, stdin: str | None = None):
    try:
        return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout, env=env, input=stdin)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, -9, "", f"timeout after {timeout}s")
    except OSError as exc:
        return subprocess.CompletedProcess(args, -1, "", f"{type(exc).__name__}: {exc}")


def py(code: str, timeout: float = 300, env: dict | None = None):
    return run([sys.executable, "-c", code], timeout=timeout, env=env)


def last_json(text: str):
    for line in reversed((text or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("{") or line.startswith("["):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None


def py_json(code: str, timeout: float = 300, env: dict | None = None):
    """Run code that prints one JSON line last. Returns (data | None, error text)."""
    r = py(code, timeout=timeout, env=env)
    data = last_json(r.stdout)
    if data is None:
        err = (r.stderr.strip().splitlines() or r.stdout.strip().splitlines() or [f"rc {r.returncode}"])[-1]
        return None, err
    return data, ""


def tail(r) -> str:
    lines = (r.stdout or "").strip().splitlines() + (r.stderr or "").strip().splitlines()
    return " | ".join(lines[-3:])[:240]


def pytest_check(target: str, required: list[str] | None = None) -> None:
    r = run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", target], timeout=900)
    summary = next((l for l in reversed(r.stdout.strip().splitlines()) if "passed" in l or "failed" in l
                    or "error" in l or "no tests" in l), tail(r))
    check(f"pytest {target}", r.returncode == 0, summary)
    if required:
        c = run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", target], timeout=300)
        names = set(re.findall(r"::(test_[A-Za-z0-9_]+)", c.stdout))
        missing = [t for t in required if t not in names]
        check("required tests present", not missing, f"missing: {missing}" if missing else f"{len(required)} found")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_yaml(path: Path):
    import yaml  # noqa: PLC0415  (installed by G1; ImportError is a failed check)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def frozen_ok() -> tuple[bool, str]:
    g = ROOT / "evaluation" / "golden"
    f = g / "FROZEN.sha256"
    if not f.is_file():
        return False, "FROZEN.sha256 missing"
    want = {}
    for line in f.read_text(encoding="utf-8").splitlines():
        if line.strip():
            h, name = line.split(maxsplit=1)
            want[name.strip().lstrip("*")] = h.strip()
    for name in ("questions.yaml", "split.json"):
        p = g / name
        if not p.is_file() or want.get(name) != sha256(p):
            return False, f"{name} does not match FROZEN.sha256"
    return True, "golden set unchanged"


def _words(t: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", t.lower())


def golden_leaks(files: list[Path], n: int = 8) -> list[str]:
    """Files that contain an n-word run from a golden question, or 60+ chars of gold SQL."""
    q = load_yaml(ROOT / "evaluation" / "golden" / "questions.yaml")
    shingles, sqls = set(), []
    for item in q.get("questions", []):
        w = _words(item.get("question", ""))
        shingles |= {" ".join(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}
        s = " ".join((item.get("gold_sql") or "").lower().split())
        if len(s) >= 60:
            sqls.append(s)
    bad = []
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        w = _words(text)
        grams = {" ".join(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}
        flat = " ".join(text.lower().split())
        if grams & shingles or any(s[:60] in flat for s in sqls):
            bad.append(str(f.relative_to(ROOT)))
    return bad


def grep(paths: list[str], pattern: str, exts=(".py", ".sql", ".yml", ".yaml", ".md", ".toml")) -> list[str]:
    rx = re.compile(pattern, re.IGNORECASE)
    hits = []
    for p in paths:
        base = ROOT / p
        files = [base] if base.is_file() else (base.rglob("*") if base.is_dir() else [])
        for f in files:
            if f.is_file() and f.suffix in exts and "target" not in f.parts and "__pycache__" not in f.parts:
                for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                    if rx.search(line):
                        hits.append(f"{f.relative_to(ROOT)}:{i}")
    return hits


def guarded(name: str, fn) -> None:
    """Run one check function; an exception becomes a failed check, never a crash."""
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        check(name, False, f"{type(exc).__name__}: {exc}")


def finish(step: str) -> None:
    ok = bool(_checks) and all(c["ok"] for c in _checks)
    fails = [c for c in _checks if not c["ok"]]
    for c in fails[:25]:
        print(f"FAIL {c['name']}: {c['detail']}")
    print(f"{len(_checks) - len(fails)}/{len(_checks)} checks passed")
    print(json.dumps({"step": step, "pass": ok, "checks": _checks}))
    sys.exit(0 if ok else 1)
