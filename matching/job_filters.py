"""
Deterministic, user-controlled job filters applied BEFORE the LLM matching stage.

These filters are hard constraints supplied by the user on the frontend (location,
position, company size, U.S. citizenship requirement, companies to avoid). Applying
them before scoring keeps results relevant and avoids paying for LLM analysis on jobs
the user has explicitly excluded.

All filters are optional — an empty/None value for a given dimension means "no filtering"
on that dimension, so the default behaviour is unchanged (every job passes).
"""

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Position categories — map a user-facing category to keywords matched against
# the job title AND description. A job passes the position filter if it matches
# ANY selected category.
#
# Keywords are surrounded by word boundaries at match time, so short tokens like
# "ai" / "ml" / "qa" don't produce false positives inside larger words.
# ---------------------------------------------------------------------------
POSITION_KEYWORDS: Dict[str, List[str]] = {
    "software_engineer": ["software engineer", "swe", "software development", "software developer", "programmer"],
    "frontend": ["frontend", "front-end", "front end", "ui engineer", "web developer"],
    "backend": ["backend", "back-end", "back end", "api"],
    "fullstack": ["full stack", "fullstack", "full-stack"],
    "data_science": ["data science", "data scientist", "data analyst", "data analytics", "analytics", "analyst"],
    "data_engineering": ["data engineer", "data engineering", "etl", "data platform"],
    "machine_learning": ["machine learning", "ml engineer", "ml", "artificial intelligence", "ai", "deep learning", "nlp", "computer vision", "llm"],
    "mobile": ["mobile", "ios", "android", "react native", "flutter", "kotlin", "swift"],
    "cloud": ["cloud", "cloud engineer", "aws", "azure", "gcp", "google cloud"],
    "devops": ["devops", "sre", "site reliability", "infrastructure", "platform engineer", "ci/cd"],
    "security": ["security", "cyber", "cybersecurity", "infosec", "appsec"],
    "qa": ["qa", "sdet", "test", "testing", "quality assurance", "quality engineer"],
    "hardware": ["hardware", "embedded", "firmware", "fpga", "asic", "verilog", "vhdl"],
}


# ---------------------------------------------------------------------------
# Company size — we don't scrape headcount, so the only bucket we can identify
# with confidence is "large / enterprise" via a curated set of well-known large
# employers. Everything else is treated as "not large" (startup / mid-size).
# This is a best-effort heuristic surfaced as such in the UI.
#
# Names here are CANONICAL: lowercased, with legal suffixes stripped. Matching is
# an O(1) set lookup after normalizing the job's company the same way (plus an
# alias table for common brand/legal-name differences).
# ---------------------------------------------------------------------------
LARGE_COMPANIES = {
    "google", "alphabet", "meta", "facebook", "amazon", "aws", "apple", "microsoft",
    "netflix", "nvidia", "intel", "ibm", "oracle", "salesforce", "adobe", "cisco",
    "qualcomm", "broadcom", "amd", "dell", "hp", "hewlett packard", "hpe", "sap",
    "vmware", "uber", "lyft", "airbnb", "tesla", "spacex", "paypal", "block", "square",
    "stripe", "snap", "snapchat", "pinterest", "twitter", "linkedin", "tiktok",
    "bytedance", "tencent", "alibaba", "samsung", "sony", "spotify", "atlassian",
    "servicenow", "workday", "snowflake", "databricks", "palantir", "twilio", "shopify",
    "doordash", "instacart", "robinhood", "coinbase", "datadog", "cloudflare",
    "jpmorgan", "jpmorgan chase", "chase", "goldman sachs", "morgan stanley",
    "bank of america", "wells fargo", "citi", "citigroup", "capital one", "american express",
    "visa", "mastercard", "fidelity", "blackrock", "deloitte", "accenture", "pwc", "ey",
    "kpmg", "mckinsey", "boston consulting group", "bcg", "bain",
    "boeing", "lockheed martin", "northrop grumman", "raytheon", "rtx", "general dynamics",
    "general motors", "gm", "ford", "general electric", "ge", "honeywell", "3m", "caterpillar",
    "johnson & johnson", "pfizer", "merck", "abbvie", "medtronic", "unitedhealth", "cvs",
    "walmart", "target", "costco", "home depot", "nike", "disney", "comcast", "nbcuniversal",
    "at&t", "verizon", "t-mobile", "exxonmobil", "chevron", "procter & gamble", "p&g",
    "coca-cola", "pepsico", "mcdonald's", "starbucks", "fedex", "ups", "kbr", "gdit",
    "booz allen hamilton", "leidos", "saic", "mitre", "intuit", "ebay", "yahoo", "dropbox",
    "zoom", "okta", "splunk", "mongodb", "roblox", "epic games", "electronic arts", "ea",
    "activision", "blizzard", "nintendo", "siemens", "bosch", "philips", "schneider electric",
}

