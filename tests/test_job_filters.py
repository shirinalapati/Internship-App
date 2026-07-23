"""
Tests for matching/job_filters.py

Pure logic, no external services — covers the edge cases called out in review:
company-size substring false positives, citizenship phrase detection,
location matching, position keyword matching (title + description), and
the normalize/apply contract.
"""
import pytest

from matching.job_filters import (
    _company_is_large,
    _passes_citizenship,
    _passes_location,
    _passes_position,
    _passes_company_size,
    _passes_avoid_companies,
    _passes_target_companies,
    normalize_filters,
    has_active_filters,
    apply_filters,
)


def _job(**kwargs):
    base = {"company": "", "title": "", "location": "", "description": ""}
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# _company_is_large — exact canonical matching, no substring false positives
# ---------------------------------------------------------------------------
class TestCompanyIsLarge:
    @pytest.mark.parametrize("company", [
        "Google", "google", "Google LLC", "Google, Inc.", "Amazon", "Amazon.com, Inc.",
        "Meta", "Meta Platforms", "Microsoft", "JPMorgan Chase", "Stripe, Inc.",
        "Lockheed Martin", "The Walt Disney Company",
    ])
    def test_known_large(self, company):
        assert _company_is_large(company) is True

    @pytest.mark.parametrize("company", [
        "Go",          # must NOT match "google" via substring
        "GoTo",        # must NOT match "google"
        "Xerox",       # must NOT match "x"/twitter
        "Goggle Labs", # typo'd unknown startup
        "TinyStartup",
        "Acme Co",
        "",
        "Notion",      # well-known but not in the curated large set → not large
    ])
    def test_not_large(self, company):
        assert _company_is_large(company) is False

    def test_alias_x_to_twitter(self):
        assert _company_is_large("X") is True
        assert _company_is_large("X Corp") is True


# ---------------------------------------------------------------------------
# _passes_company_size — two honest buckets
# ---------------------------------------------------------------------------
class TestCompanySize:
    def test_no_filter_passes_all(self):
        assert _passes_company_size(_job(company="Google"), set()) is True
        assert _passes_company_size(_job(company="Tiny"), set()) is True

    def test_large_only(self):
        assert _passes_company_size(_job(company="Google"), {"large"}) is True
        assert _passes_company_size(_job(company="Tiny"), {"large"}) is False

    def test_not_large_only(self):
        assert _passes_company_size(_job(company="Google"), {"not_large"}) is False
        assert _passes_company_size(_job(company="Tiny"), {"not_large"}) is True

    def test_both_selected_passes_all(self):
        assert _passes_company_size(_job(company="Google"), {"large", "not_large"}) is True
        assert _passes_company_size(_job(company="Tiny"), {"large", "not_large"}) is True


# ---------------------------------------------------------------------------
# _passes_citizenship — citizen_only / exclude_citizen semantics
# ---------------------------------------------------------------------------
class TestCitizenship:
    citizen_job = _job(title="SWE Intern 🇺🇸", description="US citizenship required")
    clearance_job = _job(title="Defense Intern", description="active secret clearance needed")
    no_sponsor_job = _job(title="Backend Intern 🛂", description="does not offer sponsorship")
    open_job = _job(title="Frontend Intern", description="great role, all welcome")

    def test_any_passes_all(self):
        for j in (self.citizen_job, self.no_sponsor_job, self.open_job):
            assert _passes_citizenship(j, "any") is True

    def test_citizen_only_keeps_citizen_jobs(self):
        assert _passes_citizenship(self.citizen_job, "citizen_only") is True
        assert _passes_citizenship(self.clearance_job, "citizen_only") is True
        assert _passes_citizenship(self.open_job, "citizen_only") is False

    def test_exclude_citizen_hides_citizen_and_no_sponsor(self):
        assert _passes_citizenship(self.citizen_job, "exclude_citizen") is False
        assert _passes_citizenship(self.no_sponsor_job, "exclude_citizen") is False
        assert _passes_citizenship(self.open_job, "exclude_citizen") is True


# ---------------------------------------------------------------------------
# _passes_location
# ---------------------------------------------------------------------------
class TestLocation:
    def test_no_filter(self):
        assert _passes_location(_job(location="Austin, TX"), []) is True

    def test_city_substring(self):
        assert _passes_location(_job(location="New York, NY"), ["new york"]) is True
        assert _passes_location(_job(location="Seattle, WA"), ["new york"]) is False

    def test_state_match(self):
        assert _passes_location(_job(location="San Diego, CA"), ["CA"]) is True

    def test_remote(self):
        assert _passes_location(_job(location="Remote, USA"), ["Remote"]) is True
        assert _passes_location(_job(location="Austin, TX"), ["Remote"]) is False

    def test_any_of_multiple(self):
        job = _job(location="Boston, MA")
        assert _passes_location(job, ["New York", "Boston"]) is True


