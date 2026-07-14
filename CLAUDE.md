# Internship Matcher — Claude Context

## What This Project Does
A full-stack web app that matches students to software internships using AI. Users upload a resume (PDF), and the app extracts their skills, scrapes current internship listings, and uses Claude to rank and explain the best matches. Users can also tailor their resume to a specific job with AI.

---

## Commit & PR Policy (hard rule)
- **Never add `Co-Authored-By: Claude` (or any Claude/Anthropic co-author trailer) to any commit.**
- **Never add "Generated with Claude Code" or any similar attribution line to any commit message or PR description/body.**
- This applies to every commit and every PR in this repo, no exceptions, regardless of default tooling behavior.
- Every new feature ships as its own PR branched from `dev` (never `main`) — see [PR base branch rule].

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, FastAPI 0.109.2, Uvicorn |
| AI | Anthropic Claude (Haiku 4.5 for fast ops, Sonnet 4.5 for deep ops) |
| Frontend | React 19 + TypeScript (Create React App), React Router v7 |
| Auth | Clerk (`@clerk/react` v6) — frontend only, no server-side auth guards |
| Database | SQLAlchemy 1.4 + SQLite (dev) / Supabase PostgreSQL (prod) |
| Cache | Redis (4h TTL) + DB fallback + in-memory dict (3-tier) |
| File Storage | AWS S3 (resume files via boto3) |
| Resume Parsing | pdfplumber (PDF), pytesseract + Pillow (images/OCR) |
| Resume Tailoring | Claude Sonnet + LaTeX (pdflatex compiles to PDF) |
| Scraping | BeautifulSoup4 + requests (GitHub SimplifyJobs repo) |
| Styling | Tailwind CSS v3 + shadcn/ui patterns (HSL CSS variables, CVA) |
| Streaming | SSE via sse-starlette (`/api/match-stream`) |
| Deployment | Railway (primary), Docker Compose, AWS EC2 (alternatives) |

---

## Project Structure

```
/
├── app.py                    # FastAPI app — all routes, startup/shutdown lifecycle
├── mcp_api.py                # MCP /api/v1 sub-app (X-API-Key auth, NO model calls) + /developer key CRUD
├── job_database.py           # SQLAlchemy ORM models (jobs, cache_metadata, resume_cache, api_keys, quota logs)
├── job_cache.py              # Hybrid Redis + DB caching layer
├── s3_service.py             # AWS S3 resume upload/download
├── main.py                   # CLI entry point for local testing
├── AGENTS.md                 # Agent onboarding guide (for Codex, Gemini, Cursor, etc.)
├── requirements.txt
├── Dockerfile                # Single-container build (backend + React build)
├── docker-compose.yml        # Full stack: Redis + Backend + Nginx
├── railway.toml              # Railway PaaS config
├── nginx.conf                # Reverse proxy config
├── start.sh                  # Dev startup script
│
├── job_scrapers/
│   ├── dispatcher.py         # Scraping orchestrator
│   └── scrape_github_internships.py  # PRIMARY active scraper (SimplifyJobs GitHub repo)
│   # scrape_google/meta/microsoft/salesforce.py — DISABLED (Selenium issues)
│
├── matching/
│   ├── matcher.py            # Core matching engine — orchestrates full pipeline
│   ├── llm_skill_extractor.py # Claude skill extraction + deep ranking + candidate profiling
│   ├── metadata_matcher.py   # Weighted metadata scoring (location, experience level, etc.)
│   └── llm_processing_node.py
│
├── resume_parser/
│   └── parse_resume.py       # PDF/image parsing + Claude skill extraction
│
├── resume_tailor/
│   ├── tailor_resume.py      # Claude-powered resume rewrite + LaTeX PDF generation
│   └── template.tex          # LaTeX template with parameterized font/spacing placeholders
│
├── evals/                    # Prompt eval harness (zero-API-cost, frozen baseline + LLM judge)
│   ├── run.py                # Entry point: python -m evals.run
│   ├── extract.py            # A/B extraction runner
│   ├── judge.py              # Pairwise Sonnet judge
│   ├── datasets/             # Frozen test cases
│   ├── prompts/              # Candidate prompt variants
│   └── results/              # Timestamped markdown reports
│
├── email_sender/
│   └── generate_email.py
│
├── tests/                    # pytest test suite
│
└── frontend/                 # React CRA app
    ├── src/
    │   ├── App.tsx            # Root: routes + ClerkProvider
    │   ├── pages/
    │   │   ├── LandingPage.tsx   # /  — marketing page
    │   │   ├── FindPage.tsx      # /find — main app (upload + results)
    │   │   ├── HistoryPage.tsx   # /history — past analyses
    │   │   ├── UsagePage.tsx     # /usage — weekly quota cards (incl. remote_compile)
    │   │   ├── DeveloperPage.tsx # /developer — API keys + MCP client config snippets
    │   │   ├── DocsPage.tsx      # /docs — public API/MCP docs (sans-serif reading UI)
    │   │   ├── LoginPage.tsx     # /login
    │   │   └── HomePage.tsx
    │   ├── components/
    │   │   ├── JobCard.tsx       # Rich match result card with score + reasoning
    │   │   ├── Header.tsx
    │   │   ├── ResumeUploadForm.tsx
    │   │   └── ui/               # shadcn-style primitives
    │   └── lib/
    │       └── supabaseClient.ts # Supabase client (supports Clerk JWT)
    ├── package.json
    └── tailwind.config.js
```

