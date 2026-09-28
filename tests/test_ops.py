"""The operations files in ``ops/`` (ADR 0011, ``ops/README.md``).

They are applied to the live project by hand, so these checks tie them to the code instead: the
runbook's deploy step keeps the one-instance ceiling the dashboard draws, the dashboard shows
no log entries, and the Monitoring JSON parses and targets this service.
"""

from __future__ import annotations

import json
import re
import subprocess

from tests.conftest import REPO

OPS = REPO / "ops"


def test_the_runbook_deploys_at_most_the_instances_the_dashboard_draws():
    runbook = (REPO / "docs" / "deploy-runbook.md").read_text()
    assert set(re.findall(r"--max-instances=(\d+)", runbook)) == {"1"}
    assert set(re.findall(r"--max=(\d+)", runbook)) == {"1"}
    dashboard = json.loads((OPS / "monitoring" / "dashboard.json").read_text())
    thresholds = {
        tile["widget"]["title"]: tile["widget"]["xyChart"].get("thresholds", [])
        for tile in dashboard["mosaicLayout"]["tiles"]
        if "xyChart" in tile["widget"]
    }
    assert [t["value"] for t in thresholds["Instances by state (max 1)"]] == [1]


def test_the_monitoring_json_targets_this_service():
    files = sorted((OPS / "monitoring").glob("*.json"))
    assert {f.name for f in files} == {
        "dashboard.json",
        "policy-uptime.json",
        "uptime-health.json",
    }
    for path in files:
        document = json.loads(path.read_text())
        assert document["displayName"].startswith("br-elections-mcp"), path.name
        for query in re.findall(r"run_googleapis_com:[a-z_]+\{[^}]*\}", path.read_text()):
            assert 'service_name=\\"br-elections-mcp\\"' in query, (path.name, query)
    uptime = json.loads((OPS / "monitoring" / "uptime-health.json").read_text())
    assert uptime["httpCheck"]["path"] == "/health"


def test_the_dashboard_thresholds_use_only_fields_the_api_accepts():
    # The Dashboards API rejects `color` and `direction` on an XyChart threshold (400 on
    # 2026-09-28), and `validateOnly` is the only other way to learn it before an apply.
    dashboard = json.loads((OPS / "monitoring" / "dashboard.json").read_text())
    for tile in dashboard["mosaicLayout"]["tiles"]:
        for threshold in tile["widget"].get("xyChart", {}).get("thresholds", []):
            assert set(threshold) <= {"label", "value", "targetAxis"}, tile["widget"]["title"]


def test_the_dashboard_shows_no_log_entries():
    # The request and access logs keep the voter's lat/lon or zone/section in the URL for
    # 30 days (ADR 0011: the exclusion tried on 2026-09-28 did not drop them), so a logs
    # panel would put them on screen.
    dashboard = json.loads((OPS / "monitoring" / "dashboard.json").read_text())
    assert all("logsPanel" not in tile["widget"] for tile in dashboard["mosaicLayout"]["tiles"])


def test_the_apply_script_parses():
    subprocess.run(["bash", "-n", str(OPS / "monitoring" / "apply.sh")], check=True)
