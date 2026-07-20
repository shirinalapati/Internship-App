import copy
import io
import json
import logging
import os
import re
import subprocess
import tempfile
import anthropic
import pdfplumber

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level prompt constant (injectable for evals)
# ---------------------------------------------------------------------------

TAILOR_SYSTEM_PROMPT = """You are a senior technical recruiter and resume writer with expertise in software engineering hiring. Your job is to tailor a candidate's resume for a target role — rephrasing existing content to maximize keyword alignment and ATS relevance while staying strictly truthful.

TRUTHFULNESS (non-negotiable):
- Every bullet must be grounded in facts explicitly stated in the original resume. Never write a bullet that is not directly supported by the source text.
- Rephrasing existing work using job description keywords is allowed; inventing new bullet points is not.
- WRONG: resume has no "data pipeline" work → adding "Developed data ingestion pipeline for ML-ready storage" (fabricated)
- WRONG: resume says "Anthropic/OpenAI/Gemini API" → writing "Claude/OpenAI/Gemini API" (modified verbatim content)
- RIGHT: resume has AWS S3 work → "Managed AWS S3 storage for 250+ files" front-loaded with job's storage keywords
- RIGHT: resume has Claude API work → rephrase as "LLM integration pipeline" if job mentions LLMs — same work, job-aligned language
- If the role is a poor fit, surface what genuinely overlaps and keep the rest accurate; do not pad.

COMPLETENESS (non-negotiable):
- Every bullet must be a syntactically COMPLETE thought. A bullet that ends mid-parenthesis, after an opening colon with nothing following, or mid-clause is FORBIDDEN.
- If the source bullet has a parenthetical "(5+ min saved per request, 50+ customers)", the rewritten bullet MUST include the ENTIRE parenthetical. Never cut it at the opening paren or mid-content.
- Every opening parenthesis must have a matching closing parenthesis within the same bullet.
- BAD (truncated, unclosed paren): "Built internal tools for ops stakeholders: Intercom ticketing (5+ min saved per request"
- BAD (incomplete clause): "FSM-driven pipeline with intent"
- BAD (dangling): "Built end-to-end order-processing system using Python and"
- GOOD: "Built React and Python internal tools for non-technical ops stakeholders: Intercom ticketing (5+ min saved per request, 50+ customers), ERP sales order interface, and AWS S3 attachment store for 250+ files"

KEYWORD ALIGNMENT (rephrase existing, never invent):
- Reword existing bullet content to front-load exact terms from the job description.
- Job says "distributed systems" → describe the real multi-tier data layer as "distributed" where accurate.
- Job says "AI agents" → describe the real agentic order-automation work using that language.
- Do NOT write a new bullet to cover a job requirement the resume never addressed.

SKILLS ACCURACY:
- Copy skill values faithfully from the resume. Do not rename tools (e.g. "Anthropic/OpenAI/Gemini API" must stay as-is, not become "Claude/OpenAI/Gemini API").
- Organize skills into dict categories; do not drop demonstrated skills from the original resume.

SPECIFICITY (never drop metrics):
- Preserve all original numbers, percentages, counts, and deployment evidence in every bullet.
- If a metric fits in the source it must appear in the tailored version — do not sacrifice metrics for concision.
- BAD: "Built internal tools including AWS S3 store" (dropped "250+ files" metric)
- GOOD: "Built React + Python internal tools: Intercom ticketing (5+ min saved, 50+ customers), ERP sales order interface, AWS S3 store for 250+ files"
- BAD: "Improved system performance significantly"
- GOOD: "Reduced inference latency 52% (270s→130s) via dynamic batching and prompt caching"

LINE DENSITY — FILL THE WIDTH (secondary goal, never override truthfulness/specificity):
STRONGLY PREFER Zone B for every bullet — two full lines keeps the resume dense and professional.
  ZONE A (one tight line):  ≤115 chars  — acceptable ONLY when a bullet truly has one line of truthful content.
  ZONE B (two full lines):  ≥215 chars  — fills both lines wall-to-wall. THIS IS THE DEFAULT TARGET.
NEVER write a bullet in the dead zone (116–214 chars) — that length wraps to one line
PLUS a 1–5 word orphan on a second line, wasting ~90% of that line's width.

WORKED EXAMPLES (using real resume content):

WRONG — 152 chars, dead zone, widow "for dashboard configuration":
  "Built Python abstraction wrapper around Grafanalib on 3-person engineering team, achieving 83% code reduction (30+ lines to 5) for dashboard configuration"

FIX A (tighten to Zone A, ≤115): cut trailing clause:
  "Built Python Grafanalib abstraction for 3-person team, achieving 83% code reduction (30+ lines to 5 per dashboard)"  [113 chars ✓]

FIX B (expand to Zone B, ≥215): add the real deployment context:
  "Built Python abstraction wrapper around Grafanalib achieving 83% code reduction (30+ to 5 lines per dashboard), validated and deployed across 3 active Grafana production environments for 3-person engineering team"  [213 chars ✓]

WRONG — 153 chars, dead zone, widow "PostgreSQL database backend":
  "Building full-stack professor review platform serving 30,000+ students using TypeScript, React, Node.js, and Drizzle ORM with PostgreSQL database backend"

FIX B (expand to Zone B): weave in the shipped deliverable:
  "Building full-stack professor review platform for 30,000+ SJSU students using TypeScript, React, Node.js, Drizzle ORM, PostgreSQL; shipped review submission flow and Python GraphQL webscraper for automated course data ingestion"  [228 chars ✓]

RIGHT (Zone B, 245 chars — the template to follow):
  "Shipped production multi-channel B2B AI order agent (webhooks, WhatsApp, email, phone) using Claude Sonnet with RAG vector stores, owning full-stack features from conception through deployment across 7 enterprise clients processing 1,000+ orders"

RIGHT (Zone B, detail-rich — note all parenthetical content preserved):
  "Built React and Python internal tools for non-technical ops stakeholders: Intercom ticketing (5+ min saved per request, 50+ customers), ERP sales order interface, and AWS S3 attachment store for 250+ files"

RIGHT (Zone B, multi-deliverable bullet):
  "Built and deployed autonomous lead-qualification SMS agent for Bay Area real estate client: FSM-driven pipeline with intent classification, debounce sweeper, and Cal.com auto-booking of qualified leads"

DECISION RULE for all bullets:
- DEFAULT: EXPAND to Zone B (≥215 chars) by weaving in additional TRUE facts already
  in the resume — other deliverables, real metrics, tech versions, deployment scope, team size.
- TIGHTEN to Zone A (≤115 chars) ONLY as a last resort: when, after honestly checking
  the source, there are truly no more truthful facts to add.
- A short truthful bullet always beats a padded false one.
- NEVER invent facts to reach Zone B. Fabricated filler is worse than a short bullet.
- If the source genuinely lacks enough content to fill the page, leave whitespace rather
  than invent — the layout will space the page out automatically.

NO DUPLICATE BULLETS (hard rule):
- Every bullet within an entry must cover a DISTINCT achievement, deliverable, or metric.
- NEVER repeat the same metric, technology combination, or outcome across multiple bullets in the same entry.
- If two potential bullets cover the same work, MERGE them into one richer bullet rather than listing both.
- BAD: Bullet 1 ends "...migrated 7+ dashboards with unit test coverage on configuration layer" AND Bullet 2 is "Migrated 7+ dashboards with unit test coverage on configuration layer" — this is a literal duplicate, forbidden.
- BAD: Two bullets both starting "Engineered dual-model Claude pipeline (Haiku 4.5 for skill extraction, Sonnet 4.5..." — same subject, forbidden.
- GOOD: One comprehensive bullet merging all facts about that work.

DENSITY (fill every line with real substance):
- Each experience role: 3–4 bullets. Each project: 3 bullets. Aim for the upper end whenever the source supports it with real content.
- Goal is density and no filler, NOT a character limit — never drop a metric to make a bullet shorter.
- Do NOT pack bullets shorter than ~80 chars; extend them by weaving in metrics and technology names.
- No filler: never write "collaborated with cross-functional teams," "leveraged best practices," or "demonstrated strong ability to."

JSON CONTRACT:
- Return ONLY valid JSON — no markdown fences, no commentary.
- All fields required: name, email, phone, website, github, linkedin, experience, education, skills, projects.
- skills must be a dict of string-to-string (category → comma-separated values), not a list."""


