"""
Crawl orchestrator — manages schedule, concurrency, and error tracking per company.

Replaces the current dispatcher.py for ATS sources. The SimplifyJobs scraper
continues to run in parallel via job_scrapers/dispatcher.py.
"""
import asyncio
import logging
from datetime import datetime
from typing import List, Optional

from crawlers.company_registry import CompanyRegistryStore, CompanyRecord
from crawlers.greenhouse import CompanyNotFound, RateLimitError
from crawlers.normalizer import is_intern_posting, normalize_job
from job_database import bulk_insert_jobs

logger = logging.getLogger(__name__)

CONCURRENCY = 20
RATE_LIMIT_DELAY = 0.2
BACKOFF_ON_429 = 60
MAX_RETRIES = 3


def _get_crawler(ats_type: str):
    """Return the crawler module for the given ATS type."""
    if ats_type == "greenhouse":
        import crawlers.greenhouse as m
    elif ats_type == "lever":
        import crawlers.lever as m
    elif ats_type == "ashby":
        import crawlers.ashby as m
    elif ats_type == "workday":
        import crawlers.workday as m
    elif ats_type == "smartrecruiters":
        import crawlers.smartrecruiters as m
    elif ats_type == "icims":
        import crawlers.icims as m
    else:
        return None
    return m


