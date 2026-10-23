"""Orchestrates one closed loop after a test run:

  results/run.json -> triage failures (Claude) -> Jira (create / dedupe / auto-close) -> SOPs -> dashboard CSVs

Usage:  python -m pipeline.run_pipeline [--no-ai] [--no-jira] [--no-sop] [--results results/run.json]
Without Jira credentials it runs in dry-run mode and writes the would-be bug payloads to results/jira_dryrun/.
"""
import argparse
import json
from pathlib import Path

from framework.config import RESULTS, ROOT
from pipeline import dashboard_feed, sop_generator
from pipeline.jira_client import Jira, code, doc, fingerprint, heading, ordered, para
from pipeline.triage import redact, triage


def bug_description(t: dict, tri: dict, run: dict) -> dict:
    blocks = [
        heading("AI triage"),
        para(f"Classification: {tri['classification']} (confidence {tri['confidence']:.2f}, source: {tri['source']})  |  Severity: {tri['severity']}  |  Module: {t['module']}"),
        heading("Description"),
        *[para(chunk) for chunk in tri["description"].split("\n\n")],
        heading("Probable root cause"),
        para(tri["probable_root_cause"]),
        heading("Steps to reproduce"),
        ordered(tri["steps_to_reproduce"]),
        heading("Suggested fix"),
        para(tri["suggested_fix"]),
        heading("Error excerpt (redacted)"),
        code(redact(t.get("error"))[-1500:]),
        para(f"Test: {t['nodeid']} | run {run['run_id']} | commit {run['git_sha']} | screenshot and log attached."),
    ]
    return doc(blocks)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=str(RESULTS / "run.json"))
    ap.add_argument("--no-ai", action="store_true")
    ap.add_argument("--no-jira", action="store_true")
    ap.add_argument("--no-sop", action="store_true")
    args = ap.parse_args(argv)

    run = json.loads(Path(args.results).read_text(encoding="utf-8"))
    tests = run["tests"]
    failed = [t for t in tests if t["outcome"] in ("failed", "error")]
    passed = [t for t in tests if t["outcome"] == "passed"]
    print(f"run {run['run_id']}: {len(passed)} passed, {len(failed)} failed/error, {len(tests)} total")

    jira = None if args.no_jira else Jira()
    live = bool(jira and jira.configured)
    if not live:
        print("Jira: dry-run mode (credentials missing or --no-jira)")
    open_by_fp = {}
    if live:
        try:
            open_by_fp = jira.open_bugs_by_fingerprint()
        except Exception as exc:
            print(f"Jira: could not read open bugs ({exc}); continuing without dedupe")

    triage_by_test, jira_by_test, actions = {}, {}, []
    for t in failed:
        tri = triage(t, use_ai=not args.no_ai)
        triage_by_test[t["nodeid"]] = tri
        fp = fingerprint(t["nodeid"])
        labels = ["bsg-loop", "ai-triage", fp, f"class-{tri['classification'].lower()}", f"module-{t['module']}", f"sev-{tri['severity'].lower()}"]
        if t.get("canary"):
            labels.append("canary")
        attachments = [ROOT / p for p in (t.get("failure_screenshot"), t.get("log")) if p]
        try:
            if live and fp in open_by_fp:
                key = open_by_fp[fp]
                jira.comment(key, f"Failed again in run {run['run_id']} (commit {run['git_sha']}). Triage: {tri['classification']} / {tri['severity']}.")
                jira.attach(key, attachments)
                actions.append({"test": t["nodeid"], "action": "commented", "key": key})
            elif live:
                key = jira.create_bug(tri["bug_title"], bug_description(t, tri, run), labels, tri["severity"])
                jira.attach(key, attachments)
                actions.append({"test": t["nodeid"], "action": "created", "key": key})
            else:
                key = None
                out = RESULTS / "jira_dryrun"
                out.mkdir(parents=True, exist_ok=True)
                (out / f"{t['slug']}.json").write_text(json.dumps({"summary": tri["bug_title"], "labels": labels, "severity": tri["severity"], "triage": tri, "attachments": [str(a) for a in attachments]}, indent=2))
                actions.append({"test": t["nodeid"], "action": "dry_run", "key": None})
            jira_by_test[t["nodeid"]] = key or ""
        except Exception as exc:
            print(f"  ! Jira step failed for {t['nodeid']}: {exc}")
            actions.append({"test": t["nodeid"], "action": "error", "error": str(exc)})

    if live:  # closed loop: a previously failing test that now passes closes its own bug
        for t in passed:
            key = open_by_fp.get(fingerprint(t["nodeid"]))
            if key:
                try:
                    if jira.close(key, f"Auto-verified: test passed in run {run['run_id']} (commit {run['git_sha']})."):
                        actions.append({"test": t["nodeid"], "action": "closed", "key": key})
                        jira_by_test[t["nodeid"]] = key
                except Exception as exc:
                    print(f"  ! could not close {key}: {exc}")

    (RESULTS / "triage.json").write_text(json.dumps({"triage": triage_by_test, "jira_actions": actions}, indent=2), encoding="utf-8")
    dashboard_feed.append_history(run, triage_by_test, jira_by_test)
    ok, total = dashboard_feed.append_eval(run, triage_by_test)
    if total:
        print(f"triage accuracy on labelled canaries this run: {ok}/{total} ({100 * ok / total:.0f}%)")

    if not args.no_sop:
        for r in sop_generator.generate(run, use_ai=not args.no_ai):
            print(f"SOP {r['sop']}: {r['action']}")

    if live:
        try:
            print(f"exported {dashboard_feed.export_jira_issues(jira)} Jira issues to dashboard/jira_issues.csv")
        except Exception as exc:
            print(f"! Jira export failed: {exc}")

    created = sum(a["action"] == "created" for a in actions)
    print(f"done. bugs created: {created}, commented: {sum(a['action'] == 'commented' for a in actions)}, closed: {sum(a['action'] == 'closed' for a in actions)}")


if __name__ == "__main__":
    main()
