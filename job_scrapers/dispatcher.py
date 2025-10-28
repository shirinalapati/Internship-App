from .scrape_github_internships import scrape_github_internships

def scrape_all_company_sites(keyword="intern", max_results=10000, incremental=False, max_days_old=None):
    """
    Scrape jobs from all company sites with optional incremental mode and date filtering.
    Focus on the GitHub scraper as the primary source.
    
    Args:
        keyword: Search keyword
        max_results: Maximum number of results to return
        incremental: If True, only return new jobs not in database
        max_days_old: If set, only return jobs posted within this many days (e.g., 30 for last 30 days)
    """
    all_jobs = []
    
    # Use GitHub Internships as the primary source (most reliable)
    scrape_type = "incremental" if incremental else "full"
    date_filter_msg = f" (last {max_days_old} days)" if max_days_old else ""
    print(f"🌐 [GitHub] Starting {scrape_type} scrape{date_filter_msg} from Summer 2026 Tech Internships repository...")
    
    github_jobs = scrape_github_internships(
        keyword, 
        max_results=max_results, 
        incremental=incremental,
        max_days_old=max_days_old
    )
    all_jobs.extend(github_jobs)
    
    # All other scrapers are disabled due to Selenium/WebDriver issues
    # The GitHub scraper provides comprehensive internship data
    
    if incremental:
        print(f"📋 Total new jobs scraped: {len(all_jobs)}")
    else:
        print(f"📋 Total jobs scraped: {len(all_jobs)}")
    
    return all_jobs

async def scrape_jobs(keyword="intern", max_results=10000, incremental=None, max_days_old=None):
    """
    Async wrapper for scrape_all_company_sites with smart incremental detection and date filtering.
    This function is called by the FastAPI app.
    
    Args:
        keyword: Search keyword
        max_results: Maximum number of results to return
        incremental: If None, auto-detect based on cache status
        max_days_old: If set, only return jobs posted within this many days (e.g., 30 for last 30 days)
    """
    # Auto-detect incremental mode if not specified
    if incremental is None:
        try:
            from job_cache import should_do_incremental_scrape
            incremental = should_do_incremental_scrape()
        except Exception as e:
            print(f"⚠️ Error detecting incremental mode: {e}")
            incremental = False
    
    return scrape_all_company_sites(keyword, max_results, incremental=incremental, max_days_old=max_days_old)

async def scrape_jobs_incremental(keyword="intern", max_results=10000, max_days_old=None):
    """
    Force incremental scraping - only return new jobs
    
    Args:
        keyword: Search keyword
        max_results: Maximum number of results to return
        max_days_old: If set, only return jobs posted within this many days
    """
    return scrape_all_company_sites(keyword, max_results, incremental=True, max_days_old=max_days_old)

async def scrape_jobs_full(keyword="intern", max_results=10000, max_days_old=None):
    """
    Force full scraping - return all jobs
    
    Args:
        keyword: Search keyword
        max_results: Maximum number of results to return
        max_days_old: If set, only return jobs posted within this many days
    """
    return scrape_all_company_sites(keyword, max_results, incremental=False, max_days_old=max_days_old)