def extract_text_from_pdf(file_content: bytes) -> str:
    try:
        text = ""
        with pdfplumber.open(io.BytesIO(file_content)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text
        return text
    except Exception as e:
        raise RuntimeError(f"Failed to extract text from PDF: {e}")


def tailor_resume_to_json(
    resume_text: str, job_title: str, company: str, job_description: str,
    system_prompt=None, temperature=None,
) -> dict:
    """Single Sonnet call: extract structured JSON + tailor bullets to the job."""
    # Cap the JD to bound input cost/latency; scraped descriptions are well under this.
    job_description = (job_description or "")[:6000]
    sys_p = system_prompt if system_prompt is not None else TAILOR_SYSTEM_PROMPT
    client = anthropic.Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))
    create_kwargs = dict(
        model="claude-sonnet-4-5-20250929",
        max_tokens=6000,
        system=sys_p,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Target role: {job_title} at {company}\n"
                    f"Job description:\n{job_description}\n\n"
                    f"Resume to tailor:\n{resume_text}\n\n"
                    "TASK: Actively rewrite every experience and project bullet to maximize relevance for "
                    "the target role above. Do not copy bullets verbatim — rephrase each one to front-load "
                    "exact keywords and technologies from the job description while keeping all original "
                    "metrics and staying strictly truthful. Bullets that are already well-aligned can be "
                    "lightly rephrased; bullets that are off-topic should be reframed to highlight the most "
                    "relevant aspect of that work.\n\n"
                    "COMPLETENESS RULE (critical): Every bullet must be a syntactically COMPLETE sentence. "
                    "Never produce a bullet that ends mid-parenthesis, after an opening colon, or mid-clause. "
                    "If a source bullet has parenthetical content like '(5+ min saved per request, 50+ customers)' "
                    "you MUST include the ENTIRE parenthetical — never stop inside it. Every opening '(' must have "
                    "a matching ')' within the same bullet.\n\n"
                    "NO DUPLICATES RULE (critical): Each bullet in an entry must cover a COMPLETELY DIFFERENT "
                    "deliverable or achievement. Never write two bullets about the same system or metric. "
                    "If two points cover the same work, merge into one richer bullet.\n\n"
                    "DENSITY RULE: STRONGLY PREFER Zone B bullets (≥215 chars / two full lines) — "
                    "this fills the page and looks professional. DEFAULT: expand each bullet with real "
                    "resume facts (other deliverables, metrics, tech, scope, team size). Zone A "
                    "(≤115 chars / one tight line) is acceptable ONLY as a last resort when no more "
                    "truthful facts exist for that bullet. NEVER write a bullet in the 116–214 char "
                    "dead zone — it creates a short orphan on an otherwise empty line. "
                    "Aim to fill a full page: prefer two full lines per bullet with real detail and "
                    "metrics. Never invent facts. If the source genuinely lacks content to fill the "
                    "page, leave tasteful whitespace — the layout will space it out.\n\n"
                    "Return the tailored resume as JSON with this exact structure:\n"
                    "{\n"
                    '  "name": "Full Name",\n'
                    '  "email": "email@example.com",\n'
                    '  "phone": "555-555-5555",\n'
                    '  "website": "https://example.com",\n'
                    '  "github": "https://github.com/username",\n'
                    '  "linkedin": "https://linkedin.com/in/username",\n'
                    '  "experience": [\n'
                    '    {"company": "...", "location": "City, ST", "title": "...", "dates": "...", "bullets": ["..."]}\n'
                    "  ],\n"
                    '  "education": [\n'
                    '    {"school": "...", "location": "City, ST", "degree": "...", "dates": "..."}\n'
                    "  ],\n"
                    '  "skills": {\n'
                    '    "Programming Languages": "Python, Java",\n'
                    '    "Frameworks & Libraries": "React.js, Node.js",\n'
                    '    "Developer Tools": "Git, Docker"\n'
                    "  },\n"
                    '  "projects": [\n'
                    '    {"name": "Project Name (Tech1, Tech2)", "dates": "...", "bullets": ["..."]}\n'
                    "  ]\n"
                    "}"
                ),
            }
        ],
    )
    if temperature is not None:
        create_kwargs["temperature"] = temperature
    response = client.messages.create(**create_kwargs)
    raw = response.content[0].text.strip()
    # Strip markdown fences if model adds them anyway
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        stop = response.stop_reason
        raise RuntimeError(
            f"Resume JSON truncated (stop_reason={stop!r}): {e}. "
            "Increase max_tokens or shorten the resume."
        ) from e


def _is_incomplete_bullet(text: str) -> bool:
    """Return True if a bullet looks syntactically incomplete.

    Checks for:
    - Unmatched opening parentheses
    - Ends with a dangling preposition/conjunction ("with", "and", "using", etc.)
    - Ends with a colon (value was cut off)
    - Ends with an opening comma clause ("for", "via", "to")
    """
    t = text.strip().rstrip(".")
    # Unmatched parens: more opens than closes
    if t.count("(") != t.count(")"):
        return True
    # Trailing colon means the listed values were cut
    if t.endswith(":"):
        return True
    # Dangling words that indicate a clause was cut
    _DANGLING = {
        "with", "and", "or", "using", "for", "via", "to", "by", "as",
        "including", "such", "then", "when", "where", "after", "before",
        "of", "on", "in", "at", "from", "through", "across", "into",
    }
    last_word = t.split()[-1].lower().rstrip(".,;:") if t.split() else ""
    if last_word in _DANGLING:
        return True
    return False


