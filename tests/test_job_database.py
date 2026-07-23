"""
Tests for job_database.py

Uses SQLite :memory: (set in conftest.py) so no real database is needed.
Tables are created fresh for each test class via a module-level setup.
"""
import os
import pytest
from datetime import datetime, timedelta

# DATABASE_URL is overridden to sqlite:///:memory: by conftest.py
# Import after env is set
from job_database import (
    Base,
    Job,
    ResumeCache,
    SessionLocal,
    bulk_insert_jobs,
    engine,
    generate_job_hash,
    get_active_jobs,
    get_distinct_active_companies,
    get_job_by_hash,
    get_database_stats,
    get_resume_cache,
    mark_old_jobs_inactive,
    set_resume_cache,
)


@pytest.fixture(autouse=True)
def fresh_db():
    """Drop and recreate all tables before each test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def _job(company="Acme", title="SWE Intern", location="Remote", n=0) -> dict:
    return {
        "company": company,
        "title": f"{title} {n}",
        "location": location,
        "apply_link": f"https://example.com/job/{n}",
        "description": "Great role",
        "required_skills": ["Python", "React"],
        "job_requirements": "2 years exp",
        "source": "github_internships",
        "days_since_posted": 1,
        "date_posted": "2025-03-01",
        "metadata": {},
    }


# ---------------------------------------------------------------------------
# bulk_insert_jobs
# ---------------------------------------------------------------------------

class TestBulkInsertJobs:
    def test_inserts_new_jobs(self):
        jobs = [_job(n=i) for i in range(3)]
        stats = bulk_insert_jobs(jobs)
        assert stats["new_jobs"] == 3

    def test_deduplicates_same_job(self):
        job = _job(n=1)
        stats1 = bulk_insert_jobs([job])
        stats2 = bulk_insert_jobs([job])
        assert stats1["new_jobs"] == 1
        # Second insert is an update, not a new job
        assert stats2["new_jobs"] == 0

    def test_handles_empty_list(self):
        stats = bulk_insert_jobs([])
        assert stats["new_jobs"] == 0

    def test_stores_required_fields(self):
        bulk_insert_jobs([_job(company="Google", n=99)])
        db = SessionLocal()
        try:
            job = db.query(Job).filter_by(company="Google").first()
            assert job is not None
            assert "SWE Intern" in job.title
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Regression: within-batch duplicate must not crash or drop good rows
    # ------------------------------------------------------------------

    def test_within_batch_duplicate_no_error(self):
        """Two identical dicts in one call must not raise UniqueViolation.
        This is the exact production failure: scraper emits two rows with the
        same hash in a single batch → bulk_save_objects → UniqueViolation →
        rollback → 0 new jobs. The fix (dedup + ON CONFLICT upsert) must
        handle this silently."""
        job = _job(n=42)
        stats = bulk_insert_jobs([job, job])  # same job twice
        assert "error" not in stats, f"Unexpected error: {stats.get('error')}"
        assert stats["new_jobs"] == 1
        assert stats["duplicates_collapsed"] == 1
        # Exactly one row should exist in the DB
        db = SessionLocal()
        try:
            assert db.query(Job).count() == 1
        finally:
            db.close()

    def test_within_batch_duplicate_keep_last(self):
        """When two dicts share the same hash, the last one's content wins."""
        first  = dict(_job(n=10), description="first version")
        second = dict(_job(n=10), description="last version")  # same n → same hash
        stats = bulk_insert_jobs([first, second])
        assert stats["new_jobs"] == 1
        assert stats["duplicates_collapsed"] == 1
        db = SessionLocal()
        try:
            row = db.query(Job).first()
            assert row.description == "last version"
        finally:
            db.close()

    def test_cross_batch_upsert_preserves_first_seen(self):
        """Re-inserting an existing hash must preserve first_seen / created_at
        and advance last_seen / updated_at."""
        job = _job(n=7)
        bulk_insert_jobs([job])

        db = SessionLocal()
        try:
            original = db.query(Job).first()
            original_first_seen = original.first_seen
            original_created_at = original.created_at
        finally:
            db.close()

        # Second call with same job (simulates the next daily scrape)
        import time; time.sleep(0.05)  # ensure clock advances slightly
        stats2 = bulk_insert_jobs([job])
        assert stats2["new_jobs"] == 0
        assert stats2["updated_jobs"] == 1

        db = SessionLocal()
        try:
            updated = db.query(Job).first()
            assert updated.first_seen == original_first_seen, "first_seen must be preserved"
            assert updated.created_at == original_created_at, "created_at must be preserved"
            assert updated.last_seen  >= original_first_seen, "last_seen must advance"
            assert updated.updated_at >= original_first_seen, "updated_at must advance"
        finally:
            db.close()

    def test_upsert_reactivates_inactive_job(self):
        """A job previously marked is_active=False must flip back to True when
        it reappears in a scrape batch."""
        job = _job(n=5)
        bulk_insert_jobs([job])

        # Manually deactivate
        db = SessionLocal()
        try:
            row = db.query(Job).first()
            row.is_active = False
            # backdate last_seen so the sweep won't immediately flip it back
            row.last_seen = datetime.utcnow() - timedelta(days=10)
            db.commit()
        finally:
            db.close()

        # Re-scrape the same job
        bulk_insert_jobs([job])

        db = SessionLocal()
        try:
            row = db.query(Job).first()
            assert row.is_active is True, "Reappearing job must be reactivated"
        finally:
            db.close()

    def test_inactive_sweep_commits_after_upsert(self):
        """Jobs not seen in the latest scrape for >3 days must be marked inactive.
        This was previously lost because the whole transaction rolled back."""
        stale = _job(n=1)
        fresh = _job(n=2)
        bulk_insert_jobs([stale, fresh])

        # Backdate stale job's last_seen to simulate it not appearing in the new scrape
        db = SessionLocal()
        try:
            row = db.query(Job).filter(Job.title.like("%1%")).first()
            row.last_seen = datetime.utcnow() - timedelta(days=10)
            db.commit()
        finally:
            db.close()

        # New scrape only contains the fresh job
        stats = bulk_insert_jobs([fresh])
        assert "error" not in stats

        db = SessionLocal()
        try:
            stale_row = db.query(Job).filter(Job.title.like("%1%")).first()
            assert stale_row.is_active is False, "Stale job must be swept inactive"
        finally:
            db.close()

    def test_inactive_sweep_does_not_cross_sources(self):
        """The last_seen sweep must only deactivate jobs from the same source.
        A github_internships startup scrape must not kill ats_greenhouse jobs
        that simply run on a different schedule."""
        ats_job = {**_job(n=10), "source": "ats_greenhouse"}
        github_job = _job(n=11)
        bulk_insert_jobs([ats_job, github_job])

        # Backdate both so the sweep would normally fire
        db = SessionLocal()
        try:
            for row in db.query(Job).filter(Job.title.like("%1%")).all():
                row.last_seen = datetime.utcnow() - timedelta(days=10)
            db.commit()
        finally:
            db.close()

        # Only github_internships refreshed — ATS job must survive
        bulk_insert_jobs([github_job])

        db = SessionLocal()
        try:
            ats_row = db.query(Job).filter(Job.source == "ats_greenhouse").first()
            assert ats_row.is_active is True, "ATS job must not be swept by a github scrape"
        finally:
            db.close()

    def test_summary_has_expected_keys(self):
        stats = bulk_insert_jobs([_job(n=0)])
        for key in ("new_jobs", "updated_jobs", "duplicates_collapsed",
                    "failed_rows", "inactive_jobs", "date_based_inactive_jobs",
                    "total_processed"):
            assert key in stats, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# get_job_by_hash — full-description lookup for resume tailoring