# Brand/legal-name aliases → canonical name present in LARGE_COMPANIES.
COMPANY_ALIASES = {
    "x": "twitter",                 # rebrand; bare "x" would otherwise be unmatchable/ambiguous
    "x corp": "twitter",
    "google llc": "google",
    "meta platforms": "meta",
    "amazon web services": "aws",
    "alphabet inc": "alphabet",
    "jp morgan": "jpmorgan",
    "jpmorgan chase & co": "jpmorgan chase",
    "j.p. morgan": "jpmorgan",
    "walt disney": "disney",
    "the walt disney": "disney",
}

# Legal/structural suffixes stripped before lookup so "Google LLC", "Amazon.com Inc"
# and "Stripe, Inc." all collapse to their canonical names.
_LEGAL_SUFFIX_RE = re.compile(
    r"\b("
    r"inc|incorporated|llc|l\.l\.c|llp|ltd|limited|corp|corporation|co|company|"
    r"plc|gmbh|ag|sa|nv|holdings|group|technologies|technology|labs|systems|"
    r"solutions|software|enterprises"
    r")\b\.?",
    flags=re.IGNORECASE,
)


def _normalize(text: str) -> str:
    return (text or "").strip().lower()


def _canonical_company(company: str) -> str:
    """Lowercase, strip a leading 'the', punctuation noise, and legal suffixes."""
    c = _normalize(company)
    if not c:
        return ""
    # Drop ".com" style domains and commas/periods used as separators.
    c = c.replace(".com", " ")
    c = c.replace(",", " ")
    if c.startswith("the "):
        c = c[4:]
    c = _LEGAL_SUFFIX_RE.sub(" ", c)
    # Collapse whitespace.
    c = re.sub(r"\s+", " ", c).strip()
    return c


def _company_is_large(company: str) -> bool:
    """O(1) membership test against the curated large-company set (+ aliases).

    Uses exact canonical-name matching (no substring scan) so names like "Go" or
    "Xerox" are never mistaken for "Google" / "X".
    """
    canonical = _canonical_company(company)
    if not canonical:
        return False
    canonical = COMPANY_ALIASES.get(canonical, canonical)
    return canonical in LARGE_COMPANIES


def _matches_position_keyword(text: str, keyword: str) -> bool:
    """Word-boundary keyword match (so 'ai'/'ml'/'qa' don't match inside words)."""
    return re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", text) is not None


def _job_requires_citizenship(job: Dict[str, Any]) -> bool:
    """True if the posting requires U.S. citizenship (🇺🇸 marker or explicit text)."""
    title = job.get("title", "") or ""
    text = f"{title} {job.get('description', '')}".lower()
    if "🇺🇸" in text:
        return True
    citizenship_phrases = [
        "u.s. citizen", "us citizen", "u.s. citizenship", "us citizenship",
        "must be a citizen", "citizenship required", "citizenship is required",
        "security clearance", "active clearance", "secret clearance", "ts/sci",
    ]
    return any(p in text for p in citizenship_phrases)


def _job_offers_no_sponsorship(job: Dict[str, Any]) -> bool:
    """True if the posting explicitly does NOT offer visa sponsorship (🛂 marker or text)."""
    title = job.get("title", "") or ""
    text = f"{title} {job.get('description', '')}".lower()
    if "🛂" in text:
        return True
    no_sponsor_phrases = [
        "no sponsorship", "does not offer sponsorship", "not offer sponsorship",
        "will not sponsor", "do not sponsor", "unable to sponsor",
        "without sponsorship", "no visa sponsorship", "sponsorship is not available",
    ]
    return any(p in text for p in no_sponsor_phrases)


