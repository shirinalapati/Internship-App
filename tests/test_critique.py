"""
Tests for the Critique feature: the critique_resume_to_json Sonnet wrapper,
the weekly quota helpers, and the /api/critique-resume endpoint.

External services (Anthropic) are always mocked — no real API calls.
"""
import json
from unittest.mock import MagicMock, patch

import pytest


def _mock_response(payload: dict) -> MagicMock:
    msg = MagicMock()
    msg.content = [MagicMock(text=json.dumps(payload))]
    msg.stop_reason = "end_turn"
    return msg


SAMPLE_CRITIQUE_PAYLOAD = {
    "name": "Jane Doe",
    "email": "jane@example.com",
    "phone": "555-123-4567",
    "website": "",
    "github": "",
    "linkedin": "",
    "education": [
        {"school": "State University", "location": "Austin, TX", "degree": "B.S. CS", "dates": "2021-2025"}
    ],
    "experience": [
        {
            "company": "Acme Corp",
            "location": "San Francisco, CA",
            "title": "Software Engineering Intern",
            "dates": "May 2024 - Aug 2024",
            "bullets": [
                {"id": "b1", "text": "Utilized Python to help build features"},
                {"id": "b2", "text": "Reduced query latency 43% by adding a Redis cache serving 2M req/day"},
            ],
        }
    ],
    "projects": [],
    "skills": {"Programming Languages": "Python, JavaScript"},
    "detected_category": "software",
    "critiques": [
        {"bullet_id": "b1", "severity": "red", "comment": "Vague — name the feature and the outcome."},
        {"bullet_id": "b2", "severity": "green", "comment": "Specific and quantified — do more of this."},
    ],
}


# ---------------------------------------------------------------------------
# critique_resume_to_json — unit tests
# ---------------------------------------------------------------------------

