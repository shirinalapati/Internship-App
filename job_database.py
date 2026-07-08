"""
Job Database Module - SQLAlchemy-based persistent storage for job data
Provides deduplication, historical tracking, and efficient querying
"""
import logging
import os
import hashlib
import json
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)
from typing import List, Dict, Optional, Set
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, Index, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.sql import func

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./jobs.db").strip('"')
is_postgres = DATABASE_URL.startswith("postgresql")
engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    **({
        "pool_size": 5,
        "max_overflow": 10,
        "connect_args": {"sslmode": "require"}
    } if is_postgres else {})
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Job(Base):
    """Job model for storing internship listings"""
    __tablename__ = "jobs"
    
    id = Column(Integer, primary_key=True, index=True)
    job_hash = Column(String(64), unique=True, index=True, nullable=False)
    company = Column(String(255), nullable=False, index=True)
    title = Column(String(500), nullable=False, index=True)
    location = Column(Text, nullable=False)
    apply_link = Column(Text, nullable=False)
    description = Column(Text)
    required_skills = Column(Text)  # JSON string
    job_requirements = Column(Text)
    source = Column(String(100), default='github_internships')
    job_metadata = Column(Text)  # JSON string for additional data
    
    # Timestamps
    first_seen = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # Canonical industry bucket (see job_categories.CATEGORIES). Nullable for
    # pre-backfill rows; stamped at insert time and via backfill_categories.py.
    category = Column(String(50), nullable=True, index=True)

    # Sentence embedding for semantic matching (JSON-encoded float list, nullable)
    embedding = Column(Text, nullable=True)

    # Add composite indexes for common queries
    __table_args__ = (
        Index('idx_company_title', 'company', 'title'),
        Index('idx_active_seen', 'is_active', 'last_seen'),
        Index('idx_source_active', 'source', 'is_active'),
    )

class CacheMetadata(Base):
    """Metadata for tracking cache operations"""
    __tablename__ = "cache_metadata"

    id = Column(Integer, primary_key=True, index=True)
    cache_type = Column(String(100), nullable=False, index=True)  # 'daily', 'weekly', 'full'
    last_updated = Column(DateTime, default=datetime.utcnow, nullable=False)
    job_count = Column(Integer, default=0)
    new_jobs_added = Column(Integer, default=0)
    status = Column(String(50), default='success')  # 'success', 'partial', 'failed'
    cache_metadata = Column(Text)  # JSON string for additional info

class ResumeCache(Base):
    """Cache for resume matching results, keyed by user + resume hash"""
    __tablename__ = "resume_cache"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    resume_hash = Column(String(255), nullable=False, index=True)
    results = Column(Text, nullable=False)
    skills = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    __table_args__ = (Index('idx_user_hash', 'user_id', 'resume_hash'),)


class SavedJob(Base):
    """Per-user saved job and application status tracker."""
    __tablename__ = "saved_jobs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    job_hash = Column(String(64), nullable=False, index=True)
    status = Column(String(40), default="saved", nullable=False, index=True)
    notes = Column(Text, default="", nullable=False)
    deadline = Column(String(40), nullable=True)
    job_snapshot = Column(Text, nullable=True)
    applied_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('idx_saved_user_job', 'user_id', 'job_hash', unique=True),
        Index('idx_saved_user_status', 'user_id', 'status'),
    )


SAVED_JOB_STATUSES = {"saved", "interested", "applied", "interviewing", "rejected", "offer", "ghosted"}


def _job_row_to_dict(job: Optional["Job"]) -> Optional[Dict]:
    if not job:
        return None
    return {
        'id': job.id,
        'job_hash': job.job_hash,
        'company': job.company,
        'title': job.title,
        'location': job.location,
        'apply_link': job.apply_link,
        'description': job.description,
        'required_skills': json.loads(job.required_skills) if job.required_skills else [],
        'job_requirements': job.job_requirements,
        'source': job.source,
        'category': job.category,
        'metadata': json.loads(job.job_metadata) if job.job_metadata else {},
        'first_seen': job.first_seen.isoformat() if job.first_seen else None,
        'last_seen': job.last_seen.isoformat() if job.last_seen else None,
        'is_active': bool(job.is_active),
    }


def _saved_job_to_dict(row: "SavedJob", job: Optional["Job"] = None) -> Dict:
    snapshot = None
    if row.job_snapshot:
        try:
            snapshot = json.loads(row.job_snapshot)
        except (json.JSONDecodeError, TypeError):
            snapshot = None
    return {
        "id": row.id,
        "job_hash": row.job_hash,
        "status": row.status,
        "notes": row.notes or "",
        "deadline": row.deadline,
        "applied_at": row.applied_at.isoformat() if row.applied_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "job": _job_row_to_dict(job) or snapshot,
    }


def _normalize_job_snapshot(snapshot: Optional[Dict]) -> Optional[Dict]:
    if not snapshot:
        return None
    allowed_keys = {
        "job_hash", "company", "title", "location", "apply_link", "description",
        "required_skills", "job_requirements", "source", "first_seen", "last_seen",
        "match_score", "score", "match_description", "ai_reasoning",
    }
    normalized = {k: snapshot.get(k) for k in allowed_keys if snapshot.get(k) is not None}
    if not normalized.get("job_hash"):
        return None
    return normalized


