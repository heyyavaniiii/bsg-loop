"""Writes the CSV feeds Power BI reads: test history (appended every run), Jira issues (full refresh), triage evaluation."""
import csv
from datetime import datetime, timezone

from framework.config import DASHBOARD

HISTORY_COLS = ["run_id", "run_date", "nodeid", "module", "scenario_type", "outcome", "duration_s", "classification", "jira_key"]
EVAL_COLS = ["run_id", "nodeid", "expected", "predicted", "correct", "confidence", "source"]
ISSUE_COLS = ["key", "summary", "status", "status_category", "severity", "created", "resolved", "age_days", "cycle_days", "classification", "module", "canary"]


def _existing_run_ids(path) -> set:
    if not path.exists():
        return set()
    with open(path, newline="", encoding="utf-8") as fh:
        return {row["run_id"] for row in csv.DictReader(fh)}


def _append(path, cols, rows):
    DASHBOARD.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        if new:
            w.writeheader()
        w.writerows(rows)


def append_history(run: dict, triage_by_test: dict, jira_by_test: dict) -> bool:
    path = DASHBOARD / "test_results.csv"
    if run["run_id"] in _existing_run_ids(path):
        return False
    date = run["started_at"][:10]
    rows = [
        {
            "run_id": run["run_id"],
            "run_date": date,
            "nodeid": t["nodeid"],
            "module": t["module"],
            "scenario_type": t["scenario_type"],
            "outcome": t["outcome"],
            "duration_s": t["duration_s"],
            "classification": triage_by_test.get(t["nodeid"], {}).get("classification", ""),
            "jira_key": jira_by_test.get(t["nodeid"], ""),
        }
        for t in run["tests"]
    ]
    _append(path, HISTORY_COLS, rows)
    return True


def append_eval(run: dict, triage_by_test: dict) -> tuple[int, int]:
    """Score triage against canary ground truth. Returns (correct, total) for this run."""
    rows = []
    for t in run["tests"]:
        exp = t.get("expected_class")
        tri = triage_by_test.get(t["nodeid"])
        if exp and tri:
            rows.append(
                {
                    "run_id": run["run_id"],
                    "nodeid": t["nodeid"],
                    "expected": exp,
                    "predicted": tri["classification"],
                    "correct": int(exp == tri["classification"]),
                    "confidence": tri["confidence"],
                    "source": tri["source"],
                }
            )
    if rows:
        _append(DASHBOARD / "triage_eval.csv", EVAL_COLS, rows)
    return sum(r["correct"] for r in rows), len(rows)


def _parse(ts: str | None):
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%f%z") if ts else None


def export_jira_issues(jira) -> int:
    fields = ["summary", "status", "priority", "created", "resolutiondate", "labels"]
    issues = jira.search(f'project = "{jira.project}" AND labels = "bsg-loop" ORDER BY created ASC', fields)
    now = datetime.now(timezone.utc)
    rows = []
    for i in issues:
        f = i["fields"]
        labels = f.get("labels", [])
        pick = lambda prefix: next((l[len(prefix):] for l in labels if l.startswith(prefix)), "")
        created, resolved = _parse(f["created"]), _parse(f.get("resolutiondate"))
        age = ((resolved or now) - created).total_seconds() / 86400
        rows.append(
            {
                "key": i["key"],
                "summary": f["summary"],
                "status": f["status"]["name"],
                "status_category": f["status"]["statusCategory"]["key"],
                "severity": pick("sev-").title() or (f.get("priority") or {}).get("name", ""),
                "created": created.isoformat(),
                "resolved": resolved.isoformat() if resolved else "",
                "age_days": round(age, 3),
                "cycle_days": round(age, 3) if resolved else "",
                "classification": pick("class-").upper(),
                "module": pick("module-"),
                "canary": int("canary" in labels),
            }
        )
    DASHBOARD.mkdir(parents=True, exist_ok=True)
    with open(DASHBOARD / "jira_issues.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=ISSUE_COLS)
        w.writeheader()
        w.writerows(rows)
    return len(rows)
