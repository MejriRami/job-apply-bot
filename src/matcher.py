"""Qualification logic shared by every site scraper.

A posting qualifies when it clears three independent checks (spec's
"Matching Logic" section): visa/relocation signal, English working
language, and a fuzzy title match against profile.role_target.target_titles.
Each check returns its own reasoning string so the dry-run log stays
auditable instead of a bare pass/fail.
"""
import re
from dataclasses import dataclass, field
from typing import Optional

from rapidfuzz import fuzz

VISA_KEYWORDS = [
    "visa sponsorship", "visa-sponsorship", "sponsors visa", "we sponsor",
    "sponsorship available", "relocation support", "relocation package",
    "relocation assistance", "blue card", "work permit assistance",
    "international candidates", "sponsor work visa", "will sponsor",
    "visa support",
]

# Explicit tags some sites already attach (cheaper/more reliable than text search)
VISA_TAGS = {
    "eu blue card", "blue card", "h-1b", "h1b", "skilled worker",
    "health and care worker", "visa sponsorship",
}

ENGLISH_EXPLICIT_PHRASES = [
    "english-speaking", "english speaking team", "company language is english",
    "working language is english", "language of the company is english",
    "fluent english", "business english required", "english required",
    "international team", "our company language is english",
]

GERMAN_STOPWORDS = {
    "der", "die", "das", "und", "mit", "für", "wir", "sie", "ein", "eine",
    "ist", "auf", "von", "bei", "dich", "dein", "deine", "unser", "unsere",
    "einen", "einer", "als", "auch", "wird", "werden", "sowie", "oder",
    "nicht", "kein", "keine", "du", "dir", "uns", "sich",
}
ENGLISH_STOPWORDS = {
    "the", "and", "with", "for", "you", "your", "our", "are", "is", "we",
    "team", "join", "role", "this", "will", "have", "that", "from", "about",
    "work", "experience", "skills", "responsibilities",
}

ROLE_KEYWORDS = [
    "ai engineer", "ml engineer", "machine learning engineer",
    "llm engineer", "agent engineer", "genai engineer", "gen ai engineer",
    "applied ai", "ai/backend", "ai backend", "ai architect",
    "artificial intelligence engineer", "nlp engineer", "ai developer",
    "llm/agent", "agentic ai", "python developer",
]

TITLE_FUZZY_THRESHOLD = 68

# rapidfuzz's token_set_ratio scores "Platform Engineer" vs "AI Engineer" at
# 84 just because they share the word "Engineer" -- gate the fuzzy fallback
# behind an actual AI/ML/LLM/agent qualifier so generic titles never pass on
# shared-word overlap alone.
_QUALIFIER_RE = re.compile(r"\b(ai|ml|llm|nlp|genai|gen-ai|agent|agents|agentic)\b")
_QUALIFIER_PHRASES = ("machine learning", "artificial intelligence")

# "Software Engineer" is deliberately NOT in ROLE_KEYWORDS (too generic --
# would match ordinary backend/web roles with no AI angle at all). It's
# handled separately: only a match when paired with a qualifier, reusing
# _has_qualifier() below plus "backend" specifically for this phrase only.
# "backend" is intentionally NOT added to the general _QUALIFIER_RE/
# _has_qualifier(), because that would let a plain "Backend Engineer" (no
# AI signal whatsoever) fuzzy-match your "AI/Backend Engineer" target title
# the same way "Platform Engineer" used to false-positive against
# "AI Engineer" -- the exact bug this gate exists to prevent.
_SOFTWARE_ENGINEER_PHRASE = "software engineer"
_BACKEND_RE = re.compile(r"\bbackend\b")

_WORD_RE = re.compile(r"[a-zA-ZäöüÄÖÜß]+")


@dataclass
class MatchResult:
    qualifies: bool
    visa_ok: bool
    visa_reason: str
    english_ok: Optional[bool]
    english_reason: str
    title_ok: bool
    title_reason: str
    flags: list = field(default_factory=list)


