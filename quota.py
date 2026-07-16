"""Weekly per-user quota for the resume-tailoring feature, backed by Postgres."""
from datetime import datetime, timedelta, timezone
from typing import Optional


def _utcnow() -> datetime:
    """Return the current UTC time as a naive datetime (matches DB column type)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
from sqlalchemy.orm import Session
from job_database import CritiqueRequestLog, RemoteCompileLog, TailorRequestLog, ThinkDeeperRequestLog

WEEKLY_TAILOR_LIMIT = 5
WEEKLY_THINK_DEEPER_LIMIT = 20
WEEKLY_REMOTE_COMPILE_LIMIT = 15
WEEKLY_CRITIQUE_LIMIT = 3
WEEKLY_WINDOW = timedelta(days=7)


def get_tailor_quota_status(db: Session, user_id: str) -> dict:
    """
    Return the current quota state for a user.

    Returns a dict with:
      limit      — the cap (5)
      used       — requests in the last 7 days
      remaining  — slots left
      reset_at   — ISO datetime string when the oldest slot frees up (None if nothing used)
    """
    window_start = _utcnow() - WEEKLY_WINDOW
    rows = (
        db.query(TailorRequestLog)
        .filter(
            TailorRequestLog.user_id == user_id,
            TailorRequestLog.requested_at > window_start,
        )
        .order_by(TailorRequestLog.requested_at.asc())
        .all()
    )
    used = len(rows)
    remaining = max(0, WEEKLY_TAILOR_LIMIT - used)
    # Reset time = the moment the oldest in-window row falls out of the window
    oldest_in_window: Optional[datetime] = rows[0].requested_at if rows else None
    reset_at: Optional[datetime] = (oldest_in_window + WEEKLY_WINDOW) if oldest_in_window else None

    return {
        "limit": WEEKLY_TAILOR_LIMIT,
        "used": used,
        "remaining": remaining,
        "reset_at": reset_at,
    }


def get_think_deeper_quota_status(db: Session, user_id: str) -> dict:
    """Return the current Think Deeper quota state for a user."""
    window_start = _utcnow() - WEEKLY_WINDOW
    rows = (
        db.query(ThinkDeeperRequestLog)
        .filter(
            ThinkDeeperRequestLog.user_id == user_id,
            ThinkDeeperRequestLog.requested_at > window_start,
        )
        .order_by(ThinkDeeperRequestLog.requested_at.asc())
        .all()
    )
    used = len(rows)
    remaining = max(0, WEEKLY_THINK_DEEPER_LIMIT - used)
    oldest_in_window: Optional[datetime] = rows[0].requested_at if rows else None
    reset_at: Optional[datetime] = (oldest_in_window + WEEKLY_WINDOW) if oldest_in_window else None
    return {
        "limit": WEEKLY_THINK_DEEPER_LIMIT,
        "used": used,
        "remaining": remaining,
        "reset_at": reset_at,
    }


def record_think_deeper_request(db: Session, user_id: str, resume_hash: Optional[str] = None) -> None:
    """Insert a new Think Deeper log row. Caller is responsible for db.commit()."""
    entry = ThinkDeeperRequestLog(
        user_id=user_id,
        resume_hash=resume_hash[:255] if resume_hash else None,
    )
    db.add(entry)


def get_remote_compile_quota_status(db: Session, user_id: str) -> dict:
    """Quota state for REMOTE resume compiles (the MCP /api/v1 fallback path).

    Distinct from the tailor_resume quota: this one is consumed by API-key
    traffic (uvx users with COMPILE=remote), not by the in-app tailor feature.
    Docker users compiling locally never touch it.
    """
    window_start = _utcnow() - WEEKLY_WINDOW
    rows = (
        db.query(RemoteCompileLog)
        .filter(
            RemoteCompileLog.user_id == user_id,
            RemoteCompileLog.requested_at > window_start,
        )
        .order_by(RemoteCompileLog.requested_at.asc())
        .all()
    )
    used = len(rows)
    remaining = max(0, WEEKLY_REMOTE_COMPILE_LIMIT - used)
    oldest_in_window: Optional[datetime] = rows[0].requested_at if rows else None
    reset_at: Optional[datetime] = (oldest_in_window + WEEKLY_WINDOW) if oldest_in_window else None
    return {
        "limit": WEEKLY_REMOTE_COMPILE_LIMIT,
        "used": used,
        "remaining": remaining,
        "reset_at": reset_at,
    }


def record_remote_compile(db: Session, user_id: str, key_prefix: Optional[str] = None) -> None:
    """Insert a remote-compile log row. Caller is responsible for db.commit()."""
    entry = RemoteCompileLog(
        user_id=user_id,
        key_prefix=key_prefix[:16] if key_prefix else None,
    )
    db.add(entry)


def record_tailor_request(db: Session, user_id: str, job_title: str, company: str) -> None:
    """Insert a new log row. Caller is responsible for db.commit()."""
    entry = TailorRequestLog(
        user_id=user_id,
        job_title=job_title[:500] if job_title else None,
        company=company[:500] if company else None,
    )
    db.add(entry)


def get_critique_quota_status(db: Session, user_id: str) -> dict:
    """Quota state for the Critique feature. Cache hits never call record_critique_request,
    so re-critiquing the same resume/category is free and doesn't touch this ledger."""
    window_start = _utcnow() - WEEKLY_WINDOW
    rows = (
        db.query(CritiqueRequestLog)
        .filter(
            CritiqueRequestLog.user_id == user_id,
            CritiqueRequestLog.requested_at > window_start,
        )
        .order_by(CritiqueRequestLog.requested_at.asc())
        .all()
    )
    used = len(rows)
    remaining = max(0, WEEKLY_CRITIQUE_LIMIT - used)
    oldest_in_window: Optional[datetime] = rows[0].requested_at if rows else None
    reset_at: Optional[datetime] = (oldest_in_window + WEEKLY_WINDOW) if oldest_in_window else None
    return {
        "limit": WEEKLY_CRITIQUE_LIMIT,
        "used": used,
        "remaining": remaining,
        "reset_at": reset_at,
    }


def record_critique_request(db: Session, user_id: str) -> None:
    """Insert a new Critique log row. Caller is responsible for db.commit()."""
    db.add(CritiqueRequestLog(user_id=user_id))
