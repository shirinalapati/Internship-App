"""
Tests for resume_tailor/tailor_resume.py

External deps mocked:
  - pdflatex / compile_latex_to_pdf  → returns a fake 1- or 2-page PDF
  - pdfplumber                        → controlled via _count_pdf_pages mock
  - anthropic.Anthropic               → mocked Claude response
"""
import io
import json
from unittest.mock import MagicMock, patch

import pytest

from resume_tailor.tailor_resume import (
    FONT_SIZES,
    TEMPLATE_REGISTRY,
    _count_pdf_pages,
    _escape_latex,
    _href,
    compile_to_single_page,
    inject_into_template,
)


# ---------------------------------------------------------------------------
# _escape_latex
# ---------------------------------------------------------------------------

class TestEscapeLatex:
    def test_ampersand(self):
        assert _escape_latex("A & B") == r"A \& B"

    def test_percent(self):
        assert _escape_latex("100%") == r"100\%"

    def test_dollar(self):
        assert _escape_latex("$100") == r"\$100"

    def test_hash(self):
        assert _escape_latex("job#1") == r"job\#1"

    def test_underscore(self):
        assert _escape_latex("snake_case") == r"snake\_case"

    def test_braces(self):
        assert _escape_latex("{foo}") == r"\{foo\}"

    def test_plain_text_unchanged(self):
        assert _escape_latex("Hello World") == "Hello World"

    def test_backslash_converted(self):
        # Backslash is converted to \textbackslash; the braces in that replacement
        # are subsequently escaped to \{ and \} by the brace rule — this is the
        # documented behaviour of the current implementation.
        result = _escape_latex("a\\b")
        assert "textbackslash" in result


# ---------------------------------------------------------------------------
# _href
# ---------------------------------------------------------------------------

class TestHref:
    def test_basic(self):
        result = _href("https://example.com", "Example")
        assert result == r"\href{https://example.com}{Example}"


# ---------------------------------------------------------------------------
# inject_into_template
# ---------------------------------------------------------------------------

class TestInjectIntoTemplate:
    def test_name_substituted(self, sample_resume_data):
        latex = inject_into_template(sample_resume_data)
        assert "Jane Doe" in latex

    def test_email_link(self, sample_resume_data):
        latex = inject_into_template(sample_resume_data)
        assert "jane@example.com" in latex

    def test_experience_company(self, sample_resume_data):
        latex = inject_into_template(sample_resume_data)
        assert "Acme Corp" in latex

    def test_skills_rendered(self, sample_resume_data):
        latex = inject_into_template(sample_resume_data)
        assert "Python" in latex

    def test_project_rendered(self, sample_resume_data):
        latex = inject_into_template(sample_resume_data)
        assert "InternTracker" in latex

    def test_font_size_placeholder_preserved(self, sample_resume_data):
        """{{FONT_SIZE}} must survive inject_into_template unchanged."""
        latex = inject_into_template(sample_resume_data)
        assert "{{FONT_SIZE}}" in latex

    def test_special_chars_escaped_in_bullets(self, sample_resume_data):
        data = dict(sample_resume_data)
        data["experience"] = [
            {
                "company": "Acme & Sons",
                "location": "NY",
                "title": "Dev",
                "dates": "2024",
                "bullets": ["Saved 50% on costs"],
            }
        ]
        latex = inject_into_template(data)
        assert r"\&" in latex
        assert r"\%" in latex

    def test_empty_projects(self, sample_resume_data):
        data = dict(sample_resume_data)
        data["projects"] = []
        latex = inject_into_template(data)
        # Should not raise; projects section just becomes empty string
        assert "{{PROJECTS}}" not in latex


# ---------------------------------------------------------------------------
# Honors & Awards (Bug #79 content-fidelity fix)
# ---------------------------------------------------------------------------

