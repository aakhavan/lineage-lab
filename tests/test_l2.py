"""Offline tests for L2: compose download, work copy, dbt run summary, database workflow YAML."""
import re
from pathlib import Path

import yaml

from lineagelab import dbtrun, ingest, stack, workcopy

ROOT = Path(__file__).resolve().parents[1]
FAKE = dict(username="fake_user", password="fake-password-for-tests", host_port="db.example:1",
            om_api="http://om.example/api", jwt="not-a-real-token")


def _rendered() -> str:
    return ingest.render_database_workflow(**FAKE)


def test_missing_compose_file_is_downloaded_from_the_recorded_url(tmp_path):
    om_cfg = stack.load_versions()["stacks"]["om"]
    url = om_cfg["source"]
    assert url.startswith("https://github.com/open-metadata/OpenMetadata/releases/download/2.0.5-release/")
    calls = []

    def fake_download(u):
        calls.append(u)
        return "services:\n  x:\n    image: y:1\n"

    assert stack.ensure_compose_file(om_cfg, root=tmp_path, download=fake_download, today="2026-01-02") is True
    assert calls == [url]
    text = (tmp_path / om_cfg["compose_file"]).read_text(encoding="utf-8")
    first, rest = text.split("\n", 1)
    assert first == f"# Source: {url} (downloaded 2026-01-02, unchanged below this line)"
    assert rest == "services:\n  x:\n    image: y:1\n"
    # present -> not downloaded again; a source that is not a URL (Marquez) is never downloaded
    assert stack.ensure_compose_file(om_cfg, root=tmp_path, download=fake_download) is False
    mq = stack.load_versions()["stacks"]["marquez"]
    assert stack.ensure_compose_file(mq, root=tmp_path / "empty", download=fake_download) is False
    assert calls == [url]


def test_workcopy_skips_target_logs_and_git(tmp_path):
    src = tmp_path / "proj"
    for rel in ("dbt_project.yml", "models/a.sql", "models/logs/keep.sql", "profiles/profiles.yml",
                "target/manifest.json", "logs/dbt.log", ".git/HEAD"):
        (src / rel).parent.mkdir(parents=True, exist_ok=True)
        (src / rel).write_text("x", encoding="utf-8")
    dest = tmp_path / "work" / "olist-dbt"
    dest.mkdir(parents=True)
    (dest / "stale.sql").write_text("old", encoding="utf-8")
    n = workcopy.make_copy(src, dest)
    files = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file())
    assert files == ["dbt_project.yml", "models/a.sql", "models/logs/keep.sql", "profiles/profiles.yml"]
    assert n == 4
    assert (src / "target/manifest.json").is_file() and (src / ".git/HEAD").is_file()  # source untouched


def test_database_workflow_yaml_has_only_the_three_schemas():
    wf = yaml.safe_load(_rendered())
    cfg = wf["source"]["sourceConfig"]["config"]
    assert wf["source"]["serviceName"] == "shop_testbed"
    assert cfg["databaseFilterPattern"] == {"includes": ["^shop$"]}
    pats = cfg["schemaFilterPattern"]["includes"]
    assert sorted(pats) == ["^analytics$", "^dev_governor$", "^raw$"]
    assert "excludes" not in cfg["schemaFilterPattern"]
    names = ["raw", "dev_governor", "analytics", "public", "information_schema", "dev_governor_x", "raw2"]
    kept = [n for n in names if any(re.fullmatch(p, n) for p in pats)]
    assert kept == ["raw", "dev_governor", "analytics"]
    conn = wf["source"]["serviceConnection"]["config"]
    assert conn["database"] == "shop" and conn["ingestAllDatabases"] is False


def test_database_workflow_yaml_turns_sample_data_off():
    wf = yaml.safe_load(_rendered())
    assert wf["source"]["sourceConfig"]["config"]["type"] == "DatabaseMetadata"
    assert "processor" not in wf  # no profiler / sample-data processor
    text = _rendered().lower()
    for word in ("profiler", "orm-profiler", "autoclassification"):
        assert word not in text
    for key in ("generateSampleData", "storeSampleData", "enableAutoClassification"):
        assert re.search(rf"{key.lower()}:\s*true", text) is None


def test_rendered_yaml_in_tests_holds_no_real_credentials():
    text = _rendered()
    assert "fake-password-for-tests" in text and "not-a-real-token" in text  # only what the test passed in
    assert "governor_local" not in text and "eyJ" not in text
    jwt = re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}")
    for p in (ROOT / "tests").rglob("*"):
        if p.is_file() and p.suffix in (".py", ".json", ".yml", ".yaml"):
            assert not jwt.search(p.read_text(encoding="utf-8", errors="replace")), p.name


def test_run_results_summary_reports_failing_tests():
    rr = {"results": [
        {"unique_id": "model.olist.a", "status": "success"},
        {"unique_id": "model.olist.b", "status": "error"},
        {"unique_id": "test.olist.t1", "status": "pass"},
        {"unique_id": "test.olist.t2", "status": "fail"},
        {"unique_id": "test.olist.t3", "status": "warn"},
        {"unique_id": "seed.olist.s", "status": "success"},
    ]}
    s = dbtrun.summarise_run_results(rr)
    assert (s["models"], s["models_ok"], s["models_error"]) == (2, 1, 1)
    assert (s["tests_passed"], s["tests_failed"], s["tests_warned"]) == (1, 1, 1)
    assert s["failing_tests"] == ["test.olist.t2"]


def test_dbt_command_is_isolated_and_targets_dev():
    cmd = dbtrun.dbt_command(stack.load_versions(), "build")
    assert cmd[:2] == ["uvx", "--from"] and cmd[2].startswith("dbt-core==1.12.")
    assert cmd[cmd.index("--target") + 1] == "dev" and "prod" not in cmd
    assert Path(cmd[cmd.index("--profiles-dir") + 1]).parts[-3:] == ("work", "olist-dbt", "profiles")
