"""
Company registry CRUD — maps companies to their ATS for the universal crawler.
"""
import logging
from datetime import datetime
from typing import List, Optional, Dict

from job_database import get_db, close_db, CompanyRegistry as _ORMCompanyRegistry

logger = logging.getLogger(__name__)


class CompanyRecord:
    """Lightweight dataclass mirroring the CompanyRegistry ORM row."""
    __slots__ = (
        "company_id", "display_name", "ats_type", "ats_board_id",
        "careers_url", "industry", "company_size",
        "last_crawled", "is_active", "crawl_priority",
    )

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    @classmethod
    def from_orm(cls, row: _ORMCompanyRegistry) -> "CompanyRecord":
        return cls(
            company_id=row.company_id,
            display_name=row.display_name,
            ats_type=row.ats_type,
            ats_board_id=row.ats_board_id,
            careers_url=row.careers_url,
            industry=row.industry,
            company_size=row.company_size,
            last_crawled=row.last_crawled,
            is_active=row.is_active,
            crawl_priority=row.crawl_priority,
        )


class CompanyRegistryStore:
    """CRUD helpers for the company_registry table."""

    def upsert(self, data: Dict) -> bool:
        db = get_db()
        try:
            # Dialect-aware atomic upsert (same pattern as bulk_insert_jobs) — avoids the
            # SELECT-then-INSERT TOCTOU race that silently drops one writer's update when
            # two bootstrap probes hit the same company_id concurrently.
            values = {
                k: v for k, v in data.items()
                if v is not None and hasattr(_ORMCompanyRegistry, k)
            }
            dialect = db.bind.dialect.name
            if dialect == "postgresql":
                from sqlalchemy.dialects.postgresql import insert as _insert
            else:
                from sqlalchemy.dialects.sqlite import insert as _insert

            stmt = _insert(_ORMCompanyRegistry.__table__).values(**values)
            # On conflict, refresh everything supplied except the immutable identity/creation
            # columns so a re-probe can reactivate or update a known company.
            update_cols = {
                k: getattr(stmt.excluded, k)
                for k in values
                if k not in ("company_id", "created_at")
            }
            if update_cols:
                stmt = stmt.on_conflict_do_update(
                    index_elements=["company_id"],
                    set_=update_cols,
                )
            else:
                stmt = stmt.on_conflict_do_nothing(index_elements=["company_id"])
            db.execute(stmt)
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            logger.error("company_registry upsert failed for %s: %s", data.get("company_id"), e)
            return False
        finally:
            close_db(db)

    def get_all_active(self) -> List[CompanyRecord]:
        db = get_db()
        try:
            rows = db.query(_ORMCompanyRegistry).filter_by(is_active=True).all()
            return [CompanyRecord.from_orm(r) for r in rows]
        finally:
            close_db(db)

    def get_due_for_crawl(self, priority: List[int] = None, limit: int = 200) -> List[CompanyRecord]:
        """Return active companies ordered by crawl urgency (oldest last_crawled first).

        Fetches at most ``limit`` rows (default 200) so each 15-minute GitHub Actions
        run downloads ~100 KB instead of ~5 MB for the full registry.  The
        ORDER BY last_crawled ASC naturally rotates the queue: crawled companies move
        to the back on their next run, so the full registry is still covered every
        ~12.7 hours at the default batch size.
        """
        db = get_db()
        try:
            q = db.query(_ORMCompanyRegistry).filter_by(is_active=True)
            if priority:
                q = q.filter(_ORMCompanyRegistry.crawl_priority.in_(priority))
            rows = (
                q.order_by(_ORMCompanyRegistry.last_crawled.asc().nullsfirst())
                 .limit(limit)
                 .all()
            )
            return [CompanyRecord.from_orm(r) for r in rows]
        finally:
            close_db(db)

    def mark_inactive(self, company_id: str) -> None:
        db = get_db()
        try:
            db.query(_ORMCompanyRegistry).filter_by(
                company_id=company_id
            ).update({"is_active": False})
            db.commit()
        except Exception as e:
            db.rollback()
            logger.warning("Failed to mark %s inactive: %s", company_id, e)
        finally:
            close_db(db)

    def update_last_crawled(self, companies: List[CompanyRecord]) -> None:
        if not companies:
            return
        db = get_db()
        try:
            ids = [c.company_id for c in companies]
            db.query(_ORMCompanyRegistry).filter(
                _ORMCompanyRegistry.company_id.in_(ids)
            ).update({"last_crawled": datetime.utcnow()}, synchronize_session=False)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("update_last_crawled failed: %s", e)
        finally:
            close_db(db)

    def get_all_ids(self, ats_type: Optional[str] = None, active_only: bool = True) -> List[str]:
        db = get_db()
        try:
            q = db.query(_ORMCompanyRegistry.company_id)
            if ats_type:
                q = q.filter_by(ats_type=ats_type)
            if active_only:
                q = q.filter_by(is_active=True)
            return [r[0] for r in q.all()]
        finally:
            close_db(db)

    def get_unregistered_apply_link_tokens(self, ats_type: str) -> List[str]:
        """
        Return ATS board IDs referenced in jobs.apply_link that are not yet
        in the company_registry. Used to auto-discover new companies from
        apply_link referrals after each crawl cycle.
        """
        from sqlalchemy import text
        db = get_db()
        try:
            known_rows = db.query(_ORMCompanyRegistry.company_id).filter_by(
                ats_type=ats_type
            ).all()
            known = {r[0] for r in known_rows}

            if ats_type == "greenhouse":
                # Leading % is required — real apply_links start with https://, so an
                # anchored "boards.greenhouse.io/%" pattern would never match.
                pattern = "%boards.greenhouse.io/%"
                rows = db.execute(
                    text("SELECT DISTINCT apply_link FROM jobs WHERE apply_link LIKE :p"),
                    {"p": pattern},
                ).fetchall()
                # Path segments that are part of the embed/JS widget URL, not board tokens.
                denylist = {"embed", "job_board", "js", "jobs", "job_app", "embed_job_board"}
                tokens = set()
                for (url,) in rows:
                    parts = url.split("boards.greenhouse.io/")
                    if len(parts) > 1:
                        # Strip query string/fragment before isolating the first path segment.
                        token = parts[1].split("?")[0].split("#")[0].split("/")[0]
                        if (
                            token
                            and token not in known
                            and token.lower() not in denylist
                        ):
                            tokens.add(token)
                return list(tokens)
            return []
        except Exception as e:
            logger.error("get_unregistered_apply_link_tokens failed: %s", e)
            return []
        finally:
            close_db(db)

    def get_stats(self) -> Dict:
        db = get_db()
        try:
            from sqlalchemy.sql import func as sqlfunc
            rows = db.query(
                _ORMCompanyRegistry.ats_type,
                sqlfunc.count(_ORMCompanyRegistry.id),
            ).filter_by(is_active=True).group_by(_ORMCompanyRegistry.ats_type).all()
            by_ats = {ats: cnt for ats, cnt in rows}
            total = sum(by_ats.values())
            return {"total_active": total, "by_ats": by_ats}
        finally:
            close_db(db)
