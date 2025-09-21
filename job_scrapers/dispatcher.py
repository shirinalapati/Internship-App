from .scrape_github_internships import scrape_github_internships

def scrape_all_company_sites(keyword="intern", max_results=50):
    """
    Scrape jobs from all company sites.
    Focus on the GitHub scraper as the primary source.
    """
    all_jobs = []
    
    # Use GitHub Internships as the primary source (most reliable)
    print("🌐 [GitHub] Scraping from Summer 2026 Tech Internships repository...")
    github_jobs = scrape_github_internships(keyword, max_results=max_results)
    all_jobs.extend(github_jobs)
    
    # All other scrapers are disabled due to Selenium/WebDriver issues
    # The GitHub scraper provides comprehensive internship data
    
    print(f"📋 Total jobs scraped: {len(all_jobs)}")
    return all_jobs


async def scrape_jobs(keyword="intern", max_results=50):
    """
    Async wrapper for scrape_all_company_sites.
    This function is called by the FastAPI app.
    """
    return scrape_all_company_sites(keyword, max_results)