---

## Development Commands

```bash
# Backend
uvicorn app:app --host 0.0.0.0 --port 8000 --reload

# Frontend (proxies /api → localhost:8000 via setupProxy.js)
cd frontend && npm start

# Both together
./start.sh --all

# Tests
pytest tests/

# Prompt evals (no API cost — uses cached extractions + agent-as-judge)
python -m evals.run
python -m evals.run --cases negative_context   # single case
python -m evals.run --no-cache                 # force re-extraction

# Production build (Railway runs this)
pip install -r requirements.txt
cd frontend && npm install && npm run build
uvicorn app:app --host 0.0.0.0 --port $PORT
```

---

## API Routes

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/match` | Upload resume → get matched jobs (JSON) |
| POST | `/api/match-stream` | Same but SSE streaming with real-time progress |
| GET | `/api/resume-cache/{hash}` | Check if resume results are cached |
| GET | `/api/user-history` | User's past resume analyses |
| POST | `/api/tailor-resume` | Generate tailored PDF resume for a job |
| GET | `/api/cache-status` | Redis + DB cache health |
| POST | `/api/refresh-cache` | Manually trigger full job scrape |
| POST | `/api/refresh-cache-incremental` | Incremental scrape |
| GET | `/api/database-stats` | DB statistics |
| GET | `/api/usage` | Per-user quota status (tailor, think-deeper, remote_compile) |
| GET/POST/DELETE | `/api/developer/keys` | API-key CRUD for the /developer page (Clerk auth) |
| GET | `/api/v1/jobs` | MCP: list active jobs (X-API-Key, 120/h) |
| GET | `/api/v1/jobs/{hash}` | MCP: full untruncated JD (X-API-Key, 120/h) |
| POST | `/api/v1/jobs/prefilter` | MCP: deterministic keyword+metadata scoring (X-API-Key, 120/h) |
| POST | `/api/v1/resume/compile` | MCP: fallback pdflatex compile (15/week, 3 concurrent) |
| GET | `/api/v1/openapi.json` | Published MCP contract (sub-app OpenAPI; main-app docs stay disabled) |
| POST | `/mcp` | Hosted MCP discovery tier (streamable HTTP, Python ≥3.10 only): jobs_list/job_get/jobs_prefilter |
| GET | `/{full_path}` | Catch-all → serves React SPA `index.html` |

**`/api/v1` is the MCP surface** (see `mcp_api.py` and the workspace CLAUDE.md one level
up): a mounted FastAPI sub-app, per-user `api_keys` auth, **zero model calls** — all AI
reasoning belongs to the calling agent. The deterministic cores it wraps are
`matching/matcher.prefilter_and_score` and `resume_tailor/tailor_resume.compile_resume_json_to_pdf`
(the latter is shared by value with internship-mcp — compile parity rule applies).

---

## AI / Matching Pipeline

The main flow for `/api/match-stream`:

1. **Parse resume** — pdfplumber or pytesseract OCR
2. **Extract skills** — Claude Haiku 4.5 (`claude-haiku-4-5-20251001`)
3. **Fetch jobs** — Redis cache → DB → scrape fallback
4. **Extract job skills** — Claude Haiku 4.5 (cached per job hash, 3-tier)
5. **Metadata scoring** — weighted: 40% experience, 25% location, 20% industry, 15% citizenship
6. **Skill matching** — exact match + synonym normalization + difflib fuzzy fallback
7. **Deep ranking** — Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`) re-ranks top 30 → top 10
8. **Stream results** — SSE events with `step`, `message`, `progress` fields