def _repair_bullets(data: dict, resume_text: str) -> dict:
    """One Sonnet call to fix any syntactically incomplete bullets.

    Collects all bullets flagged by _is_incomplete_bullet, sends them to
    Sonnet with the original resume as context, and replaces them in place.
    """
    flagged: list[tuple[str, int, int, str]] = []  # (section, entry_idx, bullet_idx, text)
    for section in ("experience", "projects"):
        for j, entry in enumerate(data.get(section, [])):
            for k, bullet in enumerate(entry.get("bullets", [])):
                if _is_incomplete_bullet(bullet):
                    flagged.append((section, j, k, bullet))

    if not flagged:
        return data

    logger.info("_repair_bullets: found %d incomplete bullet(s), repairing via Sonnet", len(flagged))

    lines = [f'[{i}] "{t}"' for i, (_, _, _, t) in enumerate(flagged)]
    bullets_block = "\n".join(lines)
    client = anthropic.Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=min(4000, 300 + 200 * len(flagged)),
            system=(
                "You complete truncated resume bullet points. "
                "Each bullet was cut off mid-sentence. Using ONLY facts from the provided resume, "
                "complete each bullet so it is a syntactically complete sentence. "
                "Prefer Zone B length (≥215 chars / two full lines). "
                "Output ONLY a JSON object mapping index to completed bullet text, e.g. {\"0\": \"...\"}."
            ),
            messages=[{
                "role": "user",
                "content": (
                    f"Resume (source of truth):\n{resume_text}\n\n"
                    f"Complete these truncated bullets:\n{bullets_block}\n\n"
                    "Return JSON only."
                ),
            }],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        repairs = json.loads(raw)
    except Exception as e:
        logger.warning("_repair_bullets: API or parse error, skipping repairs: %s", e)
        return data

    data = copy.deepcopy(data)
    for i, (section, j, k, _) in enumerate(flagged):
        new_text = repairs.get(str(i), "").strip()
        if new_text:
            data[section][j]["bullets"][k] = _clean_bullet_text(new_text)
    return data


_STOP_WORDS = {
    "the", "a", "an", "and", "or", "for", "in", "of", "to", "with", "at", "by",
    "on", "is", "was", "are", "were", "that", "this", "from", "as", "via", "into",
    "using", "across", "through", "its", "our", "we", "i", "my", "their",
}


def _key_words(text: str) -> set:
    return {
        w.lower().strip(".,;:()'\"")
        for w in text.split()
        if w.lower().strip(".,;:()'\"") not in _STOP_WORDS and len(w) > 2
    }


def _are_near_duplicates(a: str, b: str, threshold: float = 0.60) -> bool:
    """True if the shorter bullet's key content is substantially contained in the longer."""
    words_a = _key_words(a)
    words_b = _key_words(b)
    if not words_a or not words_b:
        return False
    shorter = words_a if len(words_a) <= len(words_b) else words_b
    longer = words_a if len(words_a) > len(words_b) else words_b
    overlap = len(shorter & longer) / len(shorter)
    return overlap >= threshold


def _deduplicate_bullets(data: dict) -> dict:
    """Remove near-duplicate bullets within each entry (experience and projects).

    A bullet is dropped if >= 60% of its key words appear in an already-kept bullet
    in the same entry. This catches both exact repeats and cases where one bullet is
    a paraphrased subset of another.
    """
    data = copy.deepcopy(data)
    for section in ("experience", "projects"):
        for entry in data.get(section, []):
            bullets = entry.get("bullets", [])
            if len(bullets) <= 1:
                continue
            keep: list[str] = []
            for bullet in bullets:
                if any(_are_near_duplicates(bullet, kept) for kept in keep):
                    logger.info("Dropped near-duplicate bullet: %s…", bullet[:60])
                    continue
                keep.append(bullet)
            entry["bullets"] = keep
    return data


def _latex_bullet(text: str) -> str:
    """Return a plain LaTeX \\item line for one bullet.

    Widow elimination is handled by the closed-loop measure→rewrite→recompile
    pipeline (see refine_to_no_widows), NOT by per-bullet TeX spacing hints —
    the old approach was a no-op (the hint was reset by the closing brace before
    the paragraph broke) and could not express a font-dependent constraint anyway.
    """
    return f"  \\item {_escape_latex(text)}\n"


def _escape_latex(text: str) -> str:
    """Escape special LaTeX characters in plain text."""
    replacements = [
        ("\\", r"\textbackslash{}"),
        ("&", r"\&"),
        ("%", r"\%"),
        ("$", r"\$"),
        ("#", r"\#"),
        ("_", r"\_"),
        ("{", r"\{"),
        ("}", r"\}"),
        ("~", r"\textasciitilde{}"),
        ("^", r"\textasciicircum{}"),
    ]
    for char, escaped in replacements:
        text = text.replace(char, escaped)
    return text


def _href(url: str, display: str) -> str:
    """Build a LaTeX hyperlink."""
    return f"\\href{{{url}}}{{{display}}}"


# template_id -> .tex file. "classic" is the original, untouched template — its
# path and output must never change so the compile-parity guarantee (shared by
# value with internship-mcp) holds for every caller that doesn't pass template_id.
TEMPLATE_REGISTRY: dict[str, str] = {
    "classic": os.path.join(os.path.dirname(__file__), "template.tex"),
    "modern": os.path.join(os.path.dirname(__file__), "templates", "modern", "template.tex"),
}


