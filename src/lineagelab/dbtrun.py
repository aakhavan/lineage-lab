"""Run dbt on the work copy (work/olist-dbt/), target dev only.

    python -m lineagelab.dbtrun build

Runs `dbt build` then `dbt docs generate` with the project's own profiles/ dir, in an isolated uv tool
environment (`uvx --from dbt-core==<pin> --with dbt-postgres==<pin>`, pins in stack/versions.yaml), never as a
dependency of this package. dbt's own logs and the command output go to logs/. `dbt docs generate` rewrites
target/run_results.json, so the build's run_results.json is put back afterwards (L3 reads its test results).
Prints one JSON line: models, tests passed / failed, and which artifacts are present. A failing test is
reported in the line and makes the exit code 1; it is never hidden.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from lineagelab.stack import load_versions

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "work" / "olist-dbt"
LOGS = ROOT / "logs"
ARTIFACTS = ("manifest.json", "catalog.json", "run_results.json")
TARGET = "dev"   # never prod


def dbt_command(versions: dict, *args: str) -> list[str]:
    t = versions["tools"]
    return ["uvx", "--from", f"dbt-core=={t['dbt_core']}", "--with", f"dbt-postgres=={t['dbt_postgres']}",
            "dbt", *args, "--project-dir", str(PROJECT), "--profiles-dir", str(PROJECT / "profiles"),
            "--target", TARGET, "--log-path", str(LOGS / "dbt")]


def summarise_run_results(rr: dict) -> dict:
    """run_results.json of `dbt build` -> counts (pure; tested offline)."""
    models = {"ok": 0, "error": 0, "skipped": 0}
    tests = {"passed": 0, "failed": 0, "warned": 0, "skipped": 0}
    failing: list[str] = []
    for r in rr.get("results") or []:
        uid, st = r.get("unique_id", ""), r.get("status")
        if uid.startswith("model."):
            models["ok" if st == "success" else "skipped" if st == "skipped" else "error"] += 1
        elif uid.startswith(("test.", "unit_test.")):
            key = {"pass": "passed", "warn": "warned", "skipped": "skipped"}.get(st, "failed")
            tests[key] += 1
            if key == "failed":
                failing.append(uid)
    return {"models": sum(models.values()), "models_ok": models["ok"], "models_error": models["error"],
            "models_skipped": models["skipped"], "tests_passed": tests["passed"], "tests_failed": tests["failed"],
            "tests_warned": tests["warned"], "tests_skipped": tests["skipped"], "failing_tests": sorted(failing)}


def _run(cmd: list[str], log_name: str) -> int:
    LOGS.mkdir(exist_ok=True)
    env = {**os.environ, "DBT_SEND_ANONYMOUS_USAGE_STATS": "false", "DO_NOT_TRACK": "1"}
    with (LOGS / log_name).open("w", encoding="utf-8") as fh:
        fh.write("$ " + " ".join(cmd) + "\n")
        fh.flush()
        return subprocess.run(cmd, cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT, env=env, timeout=3600).returncode


def build() -> dict:
    if not (PROJECT / "dbt_project.yml").is_file():
        raise SystemExit("no work copy: run `python -m lineagelab.workcopy` first")
    versions = load_versions()
    target = PROJECT / "target"
    rc_build = _run(dbt_command(versions, "build"), "dbt_build.log")
    rr_path = target / "run_results.json"
    summary = (summarise_run_results(json.loads(rr_path.read_text(encoding="utf-8")))
               if rr_path.is_file() else {"models": 0, "tests_passed": 0, "tests_failed": 0})
    kept = target / "run_results.build.json"
    if rr_path.is_file():
        shutil.copyfile(rr_path, kept)
    rc_docs = _run(dbt_command(versions, "docs", "generate"), "dbt_docs_generate.log")
    if kept.is_file():
        shutil.copyfile(kept, rr_path)   # target/run_results.json = the build's results
        kept.unlink()
    return {"target": TARGET, **summary, "dbt_build_rc": rc_build, "dbt_docs_rc": rc_docs,
            "artifacts": {a: (target / a).is_file() for a in ARTIFACTS}, "logs": "logs/dbt_build.log"}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv != ["build"]:
        print("usage: python -m lineagelab.dbtrun build", file=sys.stderr)
        return 2
    res = build()
    print(json.dumps(res))
    ok = res["dbt_docs_rc"] == 0 and all(res["artifacts"].values()) and res.get("tests_failed", 0) == 0 \
        and res["dbt_build_rc"] == 0
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