**"Think Deeper" mode** — extended analysis with Claude extended thinking, triggered by `think_deeper=true`.

**Resume tailoring** — Claude Sonnet 4.5 rewrites resume JSON for a target job, then pdflatex compiles LaTeX → PDF. Font/spacing pipeline described below.

---

## Resume Tailoring Pipeline (`resume_tailor/tailor_resume.py`)

A multi-stage pipeline that generates a single-page, page-filling PDF:

1. **`tailor_resume_to_json`** — single Sonnet call; outputs structured resume JSON with tailored bullets. `max_tokens=6000`. JD capped at 6000 chars to bound cost.
2. **`_repair_bullets`** — detects syntactically incomplete bullets (`_is_incomplete_bullet`: unmatched parens, trailing colons, dangling conjunctions) and batch-repairs them via a second Sonnet call.
3. **Deduplication** — removes near-duplicate bullets within each entry.
4. **`_lock_font` (page-fill stage)** — anchors at 11pt; if content overflows, steps DOWN `[11, 10, 9, 8]`; if content fits with slack, grows UP `[12, 14]`. Result: largest font that still fits.
5. **`refine_to_no_widows`** — iterates up to 3 rounds; detects widow lines via pdfplumber, rewrites short orphan bullets via batched Haiku call (`_batch_widow_rewrite`).
6. **Spacing stretch (stage 3)** — if page is still underfilled after widow resolution, walks `tight → normal → relaxed` spacing presets. Deterministic, no LLM call.

**Font ladder:** `FONT_SIZES = [14, 12, 11, 10, 9, 8]`, anchor `_ANCHOR_FONT = 11`.

**Spacing presets:** `tight` / `normal` / `relaxed` — defined in `_SPACING_PRESETS`, substituted into LaTeX template via `{{...}}` placeholders.

**Prompt strategy (TAILOR_SYSTEM_PROMPT):**
- Zone B bullets (≥215 chars, two full lines) are the default target — fills the page densely.
- Zone A (≤115 chars) is acceptable only when no more truthful facts exist.
- Dead zone (116–214 chars) is explicitly forbidden — creates a short orphan line.
- Bullet count: 3–4 per experience role, 3 per project.
- Truthfulness is non-negotiable: never invent facts to reach Zone B.

---

## Prompt Versioning & Usage Tracking (`app.py`)

- **`PROMPT_VERSION = "v2"`** — appended to all resume cache keys so prompt changes invalidate stale cached results. Bump this constant whenever a prompt edit changes expected output shape.
  - Cache key format: `{resume_hash}_{quick|deep}_{PROMPT_VERSION}`
