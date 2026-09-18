"""VisaSponsor.jobs scraper.

The URL guessed in the original spec (visasponsor.jobs/api/jobs?country=Germany)
does not exist -- confirmed 2026-09-18, it 404s/redirects to the homepage.
The real, client-navigable listing endpoint is:

    https://visasponsor.jobs/jobs?country=DE&page=<n>

(country uses ISO alpha-2 codes, discovered by driving the site's own filter
UI and reading window.location.href). The site is Next.js/client-rendered, so
this needs a real browser (Playwright), not requests+BeautifulSoup. robots.txt
allows everything (`Allow: /`).

Multiple countries can be queried in one request by repeating the param --
confirmed live 2026-09-18: `?country=DE&country=NL&country=IE&country=GB&country=CA`
returns their union in a single result set with normal pagination
(`&page=N` appended, same as the single-country case), not five separate
site visits.

The site's own country checkbox list (read directly from the live DOM,
2026-09-18) is exactly: AU, CA, DE, IE, NL, NZ, PT, SG, GB, US -- 10
countries total. Cross-referenced against config.ALLOWED_COUNTRIES (11
countries), this site supports Germany (DE), Netherlands (NL), Ireland (IE),
United Kingdom (GB), and Canada (CA) -- 5 of 11. It does NOT support Sweden,
France, Denmark, Norway, Finland, or Spain -- 6 of 11 -- at all; there is no
code or query value for them, so a job in one of those 6 could never be
surfaced from this source regardless of ALLOWED_COUNTRIES.

Each listing card (`a.job-card`) already carries a structured visa-type pill
(`.pill-visa`, e.g. "EU Blue Card") -- a much stronger signal than free-text
keyword search, so src.matcher treats that as a direct tag hit.

IMPORTANT: some "Apply Now" links on this site's job-detail pages route
through careerjet.de, which returned a bot-verification / "unusual traffic"
challenge page when visited directly (confirmed 2026-09-18, e.g. a Clera
posting). Others link straight to the company's own ATS with no careerjet
hop at all (confirmed same day, e.g. an Anthropic posting resolved directly
to job-boards.greenhouse.io). This module only scrapes + matches; the
careerjet-vs-direct decision, and any resulting fill attempt, happens in
src/dry_run.py, which checks each job's captured apply_url individually
rather than assuming one behavior for the whole site.
"""
import random
import time

from .. import config

LISTING_BASE = "https://visasponsor.jobs/jobs"

# Full 10-country list this site's own filter UI offers; only the ones also
# in config.ALLOWED_COUNTRIES are ever queried.
_SUPPORTED_COUNTRY_CODES = {
    "Germany": "DE",
    "Netherlands": "NL",
    "Ireland": "IE",
    "United Kingdom": "GB",
    "Canada": "CA",
    # supported by the site but not requested unless added to ALLOWED_COUNTRIES:
    "Australia": "AU",
    "New Zealand": "NZ",
    "Portugal": "PT",
    "Singapore": "SG",
    "United States": "US",
}


def _allowed_country_codes() -> list[str]:
    return [
        code for name, code in _SUPPORTED_COUNTRY_CODES.items()
        if name in config.ALLOWED_COUNTRIES
    ]


def fetch_jobs(page, max_pages: int = config.VISASPONSOR_MAX_PAGES) -> list:
    codes = _allowed_country_codes()
    if not codes:
        return []
    country_query = "&".join(f"country={c}" for c in codes)

    jobs = []
    for p in range(1, max_pages + 1):
        url = f"{LISTING_BASE}?{country_query}" + (f"&page={p}" if p > 1 else "")
        # networkidle never fires here (persistent ad/tracking connections);
        # wait for the actual listing content instead.
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        try:
            page.wait_for_selector("a.job-card", timeout=15000)
        except Exception:
            break

        cards = page.query_selector_all("a.job-card")
        if not cards:
            break

        for card in cards:
            href = card.get_attribute("href")
            title_el = card.query_selector(".job-title")
            company_el = card.query_selector(".job-company")
            location_el = card.query_selector(".job-location span")
            visa_pills = [el.inner_text().strip() for el in card.query_selector_all(".pill-visa")]
            industry_pills = [el.inner_text().strip() for el in card.query_selector_all(".pill-industry")]

            location = location_el.inner_text().strip() if location_el else ""
            # the site's own display convention is "City, Region, Country"
            # (confirmed live, e.g. "Heidelberg, Baden-Württemberg, Germany",
            # "Berlin, Germany") -- the last comma-separated segment is the
            # country name.
            country = location.split(",")[-1].strip() if location else None

            jobs.append({
                "source": "visasponsor",
                "title": title_el.inner_text().strip() if title_el else "",
                "company": company_el.inner_text().strip() if company_el else "",
                "location": location,
                "country": country,
                "tags": visa_pills + industry_pills,
                "url": f"https://visasponsor.jobs{href}" if href else "",
                "description_text": "",  # filled lazily by fetch_detail() for candidates only
            })

        has_next = page.query_selector(f'a.page-link[href*="page={p + 1}"]')
        if has_next and p < max_pages:
            time.sleep(random.uniform(*config.PER_SITE_DELAY_RANGE))
        else:
            break

    return jobs


def fetch_detail(page, job: dict) -> dict:
    """Fill in full description text + the outbound apply link for one job.
    Call only for jobs that already passed a cheap listing-level prefilter,
    to keep request volume polite.
    """
    page.goto(job["url"], wait_until="domcontentloaded", timeout=30000)
    try:
        page.wait_for_selector("main", timeout=15000)
    except Exception:
        pass

    main = page.query_selector("main")
    job["description_text"] = main.inner_text() if main else ""

    apply_link = page.query_selector('a:has-text("Apply Now")')
    job["apply_url"] = apply_link.get_attribute("href") if apply_link else None

    return job
