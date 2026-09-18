"""Personio ATS filler.

Very common for German SMEs -- an Arbeitnow "/apply" link redirected here in
testing (2026-09-18, e.g. linkbroker.jobs.personio.de). Field `name`
attributes are stable across every *.personio.de instance since it's the
same product for every tenant (verified: first_name, last_name, email,
phone, available_from, salary_expectations, documents.cv, documents.other).

Unlike Greenhouse, the redirect lands on a job-info page, not the form
itself -- reach_form() follows the "apply" link Personio renders there
(verified: `<a href="/job/<id>/apply">`) to get to the actual fields.

Dry run only: fills text fields, never touches the file inputs (no résumé
file exists in profile.json) and never clicks the submit button.
"""
from urllib.parse import urljoin

from .. import config

TEXT_FIELDS = [
    "first_name", "last_name", "email", "phone",
    "available_from", "salary_expectations",
]


def is_match(url: str) -> bool:
    return "personio.de" in url or "personio.com" in url


def reach_form(page) -> bool:
    if page.query_selector('input[name="first_name"]'):
        return True
    link = page.query_selector('a[href$="/apply"]')
    if not link:
        return False
    href = link.get_attribute("href")
    page.goto(urljoin(page.url, href), wait_until="domcontentloaded", timeout=30000)
    try:
        page.wait_for_selector('input[name="first_name"]', timeout=10000)
    except Exception:
        pass
    return page.query_selector('input[name="first_name"]') is not None


def _field_values(profile: dict, salary_region: str) -> dict:
    full_name = profile["personal"]["full_name"].strip()
    parts = full_name.split(" ", 1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) > 1 else first_name

    salary = (
        profile["application_defaults"]["salary_expectation_by_region"]
        .get(salary_region, {})
        .get("range", "Negotiable")
    )

    return {
        "first_name": first_name,
        "last_name": last_name,
        "email": profile["personal"]["email"],
        "phone": profile["personal"]["phone"],
        "available_from": profile["application_defaults"]["earliest_start_date"],
        "salary_expectations": salary,
    }


def fill_dry_run(page, profile: dict, screenshot_path: str, country: str | None = None) -> dict:
    """Fill the on-page Personio application form. Stops before any submit
    button. Returns {"filled": {...}, "missing": [...]} for the ledger log.
    """
    salary_region = config.salary_region_for_country(country)
    values = _field_values(profile, salary_region)
    filled = {}
    missing = []

    for field_name in TEXT_FIELDS:
        selector = f'input[name="{field_name}"]'
        el = page.query_selector(selector)
        if not el:
            missing.append(field_name)
            continue
        el.fill(values[field_name])
        filled[field_name] = values[field_name]

    if page.query_selector('input[name="documents.cv"]'):
        missing.append("documents.cv (résumé upload — no file path in profile.json, left empty)")

    page.screenshot(path=screenshot_path, full_page=True)

    return {"filled": filled, "missing": missing}
