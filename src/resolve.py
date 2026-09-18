"""URL canonicalization + cheap redirect resolution.

Used to dedupe the same underlying job posting when multiple source sites
link out to it independently. Confirmed live 2026-09-18: an Arbeitnow
listing and a VisaSponsor.jobs listing both pointed at the exact same
Anthropic Greenhouse posting under different tracking query strings
(?utm_source=arbeitnow.com vs no query string at all). Without this, both
would be treated as distinct candidates and the same job could be filled
(or eventually applied to) twice.
"""
from urllib.parse import urlsplit, urlunsplit

import requests

from . import config

# Lightweight redirect-resolution requests (no form interaction, nothing
# rendered) don't need the full 30-60s per-site delay reserved for real
# application actions -- that guardrail exists to avoid looking bot-like
# while filling/submitting forms, not for a single plain GET.
RESOLVE_DELAY_RANGE = (2.0, 5.0)


def canonicalize(url: str) -> str:
    """scheme://host/path -- no query string, fragment, or trailing slash.
    Strips tracking params (utm_source, ref, pid, ...) that would otherwise
    make the same posting look like two different URLs.
    """
    if not url:
        return ""
    parts = urlsplit(url)
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def resolve_arbeitnow_apply_url(job_url: str) -> str:
    """Follow Arbeitnow's own /apply redirect with a plain GET (confirmed
    2026-09-18: it's a real HTTP 302, no JS involved) so candidates can be
    deduped by final destination before spending a Playwright page load on
    each one.
    """
    apply_url = job_url.rstrip("/") + "/apply"
    try:
        resp = requests.get(
            apply_url,
            headers={"User-Agent": config.ARBEITNOW_USER_AGENT},
            allow_redirects=True,
            timeout=20,
        )
        return canonicalize(resp.url)
    except requests.RequestException:
        return ""