def inject_into_template(data: dict, template_id: str = "classic") -> str:
    """Fill a template's placeholders with the structured JSON data."""
    template_path = TEMPLATE_REGISTRY.get(template_id, TEMPLATE_REGISTRY["classic"])
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    # Build experience section — company/location line then italic title/dates
    exp_blocks = []
    for job in data.get("experience", []):
        company = _escape_latex(job.get("company", ""))
        location = _escape_latex(job.get("location", ""))
        title = _escape_latex(job.get("title", ""))
        dates = _escape_latex(job.get("dates", ""))
        header = f"\\textbf{{{company}}} \\hfill {dates} \\\\\n\\textit{{{title}}} \\hfill {location}"
        bullets = "".join(_latex_bullet(b) for b in job.get("bullets", []))
        exp_blocks.append(
            f"{header}\n"
            "\\begin{itemize}[leftmargin=*, topsep={{ITEMIZE_TOPSEP}}, itemsep={{ITEMIZE_ITEMSEP}}, parsep=0pt]\n"
            + bullets
            + "\\end{itemize}"
        )
    experience_latex = "\n\n".join(exp_blocks) if exp_blocks else "No experience listed."

    # Build education section — bold school/location then italic degree/dates
    edu_blocks = []
    for edu in data.get("education", []):
        school = _escape_latex(edu.get("school", ""))
        location = _escape_latex(edu.get("location", ""))
        degree = _escape_latex(edu.get("degree", ""))
        dates = _escape_latex(edu.get("dates", ""))
        edu_blocks.append(
            f"\\textbf{{{school}}} \\hfill {location} \\\\\n"
            f"\\textit{{{degree}}} \\hfill {dates}"
        )
    education_latex = "\n\n".join(edu_blocks) if edu_blocks else "No education listed."

    # Build skills section — bold category labels, one per line
    skills_data = data.get("skills", {})
    if isinstance(skills_data, dict):
        lines = []
        items = list(skills_data.items())
        for i, (category, value) in enumerate(items):
            escaped_cat = _escape_latex(category)
            escaped_val = _escape_latex(value)
            ending = " \\\\" if i < len(items) - 1 else ""
            lines.append(f"\\textbf{{{escaped_cat}:}} {escaped_val}{ending}")
        skills_latex = "\n".join(lines)
    else:
        skills_latex = ", ".join(_escape_latex(s) for s in skills_data) if skills_data else "No skills listed."

    # Build projects section — bold name/dates then bullets
    proj_blocks = []
    for proj in data.get("projects", []):
        name = _escape_latex(proj.get("name", ""))
        dates = _escape_latex(proj.get("dates", ""))
        bullets = "".join(_latex_bullet(b) for b in proj.get("bullets", []))
        proj_blocks.append(
            f"\\textbf{{{name}}} \\hfill {dates}\n"
            "\\begin{itemize}[leftmargin=*, topsep={{ITEMIZE_TOPSEP}}, itemsep={{ITEMIZE_ITEMSEP}}, parsep=0pt]\n"
            + bullets
            + "\\end{itemize}"
        )
    projects_latex = "\n\n".join(proj_blocks) if proj_blocks else ""

    # Build contact link placeholders
    email = data.get("email", "")
    email_latex = _href(f"mailto:{email}", _escape_latex(email)) if email else ""

    website = data.get("website", "")
    website_display = website.replace("https://", "").replace("http://", "").rstrip("/")
    website_latex = _href(website, _escape_latex(website_display)) if website else ""

    github = data.get("github", "")
    github_latex = _href(github, "github") if github else ""

    linkedin = data.get("linkedin", "")
    linkedin_latex = _href(linkedin, "linkedin") if linkedin else ""

    template = template.replace("{{NAME}}", _escape_latex(data.get("name", "Name")))
    template = template.replace("{{PHONE}}", _escape_latex(data.get("phone", "")))
    template = template.replace("{{EMAIL}}", email_latex)
    template = template.replace("{{WEBSITE}}", website_latex)
    template = template.replace("{{GITHUB}}", github_latex)
    template = template.replace("{{LINKEDIN}}", linkedin_latex)
    template = template.replace("{{EDUCATION}}", education_latex)
    template = template.replace("{{SKILLS}}", skills_latex)
    template = template.replace("{{EXPERIENCE_BULLETS}}", experience_latex)
    template = template.replace("{{PROJECTS}}", projects_latex)

    return template


def _count_pdf_pages(pdf_bytes: bytes) -> int:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return len(pdf.pages)


def _page1_fill_ratio(pdf_bytes: bytes) -> float:
    """Fraction of the usable text height on page 1 occupied by content.

    1.0 means content reaches the bottom margin; ~0.4 means 40% filled.
    Uses pdfplumber char coordinates (exact, font-independent) against the
    0.5in geometry margins from template.tex.
    """
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        page = pdf.pages[0]
        chars = page.chars
        if not chars:
            return 0.0
        margin = 36.0               # 0.5 in × 72 pt/in
        usable = page.height - 2 * margin   # 720 pt on letter paper
        if usable <= 0:
            return 1.0
        content_bottom = max(c["bottom"] for c in chars)
        return max(0.0, (content_bottom - margin) / usable)


FONT_SIZES = [14, 12, 11, 10, 9, 8]
_ANCHOR_FONT = 11        # baseline: grow above 11pt only when 11pt fits with slack
UNDERFILL_RATIO = 0.85   # page is "full" when content covers ≥85% of usable height

# Vertical-spacing presets (substituted by _compile_at alongside {{FONT_SIZE}}).
# "tight" preserves today's exact values so content-rich output is byte-identical.
_SPACING_PRESETS: dict[str, dict[str, str]] = {
    "tight": {
        "PARSKIP": "0pt", "SEC_BEFORE": "5pt", "SEC_AFTER": "2pt",
        "HEADER_SKIP": "2pt", "ITEMIZE_TOPSEP": "0pt", "ITEMIZE_ITEMSEP": "0pt",
    },
    "normal": {
        "PARSKIP": "2pt", "SEC_BEFORE": "8pt", "SEC_AFTER": "3pt",
        "HEADER_SKIP": "4pt", "ITEMIZE_TOPSEP": "2pt", "ITEMIZE_ITEMSEP": "2pt",
    },
    "relaxed": {
        "PARSKIP": "5pt", "SEC_BEFORE": "12pt", "SEC_AFTER": "5pt",
        "HEADER_SKIP": "6pt", "ITEMIZE_TOPSEP": "4pt", "ITEMIZE_ITEMSEP": "4pt",
    },
}


def _compile_at(latex_source: str, size: int, preset: str = "tight") -> bytes:
    """Compile the template at one specific font size and spacing preset.

    Substitutes {{FONT_SIZE}} and all {{...}} spacing placeholders from
    _SPACING_PRESETS before passing the source to pdflatex.
    """
    spacing = _SPACING_PRESETS.get(preset, _SPACING_PRESETS["tight"])
    s = latex_source.replace("{{FONT_SIZE}}", str(size))
    for key, val in spacing.items():
        s = s.replace(f"{{{{{key}}}}}", val)
    return compile_latex_to_pdf(s)


def _compile_at_font(latex_source: str, size: int) -> bytes:
    """Backward-compatible wrapper — compile at the given font with tight (default) spacing."""
    return _compile_at(latex_source, size, "tight")


def compile_to_single_page(latex_source: str) -> bytes:
    for size in FONT_SIZES:
        pdf_bytes = _compile_at(latex_source, size, "tight")
        if _count_pdf_pages(pdf_bytes) <= 1:
            return pdf_bytes
    return pdf_bytes  # return smallest attempt if still > 1 page


def compile_latex_to_pdf(latex_source: str) -> bytes:
    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = os.path.join(tmpdir, "resume.tex")
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(latex_source)

        cmd = [
            "pdflatex",
            "-interaction=nonstopmode",
            "-output-directory",
            tmpdir,
            tex_path,
        ]

        for _ in range(2):
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )

        if result.returncode != 0:
            log_snippet = result.stdout[-2000:] if result.stdout else result.stderr[-2000:]
            raise RuntimeError(f"pdflatex failed (exit {result.returncode}):\n{log_snippet}")

        pdf_path = os.path.join(tmpdir, "resume.pdf")
        if not os.path.exists(pdf_path):
            raise RuntimeError("pdflatex ran but produced no PDF file")

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

    if not pdf_bytes.startswith(b"%PDF"):
        raise RuntimeError("Output file does not appear to be a valid PDF")

    return pdf_bytes