def _ensure_saved_jobs_schema():
    """Best-effort compatibility for create_all(), which does not add columns."""
    try:
        from sqlalchemy import inspect, text
        inspector = inspect(engine)
        if "saved_jobs" not in inspector.get_table_names():
            return
        columns = {c["name"] for c in inspector.get_columns("saved_jobs")}
        if "job_snapshot" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE saved_jobs ADD COLUMN job_snapshot TEXT"))
            logger.info("Added missing saved_jobs.job_snapshot column")
    except Exception as e:
        logger.warning(f"Could not verify saved_jobs schema compatibility: {e}")


def _utcnow() -> datetime:
    """Naive UTC datetime — matches the DateTime column type used by both quota tables."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TailorRequestLog(Base):
    """Append-only log of successful resume-tailoring requests, used for the weekly quota."""
    __tablename__ = "tailor_request_log"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), nullable=False, index=True)
    requested_at = Column(DateTime, default=_utcnow, nullable=False, index=True)
    job_title = Column(String(500))
    company = Column(String(500))
    __table_args__ = (Index('idx_tailor_user_time', 'user_id', 'requested_at'),)


class ThinkDeeperRequestLog(Base):
    """Append-only log of successful deep-match requests, used for the weekly quota."""
    __tablename__ = "think_deeper_request_log"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), nullable=False, index=True)
    requested_at = Column(DateTime, default=_utcnow, nullable=False, index=True)
    resume_hash = Column(String(255), nullable=True)
    __table_args__ = (Index('idx_think_deeper_user_time', 'user_id', 'requested_at'),)


class RemoteCompileLog(Base):
    """Append-only log of REMOTE resume compiles on the MCP /api/v1 path,
    used for the weekly per-user quota. Local (Docker) compiles never hit
    this — the quota exists because remote compiles burn our CPU."""
    __tablename__ = "remote_compile_log"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), nullable=False, index=True)
    requested_at = Column(DateTime, default=_utcnow, nullable=False, index=True)
    key_prefix = Column(String(16), nullable=True)   # which API key triggered it
    __table_args__ = (Index('idx_remote_compile_user_time', 'user_id', 'requested_at'),)


class UserAttribution(Base):
    """First-touch UTM attribution per user. One row per Clerk user_id — never updated."""
    __tablename__ = "user_attribution"
    user_id      = Column(String(255), primary_key=True)
    utm_source   = Column(String(255), nullable=True)
    utm_medium   = Column(String(255), nullable=True)
    utm_campaign = Column(String(255), nullable=True)
    utm_content  = Column(String(255), nullable=True)
    utm_term     = Column(String(255), nullable=True)
    first_seen_at = Column(DateTime, nullable=True)   # when the browser first landed
    attributed_at = Column(DateTime, default=_utcnow, nullable=False)  # when this row was written


class CompanyRegistry(Base):
    """Registry of companies and which ATS they use, for the universal crawler."""
    __tablename__ = "company_registry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(String(255), unique=True, nullable=False)
    display_name = Column(String(500), nullable=False)
    ats_type = Column(String(50), nullable=False)
    ats_board_id = Column(String(500), nullable=False)
    careers_url = Column(Text, nullable=True)
    industry = Column(String(100), nullable=True)
    company_size = Column(String(50), nullable=True)
    last_crawled = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    crawl_priority = Column(Integer, default=2, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('idx_ats_type', 'ats_type'),
        Index('idx_active_priority', 'is_active', 'crawl_priority', 'last_crawled'),
    )


class ApiKey(Base):
    """Per-user API keys for the MCP /api/v1 surface (issued from /developer).

    Distinct from the shared INTERNSHIP_MATCHER_API_KEY admin gate — these are
    per-Clerk-user keys, hashed at rest, revocable individually.
    """
    __tablename__ = "api_keys"
    id         = Column(Integer, primary_key=True)
    user_id    = Column(String(255), index=True, nullable=False)   # Clerk sub
    key_hash   = Column(String(64), unique=True, index=True)        # sha256(raw)
    key_prefix = Column(String(16))                                 # "im_live_ab12" display
    name       = Column(String(120), nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    last_used  = Column(DateTime, nullable=True)
    revoked    = Column(Boolean, default=False, index=True)


_API_KEY_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def create_api_key(user_id: str, name: Optional[str] = None) -> tuple:
    """Generate a new raw key `im_live_<32 base62>`, store only its SHA-256.

    Returns (raw_key, ApiKey row as dict). The raw key is shown to the user once
    and never persisted.
    """
    import secrets
    raw = "im_live_" + "".join(secrets.choice(_API_KEY_ALPHABET) for _ in range(32))
    key_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    db = get_db()
    try:
        row = ApiKey(
            user_id=user_id,
            key_hash=key_hash,
            key_prefix=raw[:12],  # "im_live_ab12"
            name=name,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return raw, _api_key_to_dict(row)
    except Exception:
        db.rollback()
        raise
    finally:
        close_db(db)


def verify_api_key(raw: str) -> Optional[str]:
    """Hash the raw key, look it up, check revocation, bump last_used.

    Returns the owning user_id or None if invalid/revoked.
    """
    if not raw or not raw.startswith("im_live_"):
        return None
    key_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    db = get_db()
    try:
        row = db.query(ApiKey).filter(
            ApiKey.key_hash == key_hash,
            ApiKey.revoked == False,  # noqa: E712 — SQLAlchemy comparison
        ).first()
        if not row:
            return None
        row.last_used = _utcnow()
        db.commit()
        return row.user_id
    except Exception as e:
        db.rollback()
        logger.error(f"Error verifying API key: {e}")
        return None
    finally:
        close_db(db)


def revoke_api_key(user_id: str, key_id: int) -> bool:
    """Revoke a key the user owns. Returns True if a key was revoked."""
    db = get_db()
    try:
        row = db.query(ApiKey).filter(
            ApiKey.id == key_id, ApiKey.user_id == user_id
        ).first()
        if not row or row.revoked:
            return False
        row.revoked = True
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error revoking API key {key_id}: {e}")
        return False
    finally:
        close_db(db)


def list_api_keys(user_id: str) -> List[Dict]:
    """All non-revoked keys for a user (metadata only, never hashes)."""
    db = get_db()
    try:
        rows = db.query(ApiKey).filter(
            ApiKey.user_id == user_id,
            ApiKey.revoked == False,  # noqa: E712
        ).order_by(ApiKey.created_at.desc()).all()
        return [_api_key_to_dict(r) for r in rows]
    finally:
        close_db(db)


def _api_key_to_dict(row: "ApiKey") -> Dict:
    return {
        "id": row.id,
        "key_prefix": row.key_prefix,
        "name": row.name,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "last_used": row.last_used.isoformat() if row.last_used else None,
        "revoked": bool(row.revoked),
    }


# Database initialization
def init_database():
    """Initialize database tables"""
    try:
        Base.metadata.create_all(bind=engine)
        _ensure_saved_jobs_schema()
        _ensure_embedding_column()
        _ensure_category_column()
        logger.info("Database initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        return False


def _ensure_embedding_column():
    """Idempotent: add embedding column to existing jobs tables that predate it."""
    try:
        with engine.connect() as conn:
            if is_postgres:
                conn.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS embedding TEXT")
            else:
                # SQLite does not support IF NOT EXISTS on ALTER TABLE
                try:
                    conn.execute("ALTER TABLE jobs ADD COLUMN embedding TEXT")
                except Exception:
                    pass  # column already exists
    except Exception as exc:
        logger.warning("Could not ensure embedding column: %s", exc)


def _ensure_category_column():
    """Idempotent: add category column to existing jobs tables that predate it."""
    try:
        with engine.connect() as conn:
            if is_postgres:
                conn.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS category VARCHAR(50)")
            else:
                try:
                    conn.execute("ALTER TABLE jobs ADD COLUMN category VARCHAR(50)")
                except Exception:
                    pass  # column already exists
    except Exception as exc:
        logger.warning("Could not ensure category column: %s", exc)


def save_job_embeddings(job_hashes: List[str], embeddings: List[list], db: Session = None) -> None:
    """Batch-update embedding column for a list of job_hashes."""
    should_close = db is None
    if db is None:
        db = get_db()
    try:
        for job_hash, vec in zip(job_hashes, embeddings):
            if not vec:
                continue
            db.query(Job).filter(Job.job_hash == job_hash).update(
                {"embedding": json.dumps(vec)},
                synchronize_session=False,
            )
    finally:
        if should_close:
            db.commit()
            close_db(db)


def get_jobs_without_embeddings(db: Session = None) -> List:
    """Return active jobs that have no embedding yet (for backfill)."""
    should_close = db is None
    if db is None:
        db = get_db()
    try:
        return (
            db.query(Job)
            .filter(Job.is_active == True, Job.embedding == None)  # noqa: E711
            .all()
        )
    finally:
        if should_close:
            close_db(db)


def get_all_job_embeddings(db: Session = None) -> Dict[str, list]:
    """Return {job_hash: vector} for all active jobs that have an embedding."""
    should_close = db is None
    if db is None:
        db = get_db()
    try:
        rows = (
            db.query(Job.job_hash, Job.embedding)
            .filter(Job.is_active == True, Job.embedding != None)  # noqa: E711
            .all()
        )
        return {job_hash: json.loads(emb) for job_hash, emb in rows}
    finally:
        if should_close:
            close_db(db)

def get_db() -> Session:
    """Get database session"""
    db = SessionLocal()
    try:
        return db
    finally:
        pass  # Don't close here, let caller handle

def close_db(db: Session):
    """Close database session"""
    db.close()


def save_user_attribution(user_id: str, utm_data: dict) -> bool:
    """Record first-touch UTM attribution for a user. Idempotent — no-ops if already stored."""
    logger.info(f"Attribution: recording for user={user_id} utm_data={utm_data}")
    db = get_db()
    try:
        if db.query(UserAttribution).filter_by(user_id=user_id).first():
            logger.info(f"Attribution: user={user_id} already attributed — skipping")
            return False
        first_seen = None
        raw_ts = utm_data.get("first_seen_at")
        if raw_ts:
            try:
                from datetime import timezone as _tz
                first_seen = datetime.fromisoformat(raw_ts.replace("Z", "+00:00")).astimezone(_tz.utc).replace(tzinfo=None)
            except Exception as ts_err:
                logger.warning(f"Attribution: could not parse first_seen_at={raw_ts!r} — {ts_err}")
        db.add(UserAttribution(
            user_id=user_id,
            utm_source=utm_data.get("utm_source"),
            utm_medium=utm_data.get("utm_medium"),
            utm_campaign=utm_data.get("utm_campaign"),
            utm_content=utm_data.get("utm_content"),
            utm_term=utm_data.get("utm_term"),
            first_seen_at=first_seen,
        ))
        db.commit()
        logger.info(f"Attribution: saved user={user_id} source={utm_data.get('utm_source')!r}")
        return True
    except Exception as e:
        logger.error(f"Attribution: DB write failed for user={user_id} — {e}", exc_info=True)
        db.rollback()
        return False
    finally:
        close_db(db)


def generate_job_hash(company: str, title: str, location: str, apply_link: str) -> str:
    """
    Generate unique hash for job deduplication.
    Uses company + title + location + domain+path from apply_link.
    The URL path is included (but not query string) so distinct postings at the
    same job board no longer collide. Query-string params like ?utm_source= are
    intentionally excluded because they are volatile and carry no identity signal.
    """
    try:
        from urllib.parse import urlparse
        parsed = urlparse(apply_link)
        # netloc + path, strip trailing slash for normalisation
        domain_path = (parsed.netloc + parsed.path).rstrip("/")
    except Exception:
        domain_path = apply_link[:100]  # Fallback

    # Create normalized string for hashing
    hash_string = (
        f"{company.lower().strip()}|"
        f"{title.lower().strip()}|"
        f"{location.lower().strip()}|"
        f"{domain_path.lower()}"
    )

    # Generate SHA-256 hash
    return hashlib.sha256(hash_string.encode('utf-8')).hexdigest()

def mark_old_jobs_inactive(max_days_old: int = 30, db: Session = None) -> int:
    """
    Mark jobs as inactive if their posting date is older than max_days_old.
    This ensures old jobs don't persist even if they're still in the GitHub repo.

    Args:
        max_days_old: Maximum age in days for a job to remain active (default: 30)
        db: Database session (optional)

    Returns:
        Number of jobs marked inactive
    """
    if db is None:
        db = get_db()
        should_close = True
    else:
        should_close = False

    try:
        dialect = db.bind.dialect.name if db.bind else "sqlite"

        if dialect == "postgresql":
            # Single round-trip: let Postgres filter on the JSON field directly.
            # ::json / ::int casts are Postgres-specific; the SQLite fallback below
            # handles the test environment (sqlite:///:memory:).
            result = db.execute(
                text("""
                    UPDATE jobs
                    SET    is_active  = false,
                           updated_at = NOW()
                    WHERE  is_active = true
                      AND  job_metadata IS NOT NULL
                      AND  (job_metadata::json->>'days_since_posted')::int > :max_days
                """),
                {"max_days": max_days_old}
            )
            db.commit()
            inactive_count = result.rowcount
        else:
            # SQLite fallback (CI / local dev): ORM loop with Python-side JSON parse.
            active_jobs = db.query(Job).filter(Job.is_active == True).all()  # noqa: E712
            inactive_count = 0
            for job in active_jobs:
                try:
                    if job.job_metadata:
                        metadata = json.loads(job.job_metadata)
                        days_since_posted = metadata.get('days_since_posted')
                        if days_since_posted is not None and days_since_posted > max_days_old:
                            job.is_active = False
                            inactive_count += 1
                except (json.JSONDecodeError, TypeError):
                    continue

        if inactive_count > 0:
            logger.info(f"Marked {inactive_count} jobs inactive (>{max_days_old} days old)")
        return inactive_count

    except Exception as e:
        logger.error(f"Error marking old jobs inactive: {e}")
        return 0
    finally:
        if should_close:
            close_db(db)

def bulk_insert_jobs(jobs: List[Dict], db: Session = None) -> Dict:
    """
    Upsert jobs with full deduplication and conflict resilience.

    Design:
    - Within-batch dedup (keep-last) before touching the DB, so two scraped rows
      with the same hash never reach the INSERT layer.
    - Dialect-aware ON CONFLICT DO UPDATE (works with both Postgres prod and
      SQLite dev/test via their respective dialect inserts).
    - Chunked execution wrapped in SAVEPOINTs so one bad chunk cannot abort the
      whole batch.
    - Existing rows: last_seen, updated_at, is_active, and mutable content are
      refreshed; first_seen/created_at are preserved.
    - Inactive sweeps run AFTER upserts so freshly refreshed last_seen values
      are evaluated correctly.

    Returns a summary dict with new_jobs, updated_jobs, duplicates_collapsed,
    failed_rows, inactive_jobs, date_based_inactive_jobs, total_processed.
    On catastrophic failure returns {'error': str(e)}.
    """
    if db is None:
        db = get_db()
        should_close = True
    else:
        should_close = False

    try:
        if not jobs:
            db.commit()
            return {
                'new_jobs': 0, 'updated_jobs': 0, 'duplicates_collapsed': 0,
                'failed_rows': 0, 'inactive_jobs': 0, 'date_based_inactive_jobs': 0,
                'total_processed': 0,
            }

        # ------------------------------------------------------------------
        # Step 1: Within-batch dedup (keep-last occurrence wins).
        # Using an ordered dict: iterating jobs in order means a later item
        # with the same hash overwrites the earlier one.
        # ------------------------------------------------------------------
        deduped: dict = {}  # job_hash -> job_data
        for job_data in jobs:
            h = generate_job_hash(
                job_data.get('company', ''),
                job_data.get('title', ''),
                job_data.get('location', ''),
                job_data.get('apply_link', ''),
            )
            deduped[h] = job_data

        duplicates_collapsed = len(jobs) - len(deduped)

        # ------------------------------------------------------------------
        # Step 2: Build plain row dicts for the Core upsert.
        # Timestamps are stamped once so all rows in a batch share the same
        # effective scrape time.
        # ------------------------------------------------------------------
        now = datetime.utcnow()
        rows: List[Dict] = []
        for job_hash, job_data in deduped.items():
            metadata = dict(job_data.get('metadata') or {})
            metadata['days_since_posted'] = job_data.get('days_since_posted')
            metadata['date_posted']       = job_data.get('date_posted')
            metadata['date_posted_raw']   = job_data.get('date_posted_raw')

            rows.append({
                'job_hash':        job_hash,
                'company':         job_data.get('company', ''),
                'title':           job_data.get('title', ''),
                'location':        job_data.get('location', ''),
                'apply_link':      job_data.get('apply_link', ''),
                'description':     job_data.get('description', ''),
                'required_skills': json.dumps(job_data.get('required_skills', [])),
                'job_requirements':job_data.get('job_requirements', ''),
                'source':          job_data.get('source', 'github_internships'),
                'job_metadata':    json.dumps(metadata),
                'category':        metadata.get('category'),
                'first_seen':      now,   # preserved on conflict (not in set_)
                'last_seen':       now,
                'created_at':      now,   # preserved on conflict (not in set_)
                'updated_at':      now,   # must be explicit — onupdate= won't fire on Core upsert
                'is_active':       True,
            })

        # ------------------------------------------------------------------
        # Step 3: Lightweight pre-read for accurate new/updated counts.
        # This is reporting-only and not load-bearing for correctness.
        # ------------------------------------------------------------------
        all_incoming_hashes = [r['job_hash'] for r in rows]
        existing_hashes: Set[str] = {
            h for (h,) in db.query(Job.job_hash)
                              .filter(Job.job_hash.in_(all_incoming_hashes))
                              .all()
        }
        new_jobs     = sum(1 for r in rows if r['job_hash'] not in existing_hashes)
        updated_jobs = sum(1 for r in rows if r['job_hash'] in existing_hashes)

        # ------------------------------------------------------------------
        # Step 4: Dialect-aware chunked upsert with per-chunk SAVEPOINTs.
        # Each chunk is isolated; a failure in one chunk rolls back only that
        # chunk and increments failed_rows; the outer transaction continues.
        # ------------------------------------------------------------------
        dialect = db.bind.dialect.name
        if dialect == 'postgresql':
            from sqlalchemy.dialects.postgresql import insert as _insert
        else:
            # sqlite (dev / tests) — same API shape in SQLAlchemy 1.4
            from sqlalchemy.dialects.sqlite import insert as _insert

        CHUNK = 200
        failed_rows = 0

        for i in range(0, len(rows), CHUNK):
            chunk = rows[i:i + CHUNK]
            try:
                with db.begin_nested():   # SAVEPOINT — rolls back only this chunk on error
                    stmt = _insert(Job.__table__).values(chunk)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=['job_hash'],
                        set_={
                            # Refresh mutable content and timestamps
                            'last_seen':        stmt.excluded.last_seen,
                            'updated_at':       stmt.excluded.updated_at,
                            'is_active':        True,   # reactivate jobs that reappear
                            'job_metadata':     stmt.excluded.job_metadata,
                            'category':         stmt.excluded.category,
                            'description':      stmt.excluded.description,
                            'required_skills':  stmt.excluded.required_skills,
                            'job_requirements': stmt.excluded.job_requirements,
                            'apply_link':       stmt.excluded.apply_link,
                            # first_seen / created_at intentionally omitted → preserved
                        },
                    )
                    db.execute(stmt)
            except Exception as chunk_err:
                # Savepoint already rolled back this chunk; log and continue.
                failed_rows += len(chunk)
                logger.error(f"Upsert chunk [{i}:{i+CHUNK}] failed ({len(chunk)} rows): {chunk_err}")

        # ------------------------------------------------------------------
        # Step 5: Inactive sweeps — run AFTER upserts so refreshed last_seen
        # values are evaluated correctly.
        # Scope to the sources present in this batch: a github_internships
        # startup scrape must not deactivate ats_greenhouse / ats_lever jobs
        # simply because those crawlers run on a different schedule.
        # ------------------------------------------------------------------
        batch_sources = list({r['source'] for r in rows})
        cutoff_date = datetime.utcnow() - timedelta(days=3)
        inactive_count = db.query(Job).filter(
            Job.last_seen < cutoff_date,
            Job.is_active == True,
            Job.source.in_(batch_sources),
        ).update({Job.is_active: False}, synchronize_session=False)

        date_based_inactive_count = mark_old_jobs_inactive(max_days_old=30, db=db)

        db.commit()

        total_inactive = inactive_count + date_based_inactive_count
        logger.info(
            f"Database: {new_jobs} new, {updated_jobs} updated, "
            f"{total_inactive} marked inactive, "
            f"{duplicates_collapsed} within-batch dups collapsed, "
            f"{failed_rows} rows failed"
        )
        return {
            'new_jobs':                new_jobs,
            'updated_jobs':            updated_jobs,
            'duplicates_collapsed':    duplicates_collapsed,
            'failed_rows':             failed_rows,
            'inactive_jobs':           inactive_count,
            'date_based_inactive_jobs':date_based_inactive_count,
            'total_processed':         len(jobs),
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Database error during bulk insert: {e}")
        return {'error': str(e)}
    finally:
        if should_close:
            close_db(db)

def get_active_jobs(limit: Optional[int] = None, offset: int = 0, max_days_old: int = 30) -> List[Dict]:
    """
    Get active jobs from database, filtered by posting date.

    Args:
        limit: Maximum number of jobs to return
        offset: Number of jobs to skip
        max_days_old: Maximum age in days for jobs to include (default: 30)

    Returns:
        List of job dictionaries
    """
    db = get_db()
    try:
        query = db.query(Job).filter(Job.is_active == True).order_by(Job.last_seen.desc())

        if limit:
            query = query.offset(offset).limit(limit)

        jobs = query.all()

        result = []
        filtered_count = 0
        for job in jobs:
            # Parse metadata to check posting date
            try:
                metadata = json.loads(job.job_metadata) if job.job_metadata else {}
                days_since_posted = metadata.get('days_since_posted')

                # Filter out jobs older than max_days_old
                if days_since_posted is not None and days_since_posted > max_days_old:
                    filtered_count += 1
                    continue  # Skip this job

            except (json.JSONDecodeError, TypeError):
                # If metadata is invalid, include the job (better to show than hide)
                pass

            job_dict = {
                'id': job.id,
                'job_hash': job.job_hash,
                'company': job.company,
                'title': job.title,
                'location': job.location,
                'apply_link': job.apply_link,
                'description': job.description,
                'required_skills': json.loads(job.required_skills) if job.required_skills else [],
                'job_requirements': job.job_requirements,
                'source': job.source,
                'category': job.category,
                'metadata': metadata if 'metadata' in locals() else {},
                'first_seen': job.first_seen,
                'last_seen': job.last_seen
            }
            result.append(job_dict)

        if filtered_count > 0:
            logger.info(f"Filtered out {filtered_count} jobs older than {max_days_old} days from cache")

        return result
        
    except Exception as e:
        logger.error(f"Error getting active jobs: {e}")
        return []
    finally:
        close_db(db)


def get_job_by_hash(job_hash: str, db: Optional[Session] = None) -> Optional[Dict]:
    """
    Fetch a single job (with its FULL, untruncated description) by job_hash.

    Used by the resume-tailoring endpoint to feed the complete job description into
    the prompt. Intentionally does NOT filter on is_active — a job shown in match
    results may have been soft-deactivated (last_seen / days_since_posted) by the
    time the user tailors against it, but the row still exists.

    Args:
        job_hash: SHA-256 dedup key from generate_job_hash().
        db: Optional existing session; if omitted, one is opened and closed here.

    Returns:
        Job dict including the full 'description', or None if not found.
    """
    if not job_hash:
        return None

    should_close = db is None
    if db is None:
        db = get_db()
    try:
        job = db.query(Job).filter(Job.job_hash == job_hash).first()
        if not job:
            return None
        return {
            'id': job.id,
            'job_hash': job.job_hash,
            'company': job.company,
            'title': job.title,
            'location': job.location,
            'apply_link': job.apply_link,
            'description': job.description,
            'required_skills': json.loads(job.required_skills) if job.required_skills else [],
            'job_requirements': job.job_requirements,
            'source': job.source,
            'first_seen': job.first_seen,
            'last_seen': job.last_seen,
        }
    except Exception as e:
        logger.error(f"Error fetching job by hash {job_hash[:12]}...: {e}")
        return None
    finally:
        if should_close:
            close_db(db)


def update_job_jd(job_hash: str, description: str, job_requirements: str, required_skills: List[str]) -> bool:
    """Persist real JD text and skills fetched lazily from the apply_link.
    Called once on first job_get when the stored description is synthetic boilerplate.
    """
    db = get_db()
    try:
        job = db.query(Job).filter(Job.job_hash == job_hash).first()
        if not job:
            return False
        job.description = description
        job.job_requirements = job_requirements
        if required_skills:
            job.required_skills = json.dumps(required_skills)
        db.commit()
        return True
    except Exception as e:
        logger.error("Error updating JD for %s: %s", job_hash[:12], e)
        db.rollback()
        return False
    finally:
        close_db(db)


def get_new_jobs_since(hours: int = 24, max_days_old: int = 30) -> List[Dict]:
    """
    Get jobs added in the last N hours, filtered by posting date.

    Args:
        hours: Get jobs added within the last N hours
        max_days_old: Maximum age in days for jobs to include (default: 30)

    Returns:
        List of job dictionaries
    """
    db = get_db()
    try:
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)

        jobs = db.query(Job).filter(
            Job.first_seen >= cutoff_time,
            Job.is_active == True
        ).order_by(Job.first_seen.desc()).all()

        result = []
        filtered_count = 0
        for job in jobs:
            # Parse metadata to check posting date
            try:
                metadata = json.loads(job.job_metadata) if job.job_metadata else {}
                days_since_posted = metadata.get('days_since_posted')

                # Filter out jobs older than max_days_old
                if days_since_posted is not None and days_since_posted > max_days_old:
                    filtered_count += 1
                    continue  # Skip this job

            except (json.JSONDecodeError, TypeError):
                # If metadata is invalid, include the job
                pass

            job_dict = {
                'id': job.id,
                'job_hash': job.job_hash,
                'company': job.company,
                'title': job.title,
                'location': job.location,
                'apply_link': job.apply_link,
                'description': job.description,
                'required_skills': json.loads(job.required_skills) if job.required_skills else [],
                'job_requirements': job.job_requirements,
                'source': job.source,
                'category': job.category,
                'metadata': metadata if 'metadata' in locals() else {},
                'first_seen': job.first_seen,
                'last_seen': job.last_seen
            }
            result.append(job_dict)

        if filtered_count > 0:
            logger.info(f"Filtered out {filtered_count} jobs older than {max_days_old} days from new jobs")

        return result
        
    except Exception as e:
        logger.error(f"Error getting new jobs: {e}")
        return []
    finally:
        close_db(db)

def get_database_stats() -> Dict:
    """Get database statistics"""
    db = get_db()
    try:
        total_jobs = db.query(func.count(Job.id)).scalar()
        active_jobs = db.query(func.count(Job.id)).filter(Job.is_active == True).scalar()
        
        # Jobs by source
        sources = db.query(Job.source, func.count(Job.id)).filter(
            Job.is_active == True
        ).group_by(Job.source).all()
        
        # Recent activity
        last_24h = datetime.utcnow() - timedelta(hours=24)
        new_last_24h = db.query(func.count(Job.id)).filter(
            Job.first_seen >= last_24h
        ).scalar()
        
        # Latest cache operation
        latest_cache = db.query(CacheMetadata).order_by(
            CacheMetadata.last_updated.desc()
        ).first()
        
        return {
            'total_jobs': total_jobs,
            'active_jobs': active_jobs,
            'inactive_jobs': total_jobs - active_jobs,
            'sources': dict(sources),
            'new_jobs_24h': new_last_24h,
            'latest_cache': {
                'type': latest_cache.cache_type if latest_cache else None,
                'updated': latest_cache.last_updated.isoformat() if latest_cache and latest_cache.last_updated else None,
                'job_count': latest_cache.job_count if latest_cache else 0
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting database stats: {e}")
        return {}
    finally:
        close_db(db)

def record_cache_operation(cache_type: str, job_count: int, new_jobs: int, status: str = 'success', metadata: Dict = None):
    """Record cache operation metadata"""
    db = get_db()
    try:
        cache_record = CacheMetadata(
            cache_type=cache_type,
            job_count=job_count,
            new_jobs_added=new_jobs,
            status=status,
            cache_metadata=json.dumps(metadata or {})
        )
        
        db.add(cache_record)
        db.commit()
        
        logger.info(f"Cache operation recorded: {cache_type} — {new_jobs} new jobs")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error recording cache operation: {e}")
    finally:
        close_db(db)

def cleanup_old_metadata(days: int = 30):
    """Clean up old cache metadata entries"""
    db = get_db()
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        deleted = db.query(CacheMetadata).filter(
            CacheMetadata.last_updated < cutoff_date
        ).delete()
        
        db.commit()
        logger.info(f"Cleaned up {deleted} old cache metadata entries")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error cleaning up metadata: {e}")
    finally:
        close_db(db)

def get_resume_cache(user_id: str, resume_hash: str) -> Optional[Dict]:
    """Returns cached {results, skills} or None if miss/expired."""
    db = get_db()
    try:
        entry = db.query(ResumeCache).filter(
            ResumeCache.user_id == user_id,
            ResumeCache.resume_hash == resume_hash,
            ResumeCache.expires_at > datetime.utcnow()
        ).first()
        if entry:
            return {"results": json.loads(entry.results), "skills": json.loads(entry.skills)}
        return None
    finally:
        db.close()

def get_user_resume_history(user_id: str) -> List[Dict]:
    """Returns all non-expired resume cache entries for a user, newest first."""
    db = get_db()
    try:
        entries = db.query(ResumeCache).filter(
            ResumeCache.user_id == user_id,
            ResumeCache.expires_at > datetime.utcnow()
        ).order_by(ResumeCache.created_at.desc()).all()
        return [
            {
                "id": e.id,
                "resume_hash": e.resume_hash,
                "results": json.loads(e.results),
                "skills": json.loads(e.skills),
                "created_at": e.created_at.isoformat(),
                "expires_at": e.expires_at.isoformat(),
            }
            for e in entries
        ]
    finally:
        db.close()


def set_resume_cache(user_id: str, resume_hash: str, results: list, skills: list) -> None:
    """Upsert cache entry with 24h TTL."""
    db = get_db()
    try:
        db.query(ResumeCache).filter(
            ResumeCache.user_id == user_id,
            ResumeCache.resume_hash == resume_hash
        ).delete()
        entry = ResumeCache(
            user_id=user_id,
            resume_hash=resume_hash,
            results=json.dumps(results),
            skills=json.dumps(skills),
            expires_at=datetime.utcnow() + timedelta(days=30)
        )
        db.add(entry)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"Failed to save resume cache: {e}")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Saved jobs / application tracker
# ---------------------------------------------------------------------------

def list_saved_jobs(user_id: str) -> List[Dict]:
    """Return a user's saved jobs newest first, including job details when present."""
    db = get_db()
    try:
        rows = db.query(SavedJob, Job).outerjoin(
            Job, SavedJob.job_hash == Job.job_hash
        ).filter(
            SavedJob.user_id == user_id
        ).order_by(SavedJob.updated_at.desc()).all()
        return [_saved_job_to_dict(saved, job) for saved, job in rows]
    finally:
        close_db(db)