class CrawlOrchestrator:
    """
    Manages crawl schedule, concurrency, and error tracking per company.
    """

    def __init__(self):
        self.registry = CompanyRegistryStore()

    async def run_incremental(self, max_age_hours: int = 1, ats_types: List[str] = None) -> dict:
        """Fetch only jobs updated in last N hours. Designed to run every 15 min."""
        companies = self.registry.get_due_for_crawl(priority=[1, 2, 3])
        if ats_types:
            companies = [c for c in companies if c.ats_type in ats_types]
        return await self._crawl_batch(companies, since_hours=max_age_hours)

    async def run_full(self, ats_types: List[str] = None) -> dict:
        """Re-crawl all companies. Designed to run nightly."""
        companies = self.registry.get_all_active()
        if ats_types:
            companies = [c for c in companies if c.ats_type in ats_types]
        return await self._crawl_batch(companies, since_hours=None)

    async def _crawl_batch(self, companies: List[CompanyRecord], since_hours: Optional[int]) -> dict:
        start = datetime.utcnow()
        semaphore = asyncio.Semaphore(CONCURRENCY)
        tasks = [self._crawl_company(c, since_hours, semaphore) for c in companies]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        jobs_flat: List[dict] = []
        for r in results:
            if isinstance(r, list):
                jobs_flat.extend(r)

        insert_result = bulk_insert_jobs(jobs_flat) if jobs_flat else {"new_jobs": 0}
        if companies:
            self.registry.update_last_crawled(companies)

        # Generate sentence embeddings for crawled jobs in a background thread
        # so the crawl return is not blocked by CPU-bound model inference.
        # run_in_executor returns a Future (already scheduled) — do NOT wrap it
        # in create_task, which expects a coroutine and raises TypeError on a Future.
        if jobs_flat:
            from matching.embedder import generate_job_embeddings_sync
            loop = asyncio.get_running_loop()
            self._embed_task = loop.run_in_executor(None, generate_job_embeddings_sync, jobs_flat)

        # Auto-discover new Greenhouse companies from apply_link referrals
        self._discovery_task = asyncio.create_task(self._discover_from_apply_links())

        duration_ms = int((datetime.utcnow() - start).total_seconds() * 1000)
        return {
            "companies_crawled": len(companies),
            "jobs_found": len(jobs_flat),
            "new_jobs": insert_result.get("new_jobs", 0),
            "duration_ms": duration_ms,
        }

    async def _crawl_company(
        self,
        company: CompanyRecord,
        since_hours: Optional[int],
        semaphore: asyncio.Semaphore,
    ) -> List[dict]:
        module = _get_crawler(company.ats_type)
        if module is None:
            logger.warning("No crawler for ats_type=%s", company.ats_type)
            return []

        # get_due_for_crawl() only returns `limit` (default 200) companies per
        # incremental call, ordered oldest-last_crawled-first. With ~9,953
        # registered companies that means each company is only actually
        # visited roughly once every ~12.7h (9953 / 200 * 15min), even though
        # incremental runs every 15 minutes. A fixed since_hours=1 window
        # (the GitHub Actions default) silently misses any job that was
        # posted more than an hour before its turn came up — it's neither
        # "new" (already >1h old by the time we check) nor caught by the
        # NEXT incremental run (which won't revisit this company for another
        # ~12.7h either). Those jobs only ever surface via the once-nightly
        # full crawl, which defeats the point of running incremental every
        # 15 minutes.
        #
        # Fix: widen the window per-company to cover back to (at least) when
        # this company was last actually crawled, with a small buffer for
        # scheduling jitter. Never crawled before -> no time filter at all,
        # so a newly-discovered company gets its full current listing on its
        # first pass instead of an arbitrary 1h slice of it.
        effective_since_hours = since_hours
        if since_hours is not None:
            if company.last_crawled is not None:
                elapsed_hours = (
                    datetime.utcnow() - company.last_crawled
                ).total_seconds() / 3600
                effective_since_hours = max(since_hours, elapsed_hours + 0.25)
            else:
                effective_since_hours = None

        for attempt in range(MAX_RETRIES):
            rate_limited = False
            async with semaphore:
                try:
                    raw_jobs = await module.fetch_jobs(company, since_hours=effective_since_hours)
                    intern_jobs = [j for j in raw_jobs if is_intern_posting(j.get("_title", ""), j.get("_employment_type", ""))]
                    return [normalize_job(j, company.ats_type, company) for j in intern_jobs]
                except CompanyNotFound:
                    self.registry.mark_inactive(company.company_id)
                    return []
                except RateLimitError:
                    rate_limited = True
                except Exception as exc:
                    logger.error(
                        "Crawl error for %s (%s): %s",
                        company.company_id, company.ats_type, exc,
                    )
                    return []

            if rate_limited:
                if attempt == MAX_RETRIES - 1:
                    return []
                wait = BACKOFF_ON_429 * (attempt + 1)
                logger.info("Rate limit for %s — sleeping %ds", company.company_id, wait)
                await asyncio.sleep(wait)

        return []

    async def discover_new_companies(self) -> dict:
        """
        Discover companies not yet in the registry by probing apply_link referrals
        and delegating to the bootstrap module.
        """
        from crawlers.bootstrap import run_bootstrap
        # incremental=True: skip slugs already registered as active companies so
        # discovery spends compute on net-new / not-yet-registered boards rather
        # than re-probing the thousands already known. The /api/crawl/discover-
        # companies endpoint mirrors this default and exposes rescan_all to force
        # a full re-probe when a registry rebuild is wanted.
        return await run_bootstrap(registry=self.registry, incremental=True)

    async def _discover_from_apply_links(self) -> int:
        """
        After each crawl batch, extract Greenhouse board tokens embedded in
        apply_links of existing jobs that are not yet in the registry, probe
        them, and auto-enqueue for the next cycle.

        Called at the end of _crawl_batch; returns count of new companies added.
        """
        import httpx

        new_tokens = self.registry.get_unregistered_apply_link_tokens(ats_type="greenhouse")
        if not new_tokens:
            return 0

        added = 0
        semaphore = asyncio.Semaphore(20)

        async def _probe(token: str) -> bool:
            async with semaphore:
                try:
                    async with httpx.AsyncClient(timeout=10) as client:
                        resp = await client.get(
                            f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
                            params={"limit": 1},
                        )
                        if resp.status_code == 200:
                            self.registry.upsert({
                                "company_id": token,
                                "display_name": token.replace("-", " ").title(),
                                "ats_type": "greenhouse",
                                "ats_board_id": token,
                                "careers_url": f"https://boards.greenhouse.io/{token}",
                            })
                            return True
                except Exception:
                    pass
            return False

        tasks = [_probe(t) for t in new_tokens[:500]]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        added = sum(1 for r in results if r is True)
        if added:
            logger.info("apply_link discovery: added %d new Greenhouse companies", added)
        return added
