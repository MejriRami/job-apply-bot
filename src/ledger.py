"""applied.json ledger: dedupe + record every attempt (spec: "Data Mapping" /
"Submission Flow" steps 2 and 6).
"""
import hashlib
import json
import os
from datetime import datetime, timezone


def make_id(url: str, company: str, title: str) -> str:
    key = f"{(url or '').strip().lower()}|{(company or '').strip().lower()}|{(title or '').strip().lower()}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def load(path: str) -> list:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip()
        return json.loads(content) if content else []


def save(path: str, records: list) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)


def is_known(records: list, job_id: str) -> bool:
    return any(r.get("id") == job_id for r in records)


def find_by_resolved_url(records: list, resolved_url: str) -> dict | None:
    """Cross-source dedup: two different listing URLs (e.g. an Arbeitnow one
    and a VisaSponsor.jobs one) can both point at the same underlying ATS
    posting. `resolved_url` is empty when resolution failed/wasn't
    attempted, so an empty value never matches anything here.
    """
    if not resolved_url:
        return None
    return next((r for r in records if r.get("resolved_url") == resolved_url), None)


def append(path: str, record: dict) -> list:
    records = load(path)
    records.append(record)
    save(path, records)
    return records


def build_record(job: dict, status: str, notes: str, resolved_url: str = "") -> dict:
    job_id = make_id(job.get("url", ""), job.get("company", ""), job.get("title", ""))
    return {
        "id": job_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "site": job.get("source", ""),
        "company": job.get("company", ""),
        "job_title": job.get("title", ""),
        "url": job.get("url", ""),
        "country": job.get("country"),
        "resolved_url": resolved_url,  # final ATS destination, used for cross-source dedup
        "status": status,  # applied | failed | skipped | alert_only | dry_run_filled | needs_manual_review
        "notes": notes,
    }