- **`TRACK_USAGE`** — env var toggle (`TRACK_USAGE=true` by default). When `false`, disables weekly per-user quotas, slowapi rate limiting, and usage counters. Useful in local dev to avoid hitting limits.
  - Set `TRACK_USAGE=false` in `.env` for unrestricted local testing.

---

## Experience Level Enum

Valid values for `experience_level` in all LLM outputs and DB fields: **`student`**, **`entry_level`**, **`experienced`**. The value `recent_graduate` was removed — do not use it. The skill extractor enforces this at the prompt level.

---

## Prompt Caching (`llm_skill_extractor.py`)

`cache_control: {"type": "ephemeral"}` is set on system prompt blocks in:
- `_score_jobs_with_prompt` — scoring criteria block
- `analyze_and_match_single_call` — system instructions block
- `extract_candidate_profile` — system instructions block

This reduces Anthropic billing on repeated calls with stable system prompts.

---

## Eval Harness (`evals/`)

Measures whether prompt edits to `RESUME_ANALYSIS_SYSTEM_PROMPT` improve or regress extraction quality.

- **Zero API cost by default** — uses frozen cached extractions; only calls the API if `--no-cache` is passed.
- **A/B extraction** — runs baseline + candidate prompts via real Haiku calls (temperature=0, results cached by prompt hash).
- **Pairwise judge** — Sonnet grades both extractions with randomized A/B order to reduce position bias.
- **Structural gate** — schema validation before expensive judge calls; fails fast on malformed JSON.
- Reports written to `evals/results/report-<timestamp>.md`.

```bash
python -m evals.run                            # all 10 cases
python -m evals.run --cases negative_context   # single case
python -m evals.run --no-cache --no-judge-cache  # force full re-run
```

---

## Database Models (`job_database.py`)

**`jobs`** — internship listings
- `job_hash` (SHA-256 of company+title+location+domain) — deduplication key
- `required_skills`, `job_metadata` stored as JSON strings
- `is_active` — soft delete; jobs inactive if `last_seen` > 3 days or `days_since_posted` > 30

**`cache_metadata`** — tracks scrape operations and job skill cache entries
- `cache_type` can be `'daily'`, `'full'`, or `'job_skills_{hash}'`

**`resume_cache`** — caches matching results per user
- Keyed by `(user_id, resume_hash)` — suffix `_deep` for think-deeper mode
- 30-day TTL via `expires_at`

**`api_keys`** — per-user MCP keys (raw `im_live_<32 base62>` shown once, SHA-256 stored)
- `verify_api_key` bumps `last_used`; `revoked` is a soft kill switch
- Distinct from `INTERNSHIP_MATCHER_API_KEY` (shared admin gate) — never conflate them

**`tailor_request_log` / `think_deeper_request_log` / `remote_compile_log`** — append-only
weekly-quota ledgers (rolling 7-day window, helpers in `quota.py`). `remote_compile_log`
(15/week) is consumed ONLY by API-key remote compiles on `/api/v1/resume/compile` and
carries the triggering `key_prefix`; it is deliberately separate from the in-app tailor
quota so users can tell agent usage from web-app usage.

Schema auto-created via `Base.metadata.create_all()` — no Alembic migration files exist.

---

## Caching

| Tier | Store | TTL | Key |
|------|-------|-----|-----|
| 1 | Redis | 4 hours | `internship_jobs_cache` |
| 2 | SQLite/PostgreSQL | persistent | `jobs` table |
| 3 | In-memory dict | process lifetime | content hash |

Resume results cached in `resume_cache` table (30 days). Background `asyncio` task refreshes jobs every 24h.

---

## Authentication

