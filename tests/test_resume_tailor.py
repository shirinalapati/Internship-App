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
    compile_resume_json_to_pdf,
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
# compile_resume_json_to_pdf — template_id threading + classic byte-identity
# guarantee (compile-engine parity rule; shared by value with internship-mcp).
# ---------------------------------------------------------------------------

class TestCompileResumeJsonToPdfTemplateId:
    def _patched(self):
        """Short-circuits the widow-backstop and spacing-stretch loops (cap<=0
        breaks them on the first iteration) and the font-grow branch (fill
        ratio pinned at exactly UNDERFILL_RATIO, so neither '< UNDERFILL_RATIO'
        branch fires), so _compile_at's own output is the only thing that can
        make two calls differ — which happens iff template_id changed the
        injected LaTeX.
        """
        return (
            patch("resume_tailor.tailor_resume._compile_at", side_effect=lambda latex, size, preset="tight": latex.encode()),
            patch("resume_tailor.tailor_resume._count_pdf_pages", return_value=1),
            patch("resume_tailor.tailor_resume._page1_fill_ratio", return_value=0.85),
            patch("resume_tailor.tailor_resume.max_full_line_len", return_value=0),
        )

    def test_omitting_template_id_matches_explicit_classic(self, sample_resume_data):
        """Every pre-existing caller (MCP /api/v1/resume/compile, the vendored
        internship-mcp copy) never passes template_id — this must be byte-identical
        to explicitly passing 'classic'."""
        p1, p2, p3, p4 = self._patched()
        with p1, p2, p3, p4:
            pdf_default, diag_default = compile_resume_json_to_pdf(sample_resume_data)
        p1, p2, p3, p4 = self._patched()
        with p1, p2, p3, p4:
            pdf_classic, diag_classic = compile_resume_json_to_pdf(sample_resume_data, template_id="classic")

        assert pdf_default == pdf_classic
        assert diag_default == diag_classic

    def test_modern_template_id_produces_different_output(self, sample_resume_data):
        p1, p2, p3, p4 = self._patched()
        with p1, p2, p3, p4:
            pdf_classic, _ = compile_resume_json_to_pdf(sample_resume_data, template_id="classic")
        p1, p2, p3, p4 = self._patched()
        with p1, p2, p3, p4:
            pdf_modern, _ = compile_resume_json_to_pdf(sample_resume_data, template_id="modern")

        assert pdf_classic != pdf_modern


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