def _normalize_title(title: str) -> str:
    title = title.lower()
    # strip common German gender-marker suffixes: (m/w/d), (m/f/d), (w/m/d) ...
    title = re.sub(r"\((?:[mwfdx](?:/[mwfdx]){1,3})\)", " ", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title


def check_visa(description_text: str, tags: list) -> tuple[bool, str]:
    tag_set = {str(t).strip().lower() for t in (tags or [])}
    hit_tags = tag_set & VISA_TAGS
    if hit_tags:
        return True, f"tag match: {', '.join(sorted(hit_tags))}"

    text = (description_text or "").lower()
    hits = [kw for kw in VISA_KEYWORDS if kw in text]
    if hits:
        return True, f"keyword match: {', '.join(hits[:3])}"

    return False, "no visa/relocation/Blue Card signal found in tags or text"


def check_english(description_text: str) -> tuple[Optional[bool], str]:
    text = (description_text or "").lower()
    if not text.strip():
        return None, "no description text available to check language"

    for phrase in ENGLISH_EXPLICIT_PHRASES:
        if phrase in text:
            return True, f"explicit mention: '{phrase}'"

    words = _WORD_RE.findall(text)
    if len(words) < 15:
        return None, "description too short for a reliable language heuristic"

    de_count = sum(1 for w in words if w in GERMAN_STOPWORDS)
    en_count = sum(1 for w in words if w in ENGLISH_STOPWORDS)

    if en_count >= 3 and en_count > de_count:
        return True, f"heuristic: english stopwords {en_count} > german {de_count}"
    if de_count >= 3 and de_count > en_count:
        return False, f"heuristic: german stopwords {de_count} > english {en_count}"

    return None, f"heuristic inconclusive (en={en_count}, de={de_count})"


def _has_qualifier(norm_title: str) -> bool:
    if _QUALIFIER_RE.search(norm_title):
        return True
    return any(phrase in norm_title for phrase in _QUALIFIER_PHRASES)


def check_title(title: str, target_titles: list) -> tuple[bool, str]:
    norm = _normalize_title(title)

    for kw in ROLE_KEYWORDS:
        if kw in norm:
            return True, f"keyword match: '{kw}'"

    if _SOFTWARE_ENGINEER_PHRASE in norm:
        if _has_qualifier(norm) or _BACKEND_RE.search(norm):
            return True, f"keyword match: '{_SOFTWARE_ENGINEER_PHRASE}' + AI/ML/backend qualifier"
        return False, f"'{_SOFTWARE_ENGINEER_PHRASE}' found but no AI/ML/backend qualifier"

    if not _has_qualifier(norm):
        return False, "no AI/ML/LLM/agent qualifier found in title"

    best_score = 0
    best_target = None
    for target in target_titles:
        score = fuzz.token_set_ratio(norm, target.lower())
        if score > best_score:
            best_score = score
            best_target = target

    if best_score >= TITLE_FUZZY_THRESHOLD:
        return True, f"fuzzy match vs '{best_target}' (score={best_score:.0f})"

    return False, f"best fuzzy match vs '{best_target}' only scored {best_score:.0f}"


def evaluate_job(job: dict, profile: dict) -> MatchResult:
    description_text = job.get("description_text", "") or ""
    tags = job.get("tags", []) or []
    title = job.get("title", "") or ""
    target_titles = profile["role_target"]["target_titles"]

    visa_ok, visa_reason = check_visa(description_text, tags)
    english_ok, english_reason = check_english(description_text)
    title_ok, title_reason = check_title(title, target_titles)

    flags = []
    if english_ok is None:
        flags.append("English requirement unconfirmed — verify manually before submitting")
    if visa_ok and "keyword match" in visa_reason:
        flags.append("Visa signal from free-text keyword only, not a structured tag — verify")

    qualifies = visa_ok and title_ok and english_ok is not False

    return MatchResult(
        qualifies=qualifies,
        visa_ok=visa_ok,
        visa_reason=visa_reason,
        english_ok=english_ok,
        english_reason=english_reason,
        title_ok=title_ok,
        title_reason=title_reason,
        flags=flags,
    )