- **Frontend:** Clerk (`useAuth()` hook) — `getToken()` fetches a short-lived JWT sent as `Authorization: Bearer <token>` on all user-specific API calls
- **Backend:** `auth.py` — `require_user` FastAPI dependency verifies the Clerk JWT via JWKS (RS256), returns the verified `user_id` from the `sub` claim. Raises 401 if missing/invalid/expired.
- Protected endpoints: `/api/resume-cache/{hash}`, `/api/user-history`, `/api/match-stream`, `/api/tailor-resume`
- **Supabase:** Frontend Supabase client optionally uses Clerk JWT for RLS, but it's not enforced
- `CLERK_PUBLISHABLE_KEY` backend env var (same value as `REACT_APP_CLERK_PUBLISHABLE_CLIENT_KEY`) is required for JWKS URL derivation
- Auth was migrated: Google OAuth → Stack Auth → Clerk (some legacy code remains)
- **Third auth plane (MCP):** `require_api_key_user` in `auth.py` verifies per-user
  `X-API-Key` keys from the `api_keys` table — used only by `/api/v1`. Rate-limit
  bucket for these routes is `sha256(full key)` (never a raw prefix slice).

---

## Environment Variables

**Backend (Python):**
```
CLAUDE_API_KEY          # Anthropic API key
DATABASE_URL            # PostgreSQL URL (Supabase) — defaults to sqlite:///./jobs.db
REDIS_URL               # Redis URL — defaults to redis://localhost:6379
AWS_ACCESS_KEY_ID       # S3 credentials
AWS_SECRET_ACCESS_KEY
AWS_REGION              # default: us-east-1
AWS_BUCKET_NAME         # S3 bucket for resumes
SECRET_KEY              # Session middleware secret
ENVIRONMENT             # "development" | "staging" | "production"
PORT                    # Injected by Railway/Render
CLERK_PUBLISHABLE_KEY   # Same as REACT_APP_CLERK_PUBLISHABLE_CLIENT_KEY — used to derive JWKS URL
TRACK_USAGE             # "true" (default) | "false" — disables quotas/rate limits for local dev
INTERNSHIP_MATCHER_API_KEY  # Required for /api/refresh-cache and GitHub Actions polling workflow
```

**Frontend (React, baked in at build time):**
```
REACT_APP_CLERK_PUBLISHABLE_CLIENT_KEY
REACT_APP_SUPABASE_URL
REACT_APP_SUPABASE_ANON_KEY
REACT_APP_API_URL       # Backend URL (dev only; prod uses relative URLs)
```

---

## Deployment

**Railway (primary):**
- Dockerfile-based, single container (Python backend serves React build)
- `railway.toml` configures build and start commands
- `frontend/build/` is committed and served by FastAPI static mount

**Docker Compose:**
- 3 services: Redis, FastAPI backend, Nginx+frontend
- `docker-compose.yml` + `nginx.conf`

**AWS EC2:**
- `setup-ec2.sh` and `deploy.sh` available

**Production URL:** `https://internship-app-production.up.railway.app`

---

## Key Patterns

- **SPA serving:** FastAPI serves `frontend/build/index.html` via catch-all route `/{full_path:path}` in production
- **Dev proxy:** `frontend/src/setupProxy.js` proxies `/api` → `localhost:8000`
- **SSE streaming:** `EventSourceResponse` from sse-starlette; frontend uses native `EventSource` API
- **Job deduplication:** SHA-256 of `(company + title + location + domain)` → `job_hash`
- **Background tasks:** `asyncio.create_task()` for scraping/refresh; cleaned up on app shutdown
- **API URL detection:** `FindPage.tsx` checks `NODE_ENV === 'development'` to pick base URL
- **shadcn patterns:** Components use CVA + `cn()` util, HSL CSS variables for theming
- **LaTeX PDF:** `pdflatex` must be installed in the container for resume tailoring to work
- **Job description truncation:** JD fed to resume tailor is intentionally capped at 6000 chars — scraped JDs are well under this; the cap bounds input cost/latency.

---

## Supabase Project
- Project ID: `gninorapexsxsfbtyajl`
- Used for: `resume_cache` and user history (via frontend Supabase client)