class TestCritiqueResumeToJson:
    def test_parses_structured_result(self):
        from resume_critique.critique_resume import critique_resume_to_json

        with patch("resume_critique.critique_resume.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = _mock_response(SAMPLE_CRITIQUE_PAYLOAD)
            result = critique_resume_to_json("resume text")

        assert result["name"] == "Jane Doe"
        assert result["detected_category"] == "software"
        assert len(result["critiques"]) == 2
        assert result["experience"][0]["bullets"][0]["id"] == "b1"

    def test_strips_markdown_fences(self):
        from resume_critique.critique_resume import critique_resume_to_json

        fenced = f"```json\n{json.dumps(SAMPLE_CRITIQUE_PAYLOAD)}\n```"
        msg = MagicMock()
        msg.content = [MagicMock(text=fenced)]
        msg.stop_reason = "end_turn"

        with patch("resume_critique.critique_resume.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = msg
            result = critique_resume_to_json("resume text")

        assert result["name"] == "Jane Doe"

    def test_invalid_detected_category_falls_back(self):
        from resume_critique.critique_resume import critique_resume_to_json

        payload = {**SAMPLE_CRITIQUE_PAYLOAD, "detected_category": "not_a_real_category"}
        with patch("resume_critique.critique_resume.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = _mock_response(payload)
            result = critique_resume_to_json("resume text")

        assert result["detected_category"] == "other"

    def test_target_category_used_when_model_output_invalid(self):
        from resume_critique.critique_resume import critique_resume_to_json

        payload = {**SAMPLE_CRITIQUE_PAYLOAD, "detected_category": "garbage"}
        with patch("resume_critique.critique_resume.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = _mock_response(payload)
            result = critique_resume_to_json("resume text", target_category="data_ml")

        assert result["detected_category"] == "data_ml"

    def test_drops_malformed_critique_entries(self):
        from resume_critique.critique_resume import critique_resume_to_json

        payload = {
            **SAMPLE_CRITIQUE_PAYLOAD,
            "critiques": [
                {"bullet_id": "b1", "severity": "red", "comment": "ok"},
                {"bullet_id": "b2", "severity": "purple", "comment": "invalid severity"},
                {"severity": "green", "comment": "missing bullet_id"},
                "not even a dict",
            ],
        }
        with patch("resume_critique.critique_resume.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = _mock_response(payload)
            result = critique_resume_to_json("resume text")

        assert result["critiques"] == [{"bullet_id": "b1", "severity": "red", "comment": "ok"}]

    def test_truncated_json_raises_runtime_error(self):
        from resume_critique.critique_resume import critique_resume_to_json

        msg = MagicMock()
        msg.content = [MagicMock(text='{"name": "Truncated"')]
        msg.stop_reason = "max_tokens"

        with patch("resume_critique.critique_resume.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = msg
            with pytest.raises(RuntimeError, match="max_tokens"):
                critique_resume_to_json("resume text")

    def test_honors_preserved_verbatim(self):
        """Bug #79 (content-fidelity): an Honors & Awards section under Education
        must survive the parse, not be silently dropped."""
        from resume_critique.critique_resume import critique_resume_to_json

        payload = {
            **SAMPLE_CRITIQUE_PAYLOAD,
            "honors": [
                "AP Scholar, 2022-2023",
                "AP Scholar with Honor, 2024",
                "Level 3, State Honors in Piano, Music Teachers Association of California, 2021-2022",
            ],
        }
        with patch("resume_critique.critique_resume.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = _mock_response(payload)
            result = critique_resume_to_json("resume text")

        assert result["honors"] == [
            "AP Scholar, 2022-2023",
            "AP Scholar with Honor, 2024",
            "Level 3, State Honors in Piano, Music Teachers Association of California, 2021-2022",
        ]

    def test_honors_defaults_to_empty_list_when_absent(self):
        """SAMPLE_CRITIQUE_PAYLOAD has no 'honors' key — must not KeyError, and must
        normalize to []."""
        from resume_critique.critique_resume import critique_resume_to_json

        with patch("resume_critique.critique_resume.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = _mock_response(SAMPLE_CRITIQUE_PAYLOAD)
            result = critique_resume_to_json("resume text")

        assert result["honors"] == []

    def test_honors_non_list_normalizes_to_empty_list(self):
        """A malformed (non-list) 'honors' field from the model must not crash the
        pipeline — normalize defensively to []."""
        from resume_critique.critique_resume import critique_resume_to_json

        payload = {**SAMPLE_CRITIQUE_PAYLOAD, "honors": "not a list"}
        with patch("resume_critique.critique_resume.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = _mock_response(payload)
            result = critique_resume_to_json("resume text")

        assert result["honors"] == []

    def test_honors_drops_non_string_and_blank_entries(self):
        from resume_critique.critique_resume import critique_resume_to_json

        payload = {**SAMPLE_CRITIQUE_PAYLOAD, "honors": ["Real honor", "", None, 42, "  "]}
        with patch("resume_critique.critique_resume.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = _mock_response(payload)
            result = critique_resume_to_json("resume text")

        assert result["honors"] == ["Real honor"]


# ---------------------------------------------------------------------------
# to_compile_schema — honors passthrough (Bug #79 fix)
# ---------------------------------------------------------------------------

class TestToCompileSchemaHonors:
    def test_honors_passthrough_when_present(self):
        from resume_critique.critique_resume import to_compile_schema

        structured = {**SAMPLE_CRITIQUE_PAYLOAD, "honors": ["AP Scholar, 2022-2023"]}
        result = to_compile_schema(structured)
        assert result["honors"] == ["AP Scholar, 2022-2023"]

    def test_honors_defaults_to_empty_list_when_absent(self):
        """SAMPLE_CRITIQUE_PAYLOAD predates the honors field — to_compile_schema must
        not KeyError and must default honors to [] so downstream template rendering
        (which checks truthiness) behaves exactly as it did before this field existed."""
        from resume_critique.critique_resume import to_compile_schema

        assert "honors" not in SAMPLE_CRITIQUE_PAYLOAD
        result = to_compile_schema(SAMPLE_CRITIQUE_PAYLOAD)
        assert result["honors"] == []

    def test_bullets_still_converted_to_plain_strings(self):
        """Regression: adding honors passthrough must not disturb the existing
        {id, text} -> text bullet conversion for experience/projects."""
        from resume_critique.critique_resume import to_compile_schema

        result = to_compile_schema(SAMPLE_CRITIQUE_PAYLOAD)
        assert result["experience"][0]["bullets"] == [
            "Utilized Python to help build features",
            "Reduced query latency 43% by adding a Redis cache serving 2M req/day",
        ]


# ---------------------------------------------------------------------------
# quota.py — critique quota helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def fresh_db(tmp_path_factory):
    """File-backed SQLite, not :memory: — the in-memory DB is per-connection and
    breaks once TestClient/asyncio.to_thread touch it from a different thread
    than the one that created it (documented footgun, see test_mcp_api.py)."""
    import job_database as jd
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db_path = tmp_path_factory.mktemp("critiquedb") / "test.db"
    old_engine, old_sessionlocal = jd.engine, jd.SessionLocal
    jd.engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    jd.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=jd.engine)
    jd.Base.metadata.create_all(jd.engine)
    yield
    jd.engine, jd.SessionLocal = old_engine, old_sessionlocal


class TestCritiqueQuota:
    def test_empty_quota_status(self):
        from job_database import SessionLocal
        from quota import get_critique_quota_status, WEEKLY_CRITIQUE_LIMIT

        db = SessionLocal()
        try:
            status = get_critique_quota_status(db, "user_1")
        finally:
            db.close()

        assert status["limit"] == WEEKLY_CRITIQUE_LIMIT
        assert status["used"] == 0
        assert status["remaining"] == WEEKLY_CRITIQUE_LIMIT
        assert status["reset_at"] is None

    def test_record_and_check_quota(self):
        from job_database import SessionLocal
        from quota import get_critique_quota_status, record_critique_request, WEEKLY_CRITIQUE_LIMIT

        db = SessionLocal()
        try:
            for _ in range(WEEKLY_CRITIQUE_LIMIT):
                record_critique_request(db, "user_2")
            db.commit()
            status = get_critique_quota_status(db, "user_2")
        finally:
            db.close()

        assert status["used"] == WEEKLY_CRITIQUE_LIMIT
        assert status["remaining"] == 0
        assert status["reset_at"] is not None

    def test_quota_is_per_user(self):
        from job_database import SessionLocal
        from quota import get_critique_quota_status, record_critique_request

        db = SessionLocal()
        try:
            record_critique_request(db, "user_a")
            db.commit()
            status_a = get_critique_quota_status(db, "user_a")
            status_b = get_critique_quota_status(db, "user_b")
        finally:
            db.close()

        assert status_a["used"] == 1
        assert status_b["used"] == 0


# ---------------------------------------------------------------------------
# job_database.py — critique cache helpers
# ---------------------------------------------------------------------------

class TestCritiqueCache:
    def test_cache_miss_returns_none(self):
        from job_database import get_critique_cache

        assert get_critique_cache("user_1", "somehash", "software") is None

    def test_cache_roundtrip(self):
        from job_database import get_critique_cache, set_critique_cache

        set_critique_cache("user_1", "somehash", "software", SAMPLE_CRITIQUE_PAYLOAD)
        cached = get_critique_cache("user_1", "somehash", "software")

        assert cached is not None
        assert cached["name"] == "Jane Doe"

    def test_cache_is_scoped_to_category(self):
        from job_database import get_critique_cache, set_critique_cache

        set_critique_cache("user_1", "somehash", "software", SAMPLE_CRITIQUE_PAYLOAD)
        assert get_critique_cache("user_1", "somehash", "data_ml") is None


# ---------------------------------------------------------------------------
# /api/critique-resume — endpoint integration tests
# ---------------------------------------------------------------------------

@pytest.fixture
def frontend_static_dir():
    from pathlib import Path
    Path("frontend/build/static").mkdir(parents=True, exist_ok=True)


@pytest.fixture
def client(frontend_static_dir, mock_lifespan_deps, reset_rate_limiter):
    from starlette.testclient import TestClient
    from app import app
    from auth import require_user

    app.dependency_overrides[require_user] = lambda: "test-user-id"
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.pop(require_user, None)


class TestCritiqueEndpoint:
    def test_rejects_non_pdf(self, client):
        resp = client.post(
            "/api/critique-resume",
            files={"resume": ("resume.txt", b"not a pdf", "text/plain")},
        )
        assert resp.status_code == 400

    def test_rejects_empty_file(self, client):
        resp = client.post(
            "/api/critique-resume",
            files={"resume": ("resume.pdf", b"", "application/pdf")},
        )
        assert resp.status_code == 400

    def test_success_returns_json_and_records_quota(self, client, minimal_pdf_bytes):
        with patch(
            "resume_critique.critique_resume.critique_resume_to_json",
            return_value=SAMPLE_CRITIQUE_PAYLOAD,
        ) as mock_critique, patch(
            "resume_tailor.tailor_resume.extract_text_from_pdf", return_value="resume text"
        ):
            resp = client.post(
                "/api/critique-resume",
                files={"resume": ("resume.pdf", minimal_pdf_bytes, "application/pdf")},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Jane Doe"
        assert body["cached"] is False
        mock_critique.assert_called_once()

        from job_database import SessionLocal
        from quota import get_critique_quota_status

        db = SessionLocal()
        try:
            status = get_critique_quota_status(db, "test-user-id")
        finally:
            db.close()
        assert status["used"] == 1

    def test_cache_hit_skips_quota_and_model_call(self, client, minimal_pdf_bytes):
        with patch(
            "resume_critique.critique_resume.critique_resume_to_json",
            return_value=SAMPLE_CRITIQUE_PAYLOAD,
        ) as mock_critique, patch(
            "resume_tailor.tailor_resume.extract_text_from_pdf", return_value="resume text"
        ):
            first = client.post(
                "/api/critique-resume",
                files={"resume": ("resume.pdf", minimal_pdf_bytes, "application/pdf")},
            )
            second = client.post(
                "/api/critique-resume",
                files={"resume": ("resume.pdf", minimal_pdf_bytes, "application/pdf")},
            )

        assert first.status_code == 200 and first.json()["cached"] is False
        assert second.status_code == 200 and second.json()["cached"] is True
        mock_critique.assert_called_once()  # second request never called the model

        from job_database import SessionLocal
        from quota import get_critique_quota_status

        db = SessionLocal()
        try:
            status = get_critique_quota_status(db, "test-user-id")
        finally:
            db.close()
        assert status["used"] == 1  # cache hit didn't burn a second quota slot

    def test_weekly_quota_exceeded_returns_429(self, client, minimal_pdf_bytes):
        from job_database import SessionLocal
        from quota import record_critique_request, WEEKLY_CRITIQUE_LIMIT

        db = SessionLocal()
        try:
            for _ in range(WEEKLY_CRITIQUE_LIMIT):
                record_critique_request(db, "test-user-id")
            db.commit()
        finally:
            db.close()

        with patch(
            "resume_critique.critique_resume.critique_resume_to_json",
            return_value=SAMPLE_CRITIQUE_PAYLOAD,
        ), patch("resume_tailor.tailor_resume.extract_text_from_pdf", return_value="resume text"):
            resp = client.post(
                "/api/critique-resume",
                files={"resume": ("resume.pdf", minimal_pdf_bytes, "application/pdf")},
            )

        assert resp.status_code == 429
        assert resp.json()["detail"]["error"] == "weekly_quota_exceeded"

    def test_model_error_does_not_record_quota(self, client, minimal_pdf_bytes):
        with patch(
            "resume_critique.critique_resume.critique_resume_to_json",
            side_effect=RuntimeError("boom"),
        ), patch("resume_tailor.tailor_resume.extract_text_from_pdf", return_value="resume text"):
            resp = client.post(
                "/api/critique-resume",
                files={"resume": ("resume.pdf", minimal_pdf_bytes, "application/pdf")},
            )

        assert resp.status_code == 500

        from job_database import SessionLocal
        from quota import get_critique_quota_status

        db = SessionLocal()
        try:
            status = get_critique_quota_status(db, "test-user-id")
        finally:
            db.close()
        assert status["used"] == 0  # a failed attempt must never burn quota

    def test_usage_endpoint_includes_critique(self, client):
        resp = client.get("/api/usage")
        assert resp.status_code == 200
        body = resp.json()
        assert "critique" in body
        assert body["critique"]["limit"] == 3


# ---------------------------------------------------------------------------
# /api/critique-resume/rewrite — endpoint integration tests
# ---------------------------------------------------------------------------

REWRITTEN_PAYLOAD = {
    **{k: v for k, v in SAMPLE_CRITIQUE_PAYLOAD.items() if k != "critiques"},
    "experience": [
        {
            "company": "Acme Corp",
            "location": "San Francisco, CA",
            "title": "Software Engineering Intern",
            "dates": "May 2024 - Aug 2024",
            "bullets": [
                {"id": "b1", "text": "Utilized Python to help build features"},  # unchanged (not critiqued)
                {"id": "b2", "text": "Reduced query latency from 190ms to 40ms by adding a Redis cache serving 2M req/day"},  # rewritten
            ],
        }
    ],
}


class TestCritiqueRewriteEndpoint:
    def _critiques(self):
        return [{"bullet_id": "b2", "severity": "yellow", "comment": "needs a before/after number"}]

    def test_requires_structured_resume(self, client):
        resp = client.post("/api/critique-resume/rewrite", json={"critiques": self._critiques()})
        assert resp.status_code == 400

    def test_requires_non_green_critiques(self, client):
        resp = client.post(
            "/api/critique-resume/rewrite",
            json={
                "structured_resume": SAMPLE_CRITIQUE_PAYLOAD,
                "critiques": [{"bullet_id": "b2", "severity": "green", "comment": "great as-is"}],
            },
        )
        assert resp.status_code == 400

    def test_success_returns_rewrite_and_pdf(self, client):
        with patch(
            "resume_critique.critique_resume.apply_critique_rewrite", return_value=REWRITTEN_PAYLOAD
        ) as mock_rewrite, patch(
            "resume_tailor.tailor_resume.compile_resume_json_to_pdf",
            return_value=(b"%PDF-fake-bytes", {"pages": 1}),
        ) as mock_compile:
            resp = client.post(
                "/api/critique-resume/rewrite",
                json={
                    "structured_resume": SAMPLE_CRITIQUE_PAYLOAD,
                    "critiques": self._critiques(),
                    "extra_context": "targeting backend roles",
                },
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["rewritten_bullet_ids"] == ["b2"]
        assert body["structured_resume"]["experience"][0]["bullets"][1]["text"].startswith("Reduced query latency")
        import base64
        assert base64.b64decode(body["pdf_base64"]) == b"%PDF-fake-bytes"
        mock_rewrite.assert_called_once()
        mock_compile.assert_called_once()

        from job_database import SessionLocal
        from quota import get_tailor_quota_status

        db = SessionLocal()
        try:
            status = get_tailor_quota_status(db, "test-user-id")
        finally:
            db.close()
        assert status["used"] == 1  # consumes the TAILOR quota, not the critique quota

    def test_green_only_critiques_are_filtered_out_before_rewrite(self, client):
        with patch(
            "resume_critique.critique_resume.apply_critique_rewrite", return_value=REWRITTEN_PAYLOAD
        ) as mock_rewrite, patch(
            "resume_tailor.tailor_resume.compile_resume_json_to_pdf",
            return_value=(b"%PDF-fake-bytes", {}),
        ):
            client.post(
                "/api/critique-resume/rewrite",
                json={
                    "structured_resume": SAMPLE_CRITIQUE_PAYLOAD,
                    "critiques": [
                        {"bullet_id": "b1", "severity": "green", "comment": "exemplary"},
                        {"bullet_id": "b2", "severity": "yellow", "comment": "needs a number"},
                    ],
                },
            )

        sent_critiques = mock_rewrite.call_args[0][1]
        assert [c["bullet_id"] for c in sent_critiques] == ["b2"]

    def test_template_id_threaded_to_compile(self, client):
        with patch(
            "resume_critique.critique_resume.apply_critique_rewrite", return_value=REWRITTEN_PAYLOAD
        ), patch(
            "resume_tailor.tailor_resume.compile_resume_json_to_pdf",
            return_value=(b"%PDF-fake-bytes", {"pages": 1}),
        ) as mock_compile:
            resp = client.post(
                "/api/critique-resume/rewrite",
                json={
                    "structured_resume": SAMPLE_CRITIQUE_PAYLOAD,
                    "critiques": self._critiques(),
                    "template_id": "modern",
                },
            )

        assert resp.status_code == 200
        assert mock_compile.call_args.kwargs.get("template_id") == "modern"

    def test_invalid_template_id_returns_400(self, client):
        resp = client.post(
            "/api/critique-resume/rewrite",
            json={
                "structured_resume": SAMPLE_CRITIQUE_PAYLOAD,
                "critiques": self._critiques(),
                "template_id": "bogus-id",
            },
        )
        assert resp.status_code == 400

    def test_weekly_tailor_quota_exceeded_returns_429(self, client):
        from job_database import SessionLocal
        from quota import record_tailor_request, WEEKLY_TAILOR_LIMIT

        db = SessionLocal()
        try:
            for _ in range(WEEKLY_TAILOR_LIMIT):
                record_tailor_request(db, "test-user-id", "job", "company")
            db.commit()
        finally:
            db.close()

        with patch("resume_critique.critique_resume.apply_critique_rewrite", return_value=REWRITTEN_PAYLOAD), \
             patch("resume_tailor.tailor_resume.compile_resume_json_to_pdf", return_value=(b"%PDF", {})):
            resp = client.post(
                "/api/critique-resume/rewrite",
                json={"structured_resume": SAMPLE_CRITIQUE_PAYLOAD, "critiques": self._critiques()},
            )

        assert resp.status_code == 429
        assert resp.json()["detail"]["error"] == "weekly_quota_exceeded"

    def test_rewrite_error_does_not_record_quota(self, client):
        with patch(
            "resume_critique.critique_resume.apply_critique_rewrite", side_effect=RuntimeError("boom")
        ):
            resp = client.post(
                "/api/critique-resume/rewrite",
                json={"structured_resume": SAMPLE_CRITIQUE_PAYLOAD, "critiques": self._critiques()},
            )

        assert resp.status_code == 500

        from job_database import SessionLocal
        from quota import get_tailor_quota_status

        db = SessionLocal()
        try:
            status = get_tailor_quota_status(db, "test-user-id")
        finally:
            db.close()
        assert status["used"] == 0
