"""Start, stop and check the two lab stacks (OpenMetadata, Marquez).

    python -m lineagelab.stack up|down|status [--only om|marquez]

`up` starts the compose project(s) and waits until the HTTP endpoints answer; `down` stops them and keeps
volumes; `status` prints one JSON line. Ports, URLs and compose settings come from stack/versions.yaml.
Only the compose projects named there are touched (always passed explicitly with -p).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "stack" / "versions.yaml"
STACKS = ("om", "marquez")


def load_versions(path: Path = VERSIONS) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def compose_args(cfg: dict) -> list[str]:
    return ["docker", "compose", "-p", cfg["compose_project"], "-f", str(ROOT / cfg["compose_file"])]


def _get(url: str, timeout: float = 5.0) -> httpx.Response | None:
    try:
        return httpx.get(url, timeout=timeout)
    except httpx.HTTPError:
        return None


def probe_om(cfg: dict) -> dict:
    r = _get(cfg["urls"]["api"].rstrip("/") + "/v1/system/version")
    version = None
    if r is not None and r.status_code == 200:
        try:
            version = r.json().get("version")
        except ValueError:
            version = None
    return {"up": version is not None, "version": version, "url": cfg["urls"]["ui"]}


def probe_marquez(cfg: dict) -> dict:
    r = _get(cfg["urls"]["api"].rstrip("/") + "/api/v1/namespaces")
    return {"up": r is not None and r.status_code == 200, "url": cfg["urls"]["api"]}


def status_line(om: dict, marquez: dict) -> dict:
    """The status JSON shape the spec fixes (pure; tested offline)."""
    return {
        "openmetadata": {"up": bool(om.get("up")), "version": om.get("version"), "url": str(om.get("url", ""))},
        "marquez": {"up": bool(marquez.get("up")), "url": str(marquez.get("url", ""))},
    }


def status(versions: dict) -> dict:
    s = versions["stacks"]
    return status_line(probe_om(s["om"]), probe_marquez(s["marquez"]))


PROBES = {"om": probe_om, "marquez": probe_marquez}


def _compose(cfg: dict, *args: str, timeout: float) -> int:
    log = ROOT / "logs" / f"stack_{cfg['compose_project']}.log"
    log.parent.mkdir(exist_ok=True)
    with log.open("a", encoding="utf-8") as fh:
        fh.write(f"\n$ {' '.join(compose_args(cfg) + list(args))}\n")
        fh.flush()
        r = subprocess.run(compose_args(cfg) + list(args), cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT,
                           timeout=timeout)
    return r.returncode


def up(versions: dict, which: list[str], wait_s: float = 1800) -> dict:
    s = versions["stacks"]
    rcs = {k: _compose(s[k], "up", "-d", timeout=wait_s) for k in which}
    deadline = time.monotonic() + wait_s
    pending = [k for k in which if rcs[k] == 0]
    while pending and time.monotonic() < deadline:
        pending = [k for k in pending if not PROBES[k](s[k])["up"]]
        if pending:
            time.sleep(5)
    return {"compose_rc": rcs, "not_healthy": pending}


def down(versions: dict, which: list[str]) -> dict:
    s = versions["stacks"]
    return {"compose_rc": {k: _compose(s[k], "down", timeout=600) for k in which}}  # no -v: volumes kept


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m lineagelab.stack")
    ap.add_argument("command", choices=["up", "down", "status"])
    ap.add_argument("--only", choices=list(STACKS))
    a = ap.parse_args(argv)
    versions = load_versions()
    which = [a.only] if a.only else list(STACKS)
    rc = 0
    if a.command == "up":
        res = up(versions, which)
        rc = 0 if not res["not_healthy"] and not any(res["compose_rc"].values()) else 1
        print(json.dumps({"up": res}), file=sys.stderr)
    elif a.command == "down":
        res = down(versions, which)
        rc = 1 if any(res["compose_rc"].values()) else 0
        print(json.dumps({"down": res}), file=sys.stderr)
    print(json.dumps(status(versions)))
    return rc


if __name__ == "__main__":
    sys.exit(main())
