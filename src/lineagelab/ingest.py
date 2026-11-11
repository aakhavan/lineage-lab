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

    python -m lineagelab.ingest dbt          (L3)
    python -m lineagelab.ingest dbt-state    (read back only)

Renders the dbt workflow for service `shop_testbed` from manifest.json, catalog.json and run_results.json in
work/olist-dbt/target/ (pure `render_dbt_workflow`, written to work/ingest/dbt.yaml), copies the artifacts and the
YAML into the ingestion container, validates the sourceConfig against the container's own DbtPipeline model,
runs `metadata ingest`, and removes the copies. Prints one JSON line with exit codes and what dbt left on the
dev_governor tables (descriptions, tests, upstream edges, and a fingerprint to compare two runs).
"""
from __future__ import annotations

import hashlib
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


# ---- dbt (L3) ------------------------------------------------------------------------------------

DBT_TARGET = ROOT / "work" / "olist-dbt" / "target"
DBT_ARTIFACTS = {"manifest": "manifest.json", "catalog": "catalog.json", "run_results": "run_results.json"}
CONTAINER_DBT_DIR = "/tmp/lineagelab_dbt"
CONTAINER_DBT_YAML = "/tmp/lineagelab_dbt.yaml"
DBT_SCHEMA = "dev_governor"

# Validates the rendered sourceConfig against the *installed* version's own pydantic model (generated from
# dbtPipeline.json) inside the ingestion container. Reads the config on stdin; prints the model's fields.
_VALIDATE = (
    "import json,sys\n"
    "from metadata.generated.schema.metadataIngestion.dbtPipeline import DbtPipeline\n"
    "from metadata.generated.schema.metadataIngestion.dbtconfig.dbtLocalConfig import DbtLocalConfig\n"
    "cfg=json.load(sys.stdin)\n"
    "m=DbtPipeline.model_validate(cfg)\n"
    "print('DbtPipeline extra=', DbtPipeline.model_config.get('extra'), 'fields=', sorted(DbtPipeline.model_fields))\n"
    "print('DbtLocalConfig fields=', sorted(DbtLocalConfig.model_fields))\n"
    "print('config source type:', type(m.dbtConfigSource).__name__)\n"
)


def dbt_artifact_paths(artifact_dir: str) -> dict:
    """The three artifact paths as the runner sees them (posix: the runner is the Linux container)."""
    d = artifact_dir.rstrip("/")
    return {k: f"{d}/{name}" for k, name in DBT_ARTIFACTS.items()}


def dbt_source_config(artifact_dir: str, database: str = DATABASE, schemas=SCHEMAS) -> dict:
    """sourceConfig.config of the dbt workflow (shape of dbtPipeline.json / dbtLocalConfig.json, 2.0.5)."""
    p = dbt_artifact_paths(artifact_dir)
    return {
        "type": "DBT",
        "dbtConfigSource": {
            "dbtConfigType": "local",
            "dbtManifestFilePath": p["manifest"],
            "dbtCatalogFilePath": p["catalog"],
            "dbtRunResultsFilePath": p["run_results"],
        },
        "dbtUpdateDescriptions": True,  # dbt is the source of truth for model/column descriptions
        "includeTags": True,
        "databaseFilterPattern": _exact([database]),
        "schemaFilterPattern": _exact(schemas),  # raw is needed: dbt sources are the lineage roots
    }


def dbt_workflow(*, artifact_dir: str, om_api: str, jwt: str, service: str = SERVICE) -> dict:
    """The dbt workflow as a dict (pure). No serviceConnection: dbt attaches to the existing service."""
    return {
        "source": {"type": "dbt", "serviceName": service,
                   "sourceConfig": {"config": dbt_source_config(artifact_dir)}},
        "sink": {"type": "metadata-rest", "config": {}},
        "workflowConfig": {
            "loggerLevel": "INFO",
            "openMetadataServerConfig": {"hostPort": om_api, "authProvider": "openmetadata",
                                         "securityConfig": {"jwtToken": jwt}},
        },
    }


def render_dbt_workflow(**kw) -> str:
    """The dbt workflow YAML text (pure; tested offline with a fake token)."""
    return yaml.safe_dump(dbt_workflow(**kw), sort_keys=False)


def _validate_in_container(source_config: dict, log) -> int:
    cmd = ["docker", "exec", "-i", CONTAINER, "python", "-c", _VALIDATE]
    log.write("\n$ docker exec -i " + CONTAINER + " python -c <validate DbtPipeline>\n")
    log.flush()
    try:
        return subprocess.run(cmd, cwd=ROOT, input=json.dumps(source_config).encode(), stdout=log,
                              stderr=subprocess.STDOUT, timeout=300).returncode
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.write(f"{type(exc).__name__}: {exc}\n")
        return -1


def run_dbt_docker(jwt: str, log) -> dict:
    """Copy the artifacts and the YAML into the container, validate, ingest, then remove both copies."""
    rcs: dict[str, int] = {}
    WORK.mkdir(parents=True, exist_ok=True)
    path = WORK / "dbt.yaml"
    path.write_text(render_dbt_workflow(artifact_dir=CONTAINER_DBT_DIR, om_api=OM_API_IN_CONTAINER, jwt=jwt),
                    encoding="utf-8")
    try:
        rcs["copy"] = _run(["docker", "exec", CONTAINER, "mkdir", "-p", CONTAINER_DBT_DIR], log, timeout=60)
        for name in DBT_ARTIFACTS.values():
            if rcs["copy"] == 0:
                rcs["copy"] = _run(["docker", "cp", str(DBT_TARGET / name), f"{CONTAINER}:{CONTAINER_DBT_DIR}/{name}"],
                                   log, timeout=300)
        if rcs["copy"] == 0:
            rcs["copy"] = _run(["docker", "cp", str(path), f"{CONTAINER}:{CONTAINER_DBT_YAML}"], log, timeout=120)
        if rcs["copy"] != 0:
            return rcs
        rcs["validate"] = _validate_in_container(dbt_source_config(CONTAINER_DBT_DIR), log)
        if rcs["validate"] != 0:
            return rcs
        rcs["ingest"] = _run(["docker", "exec", CONTAINER, "metadata", "ingest", "-c", CONTAINER_DBT_YAML], log)
        return rcs
    finally:  # the YAML holds the token: remove it, and the artifact copies with it
        _run(["docker", "exec", "-u", "0", CONTAINER, "rm", "-rf", CONTAINER_DBT_YAML, CONTAINER_DBT_DIR],
             log, timeout=60)


def dbt_state(schema: str = DBT_SCHEMA) -> dict:
    """What dbt put on the tables of one schema, read back from OpenMetadata (for the idempotence check)."""
    fqn_schema = f"{SERVICE}.{DATABASE}.{schema}"
    names = sorted(t["name"] for t in om.get("/v1/tables", databaseSchema=fqn_schema, limit=1000).get("data", []))
    per: dict[str, list] = {}
    for n in names:
        fqn = f"{fqn_schema}.{n}"
        t = om.table(fqn) or {}
        u = om.upstream(fqn, 1)
        per[n] = [bool((t.get("description") or "").strip()),
                  sum(1 for c in t.get("columns", []) if (c.get("description") or "").strip()),
                  int(t.get("tests") or 0), len(u["edges"]), len(u["column_edges"])]
    tot = lambda i: sum(v[i] for v in per.values())  # noqa: E731
    return {"tables": len(per), "with_description": tot(0), "column_descriptions": tot(1), "tests": tot(2),
            "upstream_edges": tot(3), "column_edges": tot(4),
            "fingerprint": hashlib.sha256(json.dumps(per, sort_keys=True).encode()).hexdigest()[:12]}


def dbt(runner: str = "docker") -> dict:
    missing = [n for n in DBT_ARTIFACTS.values() if not (DBT_TARGET / n).is_file()]
    if missing:
        raise SystemExit(f"missing dbt artifacts in work/olist-dbt/target: {missing} (run lineagelab.dbtrun build)")
    if runner != "docker":  # the uvx pin has no dbt extra; the container is the verified runner (L2)
        raise SystemExit("only the docker runner is supported for dbt")
    om.client()
    jwt = om.bot_token()
    LOGS.mkdir(exist_ok=True)
    with (LOGS / "ingest_dbt.log").open("w", encoding="utf-8") as log:
        rcs = run_dbt_docker(jwt, log)
    ok = rcs.get("ingest") == 0
    return {"service": SERVICE, "runner": "docker_exec" if ok else None, "rc": rcs,
            "state": dbt_state() if ok else None, "workflow": "work/ingest/dbt.yaml", "log": "logs/ingest_dbt.log"}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    usage = "usage: python -m lineagelab.ingest database [auto|docker|uvx] | dbt | dbt-state"
    if not argv or len(argv) > 2 or argv[0] not in ("database", "dbt", "dbt-state"):
        print(usage, file=sys.stderr)
        return 2
    if argv[0] == "dbt-state":
        om.client()
        print(json.dumps(dbt_state()))
        return 0
    if argv[0] == "dbt":
        res = dbt(argv[1] if len(argv) == 2 else "docker")
    else:
        res = database(argv[1] if len(argv) == 2 else "auto")
    print(json.dumps(res))
    return 0 if res["runner"] else 1


if __name__ == "__main__":
    sys.exit(main())
