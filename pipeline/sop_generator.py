"""SOP / user-manual generator.

Passing journeys tagged @pytest.mark.sop(...) record numbered, screenshotted steps. Claude turns them into a
plain-language SOP (using ONLY the recorded steps). Screenshots are refreshed on every green run, the text is
regenerated only when the journey itself changes, and a SOP is flagged as possibly outdated when its journey fails.
"""
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone

import os

from framework.config import CLAUDE_MODEL, ROOT, SOP_DIR
from pipeline.triage import _parse_json

SYSTEM = """You write standard operating procedures (SOPs) for bank operations staff from recorded automation steps.
Use ONLY the supplied steps; never invent screens, fields, buttons or rules. Keep wording plain and imperative.
Return ONLY JSON: {"purpose": str, "prerequisites": [str], "step_instructions": [str], "expected_result": str}
step_instructions must have exactly one entry per recorded step, in the same order."""

STATUS_RE = re.compile(r"<!--status-->.*")


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def _hash(steps: list[dict]) -> str:
    return hashlib.sha1("|".join(s["text"] for s in steps).encode()).hexdigest()[:12]


def _draft(title: str, steps: list[dict], use_ai: bool) -> dict:
    fallback = {
        "purpose": title,
        "prerequisites": ["Access to the online banking application"],
        "step_instructions": [s["text"] for s in steps],
        "expected_result": steps[-1]["text"] if steps else "",
        "source": "recorded-steps",
    }
    if not (use_ai and os.getenv("ANTHROPIC_API_KEY")):
        return fallback
    try:
        import anthropic

        msg = anthropic.Anthropic().messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1500,
            system=SYSTEM,
            messages=[{"role": "user", "content": f"SOP title: {title}\nRecorded steps:\n" + "\n".join(f"{s['n']}. {s['text']}" for s in steps)}],
        )
        obj = _parse_json("".join(b.text for b in msg.content if getattr(b, "type", "") == "text"))
        if len(obj.get("step_instructions", [])) != len(steps):
            raise ValueError("step count mismatch")
        obj["source"] = "claude"
        return obj
    except Exception:
        return fallback


def _status_line(run: dict, ok: bool) -> str:
    if ok:
        return f"<!--status-->✅ Verified by passing automated run `{run['run_id']}` (commit `{run['git_sha']}`)."
    return f"<!--status-->⚠️ **Possible drift** - the automated test for this journey failed in run `{run['run_id']}`. Verify before relying on this SOP."


def _render(title, t, draft, run, slug) -> str:
    out = [f"# {title}", "", _status_line(run, True), "", f"_Auto-generated from test `{t['nodeid']}` ({draft['source']})._", "", "## Purpose", draft["purpose"], "", "## Prerequisites"]
    out += [f"- {p}" for p in draft.get("prerequisites", [])] + ["", "## Procedure", ""]
    for step, text in zip(t["steps"], draft["step_instructions"]):
        out += [f"### Step {step['n']}", text, "", f"![Step {step['n']}](img/{slug}/step_{step['n']:02d}.png)", ""]
    out += ["## Expected result", draft.get("expected_result", ""), ""]
    return "\n".join(out)


def _copy_images(t, slug):
    dest = SOP_DIR / "img" / slug
    dest.mkdir(parents=True, exist_ok=True)
    for s in t["steps"]:
        src = ROOT / s["screenshot"]
        if src.exists():
            shutil.copy(src, dest / f"step_{s['n']:02d}.png")


def generate(run: dict, use_ai: bool = True) -> list[dict]:
    SOP_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = SOP_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    report = []
    for t in run["tests"]:
        title = t.get("sop_title")
        if not title:
            continue
        slug = _slug(title)
        md = SOP_DIR / f"{slug}.md"
        entry = manifest.get(slug, {})
        if t["outcome"] == "passed" and t["steps"]:
            changed = entry.get("hash") != _hash(t["steps"]) or not md.exists()
            if changed:
                md.write_text(_render(title, t, _draft(title, t["steps"], use_ai), run, slug), encoding="utf-8")
            else:
                md.write_text(STATUS_RE.sub(lambda _: _status_line(run, True), md.read_text(encoding="utf-8"), count=1), encoding="utf-8")
            _copy_images(t, slug)
            manifest[slug] = {"title": title, "hash": _hash(t["steps"]), "status": "verified", "run_id": run["run_id"], "test": t["nodeid"]}
            report.append({"sop": slug, "action": "regenerated" if changed else "refreshed"})
        elif md.exists():
            md.write_text(STATUS_RE.sub(lambda _: _status_line(run, False), md.read_text(encoding="utf-8"), count=1), encoding="utf-8")
            manifest[slug] = {**entry, "status": "drift_suspected", "run_id": run["run_id"]}
            report.append({"sop": slug, "action": "flagged_drift"})
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    rows = ["# Generated SOPs", "", "| SOP | Status | Last run | Source test |", "|---|---|---|---|"]
    for slug, m in sorted(manifest.items()):
        badge = "✅ verified" if m["status"] == "verified" else "⚠️ drift suspected"
        rows.append(f"| [{m['title']}]({slug}.md) | {badge} | `{m['run_id']}` | `{m['test']}` |")
    (SOP_DIR / "README.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return report