# ---------------------------------------------------------------------------

class TestGetJobByHash:
    """The tailoring endpoint relies on this to fetch the full, untruncated JD."""

    def test_returns_full_description(self):
        job = _job(company="Stripe", n=7)
        job["description"] = "X" * 4000  # full description, far over the old 500 cap
        bulk_insert_jobs([job])
        h = generate_job_hash(job["company"], job["title"], job["location"], job["apply_link"])

        result = get_job_by_hash(h)
        assert result is not None
        assert result["job_hash"] == h
        assert result["description"] == "X" * 4000

    def test_unknown_hash_returns_none(self):
        assert get_job_by_hash("0" * 64) is None

    def test_empty_hash_returns_none(self):
        assert get_job_by_hash("") is None

    def test_finds_inactive_job(self):
        """A soft-deactivated job must still be retrievable (it may be tailored later)."""
        job = _job(company="Datadog", n=3)
        bulk_insert_jobs([job])
        h = generate_job_hash(job["company"], job["title"], job["location"], job["apply_link"])
        db = SessionLocal()
        try:
            db.query(Job).filter_by(job_hash=h).update({"is_active": False})
            db.commit()
        finally:
            db.close()

        result = get_job_by_hash(h)
        assert result is not None
        assert result["company"] == "Datadog"


# ---------------------------------------------------------------------------
# generate_job_hash — path-widening regression
# ---------------------------------------------------------------------------

class TestGenerateJobHash:
    """Verify the widened hash (domain+path, no query string)."""

    def test_same_domain_different_path_differ(self):
        """Two postings at the same job board with different paths must not collide."""
        h1 = generate_job_hash("Acme", "SWE Intern", "Remote",
                               "https://board.com/jobs/req-001")
        h2 = generate_job_hash("Acme", "SWE Intern", "Remote",
                               "https://board.com/jobs/req-002")
        assert h1 != h2, "Different paths must yield different hashes"

    def test_query_string_ignored(self):
        """utm_source and other query params must not affect the hash."""
        base = "https://board.com/jobs/req-001"
        with_utm = base + "?utm_source=Simplify&ref=Simplify"
        h1 = generate_job_hash("Acme", "SWE Intern", "Remote", base)
        h2 = generate_job_hash("Acme", "SWE Intern", "Remote", with_utm)
        assert h1 == h2, "Query string differences must not change the hash"

    def test_trailing_slash_normalised(self):
        """Trailing slash must not produce a different hash."""
        h1 = generate_job_hash("Acme", "SWE Intern", "Remote",
                               "https://board.com/jobs/req-001")
        h2 = generate_job_hash("Acme", "SWE Intern", "Remote",
                               "https://board.com/jobs/req-001/")
        assert h1 == h2, "Trailing slash must be normalised away"

    def test_same_inputs_deterministic(self):
        h1 = generate_job_hash("TikTok", "SWE Intern", "San Jose, CA",
                               "https://lifeattiktok.com/search/123456")
        h2 = generate_job_hash("TikTok", "SWE Intern", "San Jose, CA",
                               "https://lifeattiktok.com/search/123456")
        assert h1 == h2


