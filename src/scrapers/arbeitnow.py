"""Arbeitnow scraper.

Confirmed 2026-09-18: arbeitnow.com/api/job-board-api is a real, unauthenticated
public JSON API (their own docs at arbeitnow.com/blog/job-board-api explicitly
invite use of it: "please do not abuse"). No HTML scraping needed.

Fields returned: slug, company_name, title, description (HTML), remote, url,
tags, job_types, location, created_at. There is no dedicated visa/English
field, so those checks run against `tags` + `description` via src.matcher.
There's also no structured country field -- `location` is a free-text place
name (e.g. "Bonn-Ramersdorf", "Bristol") -- so country filtering here goes
through src.location_filter's text heuristic rather than a query param.
"""
import html
import random
import re
import time

import requests

from .. import config, location_filter

API_URL = "https://arbeitnow.com/api/job-board-api"

_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(raw: str) -> str:
    if not raw:
        return ""
    text = _TAG_RE.sub(" ", raw)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_jobs(max_pages: int = config.ARBEITNOW_MAX_PAGES) -> list:
    session = requests.Session()
    session.headers.update({
        "User-Agent": config.ARBEITNOW_USER_AGENT,
        "Accept": "application/json",
    })

    jobs = []
    url = API_URL
    page = 1
    while url and page <= max_pages:
        resp = session.get(url, timeout=20)
        resp.raise_for_status()
        payload = resp.json()

        for item in payload.get("data", []):
            location = (item.get("location") or "").strip()
            tags = item.get("tags", []) or []

            allowed, _reason = location_filter.is_allowed(location, tags)
            if not allowed:
                continue

            jobs.append({
                "source": "arbeitnow",
                "title": (item.get("title") or "").strip(),
                "company": (item.get("company_name") or "").strip(),
                "location": location,
                "country": location_filter.country_for_location(location, tags),
                "remote": item.get("remote", False),
                "tags": tags,
                "job_types": item.get("job_types", []) or [],
                "description_text": strip_html(item.get("description", "")),
                "url": item.get("url", ""),
                "created_at": item.get("created_at"),
            })

        url = (payload.get("links") or {}).get("next")
        page += 1
        if url and page <= max_pages:
            time.sleep(random.uniform(1.5, 3.0))

    return jobs
