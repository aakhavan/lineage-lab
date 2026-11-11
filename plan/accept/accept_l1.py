"""L1 acceptance: both stacks up, versions pinned, the OpenMetadata client works."""
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import ROOT, check, finish, grep, guarded, py_json, pytest_check, run  # noqa: E402

SERVICE = "shop_testbed.shop"


def status():
    r = run([sys.executable, "-m", "lineagelab.stack", "status"], timeout=120)
    for line in reversed((r.stdout or "").strip().splitlines()):
        if line.strip().startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                break
    return {}


def stacks_up():
    st = status()
    om, mq = st.get("openmetadata") or {}, st.get("marquez") or {}
    check("OpenMetadata is up", bool(om.get("up")), str(om)[:200])
    check("Marquez is up", bool(mq.get("up")), str(mq)[:200])
    return st


def no_secrets():
    hits = grep(["src", "stack", "docs", "tests", "README.md"], r"(eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}|Bearer\s+[A-Za-z0-9._-]{20,})")
    check("no token in the repo files", not hits, "; ".join(hits[:3]))


def static():
    om = ROOT / "stack/openmetadata/docker-compose.yml"
    text = om.read_text(encoding="utf-8") if om.is_file() else ""
    check("OpenMetadata compose file names its release URL", "releases/download/2.0.5-release/docker-compose-postgres.yml" in text.splitlines()[0] if text else False, "")
    check("OpenMetadata images are 2.0.5", "openmetadata/server:2.0.5" in text, "")
    mq = ROOT / "stack/marquez/docker-compose.yml"
    mtext = mq.read_text(encoding="utf-8") if mq.is_file() else ""
    check("Marquez compose file exists with pinned tags", bool(mtext) and ":latest" not in mtext, "")
    check("stack/versions.yaml exists", (ROOT / "stack/versions.yaml").is_file(), "")
    no_secrets()


def live():
    st = stacks_up()
    version = str((st.get("openmetadata") or {}).get("version") or "")
    check("OpenMetadata reports version 2.0.x", version.startswith("2.0"), version)
    url = str((st.get("marquez") or {}).get("url") or "").rstrip("/")
    try:
        with urllib.request.urlopen(url + "/api/v1/namespaces", timeout=20) as resp:
            check("Marquez API answers", resp.status == 200, str(resp.status))
    except Exception as exc:  # noqa: BLE001
        check("Marquez API answers", False, f"{type(exc).__name__}: {exc}")
    d, err = py_json("import json\nfrom lineagelab import om\nom.client()\n"
                     "print(json.dumps({'missing': om.table('shop_testbed.shop.nope.nope') is None}))")
    check("om.client() logs in and an unknown table is None", bool(d and d.get("missing")), err)


guarded("static", static)
guarded("live", live)
pytest_check("tests", required=["test_status_line_shape", "test_compose_files_name_their_projects",
                                "test_versions_file_lists_every_image_in_the_compose_files",
                                "test_table_and_upstream_reshape_api_payloads"])
finish("L1")