# ---------------------------------------------------------------------------
# get_active_jobs
# ---------------------------------------------------------------------------

class TestGetActiveJobs:
    def test_returns_all_active(self):
        bulk_insert_jobs([_job(n=i) for i in range(5)])
        jobs = get_active_jobs()
        assert len(jobs) == 5

    def test_respects_limit(self):
        bulk_insert_jobs([_job(n=i) for i in range(10)])
        jobs = get_active_jobs(limit=3)
        assert len(jobs) == 3

    def test_excludes_inactive(self):
        bulk_insert_jobs([_job(n=i) for i in range(3)])
        # Manually deactivate one (fetch first to avoid SQLAlchemy evaluate error)
        db = SessionLocal()
        try:
            job = db.query(Job).first()
            job.is_active = False
            db.commit()
        finally:
            db.close()

        jobs = get_active_jobs()
        assert len(jobs) == 2


# ---------------------------------------------------------------------------
# get_distinct_active_companies — backs the avoid/target-company autocomplete
# ---------------------------------------------------------------------------
class TestGetDistinctActiveCompanies:
    def test_returns_sorted_distinct_names(self):
        bulk_insert_jobs([
            _job(company="Zeta Corp", n=0),
            _job(company="Acme", n=1),
            _job(company="Acme", n=2),  # same company, different posting
        ])
        assert get_distinct_active_companies() == ["Acme", "Zeta Corp"]

    def test_excludes_inactive_jobs(self):
        bulk_insert_jobs([_job(company="Acme", n=0), _job(company="Beta", n=1)])
        db = SessionLocal()
        try:
            job = db.query(Job).filter(Job.company == "Beta").first()
            job.is_active = False
            db.commit()
        finally:
            db.close()

        assert get_distinct_active_companies() == ["Acme"]

    def test_empty_database_returns_empty_list(self):
        assert get_distinct_active_companies() == []


# ---------------------------------------------------------------------------
# mark_old_jobs_inactive
# ---------------------------------------------------------------------------

class TestMarkOldJobsInactive:
    def test_marks_stale_jobs_inactive(self):
        # Insert fresh jobs (days_since_posted=1 so bulk_insert won't deactivate them)
        bulk_insert_jobs([_job(n=i) for i in range(3)])

        # Manually backdate the metadata so jobs look 40 days old
        db = SessionLocal()
        try:
            import json as _json
            for job in db.query(Job).all():
                meta = _json.loads(job.job_metadata or "{}")
                meta["days_since_posted"] = 40
                job.job_metadata = _json.dumps(meta)
            db.commit()
        finally:
            db.close()

        count = mark_old_jobs_inactive(max_days_old=30)
        assert count == 3

    def test_leaves_fresh_jobs_active(self):
        bulk_insert_jobs([_job(n=i) for i in range(2)])
        count = mark_old_jobs_inactive(max_days_old=30)
        assert count == 0


# ---------------------------------------------------------------------------
# get_database_stats
# ---------------------------------------------------------------------------

class TestGetDatabaseStats:
    def test_returns_expected_keys(self):
        bulk_insert_jobs([_job(n=0)])
        stats = get_database_stats()
        assert "total_jobs" in stats
        assert "active_jobs" in stats

    def test_counts_active_jobs(self):
        bulk_insert_jobs([_job(n=i) for i in range(4)])
        stats = get_database_stats()
        assert stats["active_jobs"] == 4


# ---------------------------------------------------------------------------
# ResumeCache (get / set)
# ---------------------------------------------------------------------------

class TestResumeCache:
    def test_set_and_get(self):
        set_resume_cache("user1", "hash123", {"jobs": []}, ["Python"])
        result = get_resume_cache("user1", "hash123")
        assert result is not None
        assert result["skills"] == ["Python"]

    def test_miss_returns_none(self):
        result = get_resume_cache("user1", "nonexistent")
        assert result is None

    def test_different_users_isolated(self):
        set_resume_cache("user1", "h1", {"jobs": [1]}, ["Go"])
        set_resume_cache("user2", "h1", {"jobs": [2]}, ["Rust"])
        r1 = get_resume_cache("user1", "h1")
        r2 = get_resume_cache("user2", "h1")
        assert r1["skills"] == ["Go"]
        assert r2["skills"] == ["Rust"]