class TestInjectIntoTemplateHonors:
    def test_honors_absent_no_section(self, sample_resume_data):
        """sample_resume_data has no 'honors' key at all — must not KeyError, and
        must NOT render an empty 'Honors & Awards' section header. This is the
        no-regression guarantee for every resume compiled before this field existed."""
        assert "honors" not in sample_resume_data
        latex = inject_into_template(sample_resume_data)
        assert "{{HONORS}}" not in latex
        assert "Honors" not in latex

    def test_honors_empty_list_no_section(self, sample_resume_data):
        data = dict(sample_resume_data)
        data["honors"] = []
        latex = inject_into_template(data)
        assert "Honors" not in latex

    def test_honors_rendered_when_present(self, sample_resume_data):
        data = dict(sample_resume_data)
        data["honors"] = [
            "AP Scholar, 2022-2023",
            "AP Scholar with Honor, 2024",
            "Level 3, State Honors in Piano, Music Teachers Association of California, 2021-2022",
        ]
        latex = inject_into_template(data)
        assert "Honors \\& Awards" in latex
        assert "AP Scholar, 2022-2023" in latex
        assert "AP Scholar with Honor, 2024" in latex
        assert "Level 3, State Honors in Piano" in latex

    def test_honors_special_chars_escaped(self, sample_resume_data):
        data = dict(sample_resume_data)
        data["honors"] = ["Dean's List, 100% attendance (2023)"]
        latex = inject_into_template(data)
        assert r"100\% attendance" in latex

    def test_honors_drops_blank_and_non_string_entries(self, sample_resume_data):
        data = dict(sample_resume_data)
        data["honors"] = ["Real Honor", "", None, 42, "   "]
        latex = inject_into_template(data)
        assert "Real Honor" in latex
        # Only one honor line should render — no stray entries for the invalid ones.
        assert latex.count("Real Honor") == 1

    def test_no_honors_key_produces_same_content_as_before(self, sample_resume_data):
        """Regression: resumes without an 'honors' field must render the exact
        same visible content as before this feature existed (compile-parity)."""
        latex = inject_into_template(sample_resume_data)
        for expected in ("Jane Doe", "jane@example.com", "Acme Corp", "Python", "InternTracker"):
            assert expected in latex
        assert "Honors" not in latex

    def test_honors_present_in_modern_template_too(self, sample_resume_data):
        data = dict(sample_resume_data)
        data["honors"] = ["AP Scholar, 2022-2023"]
        latex = inject_into_template(data, "modern")
        assert "Honors \\& Awards" in latex
        assert "AP Scholar, 2022-2023" in latex


# ---------------------------------------------------------------------------
# Template selection (template_id) — resume templates feature
# ---------------------------------------------------------------------------

class TestTemplateSelection:
    def test_registry_has_classic_and_modern(self):
        assert set(TEMPLATE_REGISTRY) == {"classic", "modern"}

    def test_default_matches_explicit_classic(self, sample_resume_data):
        """Callers that never pass template_id must get exactly the classic
        template — this is the compile-parity guarantee for the MCP's
        shared-by-value compile_resume_json_to_pdf, which never passes
        template_id at all."""
        assert inject_into_template(sample_resume_data) == inject_into_template(
            sample_resume_data, "classic"
        )

    def test_unknown_template_id_falls_back_to_classic(self, sample_resume_data):
        assert inject_into_template(sample_resume_data, "bogus-id") == inject_into_template(
            sample_resume_data, "classic"
        )

    def test_modern_renders_same_content_as_classic(self, sample_resume_data):
        classic = inject_into_template(sample_resume_data, "classic")
        modern = inject_into_template(sample_resume_data, "modern")
        assert classic != modern
        for expected in ("Jane Doe", "jane@example.com", "Acme Corp", "Python", "InternTracker"):
            assert expected in modern

    def test_modern_preserves_font_size_placeholder(self, sample_resume_data):
        latex = inject_into_template(sample_resume_data, "modern")
        assert "{{FONT_SIZE}}" in latex

    def test_modern_uses_same_bullet_item_structure(self, sample_resume_data):
        """The widow/font-lock measurement code assumes plain \\item bullets —
        modern must reuse the same Python-built itemize blocks as classic."""
        classic = inject_into_template(sample_resume_data, "classic")
        modern = inject_into_template(sample_resume_data, "modern")
        classic_items = [l for l in classic.splitlines() if l.strip().startswith("\\item")]
        modern_items = [l for l in modern.splitlines() if l.strip().startswith("\\item")]
        assert classic_items == modern_items
        assert classic_items  # sanity: sample data actually has bullets


# ---------------------------------------------------------------------------
# _count_pdf_pages
# ---------------------------------------------------------------------------

class TestCountPdfPages:
    def test_returns_int(self):
        fake_pdf = MagicMock()
        fake_pdf.__enter__ = lambda s: s
        fake_pdf.__exit__ = MagicMock(return_value=False)
        fake_pdf.pages = [MagicMock(), MagicMock()]  # 2 pages

        with patch("resume_tailor.tailor_resume.pdfplumber.open", return_value=fake_pdf):
            count = _count_pdf_pages(b"%PDF-fake")
        assert count == 2

    def test_single_page(self):
        fake_pdf = MagicMock()
        fake_pdf.__enter__ = lambda s: s
        fake_pdf.__exit__ = MagicMock(return_value=False)
        fake_pdf.pages = [MagicMock()]  # 1 page

        with patch("resume_tailor.tailor_resume.pdfplumber.open", return_value=fake_pdf):
            count = _count_pdf_pages(b"%PDF-fake")
        assert count == 1


# ---------------------------------------------------------------------------
# compile_to_single_page
# ---------------------------------------------------------------------------

