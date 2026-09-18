"""Free-text country detection for sources with no structured country field.

Only Arbeitnow needs this. VisaSponsor.jobs filters by a real `country`
query param (its scraper builds that query directly from
config.ALLOWED_COUNTRIES). EnglishJobs.de is a dedicated Germany-only site
with no country filter of any kind -- see its scraper's docstring for what
that means and what was checked.

This is a heuristic over Arbeitnow's free-text `location` field -- there is
no structured country on that API, only a place name string (e.g.
"Bonn-Ramersdorf", "Bristol", "Berlin, Germany"). It is necessarily
incomplete:

- A location that names or contains a city/country we recognize as
  ALLOWED -> allowed.
- A location that names or contains a city/country we recognize as some
  OTHER, specific, not-allowed place -> excluded.
- A location with nothing recognizable at all -> defaults to ALLOWED. Most
  genuine German postings on Arbeitnow show a bare city name with no
  country suffix at all (confirmed live: "Bonn-Ramersdorf", "Karlsruhe",
  "Munich" all appeared with no literal "Germany" anywhere in the string).
  Requiring an explicit match would silently drop the majority of real
  German postings, which is worse than occasionally letting through a
  small-town listing this heuristic doesn't recognize.

Neither hint list is exhaustive -- a small town missing from both, with no
country name in the text either, falls through to the default-allow above.
Deliberately excludes bare 2-3 letter codes ("de", "no", "ie", "us", "uk")
as hints: they collide with ordinary words and other countries' names
("no" is an English word, "de" is a substring of "Sweden" and "Denmark"),
which would produce silent false matches.
"""
from . import config

_ALLOWED_HINTS = {
    "Germany": [
        "germany", "deutschland", "berlin", "munich", "münchen", "hamburg",
        "frankfurt", "cologne", "köln", "bonn", "düsseldorf", "stuttgart",
        "karlsruhe", "leipzig", "dresden", "hannover", "nuremberg",
        "nürnberg", "essen", "dortmund", "bremen", "mannheim", "bielefeld",
    ],
    "Netherlands": [
        "netherlands", "nederland", "holland", "amsterdam", "rotterdam",
        "the hague", "den haag", "utrecht", "eindhoven",
    ],
    "Ireland": ["ireland", "dublin", "cork", "galway", "limerick"],
    "Sweden": ["sweden", "stockholm", "gothenburg", "göteborg", "malmö", "malmo"],
    "France": ["france", "paris", "lyon", "marseille", "toulouse", "nice", "bordeaux"],
    "Denmark": ["denmark", "copenhagen", "københavn", "aarhus", "odense"],
    "Norway": ["norway", "oslo", "bergen", "trondheim"],
    "United Kingdom": [
        "united kingdom", "great britain", "england", "scotland", "wales",
        "london", "manchester", "bristol", "birmingham", "edinburgh",
        "glasgow", "leeds",
    ],
    "Finland": ["finland", "helsinki", "espoo", "tampere"],
    "Spain": ["spain", "madrid", "barcelona", "valencia", "seville"],
    "Canada": ["canada", "toronto", "vancouver", "montreal", "ottawa", "calgary"],
}

# Representative, non-exhaustive set of other commonly-seen countries --
# just enough to positively detect "not on the allowed list" for the cases
# most likely to actually show up (e.g. Austria/Switzerland are common
# neighbors on a German job board).
_OTHER_COUNTRY_HINTS = {
    "Austria": ["austria", "vienna", "wien", "graz"],
    "Switzerland": ["switzerland", "zurich", "zürich", "geneva", "genève", "basel", "bern"],
    "Poland": ["poland", "warsaw", "warszawa", "kraków", "krakow"],
    "Italy": ["italy", "rome", "roma", "milan", "milano"],
    "Portugal": ["portugal", "lisbon", "lisboa", "porto"],
    "Belgium": ["belgium", "brussels", "bruxelles", "antwerp"],
    "Czech Republic": ["czech republic", "prague", "praha"],
    "United States": ["united states", "usa", "u.s.a"],
    "India": ["india", "bangalore", "bengaluru", "mumbai", "delhi", "hyderabad", "pune"],
}


def country_for_location(location: str, tags: list | None = None) -> str | None:
    """Best-effort country name for a free-text location string, checked
    against both allowed and other-known hints. None when nothing
    recognizable is found.
    """
    text = f"{location or ''} {' '.join(tags or [])}".lower()
    for country, hints in _ALLOWED_HINTS.items():
        if any(h in text for h in hints):
            return country
    for country, hints in _OTHER_COUNTRY_HINTS.items():
        if any(h in text for h in hints):
            return country
    return None


def is_allowed(location: str, tags: list | None = None) -> tuple[bool, str]:
    country = country_for_location(location, tags)
    if country is None:
        return True, "no recognizable country in location text — defaulting to allow"
    if country in config.ALLOWED_COUNTRIES:
        return True, f"matched allowed country: {country}"
    return False, f"matched non-allowed country: {country}"
