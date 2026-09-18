"""Batch-1 dry-run orchestrator: Arbeitnow + VisaSponsor.jobs + EnglishJobs.de.

For every job that passes matcher.evaluate_job() and isn't already in
data/applied.json:
  - arbeitnow    -> follow its own "/apply" redirect to whatever ATS the
                    company uses.
  - visasponsor  -> follow the "Apply Now" link captured on the job detail
                    page. NOT every listing routes through careerjet.de --
                    testing found some (e.g. an Anthropic posting) link
                    directly to the company's ATS, others go through
                    careerjet. Only the careerjet ones are skipped as
                    alert_only (it returned a bot-verification challenge
                    page in testing; automating past that would be a
                    CAPTCHA bypass, which this tool will not do).
  - englishjobs  -> always alert_only. Every listing's apply link is a
                    tracked /clickout/ redirect that the site's own
                    robots.txt disallows crawling, and there's no detail
                    page or structured data exposing an untracked URL. This
                    one is never navigated at all, unlike the careerjet
                    case above which was only discovered empirically.

Before the daily cap is applied, every qualifying candidate's final ATS
destination is resolved and canonicalized (src/resolve.py) so the same
underlying posting found through two different sites -- confirmed live
2026-09-18, the same Anthropic Greenhouse job via both Arbeitnow and
VisaSponsor.jobs -- is only processed once. Duplicates are logged as
"skipped" and don't count against the cap.

Whatever the source, once a start URL is reached: if it lands on a known ATS
(src/ats/base.REGISTRY -- currently Personio, Greenhouse), fill the safe,
unambiguous fields and screenshot, but NEVER click submit. Unknown ATS ->
screenshot the landing page and log needs_manual_review.

Every attempt (dry_run_filled / needs_manual_review / alert_only / skipped)
is appended to data/applied.json, and a digest is printed + written to
logs/.
"""
import os
import random
import time
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

from . import config, ledger, matcher, resolve
from .ats import base as ats_base
from .profile_loader import load_profile
from .scrapers import arbeitnow, englishjobs, visasponsor