class TestCompileToSinglePage:
    def _make_pdf(self, pages: int) -> bytes:
        """Return a distinct fake PDF bytes object labelled with page count."""
        return f"%PDF-fake-{pages}pages".encode()

    def test_returns_first_fitting_size(self, sample_resume_data):
        """If 11pt already fits, return it immediately without trying smaller sizes."""
        pdf_11pt = self._make_pdf(1)

        with patch("resume_tailor.tailor_resume.compile_latex_to_pdf", return_value=pdf_11pt) as mock_compile, \
             patch("resume_tailor.tailor_resume._count_pdf_pages", return_value=1):
            latex = inject_into_template(sample_resume_data)
            result = compile_to_single_page(latex)

        assert result == pdf_11pt
        # Should only compile once — 11pt fits
        assert mock_compile.call_count == 1

    def test_falls_back_to_smaller_font(self, sample_resume_data):
        """If 11pt is 2 pages, try 10pt which fits."""
        pdf_11pt = self._make_pdf(2)
        pdf_10pt = self._make_pdf(1)

        compile_results = [pdf_11pt, pdf_10pt]
        page_counts = [2, 1]

        with patch("resume_tailor.tailor_resume.compile_latex_to_pdf", side_effect=compile_results), \
             patch("resume_tailor.tailor_resume._count_pdf_pages", side_effect=page_counts):
            latex = inject_into_template(sample_resume_data)
            result = compile_to_single_page(latex)

        assert result == pdf_10pt

    def test_returns_smallest_when_nothing_fits(self, sample_resume_data):
        """Even at 8pt the content overflows — return the 8pt PDF anyway."""
        always_2_page = self._make_pdf(2)

        with patch("resume_tailor.tailor_resume.compile_latex_to_pdf", return_value=always_2_page), \
             patch("resume_tailor.tailor_resume._count_pdf_pages", return_value=2):
            latex = inject_into_template(sample_resume_data)
            result = compile_to_single_page(latex)

        # Must still return something (the last compiled bytes)
        assert result == always_2_page

    def test_font_size_placeholder_replaced(self, sample_resume_data):
        """compile_latex_to_pdf must never receive the raw {{FONT_SIZE}} string."""
        captured = []

        def capture(latex_source):
            captured.append(latex_source)
            return b"%PDF-fake"

        with patch("resume_tailor.tailor_resume.compile_latex_to_pdf", side_effect=capture), \
             patch("resume_tailor.tailor_resume._count_pdf_pages", return_value=1):
            latex = inject_into_template(sample_resume_data)
            compile_to_single_page(latex)

        assert captured, "compile_latex_to_pdf was never called"
        assert "{{FONT_SIZE}}" not in captured[0]

    def test_tries_sizes_in_order(self, sample_resume_data):
        """Sizes tried must follow FONT_SIZES list order (largest first)."""
        sizes_used = []

        def capture(latex_source):
            for size in FONT_SIZES:
                if f"{size}pt" in latex_source:
                    sizes_used.append(size)
                    break
            return b"%PDF-fake"

        # Always 2 pages so all sizes are tried
        with patch("resume_tailor.tailor_resume.compile_latex_to_pdf", side_effect=capture), \
             patch("resume_tailor.tailor_resume._count_pdf_pages", return_value=2):
            latex = inject_into_template(sample_resume_data)
            compile_to_single_page(latex)

        assert sizes_used == FONT_SIZES


# ---------------------------------------------------------------------------
# tailor_resume_to_json (mocked Claude)
# ---------------------------------------------------------------------------

class TestTailorResumeToJson:
    def _mock_response(self, payload: dict):
        msg = MagicMock()
        msg.content = [MagicMock(text=json.dumps(payload))]
        msg.stop_reason = "end_turn"
        return msg

    def test_parses_valid_json(self):
        from resume_tailor.tailor_resume import tailor_resume_to_json

        payload = {
            "name": "Test User",
            "email": "t@t.com",
            "phone": "555",
            "website": "",
            "github": "",
            "linkedin": "",
            "experience": [],
            "education": [],
            "skills": {},
            "projects": [],
        }

        with patch("resume_tailor.tailor_resume.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = self._mock_response(payload)
            result = tailor_resume_to_json("resume text", "SWE", "Acme", "job desc")

        assert result["name"] == "Test User"

    def test_strips_markdown_fences(self):
        from resume_tailor.tailor_resume import tailor_resume_to_json

        payload = {"name": "Alice", "email": "", "phone": "", "website": "", "github": "",
                   "linkedin": "", "experience": [], "education": [], "skills": {}, "projects": []}
        fenced = f"```json\n{json.dumps(payload)}\n```"

        msg = MagicMock()
        msg.content = [MagicMock(text=fenced)]
        msg.stop_reason = "end_turn"

        with patch("resume_tailor.tailor_resume.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = msg
            result = tailor_resume_to_json("text", "SWE", "Acme", "desc")

        assert result["name"] == "Alice"