def get_saved_job_hashes(user_id: str) -> List[str]:
    """Return only the hashes a user has saved for lightweight UI state."""
    db = get_db()
    try:
        return [
            h for (h,) in db.query(SavedJob.job_hash)
            .filter(SavedJob.user_id == user_id)
            .order_by(SavedJob.updated_at.desc())
            .all()
        ]
    finally:
        close_db(db)


def upsert_saved_job(
    user_id: str,
    job_hash: str,
    status: str = "saved",
    notes: str = "",
    deadline: Optional[str] = None,
    job_snapshot: Optional[Dict] = None,
) -> Dict:
    """Create or update a saved job row owned by user_id."""
    if status not in SAVED_JOB_STATUSES:
        raise ValueError(f"Invalid status: {status}")
    normalized_snapshot = _normalize_job_snapshot(job_snapshot)
    db = get_db()
    try:
        job = db.query(Job).filter(Job.job_hash == job_hash).first()
        if not job and not normalized_snapshot:
            normalized_snapshot = {"job_hash": job_hash}
        row = db.query(SavedJob).filter(
            SavedJob.user_id == user_id,
            SavedJob.job_hash == job_hash,
        ).first()
        now = datetime.utcnow()
        if not row:
            row = SavedJob(user_id=user_id, job_hash=job_hash)
            db.add(row)
        row.status = status
        row.notes = notes or ""
        row.deadline = deadline or None
        if normalized_snapshot:
            row.job_snapshot = json.dumps(normalized_snapshot)
        row.applied_at = now if status == "applied" and row.applied_at is None else row.applied_at
        row.updated_at = now
        db.commit()
        db.refresh(row)
        return _saved_job_to_dict(row, job)
    except Exception:
        db.rollback()
        raise
    finally:
        close_db(db)


