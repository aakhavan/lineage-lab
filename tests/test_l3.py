"""Offline tests for L3: the dbt workflow YAML."""
import yaml

from lineagelab import ingest

FAKE = dict(artifact_dir="/tmp/artifacts/", om_api="http://om.example/api", jwt="not-a-real-token")


def _wf() -> dict:
    return yaml.safe_load(ingest.render_dbt_workflow(**FAKE))


def test_dbt_workflow_yaml_points_at_the_three_artifacts():
    cfg = _wf()["source"]["sourceConfig"]["config"]
    assert cfg["type"] == "DBT"
    src = cfg["dbtConfigSource"]
    assert src == {
        "dbtConfigType": "local",
        "dbtManifestFilePath": "/tmp/artifacts/manifest.json",
        "dbtCatalogFilePath": "/tmp/artifacts/catalog.json",
        "dbtRunResultsFilePath": "/tmp/artifacts/run_results.json",
    }
    # the container copy uses the same three file names as work/olist-dbt/target
    assert sorted(ingest.DBT_ARTIFACTS.values()) == ["catalog.json", "manifest.json", "run_results.json"]


def test_dbt_workflow_yaml_names_the_service():
    wf = _wf()
    assert wf["source"]["type"] == "dbt"
    assert wf["source"]["serviceName"] == "shop_testbed"
    assert "serviceConnection" not in wf["source"]  # dbt attaches to the existing database service
    cfg = wf["source"]["sourceConfig"]["config"]
    assert cfg["databaseFilterPattern"] == {"includes": ["^shop$"]}
    assert sorted(cfg["schemaFilterPattern"]["includes"]) == ["^analytics$", "^dev_governor$", "^raw$"]
    assert wf["sink"]["type"] == "metadata-rest"
    assert "processor" not in wf