def normalize_filters(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Coerce a raw filters dict (e.g. parsed from a JSON form field) into a clean,
    validated structure. Returns a dict with consistent types and lowercased values.

    The result is the canonical shape consumed by ``apply_normalized_filters`` and
    ``has_active_filters`` — normalize ONCE per request and reuse it.
    """
    raw = raw or {}

    def _as_str_list(value) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            parts = re.split(r"[,\n;]", value)
        elif isinstance(value, (list, tuple)):
            parts = [str(v) for v in value]
        else:
            return []
        return [p.strip() for p in parts if p and p.strip()]

    citizenship = _normalize(raw.get("citizenship", "any")) or "any"
    if citizenship not in ("any", "citizen_only", "exclude_citizen"):
        citizenship = "any"

    # Company size collapsed to the two buckets we can actually distinguish.
    raw_sizes = {_normalize(x) for x in _as_str_list(raw.get("company_sizes"))}
    # Backward-compat: map legacy startup/midsize values onto "not_large".
    company_sizes = set()
    for s in raw_sizes:
        if s == "large":
            company_sizes.add("large")
        elif s in ("not_large", "startup", "midsize", "mid-size", "small"):
            company_sizes.add("not_large")

    positions = {p for p in (_normalize(x) for x in _as_str_list(raw.get("positions"))) if p in POSITION_KEYWORDS}

    return {
        "locations": _as_str_list(raw.get("locations")),
        "positions": sorted(positions),
        "company_sizes": sorted(company_sizes),
        "citizenship": citizenship,
        "avoid_companies": _as_str_list(raw.get("avoid_companies")),
        # Restrict results to these specific (typically large/well-known) employers.
        "target_companies": _as_str_list(raw.get("target_companies")),
    }


def has_active_filters(normalized: Dict[str, Any]) -> bool:
    """True if a NORMALIZED filters dict actually constrains the result set."""
    if not normalized:
        return False
    return bool(
        normalized.get("locations")
        or normalized.get("positions")
        or normalized.get("company_sizes")
        or normalized.get("avoid_companies")
        or normalized.get("target_companies")
        or normalized.get("citizenship", "any") != "any"
    )


_STATE_ABBREVS: Dict[str, str] = {
    "alabama": "al", "alaska": "ak", "arizona": "az", "arkansas": "ar",
    "california": "ca", "colorado": "co", "connecticut": "ct", "delaware": "de",
    "florida": "fl", "georgia": "ga", "hawaii": "hi", "idaho": "id",
    "illinois": "il", "indiana": "in", "iowa": "ia", "kansas": "ks",
    "kentucky": "ky", "louisiana": "la", "maine": "me", "maryland": "md",
    "massachusetts": "ma", "michigan": "mi", "minnesota": "mn", "mississippi": "ms",
    "missouri": "mo", "montana": "mt", "nebraska": "ne", "nevada": "nv",
    "new hampshire": "nh", "new jersey": "nj", "new mexico": "nm", "new york": "ny",
    "north carolina": "nc", "north dakota": "nd", "ohio": "oh", "oklahoma": "ok",
    "oregon": "or", "pennsylvania": "pa", "rhode island": "ri", "south carolina": "sc",
    "south dakota": "sd", "tennessee": "tn", "texas": "tx", "utah": "ut",
    "vermont": "vt", "virginia": "va", "washington": "wa", "west virginia": "wv",
    "wisconsin": "wi", "wyoming": "wy", "district of columbia": "dc",
}


def _passes_location(job: Dict[str, Any], locations: List[str]) -> bool:
    if not locations:
        return True
    job_location = _normalize(job.get("location", ""))
    for loc in locations:
        loc_l = _normalize(loc)
        if not loc_l:
            continue
        if loc_l in ("remote", "remote only"):
            if "remote" in job_location:
                return True
            continue
        if loc_l in job_location:
            return True
        abbrev = _STATE_ABBREVS.get(loc_l)
        if abbrev and f", {abbrev}" in job_location:
            return True
    return False


def _passes_position(job: Dict[str, Any], positions) -> bool:
    if not positions:
        return True
    # Match against title AND description — SimplifyJobs listings often carry a
    # generic title ("Summer 2026 Intern") with the real role in the description.
    haystack = f"{_normalize(job.get('title', ''))} {_normalize(job.get('description', ''))}"
    for category in positions:
        for kw in POSITION_KEYWORDS.get(category, []):
            if _matches_position_keyword(haystack, kw):
                return True
    return False


def _passes_company_size(job: Dict[str, Any], company_sizes) -> bool:
    if not company_sizes:
        return True
    is_large = _company_is_large(job.get("company", ""))
    if is_large:
        return "large" in company_sizes
    return "not_large" in company_sizes


def _passes_citizenship(job: Dict[str, Any], citizenship: str) -> bool:
    if citizenship == "citizen_only":
        # Only roles that require U.S. citizenship.
        return _job_requires_citizenship(job)
    if citizenship == "exclude_citizen":
        # Hide roles that require citizenship or explicitly refuse sponsorship.
        return not (_job_requires_citizenship(job) or _job_offers_no_sponsorship(job))
    return True  # "any"


def _passes_avoid_companies(job: Dict[str, Any], avoid_companies: List[str]) -> bool:
    if not avoid_companies:
        return True
    company = _canonical_company(job.get("company", ""))
    if not company:
        return True
    for avoided in avoid_companies:
        a = _canonical_company(avoided)
        if not a:
            continue
        # Exact canonical match, or whole-word containment in either direction.
        # Word boundaries stop "Meta" from excluding "Metamorphic Labs".
        if (
            a == company
            or _matches_position_keyword(company, a)
            or _matches_position_keyword(a, company)
        ):
            return False
    return True


def _passes_target_companies(job: Dict[str, Any], target_companies: List[str]) -> bool:
    """Include-only filter: keep a job only if its employer is one of the
    user-selected companies (whole-word/canonical match, mirroring the avoid logic)."""
    if not target_companies:
        return True
    company = _canonical_company(job.get("company", ""))
    if not company:
        return False
    for target in target_companies:
        t = _canonical_company(target)
        if not t:
            continue
        if (
            t == company
            or _matches_position_keyword(company, t)
            or _matches_position_keyword(t, company)
        ):
            return True
    return False


def apply_normalized_filters(jobs: List[Dict[str, Any]], normalized: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Filter ``jobs`` using an ALREADY-normalized filters dict (see normalize_filters).

    Prefer this in request handlers that already normalized once — it avoids
    re-normalizing the same payload repeatedly.
    """
    if not has_active_filters(normalized):
        return jobs

    locations = normalized["locations"]
    positions = normalized["positions"]
    company_sizes = normalized["company_sizes"]
    citizenship = normalized["citizenship"]
    avoid_companies = normalized["avoid_companies"]
    target_companies = normalized.get("target_companies", [])

    filtered = [
        job for job in jobs
        if _passes_avoid_companies(job, avoid_companies)
        and _passes_target_companies(job, target_companies)
        and _passes_location(job, locations)
        and _passes_position(job, positions)
        and _passes_company_size(job, company_sizes)
        and _passes_citizenship(job, citizenship)
    ]

    logger.info(
        f"[Filters] {len(filtered)}/{len(jobs)} jobs passed "
        f"(locations={locations}, positions={sorted(positions)}, "
        f"company_sizes={sorted(company_sizes)}, citizenship={citizenship}, "
        f"avoid={avoid_companies}, target={target_companies})"
    )
    return filtered


def apply_filters(jobs: List[Dict[str, Any]], raw_filters: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filter the job list according to raw (un-normalized) user preferences.

    Convenience wrapper that normalizes then delegates to ``apply_normalized_filters``.
    If no filters are active the original list is returned unchanged.
    """
    return apply_normalized_filters(jobs, normalize_filters(raw_filters))