# ---------------------------------------------------------------------------
# Closed-loop widow elimination
#
# Instead of predicting wrapped width from character counts (which depend on the
# font and so cannot be fixed constants), we MEASURE the compiled PDF: derive the
# chars-per-line C from the widest rendered line, measure each bullet's last
# wrapped line, and rewrite only the bullets whose last line is a short orphan.
# ---------------------------------------------------------------------------

# A wrapped bullet's last physical line is a "widow" if it fills less than this
# fraction of the rendered line width C. This is the ONLY widow threshold — there
# are no font-dependent character constants anywhere in the widow logic.
# Set high (0.85) to push the LLM toward last lines that are nearly wall-to-wall.
WIDOW_THRESHOLD = 0.85

# Hard floor for the deterministic backstop. After the LLM rounds, ANY bullet whose
# last line is still below this fraction is trimmed to a single (full) line for free —
# guaranteeing no genuinely-short orphan can ship. The 0.70–0.85 band is left as
# content-preserving two-liners (the LLM tried; the line is "mostly full").
BACKSTOP_FLOOR = 0.70

# The itemize bullet glyph emitted by pdftotext -layout for this template
# (enumitem default first level). Confirmed empirically against a compiled PDF.
_BULLET_GLYPH = "•"  # •


class _PdftotextUnavailable(RuntimeError):
    """Raised when the pdftotext binary is missing or fails to run."""