## Job Data Source
- GitHub: `SimplifyJobs/Summer2026-Internships` README.md (parsed via BeautifulSoup)
- Other scrapers (Google, Meta, Microsoft, Salesforce) exist but are **disabled**

---

## Self Learning

This section tracks architectural decisions and non-obvious changes made during active development. When you land on this branch and something in the code doesn't match an older mental model, check here first.

**How this works:** After each meaningful PR or set of changes, append an entry below with: the branch/PR, what changed, and *why* (the constraint or problem that drove it). Entries are chronological newest-last so `git blame` and reading top-to-bottom both make sense.

---

### tweaking-prompts branch (PR #22)

**Resume tailor: font-grow-to-fill (Jun 8–9 2026)**
- Problem: sparse resumes were compiled at the minimum font that fits, leaving large bottom whitespace.
- Fix: `_lock_font` now anchors at 11pt and grows UP (to 12pt, 14pt) when the page fits with slack. Shrinks only if 11pt overflows.
- Font ladder expanded: `[14, 12, 11, 10, 9, 8]` (was `[11, 10, 9, 8]`).
- `template.tex` spacing parameterized with `{{...}}` placeholders. Three presets: `tight`, `normal`, `relaxed`.
- Stage 3 spacing stretch walks presets after widow resolution if page is still underfilled.

**Resume tailor: density prompt overhaul (Jun 8–9 2026)**
- `TAILOR_SYSTEM_PROMPT` now defaults to *expand* (Zone B ≥215 chars) instead of tighten. Previous default was concision-first.
- DENSITY section renamed from CONCISION; bullet count guidance raised to 3–4 per role, 3 per project.
- User message rewritten to match density-first framing. Explicit "dead zone" (116–214 chars) guidance added.

**Resume tailor: incomplete bullet repair (Jun 9 2026)**
- Added `_is_incomplete_bullet` validator (unmatched parens, trailing colon, dangling preposition/conjunction).
- Added `_repair_bullets` — batches all flagged bullets in one Sonnet call, spliced back into the data dict.
- Repair runs between initial JSON generation and deduplication in the pipeline.
- `max_tokens` raised from 4000 → 6000 on `tailor_resume_to_json` to prevent truncation on dense resumes.

**Resume tailor: section order matches industry standard (Jun 9 2026)**
- Template section order changed: Education → Experience → Projects → Technical Skills (was Education → Technical Skills → Experience → Projects).

**Prompt versioning: `PROMPT_VERSION = "v2"` (Jun 6 2026)**
- All resume cache keys now include `PROMPT_VERSION` so prompt changes bust stale cache entries.
- Bump this constant in `app.py` whenever a prompt edit would change expected output shape.
- Bug fixed: early-exit cache key path in `app.py` was missing the version suffix (now included).

**Experience level enum cleanup (Jun 6 2026)**
- Removed `recent_graduate` from the valid set everywhere (prompt, ORM enum, metadata logic).
- Valid values are now exactly: `student`, `entry_level`, `experienced`.
- If you see `recent_graduate` anywhere it is a bug — remove it.

**Prompt caching wired (`cache_control: ephemeral`) (Jun 6 2026)**
- `analyze_and_match_single_call` and `_score_jobs_with_prompt` system prompts now carry `cache_control`.
- Cuts Anthropic billing on repeated calls with stable system prompts.

**`TRACK_USAGE` toggle added (Jun 2026)**
- `TRACK_USAGE=false` in `.env` disables quotas, rate limits, and usage counters for local dev.
- `tests/conftest.py` forces `TRACK_USAGE=true` so the test suite always exercises quota logic.

**`INTERNSHIP_MATCHER_API_KEY` secret (Jun 6 2026)**
- GitHub Actions "polling internships" workflow requires this secret set in the repo.
- Was previously named `CACHE_REFRESH_API_KEY` — all references updated.