def update_saved_job(
    user_id: str,
    job_hash: str,
    status: Optional[str] = None,
    notes: Optional[str] = None,
    deadline: Optional[str] = None,
) -> Optional[Dict]:
    """Update an existing saved job. Returns None when it is not saved."""
    if status is not None and status not in SAVED_JOB_STATUSES:
        raise ValueError(f"Invalid status: {status}")
    db = get_db()
    try:
        row = db.query(SavedJob).filter(
            SavedJob.user_id == user_id,
            SavedJob.job_hash == job_hash,
        ).first()
        if not row:
            return None
        if status is not None:
            row.status = status
            if status == "applied" and row.applied_at is None:
                row.applied_at = datetime.utcnow()
        if notes is not None:
            row.notes = notes
        if deadline is not None:
            row.deadline = deadline or None
        row.updated_at = datetime.utcnow()
        job = db.query(Job).filter(Job.job_hash == job_hash).first()
        db.commit()
        db.refresh(row)
        return _saved_job_to_dict(row, job)
    except Exception:
        db.rollback()
        raise
    finally:
        close_db(db)


def delete_saved_job(user_id: str, job_hash: str) -> bool:
    """Remove a saved job owned by the user."""
    db = get_db()
    try:
        deleted = db.query(SavedJob).filter(
            SavedJob.user_id == user_id,
            SavedJob.job_hash == job_hash,
        ).delete()
        db.commit()
        return deleted > 0
    except Exception:
        db.rollback()
        raise
    finally:
        close_db(db)

# Initialize database on import
if __name__ == "__main__":
    init_database()
    stats = get_database_stats()
    print(f"Database stats: {stats}")