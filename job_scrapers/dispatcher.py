from .scrape_salesforce import scrape_salesforce_jobs

def scrape_all_company_sites(keyword, location="United States", max_results=10):
    jobs = []
    jobs.extend(scrape_salesforce_jobs(keyword, max_results=max_results))
    return jobs