def _process_ats_candidate(page, job, profile, start_url: str) -> tuple[str, str]:
    job_id = ledger.make_id(job["url"], job["company"], job["title"])
    screenshot_path = os.path.join(config.SCREENSHOT_DIR, f"{job_id}.png")

    try:
        page.goto(start_url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        return "failed", f"could not load apply page: {e}"
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass  # best-effort settle; some ATS pages keep long-poll connections open

    final_url = page.url
    module = ats_base.detect(final_url)

    if module is None:
        page.screenshot(path=screenshot_path, full_page=True)
        return "needs_manual_review", (
            f"unrecognized ATS at {final_url} — no filler implemented yet; "
            f"screenshot saved to {screenshot_path}"
        )

    if hasattr(module, "reach_form") and not module.reach_form(page):
        page.screenshot(path=screenshot_path, full_page=True)
        return "needs_manual_review", (
            f"landed on {module.__name__.rsplit('.', 1)[-1]} domain ({final_url}) but "
            f"could not find the application form; screenshot saved to {screenshot_path}"
        )

    result = module.fill_dry_run(page, profile, screenshot_path, country=job.get("country"))
    note = f"dry-run filled {list(result['filled'].keys())}; screenshot: {screenshot_path}"
    if result["missing"]:
        note += f"; needs attention: {result['missing']}"
    return "dry_run_filled", note


def _gather_arbeitnow_candidates(profile, ledger_records) -> list:
    print("Fetching Arbeitnow jobs via public API...")
    jobs = arbeitnow.fetch_jobs()
    print(f"  {len(jobs)} jobs fetched")

    candidates = []
    for job in jobs:
        job_id = ledger.make_id(job["url"], job["company"], job["title"])
        if ledger.is_known(ledger_records, job_id):
            continue
        result = matcher.evaluate_job(job, profile)
        if result.qualifies:
            candidates.append((job, result))
    print(f"  {len(candidates)} qualify and are not yet in the ledger")
    return candidates


def _gather_visasponsor_candidates(page, profile, ledger_records) -> list:
    print(f"Fetching VisaSponsor.jobs listings (countries: {visasponsor._allowed_country_codes()})...")
    jobs = visasponsor.fetch_jobs(page)
    print(f"  {len(jobs)} listings fetched")

    candidates = []
    for job in jobs:
        job_id = ledger.make_id(job["url"], job["company"], job["title"])
        if ledger.is_known(ledger_records, job_id):
            continue
        # cheap listing-level prefilter (title + tag) before spending a
        # request on the detail page
        prelim = matcher.evaluate_job(job, profile)
        if prelim.title_ok and prelim.visa_ok:
            time.sleep(random.uniform(*config.PER_SITE_DELAY_RANGE))
            visasponsor.fetch_detail(page, job)
            full_result = matcher.evaluate_job(job, profile)
            if full_result.qualifies:
                candidates.append((job, full_result))
    print(f"  {len(candidates)} qualify and are not yet in the ledger")
    return candidates


def _gather_englishjobs_candidates(page, profile, ledger_records) -> list:
    print("Fetching EnglishJobs.de listings (visa-sponsorship)...")
    jobs = englishjobs.fetch_jobs(page)
    print(f"  {len(jobs)} listings fetched")

    candidates = []
    for job in jobs:
        job_id = ledger.make_id(job["url"], job["company"], job["title"])
        if ledger.is_known(ledger_records, job_id):
            continue
        # no detail page on this site -- the listing snippet is the full
        # description text already, so one evaluate_job() call is enough
        result = matcher.evaluate_job(job, profile)
        if result.qualifies:
            candidates.append((job, result))
    print(f"  {len(candidates)} qualify and are not yet in the ledger")
    return candidates


def _resolve_and_dedup(candidates: list, ledger_records: list, digest: list) -> list:
    """Resolve each candidate's final ATS URL and drop any that duplicate
    either an earlier candidate in this same run or something already in
    the ledger. Duplicates are logged as "skipped" immediately (cheap: this
    only costs a plain GET for arbeitnow, nothing extra for visasponsor)
    so they never eat into the daily cap.
    """
    kept = []
    seen_this_run = set()

    for job, result in candidates:
        if job["source"] == "arbeitnow":
            time.sleep(random.uniform(*resolve.RESOLVE_DELAY_RANGE))
            resolved_url = resolve.resolve_arbeitnow_apply_url(job["url"])
        else:
            apply_url = job.get("apply_url") or job["url"]
            resolved_url = resolve.canonicalize(apply_url)

        dup_in_ledger = ledger.find_by_resolved_url(ledger_records, resolved_url)
        if resolved_url and (resolved_url in seen_this_run or dup_in_ledger):
            duplicate_of = dup_in_ledger["company"] + " — " + dup_in_ledger["job_title"] if dup_in_ledger else "a candidate already queued in this run"
            notes = f"duplicate posting (resolved to {resolved_url}), same as {duplicate_of}"
            record = ledger.build_record(job, "skipped", notes, resolved_url=resolved_url)
            ledger.append(config.LEDGER_PATH, record)
            digest.append(record)
            print(f"  [skipped] {job['company']} — {job['title']} ({job['source']}) — duplicate")
            continue

        if resolved_url:
            seen_this_run.add(resolved_url)
        kept.append((job, result, resolved_url))

    return kept


def run(limit: int = config.DAILY_CAP) -> list:
    os.makedirs(config.SCREENSHOT_DIR, exist_ok=True)
    profile = load_profile()
    ledger_records = ledger.load(config.LEDGER_PATH)
    digest = []

    arbeitnow_candidates = _gather_arbeitnow_candidates(profile, ledger_records)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()

        visa_candidates = _gather_visasponsor_candidates(page, profile, ledger_records)
        englishjobs_candidates = _gather_englishjobs_candidates(page, profile, ledger_records)

        print("\nResolving final ATS destinations for cross-source dedup...")
        all_candidates = _resolve_and_dedup(
            arbeitnow_candidates + visa_candidates + englishjobs_candidates,
            ledger_records, digest,
        )
        all_candidates = all_candidates[:limit]
        print(f"\nProcessing {len(all_candidates)} candidates (daily cap = {limit})...\n")

        for job, result, resolved_url in all_candidates:
            flags_note = f" | flags: {result.flags}" if result.flags else ""

            if job["source"] == "arbeitnow":
                start_url = resolved_url or (job["url"].rstrip("/") + "/apply")
                status, notes = _process_ats_candidate(page, job, profile, start_url)
            elif job["source"] == "englishjobs":
                status = "alert_only"
                notes = (
                    "Apply link is a tracked /clickout/ redirect that this site's "
                    "robots.txt disallows crawling — not automated. "
                    f"Apply manually: {job.get('apply_url') or job['url']}"
                )
            else:  # visasponsor
                apply_url = job.get("apply_url")
                if not apply_url:
                    status = "needs_manual_review"
                    notes = f"no 'Apply Now' link found on {job['url']}"
                elif "careerjet" in apply_url:
                    status = "alert_only"
                    notes = (
                        "Apply routes through careerjet.de, which returned a bot-"
                        "verification challenge page during testing — not automated. "
                        f"Apply manually: {apply_url}"
                    )
                else:
                    status, notes = _process_ats_candidate(page, job, profile, apply_url)

            notes += flags_note
            record = ledger.build_record(job, status, notes, resolved_url=resolved_url)
            ledger.append(config.LEDGER_PATH, record)
            digest.append(record)
            print(f"  [{status}] {job['company']} — {job['title']} ({job['source']})")

            time.sleep(random.uniform(*config.PER_SITE_DELAY_RANGE))

        browser.close()

    _write_digest(digest)
    return digest


def _write_digest(records: list) -> None:
    os.makedirs(config.LOGS_DIR, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = os.path.join(config.LOGS_DIR, f"digest_{date_str}.txt")

    lines = [f"Dry-run digest — {datetime.now(timezone.utc).isoformat()}", ""]
    by_status = {}
    for r in records:
        by_status.setdefault(r["status"], []).append(r)

    for status, items in by_status.items():
        lines.append(f"{status.upper()} ({len(items)})")
        for r in items:
            lines.append(f"  - {r['company']} — {r['job_title']} [{r['site']}] {r['url']}")
            lines.append(f"    {r['notes']}")
        lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\nDigest written to {path}")
