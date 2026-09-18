"""Shared paths and run constants for the job-application automation.

Batch 1 scope: Arbeitnow + VisaSponsor.jobs, dry-run only (fill + screenshot,
never submit). Numbers below are intentionally small for a first supervised
run; raise ARBEITNOW_MAX_PAGES / VISASPONSOR_MAX_PAGES / DAILY_CAP later once
the output has been reviewed.
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
LOGS_DIR = os.path.join(ROOT, "logs")
SCREENSHOT_DIR = os.path.join(LOGS_DIR, "screenshots")

PROFILE_PATH = os.path.join(DATA_DIR, "profile.json")
LEDGER_PATH = os.path.join(DATA_DIR, "applied.json")

# Safety guardrails (spec: "Safety Guardrails" section)
DAILY_CAP = 8
PER_SITE_DELAY_RANGE = (30, 60)  # seconds, randomized between site actions

ARBEITNOW_MAX_PAGES = 2       # 250 jobs/page
VISASPONSOR_MAX_PAGES = 3     # ~30 jobs/page, country=DE
ENGLISHJOBS_MAX_PAGES = 3     # 20 jobs/page

ARBEITNOW_USER_AGENT = (
    "job-application-bot/0.1 (+personal job search assistant; "
    "contact ramimejri76@gmail.com)"
)

DEFAULT_SALARY_REGION = "EU_Germany_Netherlands_France"

# profile.json only defines 4 salary buckets; not every ALLOWED_COUNTRIES
# entry has its own. Ireland, Sweden, Denmark, Norway, Finland, Spain all
# fall back to the EU bucket as the closest approximation -- flagging this
# since it's an assumption, not an exact fit (that bucket's own key/notes
# only mention Germany/Netherlands/France explicitly).
SALARY_REGION_BY_COUNTRY = {
    "Germany": "EU_Germany_Netherlands_France",
    "Netherlands": "EU_Germany_Netherlands_France",
    "France": "EU_Germany_Netherlands_France",
    "Ireland": "EU_Germany_Netherlands_France",
    "Sweden": "EU_Germany_Netherlands_France",
    "Denmark": "EU_Germany_Netherlands_France",
    "Norway": "EU_Germany_Netherlands_France",
    "Finland": "EU_Germany_Netherlands_France",
    "Spain": "EU_Germany_Netherlands_France",
    "United Kingdom": "UK",
    "Canada": "US_Canada",
}


def salary_region_for_country(country: str | None) -> str:
    if country and country in SALARY_REGION_BY_COUNTRY:
        return SALARY_REGION_BY_COUNTRY[country]
    return DEFAULT_SALARY_REGION

# Shared across all 3 scrapers. See src/location_filter.py for how each
# source applies it (VisaSponsor.jobs: structured `country` query param;
# Arbeitnow: free-text heuristic over its `location` field; EnglishJobs.de:
# a hardcoded single-country guard, since that site can't be filtered at
# all -- see its scraper's docstring).
ALLOWED_COUNTRIES = [
    "Germany", "Netherlands", "Ireland", "Sweden", "France", "Denmark",
    "Norway", "United Kingdom", "Finland", "Spain", "Canada",
]
