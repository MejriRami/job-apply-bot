"""EnglishJobs.de scraper.

Listing endpoint (confirmed live 2026-09-18): englishjobs.de/jobs/visa-sponsorship
?page=N, 20 listings/page, plain server-rendered HTML (no client-side gating,
unlike VisaSponsor.jobs) -- but it's still fetched with Playwright to reuse
the same structural-selector pattern as visasponsor.py rather than add a new
HTML-parsing dependency (bs4 isn't installed) for one source.

Reuses the existing pattern almost entirely: a repeating card selector,
CSS-based field extraction, `?page=N` pagination. Two things it can't reuse:

  1. No detail pages exist here at all -- the listing card's own snippet is
     the only description text available. There's no fetch_detail() step
     the way visasponsor.py has one; description_text is filled in directly
     during fetch_jobs().

  2. Every job link is a tracked `/clickout/<id>?...&sig=...&e=<opaque>...`
     redirect (source="lifeworq" -- this board aggregates from a job network,
     it isn't the original poster). robots.txt explicitly disallows crawling
     `/clickout/*`, `/clickredirect/*`, etc., and there's no JSON-LD or other
     structured data exposing a direct, untracked URL. Unlike VisaSponsor.jobs
     (where the careerjet gate was only discovered empirically at the
     destination), this site is telling automated agents up front not to
     touch that path -- so it's never followed at all, not even to resolve a
     canonical URL for dedup. src/dry_run.py treats every EnglishJobs.de
     candidate as alert_only unconditionally.

The site's own premise (an "English speakers" + "visa sponsorship" filtered
board) already satisfies both of matcher.py's visa and English checks for
most listings -- the "visa sponsorship" pill maps onto VISA_TAGS same as
VisaSponsor.jobs's "EU Blue Card" pill, and the snippet text is in English so
the language heuristic passes it naturally. Nothing special-cased for that;
matcher.py runs unchanged.

COUNTRY SCOPE (checked live 2026-09-18): englishjobs.de itself has no country
filter of any kind -- no query parameter, no alternate URL path. Its own
listing content confirms this: "Jobs by State"/"Jobs by City" are exclusively
German states and cities (Bavaria, NRW, Munich, Berlin, ...); there is
nothing to switch. This source is therefore Germany-only, permanently,
regardless of config.ALLOWED_COUNTRIES -- fetch_jobs() below returns nothing
at all if Germany isn't in that list, rather than silently ignoring it.

Separately (found while checking, NOT the same as an on-site filter, and NOT
wired up here): englishjobs.de's own footer links to a network of sibling
sites, one per country, on different domains entirely:
  englishjobs.dk (Denmark), englishjobs.es (Spain), englishjobs.fi (Finland),
  englishjobs.fr (France), englishjobs.no (Norway), englishjobsearch.nl
  (Netherlands -- note the different domain pattern), englishjobsearch.se
  (Sweden -- same pattern), plus englishjobsearch.at (Austria), englishjobs.be
  (Belgium), englishjobsearch.ch (Switzerland), englishjobs.it (Italy),
  englishjobs.lu (Luxembourg), englishjobs.pl (Poland), englishjobs.pt
  (Portugal). That covers 7 of the 11 ALLOWED_COUNTRIES (Denmark, Spain,
  Finland, France, Norway, Netherlands, Sweden).
  It does NOT cover Ireland, United Kingdom, or Canada at all -- no sibling
  site exists for any of those three in this footer. Adding those sibling
  sites as sources of their own is a separate, larger task (each is an
  unverified new site needing its own reconnaissance) and was not done here.
"""
import random
import time

from .. import config

SITE_ROOT = "https://englishjobs.de"
LISTING_URL = f"{SITE_ROOT}/jobs/visa-sponsorship"
CARD_SELECTOR = "div.job.js-job"


def fetch_jobs(page, max_pages: int = config.ENGLISHJOBS_MAX_PAGES) -> list:
    if "Germany" not in config.ALLOWED_COUNTRIES:
        return []

    jobs = []
    for p in range(1, max_pages + 1):
        url = LISTING_URL if p == 1 else f"{LISTING_URL}?page={p}"
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        try:
            page.wait_for_selector(CARD_SELECTOR, timeout=15000)
        except Exception:
            break

        cards = page.query_selector_all(CARD_SELECTOR)
        if not cards:
            break

        for card in cards:
            card_id = card.get_attribute("id")
            title_el = card.query_selector('h3[itemprop="title"]')
            apply_el = card.query_selector('a[itemprop="url"]')
            desc_el = card.query_selector("div.flex-1 + div")

            lis = card.query_selector_all("ul > li")
            company = lis[0].inner_text().strip() if len(lis) > 0 else ""
            location = lis[1].inner_text().strip() if len(lis) > 1 else ""
            tags = [li.inner_text().strip() for li in lis[3:]] if len(lis) > 3 else []

            jobs.append({
                "source": "englishjobs",
                "title": title_el.inner_text().strip() if title_el else "",
                "company": company,
                "location": location,
                "country": "Germany",  # this source is Germany-only, see module docstring
                "tags": tags,
                # not a real deep link (this site has no per-job detail page) --
                # a stable synthetic id for ledger dedup, kept alongside the
                # real (never-navigated) apply_url for the human to click.
                "url": f"{LISTING_URL}#{card_id}",
                "apply_url": (
                    f"{SITE_ROOT}{apply_el.get_attribute('href')}"
                    if apply_el and apply_el.get_attribute("href")
                    else None
                ),
                "description_text": desc_el.inner_text().strip() if desc_el else "",
            })

        has_next = page.query_selector(f'a[href*="page={p + 1}"]')
        if has_next and p < max_pages:
            time.sleep(random.uniform(*config.PER_SITE_DELAY_RANGE))
        else:
            break

    return jobs
