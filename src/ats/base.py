"""ATS registry.

Companies found via Arbeitnow/VisaSponsor.jobs redirect out to whichever
application platform they use in-house (spec's "shared ATS-fill module"
idea). Each module below owns detection (is_match) and a dry-run filler
(fill_dry_run). Add new modules here as they're built (Greenhouse, Lever,
Workday, ...); anything unrecognized falls through to needs_manual_review
in src/dry_run.py rather than guessing at a form it has never inspected.
"""
from . import greenhouse, personio

REGISTRY = [
    personio,     # confirmed live 2026-09-18 via an Arbeitnow /apply redirect
    greenhouse,   # confirmed live 2026-09-18 via Arbeitnow + VisaSponsor.jobs redirects
]


def detect(url: str):
    for module in REGISTRY:
        if module.is_match(url):
            return module
    return None
