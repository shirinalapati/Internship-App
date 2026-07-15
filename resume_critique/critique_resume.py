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

- "red" (critical): the bullet does NOT name any specific accomplishment or deliverable — it is a
  category label ("Multi-service integration:", "Worked on backend systems:") or a category-plus-
  tool-inventory (a semicolon/comma-separated list of technologies, protocols, or service names)
  with no verb of accomplishment and no named thing that was built. Also red: vague/passive language
  where a recruiter cannot tell what the person actually did ("responsible for", "helped with", "was
  involved in"). The test: if you cannot state, in your own words, ONE concrete thing this person
  built or shipped from reading only this bullet, it is red. Judge every bullet on its own content —
  do not let a strong neighboring bullet in the same entry talk you out of flagging this one.
- "yellow" (needs work): the bullet DOES name a specific, real deliverable or accomplishment (a
  system, feature, or task with a clear verb — "built X", "migrated Y", "designed Z") — the test above
  passes — but it's missing a magnitude/outcome number or buries the real result. This is a bullet
  that already clears the red bar; it just doesn't yet prove impact.
- "green" (strong): specific, quantified, shows real ownership and impact — do not rewrite these, but
  you may note briefly why it works so the pattern is clear.

CALIBRATION (do not default to caution): "sparse" means few bullets flagged, not muted severity.
If a bullet is a textbook match for one of the patterns above, flag it at that severity even if the
surrounding bullets on the resume are strong. Do not soften a clear red into a yellow just because
the candidate looks impressive overall. Separately: if the resume contains genuinely standout
bullets (specific, quantified, real ownership and impact), you MUST flag at least 1-2 of the best as
green — a critique set with zero green flags on a resume that clearly has exceptional bullets is a
failure to find your positive examples, not appropriate restraint. Green flags are not optional
garnish; they are how the candidate learns which of their own bullets to write more like.

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


REWRITE_SYSTEM_PROMPT = """You are rewriting SPECIFIC flagged bullets on a resume based on critique \
feedback and optional candidate context. This is a targeted edit, not a full tailoring pass against a \
job description — most of the resume must come back byte-for-byte unchanged.

You will receive the full structured resume (every experience/project bullet has an "id") and a list \
of critiques ({bullet_id, severity, comment}) naming exactly which bullets need rewriting.

RULES (strict):
1. For every bullet whose id does NOT appear in the critiques list: copy its "text" field character-for-
   character unchanged. Do not rephrase, do not fix typos, do not touch it in any way.
2. For every bullet whose id DOES appear in the critiques list: rewrite it to directly address that
   exact critique comment. Stay strictly truthful — never invent facts, numbers, clients, systems,
   integrations, protocols, teams, or scope beyond what the original bullet or the candidate's own
   added context supports.
3. If the candidate provided additional context, use it only to inform tone/emphasis on the bullets
   you are rewriting — never to fabricate a new claim that isn't grounded in the original resume.

GROUNDING CHECK (this is the rule most often violated — apply it to every rewritten bullet before you
finalize the JSON): every specific noun in a rewritten bullet — a system name, a third-party API, a
protocol usage ("via gRPC", "published to Kafka"), a team count, a percentage, a duration, a user
count — must trace back verbatim or near-verbatim to either (a) the original bullet's own wording, or
(b) a sentence in the candidate's extra_context that names that exact fact. "Multi-service integration:
gRPC, Kafka, Kubernetes, Terraform, GitHub Actions" tells you which tools were touched, NOT what was
built with them, who consumed the output, or what the measured impact was — you may NOT invent a
downstream integration ("connected to a third-party logistics provider's SOAP API"), a consumer
("published events to 3 internal teams"), or a metric ("reducing setup time by 45 minutes") to fill
that gap. A tool-list bullet with no extra_context stays a tool-list bullet, reframed as an honest
sentence about the technical scope of the role (e.g. "Used gRPC, Kafka, Kubernetes, Terraform, and
GitHub Actions to support service-to-service communication and deployment for the platform") — not a
fabricated project. If the honest rewrite is still modest, that is the correct output: a truthful
Zone-A bullet beats a fabricated Zone-B one. When in doubt about whether a specific detail is grounded,
leave it out.

WHEN THE CRITIQUE ASKS FOR SOMETHING YOU DON'T HAVE: some critique comments say things like "add an
outcome number" or "how many users?" or "what problem did it solve?" — these are asking the *human* to
supply that detail, not asking you to invent a plausible-sounding one. If that number, scope detail, or
mechanism (e.g. "JWT tokens", "deck creation and progress tracking", "study streak") is not already in
the original bullet, a sibling bullet in the same entry, or extra_context, do NOT add it just because
the critique asked for it. Tighten the verb and phrasing instead — e.g. "Implemented a leaderboard
feature" can honestly become "Designed and implemented a leaderboard feature to surface top-performing
users," but NOT "...by study streak, encouraging daily engagement" unless "study streak" or "daily
engagement" appears in the resume or extra_context. A bullet that still reads as Zone A after your best
truthful attempt is the correct, honest output — do not close the gap with invention.

This also covers inferring "typical" features of a described product — e.g. assuming a flashcard app
must have "deck creation" and "card review scheduling," or that any full-stack app must have "user
authentication," just because those are common in that category of product. Only claim a specific
feature, component, or mechanism if it is explicitly named somewhere in the resume (this bullet or a
sibling bullet in the same entry) or in extra_context — plausible-for-the-category is not grounded. A
sibling bullet naming the product's *category* (e.g. "a spaced-repetition flashcard web app") grounds
you rewriting THIS bullet's tech-stack list into a sentence about that category, but it does NOT grant
you license to name specific sub-features ("deck creation", "authentication", "scheduling logic") that
no bullet actually lists — describe the stack's role at the level of specificity the resume already
gives you, no deeper. "User authentication" and "session management" are your own most common invented
fillers for a frontend+backend tech-list bullet with no stated feature — do not reach for them (or any
other named feature/component) unless the word appears in this entry's other bullets. If every bullet
in the entry is just a tech-stack list with zero named feature anywhere, the honest rewrite names ONLY
the technologies and the general category of work (e.g. "built the frontend and backend for the
[product, from a sibling bullet] using X, Y, Z") — it does not name a specific capability inside that
product.

4. Preserve the exact same JSON structure: same sections, same entries in the same order, same bullet
   ids, same non-bullet fields (name, email, education, skills, detected_category, etc.) unchanged.
5. Do not add or remove bullets, entries, or sections.

Return ONLY valid JSON (no markdown fences), same shape as the input resume (bullets keep their "id"):
{
  "name": "...", "email": "...", "phone": "...", "website": "...", "github": "...", "linkedin": "...",
  "education": [{"school": "...", "location": "...", "degree": "...", "dates": "..."}],
  "experience": [
    {"company": "...", "location": "...", "title": "...", "dates": "...",
     "bullets": [{"id": "b1", "text": "..."}]}
  ],
  "projects": [{"name": "...", "dates": "...", "bullets": [{"id": "b4", "text": "..."}]}],
  "skills": {"...": "..."},
  "detected_category": "..."
}"""


def apply_critique_rewrite(
    structured_resume: dict, critiques: list, extra_context: str = "", system_prompt=None, temperature=None
) -> dict:
    """Single Sonnet call: rewrite ONLY the flagged bullets, leave everything else untouched.

    Unlike resume_tailor.tailor_resume_to_json (which actively rewrites nearly every bullet to
    align with a job description), this targets exactly the bullet_ids in `critiques` — the
    caller can compute which bullets changed just by checking membership in that same list,
    no fuzzy text diffing required.
    """
    sys_p = system_prompt if system_prompt is not None else REWRITE_SYSTEM_PROMPT
    client = anthropic.Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))

    user_msg = (
        "Structured resume:\n" + json.dumps(structured_resume) +
        "\n\nCritiques (bullets to rewrite):\n" + json.dumps(critiques)
    )
    if extra_context and extra_context.strip():
        user_msg += "\n\nAdditional context from candidate: " + extra_context.strip()

    create_kwargs = dict(
        model="claude-sonnet-4-5-20250929",
        max_tokens=6000,
        system=sys_p,
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
        return json.loads(raw)
    except json.JSONDecodeError as e:
        stop = response.stop_reason
        raise RuntimeError(
            f"Rewrite JSON truncated (stop_reason={stop!r}): {e}. "
            "Increase max_tokens or shorten the resume."
        ) from e


def to_compile_schema(structured_resume: dict) -> dict:
    """Convert critique's {id, text} bullet objects into the plain-string bullet lists
    that resume_tailor.compile_resume_json_to_pdf / inject_into_template expect."""
    data = dict(structured_resume)
    for section in ("experience", "projects"):
        entries = []
        for entry in data.get(section, []):
            entry = dict(entry)
            entry["bullets"] = [b["text"] if isinstance(b, dict) else b for b in entry.get("bullets", [])]
            entries.append(entry)
        data[section] = entries
    return data