**Eval harness (`evals/`) added (Jun 8–9 2026)**
- Zero-API-cost by default: frozen cached extractions, no Anthropic spend unless `--no-cache`.
- Agent-as-judge pattern: Claude Code acts as model+judge instead of calling real Sonnet.
- Use this before merging any prompt edit to `RESUME_ANALYSIS_SYSTEM_PROMPT`.

### developer-page / docs-page / compile-quota branches (PRs #25–#27, Jun 2026)

**MCP apply-agent surface added (PR #25)**
- New `/api/v1` mounted FastAPI sub-app (`mcp_api.py`) — the data plane for the public
  `internship-mcp-server` repo (github.com/internship-app1/internship-mcp-server).
  Prime Directive: NO model calls behind any `/api/v1` route; the calling agent does all
  reasoning. A test monkeypatches `anthropic.Anthropic` to raise to enforce this.
- Deterministic cores extracted ADDITIVELY (web behavior unchanged):
  `compile_resume_json_to_pdf` in `tailor_resume.py` (font lock → widow backstop →
  spacing stretch → widow diagnostics; shared by value with the MCP repo — parity rule)
  and `prefilter_and_score` + `_passes_hard_filters` in `matcher.py`.
- `/developer` page: key CRUD, per-client MCP config snippets (Codex tab renders real
  TOML, not JSON), ToS disclaimer.
- Review fixes worth remembering: rate-limit bucket = sha256(full key) — raw[:12] only
  has 4 random chars past "im_live_" and collides; compile overload uses a bounded
  admission COUNTER, not Semaphore.locked() (point-in-time check let requests queue
  instead of 429ing).

**Docs page (PR #26)**
- Public `/docs` (DocsPage.tsx): sans-serif reading UI (the site's mono-everywhere style
  was unreadable for long-form docs), sticky sidebar with IntersectionObserver highlight,
  cURL/Python/JS request-sample selector (one shared preference), field-level schema
  tables with type/required badges.

**Remote-compile weekly quota (PR #27)**
- 15/week per account for `/api/v1/resume/compile`, ledger `remote_compile_log`
  (key_prefix-attributed). Checked BEFORE compiling; recorded only on success; cache
  hits free. Surfaced on /usage (own card, labelled API-key) + /developer (usage strip).
  Deliberately separate from the tailor quota so agent usage ≠ web-app usage.

**Hosted MCP discovery tier (hosted-mcp branch)**
- New `/mcp` mount (`mcp_remote.py`) serves streamable HTTP for zero-install clients.
  It intentionally exposes only stateless discovery tools: `jobs_list`, `job_get`, and
  `jobs_prefilter` plus a resource that points users to the full local agent.
- No profile vault, resume parsing, remote compile, packets, tracker, or Playwright on
  hosted MCP. This keeps PII and heavy work off our servers.
- Auth accepts `X-API-Key` or `?key=` for claude.ai custom connector compatibility.
  Header wins when both are present. OAuth is the v2 replacement.
- The `mcp` SDK requires Python ≥3.10. `app.py` guards the import so the local 3.9 venv
  still boots and skips `/mcp`; production 3.11 mounts it. Keep this guard unless local
  dev/CI moves to 3.11.
- Starlette redirects `/mcp` → `/mcp/` for mounted apps; MCP clients POST and may not
  follow 307s. The `_McpSlashRewrite` middleware rewrites the bare path in-process.

**Testing footguns (recurring)**
- App.test.tsx's Route mock renders EVERY route's element — stub each new page in the
  mock list or the suite fails on unmocked hooks (bit us twice: DeveloperPage, DocsPage).
- conftest's `sqlite:///:memory:` DB is per-connection; tests that cross threads
  (TestClient, asyncio.to_thread) need the file-backed-DB fixture in test_mcp_api.py.
- tests/test_resume_parser.py mock failures pre-date this work (verified on clean HEAD).
