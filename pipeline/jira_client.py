"""Minimal Jira Cloud REST v3 client: create bug, attach files, dedupe by fingerprint label, auto-close, export."""
import hashlib
import os
from pathlib import Path

import requests

import framework.config  # noqa: F401  (loads .env)

PRIORITY = {"Critical": "Highest", "High": "High", "Medium": "Medium", "Low": "Low"}


def fingerprint(nodeid: str) -> str:
    return "fp-" + hashlib.sha1(nodeid.encode()).hexdigest()[:10]


# ---------- Atlassian Document Format helpers ----------
def _text(s: str) -> list:
    return [{"type": "text", "text": s}] if s else []


def para(s: str) -> dict:
    return {"type": "paragraph", "content": _text(s or "-")}


def heading(s: str, level: int = 3) -> dict:
    return {"type": "heading", "attrs": {"level": level}, "content": _text(s)}


def ordered(items: list[str]) -> dict:
    return {"type": "orderedList", "content": [{"type": "listItem", "content": [para(i)]} for i in items]}


def code(s: str) -> dict:
    return {"type": "codeBlock", "content": _text(s[:3000] or "-")}


def doc(blocks: list[dict]) -> dict:
    return {"type": "doc", "version": 1, "content": blocks}


class Jira:
    def __init__(self):
        self.base = os.getenv("JIRA_BASE_URL", "").rstrip("/")
        self.email = os.getenv("JIRA_EMAIL", "")
        self.token = os.getenv("JIRA_API_TOKEN", "")
        self.project = os.getenv("JIRA_PROJECT_KEY", "")
        self.s = requests.Session()
        self.s.auth = (self.email, self.token)
        self.s.headers.update({"Accept": "application/json"})

    @property
    def configured(self) -> bool:
        return all([self.base, self.email, self.token, self.project]) and "your-site" not in self.base

    def _req(self, method: str, path: str, **kw):
        r = self.s.request(method, f"{self.base}/rest/api/3{path}", timeout=30, **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"Jira {method} {path} -> {r.status_code}: {r.text[:300]}")
        return r.json() if r.text else {}

    def search(self, jql: str, fields: list[str], limit: int | None = None) -> list[dict]:
        out, token = [], None
        while True:
            params = {"jql": jql, "fields": ",".join(fields), "maxResults": 100}
            if token:
                params["nextPageToken"] = token
            data = self._req("GET", "/search/jql", params=params)
            out += data.get("issues", [])
            token = data.get("nextPageToken")
            if not token or data.get("isLast", True) or (limit and len(out) >= limit):
                return out

    def open_bugs_by_fingerprint(self) -> dict[str, str]:
        jql = f'project = "{self.project}" AND labels = "bsg-loop" AND statusCategory != Done'
        res = {}
        for issue in self.search(jql, ["labels"]):
            for label in issue["fields"].get("labels", []):
                if label.startswith("fp-"):
                    res[label] = issue["key"]
        return res

    def create_bug(self, summary: str, description_adf: dict, labels: list[str], severity: str) -> str:
        fields = {
            "project": {"key": self.project},
            "issuetype": {"name": "Bug"},
            "summary": summary[:250],
            "description": description_adf,
            "labels": labels,
        }
        try:
            return self._req("POST", "/issue", json={"fields": {**fields, "priority": {"name": PRIORITY.get(severity, "Medium")}}})["key"]
        except RuntimeError as exc:
            if "priority" not in str(exc).lower():
                raise
            return self._req("POST", "/issue", json={"fields": fields})["key"]  # project screen has no priority field

    def comment(self, key: str, text: str):
        self._req("POST", f"/issue/{key}/comment", json={"body": doc([para(text)])})

    def attach(self, key: str, paths: list[Path]):
        for p in paths:
            if p and Path(p).exists():
                with open(p, "rb") as fh:
                    r = self.s.post(
                        f"{self.base}/rest/api/3/issue/{key}/attachments",
                        headers={"X-Atlassian-Token": "no-check"},
                        files={"file": (Path(p).name, fh)},
                        timeout=60,
                    )
                if r.status_code >= 400:
                    raise RuntimeError(f"attach {p} -> {r.status_code}: {r.text[:200]}")

    def close(self, key: str, text: str) -> bool:
        trans = self._req("GET", f"/issue/{key}/transitions").get("transitions", [])
        done = next((t for t in trans if t.get("to", {}).get("statusCategory", {}).get("key") == "done"), None)
        if not done:
            return False
        self.comment(key, text)
        self._req("POST", f"/issue/{key}/transitions", json={"transition": {"id": done["id"]}})
        return True