# ---------------------------------------------------------------------------
# _passes_position — title + description, word-boundary short tokens
# ---------------------------------------------------------------------------
class TestPosition:
    def test_no_filter(self):
        assert _passes_position(_job(title="Software Engineer Intern"), set()) is True

    def test_title_match(self):
        assert _passes_position(_job(title="Frontend Engineer Intern"), {"frontend"}) is True

    def test_description_match_when_title_generic(self):
        # Generic title, role detail only in the description.
        job = _job(title="Summer 2026 Intern", description="Work on our machine learning platform")
        assert _passes_position(job, {"machine_learning"}) is True

    def test_short_token_word_boundary(self):
        # "ai" should not match inside "maintain"; should match standalone "AI".
        assert _passes_position(_job(title="Software Maintainer Intern"), {"machine_learning"}) is False
        assert _passes_position(_job(title="AI Research Intern"), {"machine_learning"}) is True

    def test_cloud_category(self):
        assert _passes_position(_job(title="Cloud Engineer Intern"), {"cloud"}) is True

    def test_kotlin_mobile(self):
        assert _passes_position(_job(title="Intern", description="Android app in Kotlin"), {"mobile"}) is True

    def test_no_match(self):
        assert _passes_position(_job(title="Marketing Intern"), {"backend"}) is False


# ---------------------------------------------------------------------------
# _passes_avoid_companies
# ---------------------------------------------------------------------------
class TestAvoidCompanies:
    def test_no_filter(self):
        assert _passes_avoid_companies(_job(company="Amazon"), []) is True

    def test_excludes_match(self):
        assert _passes_avoid_companies(_job(company="Amazon"), ["amazon"]) is False
        assert _passes_avoid_companies(_job(company="Google"), ["amazon"]) is True

    def test_no_substring_false_positive(self):
        # "Meta" must not exclude "Metamorphic Labs" (meta is a substring, not a word).
        assert _passes_avoid_companies(_job(company="Metamorphic Labs"), ["Meta"]) is True
        assert _passes_avoid_companies(_job(company="Meta"), ["Meta"]) is False

    def test_matches_whole_word_with_legal_suffix(self):
        # Canonicalization strips suffixes so "Amazon" still excludes real Amazon entities.
        assert _passes_avoid_companies(_job(company="Amazon.com Inc"), ["Amazon"]) is False
        assert _passes_avoid_companies(_job(company="Amazon Web Services"), ["Amazon"]) is False


# ---------------------------------------------------------------------------
# _passes_target_companies — include-only big-company filter
# ---------------------------------------------------------------------------
class TestTargetCompanies:
    def test_no_filter(self):
        assert _passes_target_companies(_job(company="TinyStartup"), []) is True

    def test_includes_only_selected(self):
        assert _passes_target_companies(_job(company="Google"), ["Google"]) is True
        assert _passes_target_companies(_job(company="TinyStartup"), ["Google"]) is False

    def test_matches_legal_suffix_variants(self):
        assert _passes_target_companies(_job(company="Amazon.com Inc"), ["Amazon"]) is True
        assert _passes_target_companies(_job(company="Amazon Web Services"), ["Amazon"]) is True

    def test_no_substring_false_positive(self):
        assert _passes_target_companies(_job(company="Metamorphic Labs"), ["Meta"]) is False

    def test_blank_company_excluded(self):
        assert _passes_target_companies(_job(company=""), ["Google"]) is False


# ---------------------------------------------------------------------------
# normalize_filters / has_active_filters / apply_filters
# ---------------------------------------------------------------------------
class TestNormalizeAndApply:
    def test_normalize_empty(self):
        n = normalize_filters(None)
        assert has_active_filters(n) is False

    def test_normalize_accepts_comma_string_and_list(self):
        n = normalize_filters({"locations": "New York, Boston", "avoid_companies": ["Meta"]})
        assert n["locations"] == ["New York", "Boston"]
        assert n["avoid_companies"] == ["Meta"]

    def test_normalize_legacy_sizes_collapse(self):
        n = normalize_filters({"company_sizes": ["startup", "midsize"]})
        assert n["company_sizes"] == ["not_large"]

    def test_normalize_drops_invalid_position_and_citizenship(self):
        n = normalize_filters({"positions": ["frontend", "bogus"], "citizenship": "weird"})
        assert n["positions"] == ["frontend"]
        assert n["citizenship"] == "any"

    def test_apply_end_to_end(self):
        jobs = [
            _job(company="Google", title="Software Engineer Intern", location="Mountain View, CA"),
            _job(company="TinyStartup", title="Frontend Engineer Intern", location="New York, NY"),
            _job(company="Lockheed Martin", title="SWE Intern 🇺🇸", location="Bethesda, MD", description="US citizenship required"),
            _job(company="Amazon", title="Data Scientist Intern", location="Seattle, WA", description="analytics"),
        ]
        # Non-citizen + avoid Amazon + NY → only TinyStartup
        out = apply_filters(jobs, {
            "citizenship": "exclude_citizen",
            "avoid_companies": "Amazon",
            "locations": ["New York"],
        })
        assert [j["company"] for j in out] == ["TinyStartup"]

    def test_apply_no_filters_returns_original(self):
        jobs = [_job(company="A"), _job(company="B")]
        assert apply_filters(jobs, {}) is jobs

    def test_normalize_target_companies(self):
        n = normalize_filters({"target_companies": ["Google", "Meta"]})
        assert n["target_companies"] == ["Google", "Meta"]
        assert has_active_filters(n) is True

    def test_apply_target_companies_restricts(self):
        jobs = [
            _job(company="Google", title="SWE Intern"),
            _job(company="TinyStartup", title="SWE Intern"),
            _job(company="Nvidia", title="SWE Intern"),
        ]
        out = apply_filters(jobs, {"target_companies": ["Google", "Nvidia"]})
        assert sorted(j["company"] for j in out) == ["Google", "Nvidia"]
