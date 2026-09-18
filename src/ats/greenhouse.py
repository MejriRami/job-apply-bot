"""Greenhouse ATS filler (job-boards.greenhouse.io).

Verified live 2026-09-18 against two different companies' boards (Anthropic,
Graphcore) -- both Arbeitnow's needs_manual_review hits landed here, which is
also what the original spec named as the first ATS module to build.

Stable field ids across every tenant (same underlying product): first_name,
last_name, email, phone, country, resume, cover_letter.

Deliberately NOT filled, on both boards:
  - #country: a real autocomplete combobox (confirmed by typing into it and
    watching a listbox of matching options appear) -- typing free text alone
    does not "select" a value the way Greenhouse's React state expects, and
    guessing at a fragile click-to-select flow risks a wrong or no-op
    selection. Flagged for manual completion instead.
  - Per-posting `question_<id>` fields (custom questions like "Why do you
    want to work here?", "LinkedIn Profile") -- ids aren't stable across
    postings and answers are company-specific; flagged by label text rather
    than guessed.
  - Hidden `aria-hidden="true" required` shadow inputs -- these back custom
    dropdown/radio widgets, not plain text fields. Inspecting their nearest
    <legend>/<label> on both test postings showed exactly the fields that
    matter most to get right (or leave to the human): right-to-work/visa
    sponsorship questions and EEO/demographic self-identification (gender,
    ethnicity, disability). Never guessed, especially the demographic ones,
    which profile.json has no data for and which are meant to be voluntary.
  - reCAPTCHA (`g-recaptcha-response`) was present on both test postings.
    Filling visible fields doesn't trigger it, but it's flagged because it
    means a real auto-submit later would likely be blocked without a human
    solving it -- this tool will never attempt to bypass a CAPTCHA.
"""

SIMPLE_FIELDS = ["first_name", "last_name", "email", "phone"]

_LABEL_WALK_JS = """(el) => {
    let node = el;
    for (let i = 0; i < 5 && node; i++) {
        node = node.parentElement;
        if (!node) break;
        const legend = node.querySelector && node.querySelector('legend, label');
        if (legend && legend.textContent.trim()) return legend.textContent.trim();
    }
    return null;
}"""


def is_match(url: str) -> bool:
    return "greenhouse.io" in url


def _field_values(profile: dict) -> dict:
    full_name = profile["personal"]["full_name"].strip()
    parts = full_name.split(" ", 1)
    return {
        "first_name": parts[0],
        "last_name": parts[1] if len(parts) > 1 else parts[0],
        "email": profile["personal"]["email"],
        "phone": profile["personal"]["phone"],
    }


def fill_dry_run(page, profile: dict, screenshot_path: str, country: str | None = None) -> dict:
    values = _field_values(profile)
    filled = {}
    missing = []

    for field_id in SIMPLE_FIELDS:
        el = page.query_selector(f"#{field_id}")
        if not el:
            missing.append(field_id)
            continue
        el.fill(values[field_id])
        filled[field_id] = values[field_id]

    if page.query_selector("#country"):
        missing.append(
            "country (autocomplete dropdown — needs manual selection, "
            f"e.g. '{profile['personal']['location_current'].split(',')[-1].strip()}')"
        )
    if page.query_selector("#resume"):
        missing.append("resume (file upload — no file path in profile.json, left empty)")
    if page.query_selector("#cover_letter"):
        missing.append("cover_letter (file upload — left empty)")

    for q in page.query_selector_all('input[id^="question_"], textarea[id^="question_"]'):
        label = q.get_attribute("aria-label")
        if label:
            missing.append(f"custom question: '{label}' — needs manual answer")

    for hidden in page.query_selector_all('input[aria-hidden="true"][required]'):
        label_text = page.evaluate(_LABEL_WALK_JS, hidden)
        if label_text:
            missing.append(f"dropdown/select question: '{label_text}' — needs manual selection")

    if page.query_selector('[name="g-recaptcha-response"], .g-recaptcha, iframe[src*="recaptcha"]'):
        missing.append(
            "reCAPTCHA present on this form — a real auto-submit would likely be "
            "blocked without manually solving it; this tool will not attempt to bypass it"
        )

    page.screenshot(path=screenshot_path, full_page=True)
    return {"filled": filled, "missing": missing}
