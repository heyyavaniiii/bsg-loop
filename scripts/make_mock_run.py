"""Writes a MOCK results/run.json so you can preview the pipeline (triage, SOPs, dashboard CSVs) without touching ParaBank.

    python -m scripts.make_mock_run && python -m pipeline.run_pipeline --no-ai --no-jira

Mock data is for previewing only - never screenshot dashboards built from it for your CV.
"""
import base64
import json
from datetime import datetime, timezone

from framework.config import ARTIFACTS, RESULTS, ROOT

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGD4DwABBAEAX+XDSwAAAABJRU5ErkJggg==")


def _steps(slug, texts):
    d = ARTIFACTS / slug
    d.mkdir(parents=True, exist_ok=True)
    out = []
    for i, text in enumerate(texts, 1):
        p = d / f"step_{i:02d}.png"
        p.write_bytes(PNG)
        out.append({"n": i, "text": text, "screenshot": str(p.relative_to(ROOT))})
    return out


def _test(nodeid, module, outcome, **kw):
    slug = "".join(c if c.isalnum() else "_" for c in nodeid)[-120:]
    d = ARTIFACTS / slug
    d.mkdir(parents=True, exist_ok=True)
    log = d / "run.log"
    log.write_text(f"mock log for {nodeid}\n", encoding="utf-8")
    t = {"nodeid": nodeid, "slug": slug, "module": module, "scenario_type": kw.pop("scenario_type", "positive"), "outcome": outcome,
         "duration_s": 3.2, "error": "", "final_url": None, "steps": [], "failure_screenshot": None, "log": str(log.relative_to(ROOT)),
         "sop_title": None, "expected_class": None, "canary": False}
    t.update(kw)
    return t


def main():
    now = datetime.now(timezone.utc)
    tests = [
        _test("tests/test_login.py::test_login_valid_credentials", "login", "passed", sop_title="Log in to online banking",
              steps=_steps("mock_login", ["Open the online banking home page", "Enter your username and password", "Select Log In"])),
        _test("tests/test_transfer.py::test_transfer_valid_amounts_update_balances[10.55]", "transfer", "passed"),
        _test("tests/test_canaries.py::test_canary_ui_change_button_renamed[Sign In]", "canaries", "failed", canary=True, scenario_type="canary",
              expected_class="UI_CHANGE", error="playwright._impl._errors.TimeoutError: Page.click: Timeout 3000ms exceeded.\n  - waiting for locator('input[value=\"Sign In\"]')"),
        _test("tests/test_canaries.py::test_canary_spec_mismatch_balance[10.00]", "canaries", "failed", canary=True, scenario_type="canary",
              expected_class="REAL_DEFECT", error="AssertionError: expected source balance to remain 415.50 after transfer of 10.00, got 405.50"),
    ]
    run = {"run_id": now.strftime("%Y%m%dT%H%M%SZ"), "started_at": now.isoformat(), "base_url": "mock", "git_sha": "mock000", "tests": tests}
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "run.json").write_text(json.dumps(run, indent=2), encoding="utf-8")
    print("wrote results/run.json (MOCK)")


if __name__ == "__main__":
    main()
