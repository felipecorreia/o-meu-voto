"""The refresh trigger chain: Cloud Scheduler -> Workflows refresh-dispatch -> refresh.yml.

The live jobs and workflow are deployed by hand (docs/deploy-runbook.md, step G); these
tests pin the two repository files that chain depends on, so an edit to one cannot silently
break the other.
"""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
REFRESH_WORKFLOW = ROOT / ".github" / "workflows" / "refresh.yml"
DISPATCH_WORKFLOW = ROOT / "ops" / "refresh-dispatch" / "workflow.yaml"


@pytest.fixture(scope="module")
def dispatch_steps() -> dict:
    document = yaml.safe_load(DISPATCH_WORKFLOW.read_text(encoding="utf-8"))
    return {name: body for step in document["main"]["steps"] for name, body in step.items()}


def test_refresh_workflow_runs_only_on_dispatch():
    document = yaml.safe_load(REFRESH_WORKFLOW.read_text(encoding="utf-8"))
    # PyYAML reads the bare key `on` as the boolean True.
    triggers = document[True]
    assert "workflow_dispatch" in triggers
    assert "schedule" not in triggers


def test_dispatch_targets_refresh_workflow_on_main(dispatch_steps):
    call = dispatch_steps["dispatch"]["try"]
    assert call["call"] == "http.post"
    url = call["args"]["url"]
    assert url.startswith("https://api.github.com/repos/")
    assert url.endswith(f"/actions/workflows/{REFRESH_WORKFLOW.name}/dispatches")
    assert call["args"]["body"] == {"ref": "main", "return_run_details": True}
    assert dispatch_steps["dispatch"]["retry"] == "${http.default_retry_non_idempotent}"


def test_token_comes_from_secret_manager_only(dispatch_steps):
    read = dispatch_steps["read_token"]
    assert read["call"] == "googleapis.secretmanager.v1.projects.secrets.versions.accessString"
    assert read["args"] == {"secret_id": "github-refresh-dispatch-token", "version": "latest"}
    headers = dispatch_steps["dispatch"]["try"]["args"]["headers"]
    assert headers["Authorization"] == '${"Bearer " + ' + read["result"] + "}"
    source = DISPATCH_WORKFLOW.read_text(encoding="utf-8")
    assert not re.search(r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}", source)
