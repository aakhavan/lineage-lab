"""Run dbt-ol on the work copy so OpenLineage events reach Marquez and a local file.

    python -m lineagelab.olrun

Runs ``dbt-ol build`` (package openlineage-dbt, artifact mode: dbt runs, then events are built from
the artifacts) with dbt-core and dbt-postgres in an isolated uv tool environment. One invocation uses
the OpenLineage client's composite transport: an HTTP transport to Marquez and a file transport that
appends each event, unedited, as one JSON line in ``artifacts/openlineage/events.ndjson``. Job namespace
is ``lineagelab``. Column lineage is on by default (compiled SQL); ``catalog.json`` is left in place
so column metadata is included. No flag turns column lineage on.

``dbt build`` overwrites ``target/``. The three L2/L3 artifacts (manifest, catalog, run_results) are
copied aside and put back afterwards so the catalogue load keeps its test results.

Prints one JSON line: events saved, jobs seen in Marquez.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx
import yaml

from lineagelab.olevents import edges, load, summary
from lineagelab.stack import load_versions

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "work" / "olist-dbt"
LOGS = ROOT / "logs"
TARGET = "dev"  # never prod
NAMESPACE = "lineagelab"
EVENTS = ROOT / "artifacts" / "openlineage" / "events.ndjson"
CONFIG = LOGS / "openlineage-dbt.yml"
BACKUP = LOGS / "l4-artifact-backup"
ARTIFACTS = ("manifest.json", "catalog.json", "run_results.json")


def dbt_ol_command(versions: dict, *args: str) -> list[str]:
    t = versions["tools"]
    return ["uvx", "--from", f"openlineage-dbt=={t['openlineage_dbt']}",
            "--with", f"dbt-core=={t['dbt_core']}", "--with", f"dbt-postgres=={t['dbt_postgres']}",
            "dbt-ol", *args, "--project-dir", str(PROJECT), "--profiles-dir", str(PROJECT / "profiles"),
            "--target", TARGET, "--log-path", str(LOGS / "dbt-ol")]


def write_transport_config(path: Path, events_file: Path, marquez_url: str, *, file: bool = True,
                           http: bool = True) -> None:
    """Composite (or single) transport. YAML, not OPENLINEAGE__ env vars: those values are lowercased."""
    transports: dict = {}
    if file:
        transports["file"] = {"type": "file", "log_file_path": events_file.as_posix(), "append": True}
    if http:
        transports["marquez"] = {"type": "http", "url": marquez_url.rstrip("/"), "endpoint": "api/v1/lineage"}
    if not transports:
        raise ValueError("transport needs a file, Marquez, or both")
    body = transports[next(iter(transports))] if len(transports) == 1 else {
        "type": "composite", "continue_on_failure": True, "transports": transports}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"transport": body}, sort_keys=False), encoding="utf-8")


def child_env(config: Path) -> dict[str, str]:
    """Drop inherited OpenLineage settings so only this run's config and namespace apply."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("OPENLINEAGE")}
    env.update({
        "OPENLINEAGE_CONFIG": str(config),
        "OPENLINEAGE_NAMESPACE": NAMESPACE,
        "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
        "DO_NOT_TRACK": "1",
    })
    return env


def _run(cmd: list[str], env: dict[str, str], log_name: str) -> int:
    LOGS.mkdir(exist_ok=True)
    with (LOGS / log_name).open("w", encoding="utf-8") as fh:
        fh.write("$ " + " ".join(cmd) + "\n")
        fh.flush()
        return subprocess.run(cmd, cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT, env=env, timeout=3600).returncode


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _backup(target: Path) -> dict[str, str]:
    BACKUP.mkdir(parents=True, exist_ok=True)
    digests = {}
    for name in ARTIFACTS:
        src = target / name
        if not src.is_file():
            raise SystemExit(f"missing {src}: run `python -m lineagelab.dbtrun build` first")
        shutil.copy2(src, BACKUP / name)
        digests[name] = _sha256(src)
    return digests


def _restore(target: Path) -> bool:
    for name in ARTIFACTS:
        shutil.copy2(BACKUP / name, target / name)
    return all(_sha256(target / name) == _sha256(BACKUP / name) for name in ARTIFACTS)


def marquez_job_count(url: str, namespace: str = NAMESPACE) -> int:
    try:
        r = httpx.get(f"{url.rstrip('/')}/api/v1/namespaces/{namespace}/jobs", params={"limit": 200}, timeout=30)
    except httpx.HTTPError:
        return 0
    if r.status_code != 200:
        return 0
    body = r.json()
    return int(body.get("totalCount", len(body.get("jobs") or [])))


def _wait_jobs(url: str, seconds: float = 20) -> int:
    deadline = time.time() + seconds
    count = 0
    while True:
        count = marquez_job_count(url)
        if count >= 5 or time.time() >= deadline:
            return count
        time.sleep(2)


def run() -> dict:
    if not (PROJECT / "dbt_project.yml").is_file():
        raise SystemExit("no work copy: run `python -m lineagelab.workcopy` first")
    versions = load_versions()
    marquez = versions["stacks"]["marquez"]["urls"]["api"]
    target = PROJECT / "target"
    before = _backup(target)
    EVENTS.parent.mkdir(parents=True, exist_ok=True)
    if EVENTS.is_file():
        EVENTS.unlink()
    write_transport_config(CONFIG, EVENTS, marquez)
    env = child_env(CONFIG)
    replay = None
    after_build: dict[str, str | None] = {}
    try:
        rc = _run(dbt_ol_command(versions, "build"), env, "olrun.log")
        after_build = {name: _sha256(target / name) if (target / name).is_file() else None for name in ARTIFACTS}
        saved = summary(load(EVENTS))["events"] if EVENTS.is_file() else 0
        jobs = _wait_jobs(marquez) if saved else marquez_job_count(marquez)
        if saved == 0 and (target / "run_results.json").is_file():
            replay = "send-events"
            rc_send = _run(dbt_ol_command(versions, "send-events"), env, "olrun-send.log")
            rc = rc or rc_send
            jobs = _wait_jobs(marquez)
        elif saved > 0 and jobs == 0:
            replay = "send-events-http"
            write_transport_config(CONFIG, EVENTS, marquez, file=False, http=True)
            rc_send = _run(dbt_ol_command(versions, "send-events"), env, "olrun-send.log")
            rc = rc or rc_send
            jobs = _wait_jobs(marquez)
        loaded = load(EVENTS) if EVENTS.is_file() else {"events": [], "blank": 0, "broken": 0}
        s = summary(loaded)
        e = edges(loaded)
    finally:
        restored = _restore(target)
    catalog_unchanged = after_build.get("catalog.json") == before["catalog.json"]
    return {
        "events_saved": s["events"],
        "jobs_in_marquez": jobs,
        "namespace": NAMESPACE,
        "event_types": s["event_types"],
        "column_lineage_outputs": s["column_lineage_outputs"],
        "table_edges": len(e["table"]),
        "column_edges": len(e["column"]),
        "blank": loaded["blank"],
        "broken": loaded["broken"],
        "dbt_ol_rc": rc,
        "replay": replay,
        "artifacts_restored": restored,
        "catalog_unchanged_by_build": catalog_unchanged,
        "events_file": "artifacts/openlineage/events.ndjson",
    }


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv:
        print("usage: python -m lineagelab.olrun", file=sys.stderr)
        return 2
    res = run()
    print(json.dumps(res))
    ok = (res["dbt_ol_rc"] == 0 and res["events_saved"] > 0 and res["jobs_in_marquez"] > 0
          and res["artifacts_restored"])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
