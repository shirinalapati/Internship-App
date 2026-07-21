"""
Regression tests for crawlers.orchestrator._crawl_company's since_hours widening.

Bug being guarded against (GitHub issue #80): get_due_for_crawl() only returns
`limit` (default 200) companies per incremental call, ordered oldest-
last_crawled-first. With ~9,953 registered companies that means a company is
only actually revisited roughly once every ~12.7h, even though the
"incremental" GitHub Actions workflow fires every 15 minutes with a fixed
since_hours=1. Passing that fixed 1h window straight through to the ATS
crawler silently drops any job that was posted more than an hour before its
turn came back up in the rotation — it's too old to count as "new" but the
company won't be checked again for another ~12.7h either. Production showed
exactly this: the most recent incremental run crawled 200 companies and
found 0 jobs, while new postings only ever surfaced via the nightly full
crawl.

_crawl_company must widen the effective since_hours per company to cover
back to (at least) that company's own last_crawled timestamp, so no gap
opens between the rotation cadence and the freshness window.
"""
import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from crawlers.orchestrator import CrawlOrchestrator


def _company(last_crawled=None):
    return SimpleNamespace(
        company_id="acme",
        display_name="Acme",
        ats_type="greenhouse",
        ats_board_id="acme",
        careers_url="",
        industry="",
        company_size="",
        last_crawled=last_crawled,
        is_active=True,
        crawl_priority=1,
    )


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class _FakeModule:
    """Stand-in for crawlers.greenhouse (or any ATS module) that just records
    the since_hours it was called with."""

    def __init__(self):
        self.received_since_hours = None

    async def fetch_jobs(self, company, since_hours=None):
        self.received_since_hours = since_hours
        return []


@pytest.fixture(autouse=True)
def _no_semaphore_delay():
    yield


def test_widens_window_when_company_last_crawled_before_the_fixed_cutoff():
    """
    A company last crawled 13 hours ago, with the GH Actions default
    max_age_hours=1, must be fetched with a window that reaches back past
    13h — not the raw 1h — or jobs posted in that gap are silently lost.
    """
    orchestrator = CrawlOrchestrator()
    company = _company(last_crawled=datetime.utcnow() - timedelta(hours=13))
    fake_module = _FakeModule()

    with patch("crawlers.orchestrator._get_crawler", return_value=fake_module):
        _run(orchestrator._crawl_company(company, since_hours=1, semaphore=asyncio.Semaphore(1)))

    assert fake_module.received_since_hours is not None
    assert fake_module.received_since_hours >= 13


def test_does_not_narrow_window_when_company_was_recently_crawled():
    """
    A company crawled 5 minutes ago should still get at least the requested
    since_hours=1 window — the fix must never shrink below the caller's ask.
    """
    orchestrator = CrawlOrchestrator()
    company = _company(last_crawled=datetime.utcnow() - timedelta(minutes=5))
    fake_module = _FakeModule()

    with patch("crawlers.orchestrator._get_crawler", return_value=fake_module):
        _run(orchestrator._crawl_company(company, since_hours=1, semaphore=asyncio.Semaphore(1)))

    assert fake_module.received_since_hours >= 1


def test_never_crawled_company_gets_no_time_filter():
    """
    A brand-new company (last_crawled is None) should get its full current
    listing on the first pass, not an arbitrary 1h slice of it.
    """
    orchestrator = CrawlOrchestrator()
    company = _company(last_crawled=None)
    fake_module = _FakeModule()

    with patch("crawlers.orchestrator._get_crawler", return_value=fake_module):
        _run(orchestrator._crawl_company(company, since_hours=1, semaphore=asyncio.Semaphore(1)))

    assert fake_module.received_since_hours is None


def test_full_crawl_since_hours_none_is_left_untouched():
    """
    run_full() passes since_hours=None (no filter at all) — the widening
    logic must be a no-op in that case regardless of last_crawled.
    """
    orchestrator = CrawlOrchestrator()
    company = _company(last_crawled=datetime.utcnow() - timedelta(days=30))
    fake_module = _FakeModule()

    with patch("crawlers.orchestrator._get_crawler", return_value=fake_module):
        _run(orchestrator._crawl_company(company, since_hours=None, semaphore=asyncio.Semaphore(1)))

    assert fake_module.received_since_hours is None