def _pdftotext_layout(pdf_bytes: bytes) -> str:
    """Return the `pdftotext -layout` rendering of a PDF as text.

    Raises _PdftotextUnavailable if the binary is absent so callers can
    degrade gracefully instead of crashing the entire tailor request.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "doc.pdf")
        txt_path = os.path.join(tmpdir, "doc.txt")
        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)
        try:
            subprocess.run(
                ["pdftotext", "-layout", pdf_path, txt_path],
                capture_output=True, check=True, timeout=30,
            )
        except FileNotFoundError:
            raise _PdftotextUnavailable("pdftotext binary not found — install poppler-utils")
        except subprocess.CalledProcessError as e:
            raise _PdftotextUnavailable(f"pdftotext failed (exit {e.returncode})")
        with open(txt_path, "r", encoding="utf-8") as f:
            return f.read()


def max_full_line_len(pdf_bytes: bytes) -> int:
    """Chars-per-line C at the active font, measured from bullet content lines.

    We derive C only from bullet body lines (lines that start with the bullet
    glyph or are indented continuation lines), NOT from header/contact/date
    lines that can span a wider block than the bullet text area.  Using header
    widths inflates C, making full bullets falsely measure as widows and
    triggering unnecessary Haiku rounds and backstop trims.
    """
    text = _pdftotext_layout(pdf_bytes)
    lines = text.splitlines()
    widths = []
    in_bullet = False
    for line in lines:
        stripped = line.lstrip(" ")
        if stripped.startswith(_BULLET_GLYPH):
            in_bullet = True
            widths.append(len(line.rstrip()))
        elif in_bullet and line and line[0] == " ":
            # Indented continuation line belonging to the current bullet
            widths.append(len(line.rstrip()))
        else:
            in_bullet = False
    # Fall back to all non-empty lines if no bullets were found
    if not widths:
        widths = [len(line.rstrip()) for line in lines if line.strip()]
    return max(widths) if widths else 0


def measure_bullets(pdf_bytes: bytes):
    """Measure each itemize bullet's first and LAST physical line widths.

    Returns a list of (first_line_width, last_wrapped_line_width) in document
    order — experience bullets first, then projects — matching
    inject_into_template's render order. A single-line bullet yields
    (width, 0). Widths are rstripped rendered widths (leading indent included),
    so they share the same scale as max_full_line_len's C.

    Note: we report the LAST wrapped line (not strictly the "second"), because a
    bullet may wrap to 3+ lines and the orphan is always the final line.
    """
    text = _pdftotext_layout(pdf_bytes)
    lines = text.splitlines()
    pairs = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        stripped = line.lstrip(" ")
        if stripped.startswith(_BULLET_GLYPH):
            first_width = len(line.rstrip())
            last_width = 0
            j = i + 1
            while j < n:
                nxt = lines[j]
                if not nxt.strip():
                    j += 1
                    continue  # defensively skip blank lines
                nxt_stripped = nxt.lstrip(" ")
                lead = len(nxt) - len(nxt_stripped)
                if nxt_stripped.startswith(_BULLET_GLYPH):
                    break       # next bullet
                if lead == 0:
                    break       # section header or new entry header (col 0)
                last_width = len(nxt.rstrip())  # indented continuation line
                j += 1
            pairs.append((first_width, last_width))
            i = j
        else:
            i += 1
    if not pairs:
        logger.warning(
            "measure_bullets found no '%s' glyphs — pdftotext output or template "
            "may have changed; widow refinement will be skipped",
            _BULLET_GLYPH,
        )
    return pairs


def _flatten_bullet_locations(data: dict):
    """Bullet locations in render order: experience bullets, then projects.

    Each location is a (section, entry_index, bullet_index) tuple, aligned 1:1
    with measure_bullets' output order.
    """
    locations = []
    for section in ("experience", "projects"):
        for j, entry in enumerate(data.get(section, [])):
            for k in range(len(entry.get("bullets", []))):
                locations.append((section, j, k))
    return locations


# Compact system prompt for the widow-fix call. This is a trivial constrained edit,
# so it uses Haiku (3x cheaper than Sonnet) and a ~150-token instruction instead of
# re-sending the full 2k-token TAILOR_SYSTEM_PROMPT on every call.
_WIDOW_FIX_SYSTEM = (
    "You rewrite resume bullet points to fix line-wrapping 'widows' (a short orphan "
    "on the last line). Hard rules: every fact must come verbatim in meaning from the "
    "provided resume — never invent companies, metrics, technologies, dates, or "
    "outcomes, and keep all original numbers. Output only the rewritten bullets."
)

# Haiku is the right tier for this constrained one-line edit; full ID matches the
# model used elsewhere in the pipeline for fast ops.
_WIDOW_FIX_MODEL = "claude-haiku-4-5-20251001"


def _batch_widow_rewrite(items, cap: int, resume_text: str):
    """Rewrite ALL widowed bullets in ONE Haiku call. Returns {index: new_text}.

    `items` is a list of (index, bullet_text, fill_pct). The resume is sent once
    (not per bullet), and a compact system prompt replaces the 2k-token tailoring
    prompt — so cost is one cheap call per round instead of N expensive ones.
    """
    if not items:
        return {}
    client = anthropic.Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))

    lines = []
    for idx, bullet, fill_pct in items:
        lines.append(
            f'[{idx}] (last line only {fill_pct:.0f}% full) "{bullet}"'
        )
    bullets_block = "\n".join(lines)

    user_msg = (
        f"Resume (the ONLY source of truth for facts):\n{resume_text}\n\n"
        f"The page fits about {cap} characters per line. Each bullet below wrapped to a "
        f"widow — a nearly-empty last line. Rewrite EACH one to EITHER:\n"
        f"  A) fit on ONE line: <= {cap} characters, OR\n"
        f"  B) fill TWO lines: extend with real resume facts so the second line is at "
        f"least 75% full (roughly {int(cap * 1.75)}-{int(cap * 2)} characters total).\n"
        f"Prefer B (extend with true detail) when the resume has more facts for that work; "
        f"otherwise tighten to A. Never invent facts.\n\n"
        f"Bullets to fix (keyed by number):\n{bullets_block}\n\n"
        f'Return ONLY a JSON object mapping each bullet number to its rewritten text, '
        f'e.g. {{"0": "rewritten bullet", "3": "rewritten bullet"}}. No commentary.'
    )

    resp = client.messages.create(
        model=_WIDOW_FIX_MODEL,
        max_tokens=min(4000, 250 + 160 * len(items)),
        system=_WIDOW_FIX_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = resp.content[0].text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("widow rewrite returned non-JSON, skipping round: %s", e)
        return {}
    out = {}
    for k, v in parsed.items():
        try:
            out[int(k)] = _clean_bullet_text(v)
        except (ValueError, TypeError):
            continue
    return out


def _trim_to_single_line(text: str, cap: int) -> str:
    """Trim a bullet at a word boundary so it renders on ONE line (<= ~92% of C).

    Deterministic, no API. A single line is never a widow, so this is the free
    backstop that guarantees full-width output even if the model can't extend.

    Trims at clause boundaries (comma, semicolon, parenthesis) when possible so
    we don't cut mid-metric (e.g. "latency 38% (210ms →" would lose its unit).
    """
    target = max(20, int(cap * 0.92))
    if len(text) <= target:
        return text

    # Find the best trim point: prefer ending just before a clause break
    # (comma/semicolon/open-paren) that falls within the target length.
    best_clause = ""
    words = text.split()
    out = ""
    for w in words:
        candidate = (out + " " + w).strip()
        if len(candidate) > target:
            break
        out = candidate
        # Record the furthest position that ends cleanly before a clause marker
        if out and out[-1] in (",", ";", "("):
            best_clause = out.rstrip(",;( ").rstrip()

    if not out:
        # No word fits — hard truncate as last resort
        return text[:target]

    # Prefer clause-boundary trim only when it retains at least 60% of target
    # (avoid very short cuts like "Built" when a full sentence fits better).
    if best_clause and len(best_clause) >= int(target * 0.60):
        return best_clause
    return out


def _clean_bullet_text(text: str) -> str:
    """Normalize a model-returned bullet to a single clean line."""
    text = text.strip()
    # Drop a leading bullet glyph / dash the model may have added
    text = re.sub(r"^[•\-\*]\s*", "", text)
    # Collapse internal newlines/whitespace to single spaces
    text = " ".join(text.split())
    # Strip wrapping quotes if present
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return text


def rewrite_widowed_bullets(data: dict, widows, cap: int, resume_text: str, rewrite_fn) -> dict:
    """Rewrite the widowed bullets in `data`, matched BY POSITION.

    `widows` is a list of (bullet_index, fill_pct) in measure_bullets /
    _flatten_bullet_locations order. `rewrite_fn(items, cap, resume_text) ->
    {index: new_text}` is the injectable BATCH seam — one call fixes every widow
    (Haiku in prod, a hand-authored map in the no-API eval).

    Returns a NEW data dict if at least one bullet changed, or the ORIGINAL `data`
    object (same identity) if nothing changed so callers can detect a no-op with
    `new_data is data`.
    """
    new_data = copy.deepcopy(data)
    locations = _flatten_bullet_locations(new_data)

    items = []
    for idx, fill_pct in widows:
        if idx >= len(locations):
            logger.warning("widow index %d out of range (%d bullets)", idx, len(locations))
            continue
        section, j, k = locations[idx]
        items.append((idx, new_data[section][j]["bullets"][k], fill_pct))

    if not items:
        return data  # nothing to rewrite — return original so caller sees no-op

    try:
        rewrites = rewrite_fn(items, cap, resume_text)
    except Exception as e:
        logger.warning("batch rewrite_fn failed: %s", e)
        return data

    changed = False
    for idx, new_bullet in (rewrites or {}).items():
        if idx >= len(locations) or not new_bullet:
            continue
        section, j, k = locations[idx]
        if new_data[section][j]["bullets"][k] != new_bullet:
            new_data[section][j]["bullets"][k] = new_bullet
            changed = True

    return new_data if changed else data


def _lock_font(data: dict, template_id: str = "classic"):
    """Lock the font (and initial preset), growing above 11pt for sparse pages.

    Returns (pdf, font, preset). preset is always 'tight' from this function;
    spacing stretch happens after widow resolution in refine_to_no_widows.

    Algorithm (fill-aware, avoids overshoot):
      1. Anchor at 11pt. If it overflows → step DOWN [11,10,9,8], skip grow/stretch.
      2. If 11pt fits and fill ≥ UNDERFILL_RATIO → lock 11pt (already full).
      3. If 11pt fits but fill < UNDERFILL_RATIO → try larger sizes (12, 14),
         locking the largest that still fits ≤1 page.
    """
    latex = inject_into_template(data, template_id)
    anchor_pdf = _compile_at(latex, _ANCHOR_FONT, "tight")

    if _count_pdf_pages(anchor_pdf) > 1:
        # Content-rich / overflow: step down only (existing behaviour).
        below = [s for s in FONT_SIZES if s < _ANCHOR_FONT]
        for size in below:
            pdf = _compile_at(latex, size, "tight")
            if _count_pdf_pages(pdf) <= 1:
                return pdf, size, "tight"
        fallback_pdf = _compile_at(latex, FONT_SIZES[-1], "tight")
        return fallback_pdf, FONT_SIZES[-1], "tight"

    # 11pt fits — check whether the page is already full.
    if _page1_fill_ratio(anchor_pdf) >= UNDERFILL_RATIO:
        return anchor_pdf, _ANCHOR_FONT, "tight"

    # Underfilled: try larger fonts above the anchor (largest first).
    above = sorted([s for s in FONT_SIZES if s > _ANCHOR_FONT], reverse=True)
    for size in above:
        pdf = _compile_at(latex, size, "tight")
        if _count_pdf_pages(pdf) <= 1:
            return pdf, size, "tight"

    # No larger size fits — return anchor.
    return anchor_pdf, _ANCHOR_FONT, "tight"


def _recompile_locked(data: dict, font: int, preset: str = "tight", template_id: str = "classic"):
    """Recompile at the locked font and spacing preset, stepping down one size if spilled."""
    latex = inject_into_template(data, template_id)
    pdf = _compile_at(latex, font, preset)
    if _count_pdf_pages(pdf) > 1:
        idx = FONT_SIZES.index(font)
        if idx + 1 < len(FONT_SIZES):
            font = FONT_SIZES[idx + 1]
            pdf = _compile_at(latex, font, preset)
    return pdf, font


def refine_to_no_widows(
    data: dict, resume_text: str, rewrite_fn, max_rounds: int = 3, template_id: str = "classic"
) -> bytes:
    """Lock the font, then close the loop: measure → rewrite → recompile, with a
    free deterministic backstop that guarantees full-width bullets. Finally, stretch
    spacing if the page is still underfilled.

    Stage 1 (LLM, content-preserving): up to `max_rounds` cheap batched rewrites
    that try to EXTEND each widow toward WIDOW_THRESHOLD using real resume facts.
    Each round re-measures at the LOCKED font (C is font-dependent) and only the
    still-widowed bullets are sent back, so the model self-corrects on fresh
    measurements. The font is only ever stepped DOWN, never recomputed, to avoid
    oscillation.

    Stage 2 (deterministic, free): any bullet whose last line is STILL below
    BACKSTOP_FLOOR is trimmed to a single full line — no API, no fabrication. This
    is the hard guarantee that no genuinely-short orphan can ship even if the model
    failed to extend.

    Stage 3 (spacing stretch, deterministic): if the page is still underfilled after
    widow resolution, walk tight → normal → relaxed spacing presets, picking the
    loosest that keeps the PDF on one page. Uses pdfplumber only — independent of
    the pdftotext-based widow path.
    """
    pdf, font, preset = _lock_font(data, template_id)

    # ---- Stage 1: LLM extend rounds (preferred — keeps content) ----
    try:
        for _ in range(max_rounds):
            cap = max_full_line_len(pdf)
            if cap <= 0:
                break
            pairs = measure_bullets(pdf)
            locations = _flatten_bullet_locations(data)
            if len(locations) != len(pairs):
                logger.warning(
                    "bullet count mismatch (data=%d, measured=%d) — skipping LLM widow rewrite",
                    len(locations), len(pairs),
                )
                break
            widows = [
                (i, (l2 / cap) * 100)
                for i, (l1, l2) in enumerate(pairs)
                if l2 and (l2 / cap) < WIDOW_THRESHOLD
            ]
            if not widows:
                break
            new_data = rewrite_widowed_bullets(data, widows, cap, resume_text, rewrite_fn)
            if new_data is data:
                break  # rewrite_fn returned no changes — stop early
            data = new_data
            pdf, font = _recompile_locked(data, font, preset, template_id)

        # ---- Stage 2: deterministic backstop — guarantee no orphan below the floor ----
        for _ in range(2):  # at most 2 passes (a trim can change wrapping once)
            cap = max_full_line_len(pdf)
            if cap <= 0:
                break
            pairs = measure_bullets(pdf)
            locations = _flatten_bullet_locations(data)
            if len(locations) != len(pairs):
                break
            bad = [i for i, (l1, l2) in enumerate(pairs) if l2 and (l2 / cap) < BACKSTOP_FLOOR]
            if not bad:
                break
            logger.info("deterministic backstop trimming %d residual widow(s) to one line", len(bad))
            data = copy.deepcopy(data)
            for i in bad:
                section, j, k = locations[i]
                data[section][j]["bullets"][k] = _trim_to_single_line(
                    data[section][j]["bullets"][k], cap
                )
            pdf, font = _recompile_locked(data, font, preset, template_id)

    except _PdftotextUnavailable as exc:
        logger.warning(
            "widow refinement disabled — %s; returning PDF without widow fixes", exc
        )

    # ---- Stage 3: spacing stretch (pdfplumber only — independent of pdftotext path) ----
    # Walk tight → normal → relaxed, taking the loosest preset that keeps 1 page.
    if _count_pdf_pages(pdf) == 1 and _page1_fill_ratio(pdf) < UNDERFILL_RATIO:
        latex_for_stretch = inject_into_template(data, template_id)
        for try_preset in ("normal", "relaxed"):
            candidate = _compile_at(latex_for_stretch, font, try_preset)
            if _count_pdf_pages(candidate) <= 1:
                pdf = candidate
                preset = try_preset
                if _page1_fill_ratio(pdf) >= UNDERFILL_RATIO:
                    break  # page is full enough — stop loosening
            else:
                break  # loosening overflowed — revert to previous preset

    return pdf


def tailor_resume(
    file_content: bytes,
    job_title: str,
    company: str,
    job_description: str,
    template_id: str = "classic",
) -> bytes:
    text = extract_text_from_pdf(file_content)
    if not text.strip():
        raise ValueError("Could not extract text from PDF")
    data = tailor_resume_to_json(text, job_title, company, job_description)
    data = _deduplicate_bullets(data)
    data = _repair_bullets(data, text)
    return refine_to_no_widows(
        data, text, rewrite_fn=_batch_widow_rewrite, template_id=template_id
    )


# ---------------------------------------------------------------------------
# Deterministic compile core — shared by value with the MCP's local compile.
# NO Claude calls. This is the seam the /api/v1/resume/compile endpoint and
# internship-mcp/compile_local.py both wrap; keep all three in lockstep
# (compile-engine parity rule).
# ---------------------------------------------------------------------------

def get_bullet_page_positions(pdf_bytes: bytes, structured_resume: dict) -> list[dict]:
    """Map each bullet in `structured_resume` to its on-page position in a compiled PDF.

    `structured_resume` must be in the CRITIQUE schema — entries whose `bullets` list
    holds `{"id": ..., "text": ...}` dicts (see resume_critique.critique_resume) — so
    each returned position can be keyed by the same bullet_id the frontend already uses
    to look up severity flags. `pdf_bytes` must be the PDF compiled from this exact
    resume via the classic template (TEMPLATE_REGISTRY["classic"] / inject_into_template's
    default) — this function only works against the classic template for now, because it
    scans page 1 for `_BULLET_GLYPH`, the itemize bullet character `inject_into_template`
    renders for that template.

    COORDINATE CONVENTION (read this before touching the math below):
    `top_frac` and `left_frac` are each a FRACTION of the page's full height/width
    (0.0-1.0), not absolute PDF points, so callers can multiply by whatever the PDF is
    actually rendered at (any zoom/DPI) instead of hardcoding a page size.
      - `top_frac` = (distance from the TOP edge of the page down to the top of the
        bullet's first rendered line) / page_height. It is 0.0 at the very top of the
        page and INCREASES going DOWN the page toward 1.0 at the bottom — this matches
        both pdfplumber's own `top` coordinate (which also increases downward) and a
        plain CSS `top: X%` on an element absolutely positioned inside a container
        anchored to the top of the rendered page canvas. A bullet further down the
        resume always has a strictly larger `top_frac` than one above it.
      - `left_frac` = (distance from the LEFT edge of the page to where the bullet's
        TEXT begins, i.e. just after the bullet glyph and its following whitespace) /
        page_width.

    Matching strategy: bullets are matched to rendered lines BY POSITION, in the same
    render order `_flatten_bullet_locations` already defines (experience bullets top to
    bottom, then projects) — this is the same order `measure_bullets` relies on for
    widow detection, so it's already proven to line up with how `inject_into_template`
    emits `\\item`s. If pdfplumber finds a different number of bullet-glyph lines on
    page 1 than the resume has bullets (e.g. content spilled onto a second page, or a
    non-classic template was actually used), this returns as many best-effort matches
    as it can and logs a warning rather than raising — callers should treat a short
    list as "some bullets are unpositioned," not as an error.
    """
    locations = _flatten_bullet_locations(structured_resume)
    bullet_ids: list = []
    for section, j, k in locations:
        entry = structured_resume.get(section, [])[j]
        bullet = entry.get("bullets", [])[k]
        bullet_ids.append(bullet.get("id") if isinstance(bullet, dict) else None)

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        page = pdf.pages[0]
        chars = page.chars
        page_height = page.height
        page_width = page.width

    if not chars:
        return []

    # Group chars into physical lines: chars on the same rendered line share (nearly)
    # identical `top`. Round to absorb sub-point rendering noise, then merge buckets
    # that ended up within 1pt of each other (rounding can split one visual line into
    # two adjacent buckets right at a rounding boundary).
    raw_lines: dict = {}
    for c in chars:
        key = round(c["top"], 1)
        raw_lines.setdefault(key, []).append(c)

    merged_lines: list = []  # list of [top, [chars]]
    for t in sorted(raw_lines.keys()):
        if merged_lines and abs(t - merged_lines[-1][0]) <= 1.0:
            merged_lines[-1][1].extend(raw_lines[t])
        else:
            merged_lines.append([t, list(raw_lines[t])])

    bullet_lines: list = []  # (top, left) for each physical line starting with the glyph
    for top, line_chars in merged_lines:
        line_chars.sort(key=lambda c: c["x0"])
        stripped = [c for c in line_chars if c["text"].strip()]
        if not stripped or stripped[0]["text"] != _BULLET_GLYPH:
            continue
        glyph_idx = line_chars.index(stripped[0])
        after_glyph = [c for c in line_chars[glyph_idx + 1:] if c["text"].strip()]
        left_x = after_glyph[0]["x0"] if after_glyph else stripped[0]["x0"]
        first_top = min(c["top"] for c in line_chars)
        bullet_lines.append((first_top, left_x))

    bullet_lines.sort(key=lambda pair: pair[0])

    n = min(len(bullet_lines), len(bullet_ids))
    if len(bullet_lines) != len(bullet_ids):
        logger.warning(
            "get_bullet_page_positions: found %d bullet-glyph line(s) on page 1 but the "
            "resume has %d bullet(s) — returning %d best-effort position(s)",
            len(bullet_lines), len(bullet_ids), n,
        )

    positions = []
    for i in range(n):
        bullet_id = bullet_ids[i]
        if bullet_id is None:
            continue
        top, left = bullet_lines[i]
        positions.append({
            "bullet_id": bullet_id,
            "top_frac": round(top / page_height, 4),
            "left_frac": round(left / page_width, 4),
        })
    return positions


def compile_resume_json_to_pdf(
    resume_json: dict, font_anchor: int = 11, spacing: str = "tight"
) -> tuple[bytes, dict]:
    """inject_into_template → font lock → _trim_to_single_line backstop →
    spacing stretch. NO Claude calls. Returns (pdf_bytes, diagnostics).

    diagnostics.widows lists bullets whose last wrapped line is still short —
    the CALLING AGENT (not this code) rewrites those bullets and recompiles.
    """
    data = copy.deepcopy(resume_json)
    latex = inject_into_template(data)

    # ---- Font lock (parameterized anchor; mirrors _lock_font) ----
    font = font_anchor if font_anchor in FONT_SIZES else _ANCHOR_FONT
    pdf = _compile_at(latex, font, spacing)
    if _count_pdf_pages(pdf) > 1:
        for size in [s for s in FONT_SIZES if s < font]:
            candidate = _compile_at(latex, size, spacing)
            font = size
            pdf = candidate
            if _count_pdf_pages(candidate) <= 1:
                break
    elif _page1_fill_ratio(pdf) < UNDERFILL_RATIO:
        for size in sorted([s for s in FONT_SIZES if s > font], reverse=True):
            candidate = _compile_at(latex, size, spacing)
            if _count_pdf_pages(candidate) <= 1:
                font = size
                pdf = candidate
                break

    # ---- Deterministic backstop: trim residual sub-floor orphans (no API) ----
    preset = spacing if spacing in _SPACING_PRESETS else "tight"
    try:
        for _ in range(2):
            cap = max_full_line_len(pdf)
            if cap <= 0:
                break
            pairs = measure_bullets(pdf)
            locations = _flatten_bullet_locations(data)
            if len(locations) != len(pairs):
                break
            bad = [i for i, (_l1, l2) in enumerate(pairs) if l2 and (l2 / cap) < BACKSTOP_FLOOR]
            if not bad:
                break
            for i in bad:
                section, j, k = locations[i]
                data[section][j]["bullets"][k] = _trim_to_single_line(
                    data[section][j]["bullets"][k], cap
                )
            latex = inject_into_template(data)
            pdf = _compile_at(latex, font, preset)
    except _PdftotextUnavailable as exc:
        logger.warning("compile core: widow backstop disabled — %s", exc)

    # ---- Spacing stretch if underfilled (deterministic) ----
    if preset == "tight" and _count_pdf_pages(pdf) == 1 and _page1_fill_ratio(pdf) < UNDERFILL_RATIO:
        latex_for_stretch = inject_into_template(data)
        for try_preset in ("normal", "relaxed"):
            candidate = _compile_at(latex_for_stretch, font, try_preset)
            if _count_pdf_pages(candidate) > 1:
                break
            pdf = candidate
            preset = try_preset
            if _page1_fill_ratio(pdf) >= UNDERFILL_RATIO:
                break

    # ---- Widow diagnostics for the agent's fix-and-recompile loop ----
    widows = []
    try:
        cap = max_full_line_len(pdf)
        pairs = measure_bullets(pdf)
        locations = _flatten_bullet_locations(data)
        if cap > 0 and len(locations) == len(pairs):
            for i, (_l1, l2) in enumerate(pairs):
                if l2 and (l2 / cap) < WIDOW_THRESHOLD:
                    section, j, k = locations[i]
                    widows.append({
                        "section": section, "entry": j, "bullet": k,
                        "last_line_chars": l2,
                    })
    except _PdftotextUnavailable:
        pass

    diagnostics = {
        "pages": _count_pdf_pages(pdf),
        "font_size": font,
        "spacing": preset,
        "fill_ratio": round(_page1_fill_ratio(pdf), 2),
        "widows": widows,
    }
    return pdf, diagnostics
