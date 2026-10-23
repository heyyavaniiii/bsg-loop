"""Shared fixtures + the results hook that feeds the whole pipeline.

Every test run writes results/run.json containing, per test: outcome, error, step list (with screenshots),
failure screenshot and a plain-text log. The pipeline (triage -> Jira -> SOPs -> dashboard feed) reads only that file.
"""
import datetime as dt
import json
import os
import re
import zlib

import pytest

from framework import data
from framework import parabank as pb
from framework.config import ARTIFACTS, BASE_URL, RESULTS, ROOT

_RESULTS: list[dict] = []
_STARTED = dt.datetime.now(dt.timezone.utc)


def slugify(nodeid: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", nodeid).strip("_")[-120:]


class Recorder:
    """Records numbered, screenshotted steps (these become SOP steps) and browser-side events (these become the bug log)."""

    def __init__(self, page, nodeid: str):
        self.page = page
        self.slug = slugify(nodeid)
        self.dir = ARTIFACTS / self.slug
        self.dir.mkdir(parents=True, exist_ok=True)
        self.steps: list[dict] = []
        self.events: list[str] = []
        page.on("console", lambda m: self.events.append(f"console.{m.type}: {m.text}") if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: self.events.append(f"pageerror: {e}"))
        page.on("requestfailed", lambda r: self.events.append(f"requestfailed: {r.method} {r.url} {r.failure}"))
        page.on("response", lambda r: self.events.append(f"http {r.status}: {r.request.method} {r.url}") if r.status >= 400 else None)

    def step(self, text: str):
        n = len(self.steps) + 1
        path = self.dir / f"step_{n:02d}.png"
        self.page.screenshot(path=str(path))
        self.steps.append({"n": n, "text": text, "screenshot": str(path.relative_to(ROOT))})


# ---------------- fixtures ----------------
@pytest.fixture
def rec(page, request):
    return Recorder(page, request.node.nodeid)


def _offset(request) -> int:
    return zlib.crc32(request.node.nodeid.encode()) % 10000


@pytest.fixture
def customer(request):
    return data.customer(_offset(request))


@pytest.fixture
def banked(page, rec, customer):
    """A freshly registered, logged-in synthetic customer (registration is NOT recorded as SOP steps)."""
    pb.register(page, customer)
    pb.expect_registered(page)
    return customer


@pytest.fixture
def two_accounts(page, banked):
    first = next(iter(pb.balances(page)))
    second = pb.open_account(page, "SAVINGS")
    return first, second


# ---------------- collection ----------------
def pytest_collection_modifyitems(config, items):
    if os.getenv("RUN_CANARIES") == "1":
        return
    skip = pytest.mark.skip(reason="canary tests need RUN_CANARIES=1")
    for item in items:
        if item.get_closest_marker("canary"):
            item.add_marker(skip)


# ---------------- results hook ----------------
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    is_call = rep.when == "call"
    is_setup_error = rep.when == "setup" and rep.failed
    if not (is_call or is_setup_error) or rep.skipped:
        return

    status = "error" if is_setup_error else rep.outcome
    rec = item.funcargs.get("rec")
    page = item.funcargs.get("page")
    slug = slugify(item.nodeid)
    folder = rec.dir if rec else ARTIFACTS / slug
    folder.mkdir(parents=True, exist_ok=True)

    failure_shot = None
    final_url = None
    if page is not None:
        try:
            final_url = page.url
            if status != "passed":
                p = folder / "failure.png"
                page.screenshot(path=str(p))
                failure_shot = str(p.relative_to(ROOT))
        except Exception:
            pass

    error = rep.longreprtext[-4000:] if status != "passed" else ""
    log_path = folder / "run.log"
    lines = [f"test: {item.nodeid}", f"outcome: {status}", f"final_url: {final_url}", "", "== steps =="]
    lines += [f"{s['n']}. {s['text']}" for s in (rec.steps if rec else [])]
    lines += ["", "== browser events (last 60) =="] + (rec.events[-60:] if rec else [])
    lines += ["", "== error ==", error]
    log_path.write_text("\n".join(lines), encoding="utf-8")

    names = {m.name for m in item.iter_markers()}
    sop = item.get_closest_marker("sop")
    exp = item.get_closest_marker("expected_class")
    scenario = "canary" if "canary" in names else "negative" if "negative" in names else "boundary" if "boundary" in names else "positive"
    _RESULTS.append(
        {
            "nodeid": item.nodeid,
            "slug": slug,
            "module": item.path.stem.replace("test_", ""),
            "scenario_type": scenario,
            "outcome": status,
            "duration_s": round(rep.duration, 2),
            "error": error,
            "final_url": final_url,
            "steps": rec.steps if rec else [],
            "failure_screenshot": failure_shot,
            "log": str(log_path.relative_to(ROOT)),
            "sop_title": sop.args[0] if sop and sop.args else None,
            "expected_class": exp.args[0] if exp and exp.args else None,
            "canary": "canary" in names,
        }
    )


def pytest_sessionfinish(session, exitstatus):
    RESULTS.mkdir(parents=True, exist_ok=True)
    run = {
        "run_id": _STARTED.strftime("%Y%m%dT%H%M%SZ"),
        "started_at": _STARTED.isoformat(),
        "base_url": BASE_URL,
        "git_sha": os.getenv("GITHUB_SHA", "local")[:7],
        "tests": _RESULTS,
    }
    (RESULTS / "run.json").write_text(json.dumps(run, indent=2), encoding="utf-8")
