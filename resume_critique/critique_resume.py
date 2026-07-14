"""Deterministic wrapper around the Critique feature's single Sonnet call.

Parses a resume into structured JSON (same shape family as
resume_tailor.tailor_resume.tailor_resume_to_json) and produces a SPARSE set of
per-bullet critiques — most bullets get none. Reuses extract_text_from_pdf from
the tailor module rather than duplicating PDF parsing.
"""
import json
import logging
import os
import re

import anthropic

from job_categories import CATEGORY_IDS
from resume_tailor.tailor_resume import extract_text_from_pdf  # noqa: F401 (re-exported)

logger = logging.getLogger(__name__)

CRITIQUE_SYSTEM_PROMPT = """You are a senior technical recruiter who reviews resumes the way top-tier \
internship programs (YC-affiliated startups, selective ATS screens) actually screen them: against \
specific, verifiable criteria — not vibes. "Excellent communicator" is not shown by the word \
"communicator"; it is shown by a bullet that names an audience, an action, and an outcome.

TASK 1 — PARSE
Parse the resume text into structured JSON, faithfully preserving all real content. Never invent
facts, companies, dates, or numbers that are not in the source text.

Assign every bullet inside "experience" and "projects" entries a sequential id "b1", "b2", "b3", ...
in reading order (top to bottom of the resume, experience before projects, first bullet of an entry
before the next). Bullets inside "education" or "skills" do NOT get ids and are never critiqued.

TASK 2 — DETECT OR APPLY INDUSTRY
If the caller supplies a target_category, use that value verbatim in "detected_category" and do not
second-guess it. Otherwise infer the single best-fit bucket from this fixed list based on the resume's
actual content (skills, titles, coursework): software, data_ml, hardware, security, product, design,
business, healthcare, legal, policy, education, other. Pick exactly one id from that list.

TASK 3 — CRITIQUE (sparse, this is the most important rule)
Only flag a bullet if it clearly belongs in one of these three buckets. Leave the clear majority of
bullets OUT of the critiques array entirely — an unflagged bullet is not an oversight, it means "this
is fine as-is." Worst case, a couple of bullets get a critique; never critique every bullet.

- "red" (critical): vague, passive, or unfalsifiable — a recruiter cannot tell what the person actually
  did or verify it. E.g. "responsible for", "helped with", "was involved in", a bare tech-stack list
  with no outcome.
- "yellow" (needs work): concrete and specific, but under-quantified or buries the real result — decent
  verb and detail, missing a number or a clear downstream effect.
- "green" (strong): specific, quantified, shows real ownership and impact — do not rewrite these, but
  you may note briefly why it works so the pattern is clear.

Each critique comment is 1-2 sentences, specific to that exact bullet's wording, and actionable —
never generic advice like "add more detail."

Return ONLY valid JSON (no markdown fences) with this exact structure:
{
  "name": "Full Name", "email": "...", "phone": "...", "website": "...", "github": "...", "linkedin": "...",
  "education": [{"school": "...", "location": "City, ST", "degree": "...", "dates": "..."}],
  "experience": [
    {"company": "...", "location": "City, ST", "title": "...", "dates": "...",
     "bullets": [{"id": "b1", "text": "..."}]}
  ],
  "projects": [
    {"name": "...", "dates": "...", "bullets": [{"id": "b4", "text": "..."}]}
  ],
  "skills": {"Programming Languages": "Python, Java", "Frameworks & Libraries": "React, Node.js"},
  "detected_category": "software",
  "critiques": [{"bullet_id": "b1", "severity": "red", "comment": "..."}]
}"""


def critique_resume_to_json(resume_text: str, target_category=None, system_prompt=None, temperature=None) -> dict:
    """Single Sonnet call: parse resume into structured JSON + sparse bullet critiques.

    `target_category` — pass one of job_categories.CATEGORY_IDS to skip auto-detection
    (e.g. the user picked a category from the fallback dropdown); None triggers inference.
    """
    sys_p = system_prompt if system_prompt is not None else CRITIQUE_SYSTEM_PROMPT
    client = anthropic.Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))

    user_msg = "Resume to critique:\n" + resume_text
    if target_category:
        user_msg += f"\n\ntarget_category (use verbatim, do not infer): {target_category}"

    create_kwargs = dict(
        model="claude-sonnet-4-5-20250929",
        max_tokens=6000,
        system=[{"type": "text", "text": sys_p, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_msg}],
    )
    if temperature is not None:
        create_kwargs["temperature"] = temperature
    response = client.messages.create(**create_kwargs)
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        stop = response.stop_reason
        raise RuntimeError(
            f"Critique JSON truncated (stop_reason={stop!r}): {e}. "
            "Increase max_tokens or shorten the resume."
        ) from e

    if data.get("detected_category") not in CATEGORY_IDS:
        data["detected_category"] = target_category if target_category in CATEGORY_IDS else "other"
    data["critiques"] = [
        c for c in data.get("critiques", [])
        if isinstance(c, dict) and c.get("severity") in ("red", "yellow", "green") and c.get("bullet_id")
    ]
    return data
