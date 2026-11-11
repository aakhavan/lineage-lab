"""Metadata ingestion of the governor test bed into OpenMetadata.

    python -m lineagelab.ingest database

Registers the Postgres database service `shop_testbed` (PUT, idempotent) and runs the metadata workflow for
database `shop`, schemas raw, dev_governor and analytics only. No sample data and no profiler: the workflow is
the DatabaseMetadata type only (OpenMetadata 2.x has no sample-data switch in it; sample data and profiling
are separate Profiler / AutoClassification workflows, which this lab never runs).

The workflow YAML is rendered by the pure function `render_database_workflow` and written to
work/ingest/database.yaml (git-ignored): the DSN parts (env LAB_PG_DSN, default the documented test-bed admin
DSN) and the ingestion-bot JWT (fetched at run time) are filled in only there.

Runner: `docker exec` in the ingestion container first (the `metadata` CLI matches the server; the test bed is
host.docker.internal:55432 from there), then `uvx --from openmetadata-ingestion[postgres]==<pin>`. Prints one
JSON line: runner used, exit codes, and the table count per schema read back from OpenMetadata.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

import yaml

from lineagelab import om
from lineagelab.stack import load_versions

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "work" / "ingest"
LOGS = ROOT / "logs"
SERVICE = "shop_testbed"
DATABASE = "shop"
SCHEMAS = ("raw", "dev_governor", "analytics")
DEFAULT_DSN = "postgresql://governor_admin:governor_local@localhost:55432/shop"  # documented test-bed default
CONTAINER = "openmetadata_ingestion"
CONTAINER_YAML = "/tmp/lineagelab_database.yaml"
OM_API_IN_CONTAINER = "http://openmetadata-server:8585/api"
TESTBED_FROM_CONTAINER = "host.docker.internal"


def pg_parts(dsn: str) -> dict:
    u = urlparse(dsn)
    return {"username": unquote(u.username or ""), "password": unquote(u.password or ""),
            "host": u.hostname or "localhost", "port": u.port or 5432, "database": (u.path or "/").lstrip("/")}


def connection_config(username: str, password: str, host_port: str, database: str = DATABASE) -> dict:
    return {"type": "Postgres", "scheme": "postgresql+psycopg2", "username": username,
            "authType": {"password": password}, "hostPort": host_port, "database": database,
            "ingestAllDatabases": False}


def _exact(names) -> dict:
    return {"includes": [f"^{n}$" for n in names]}


def database_workflow(*, username: str, password: str, host_port: str, om_api: str, jwt: str,
                      service: str = SERVICE, database: str = DATABASE, schemas=SCHEMAS) -> dict:
    """The metadata workflow as a dict (pure). Metadata only: no profiler processor, no sample data."""
    return {
        "source": {
            "type": "postgres",
            "serviceName": service,
            "serviceConnection": {"config": connection_config(username, password, host_port, database)},
            "sourceConfig": {"config": {
                "type": "DatabaseMetadata",
                "databaseFilterPattern": _exact([database]),
                "schemaFilterPattern": _exact(schemas),
                "includeTables": True,
                "includeViews": True,
                "includeTags": False,
                "includeOwners": False,
                "includeStoredProcedures": False,
                "markDeletedTables": True,
            }},
        },
        "sink": {"type": "metadata-rest", "config": {}},
        "workflowConfig": {
            "loggerLevel": "INFO",
            "openMetadataServerConfig": {"hostPort": om_api, "authProvider": "openmetadata",
                                         "securityConfig": {"jwtToken": jwt}},
        },
    }


def render_database_workflow(**kw) -> str:
    """The workflow YAML text (pure; tested offline with fake credentials)."""
    return yaml.safe_dump(database_workflow(**kw), sort_keys=False)


def service_request(username: str, password: str, host_port: str) -> dict:
    return {"name": SERVICE, "serviceType": "Postgres",
            "description": "governor test bed (database shop), registered by lineage-lab",
            "connection": {"config": connection_config(username, password, host_port)}}


# ---- runners -------------------------------------------------------------------------------------

def _run(cmd: list[str], log, timeout: float = 1800) -> int:
    log.write("\n$ " + " ".join(cmd) + "\n")
    log.flush()
    try:
        return subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=timeout).returncode
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.write(f"{type(exc).__name__}: {exc}\n")
        return -1


def _write(text: str) -> Path:
    WORK.mkdir(parents=True, exist_ok=True)
    path = WORK / "database.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def run_docker(pg: dict, jwt: str, log) -> int:
    host_port = f"{TESTBED_FROM_CONTAINER}:{pg['port']}"
    path = _write(render_database_workflow(username=pg["username"], password=pg["password"], host_port=host_port,
                                           om_api=OM_API_IN_CONTAINER, jwt=jwt, database=pg["database"]))
    rc = _run(["docker", "cp", str(path), f"{CONTAINER}:{CONTAINER_YAML}"], log, timeout=120)
    if rc != 0:
        return rc
    try:
        return _run(["docker", "exec", CONTAINER, "metadata", "ingest", "-c", CONTAINER_YAML], log)
    finally:  # the copy in the container holds the token: remove it
        _run(["docker", "exec", "-u", "0", CONTAINER, "rm", "-f", CONTAINER_YAML], log, timeout=60)


def run_uvx(pg: dict, jwt: str, versions: dict, log) -> int:
    host_port = f"{pg['host']}:{pg['port']}"
    path = _write(render_database_workflow(username=pg["username"], password=pg["password"], host_port=host_port,
                                           om_api=versions["stacks"]["om"]["urls"]["api"], jwt=jwt,
                                           database=pg["database"]))
    pin = versions["tools"]["openmetadata_ingestion"]
    return _run(["uvx", "--python", "3.11", "--from", f"openmetadata-ingestion[postgres]{pin}",
                 "metadata", "ingest", "-c", str(path)], log)


def table_counts() -> dict:
    out = {}
    for s in SCHEMAS:
        d = om.get("/v1/tables", databaseSchema=f"{SERVICE}.{DATABASE}.{s}", limit=1)
        out[s] = int((d.get("paging") or {}).get("total", 0))
    return out


def database(runner: str = "auto") -> dict:
    versions = load_versions()
    pg = pg_parts(os.environ.get("LAB_PG_DSN") or DEFAULT_DSN)
    if pg["database"] != DATABASE:
        raise SystemExit(f"LAB_PG_DSN must point at database {DATABASE}")
    om.client()
    jwt = om.bot_token()
    in_container = runner in ("auto", "docker")
    host_port = f"{TESTBED_FROM_CONTAINER if in_container else pg['host']}:{pg['port']}"
    om.put("/v1/services/databaseServices", service_request(pg["username"], pg["password"], host_port))
    LOGS.mkdir(exist_ok=True)
    rcs: dict[str, int] = {}
    used = None
    with (LOGS / "ingest_database.log").open("w", encoding="utf-8") as log:
        if runner in ("auto", "docker"):
            rcs["docker_exec"] = run_docker(pg, jwt, log)
            used = "docker_exec" if rcs["docker_exec"] == 0 else None
        if used is None and runner in ("auto", "uvx"):
            if in_container:  # the service must reach the test bed from the host now
                om.put("/v1/services/databaseServices",
                       service_request(pg["username"], pg["password"], f"{pg['host']}:{pg['port']}"))
            rcs["uvx"] = run_uvx(pg, jwt, versions, log)
            used = "uvx" if rcs["uvx"] == 0 else None
    return {"service": SERVICE, "runner": used, "rc": rcs, "tables": table_counts(),
            "workflow": "work/ingest/database.yaml", "log": "logs/ingest_database.log"}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] != "database" or len(argv) > 2:
        print("usage: python -m lineagelab.ingest database [auto|docker|uvx]", file=sys.stderr)
        return 2
    res = database(argv[1] if len(argv) == 2 else "auto")
    print(json.dumps(res))
    return 0 if res["runner"] else 1


if __name__ == "__main__":
    sys.exit(main())
