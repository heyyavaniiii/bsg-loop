"""Offline unit tests for the pipeline logic (no browser, no network, no API keys).  Run: pytest tests_unit"""
import csv
import json

import pytest

from pipeline import dashboard_feed, sop_generator, triage
from pipeline.jira_client import doc, fingerprint, ordered, para


def test_redact_removes_pii_shapes():
    text = "user ravi.k@example.com PAN ABCDE1234F card 4111 1111 1111 1111 password: Hunter2!"
    out = triage.redact(text)
    for secret in ("ravi.k@example.com", "ABCDE1234F", "4111 1111 1111 1111", "Hunter2!"):
        assert secret not in out


@pytest.mark.parametrize(
    "error, expected",
    [
        ("net::ERR_CONNECTION_REFUSED at goto", "ENVIRONMENT"),
        ("AssertionError: expected balance 10 got 5", "REAL_DEFECT"),
        ("Page.click: Timeout 3000ms exceeded. waiting for locator('input')", "UI_CHANGE"),
        ("The username and password could not be verified", "DATA_ISSUE"),
    ],
)
def test_heuristic_classes(error, expected):
    t = {"nodeid": "tests/test_x.py::t", "module": "transfer", "error": error, "steps": []}
    assert triage.heuristic(t)["classification"] == expected


def test_money_defect_is_critical():
    t = {"nodeid": "tests/test_transfer.py::t", "module": "transfer", "error": "AssertionError: expected 1 got 2", "steps": []}
    assert triage.heuristic(t)["severity"] == "Critical"


def test_normalise_rejects_bad_model_output():
    t = {"nodeid": "tests/test_login.py::t", "module": "login", "error": "x", "steps": []}
    out = triage._normalise({"classification": "banana", "severity": "Apocalyptic", "confidence": "high"}, t)
    assert out["classification"] in triage.CLASSES and out["severity"] in triage.SEVERITIES and 0 <= out["confidence"] <= 1


def test_parse_json_tolerates_prose_around_json():
    assert triage._parse_json('Sure!\n{"a": 1}\nDone') == {"a": 1}


def test_fingerprint_is_stable_and_label_safe():
    assert fingerprint("a::b") == fingerprint("a::b") != fingerprint("a::c")
    assert " " not in fingerprint("a b")


def test_adf_shapes():
    d = doc([para("hi"), ordered(["one", "two"])])
    assert d["type"] == "doc" and d["version"] == 1 and len(d["content"][1]["content"]) == 2


def _run(outcome):
    return {
        "run_id": "20261023T000000Z", "started_at": "2026-10-23T00:00:00+00:00", "git_sha": "abc1234",
        "tests": [{"nodeid": "tests/test_login.py::test_login_valid_credentials", "slug": "s", "module": "login", "scenario_type": "positive",
                   "outcome": outcome, "duration_s": 1.0, "sop_title": "Log in to online banking", "expected_class": None,
                   "steps": [{"n": 1, "text": "Open the home page", "screenshot": "none.png"}, {"n": 2, "text": "Select Log In", "screenshot": "none.png"}]}],
    }


def test_sop_lifecycle_generate_then_flag_drift(tmp_path, monkeypatch):
    monkeypatch.setattr(sop_generator, "SOP_DIR", tmp_path)
    report = sop_generator.generate(_run("passed"), use_ai=False)
    assert report[0]["action"] == "regenerated"
    md = (tmp_path / "log-in-to-online-banking.md").read_text(encoding="utf-8")
    assert "Verified by passing automated run" in md and "### Step 2" in md
    assert sop_generator.generate(_run("passed"), use_ai=False)[0]["action"] == "refreshed"
    assert sop_generator.generate(_run("failed"), use_ai=False)[0]["action"] == "flagged_drift"
    assert "Possible drift" in (tmp_path / "log-in-to-online-banking.md").read_text(encoding="utf-8")
    assert json.loads((tmp_path / "manifest.json").read_text())["log-in-to-online-banking"]["status"] == "drift_suspected"


def test_history_is_idempotent_per_run(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_feed, "DASHBOARD", tmp_path)
    run = _run("passed")
    assert dashboard_feed.append_history(run, {}, {}) is True
    assert dashboard_feed.append_history(run, {}, {}) is False
    with open(tmp_path / "test_results.csv", newline="") as fh:
        assert len(list(csv.DictReader(fh))) == 1


def test_eval_scores_against_expected_class(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_feed, "DASHBOARD", tmp_path)
    run = _run("failed")
    run["tests"][0]["expected_class"] = "UI_CHANGE"
    tri = {run["tests"][0]["nodeid"]: {"classification": "UI_CHANGE", "confidence": 0.9, "source": "claude"}}
    assert dashboard_feed.append_eval(run, tri) == (1, 1)
