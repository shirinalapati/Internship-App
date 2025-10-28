# Date Filtering Feature for GitHub Internships Scraper

## Summary
Updated the GitHub internships scraper to collect and parse posting dates, enabling proper filtering of recently posted jobs.

## Files Modified

1. **`job_scrapers/scrape_github_internships.py`** - Main scraper with date parsing logic
2. **`job_scrapers/dispatcher.py`** - Job dispatcher with date filtering support
3. **`examples/date_filtering_example.py`** - Usage examples (NEW FILE)
4. **`changes/DATE_FILTERING_FEATURE.md`** - This documentation (NEW FILE)

## Changes Made

### 1. **New Function: `parse_date_to_days()`** (scrape_github_internships.py)
- **Location**: Lines 1098-1203
- **Purpose**: Converts various date formats to normalized days since posted
- **Supported Formats**:
  - Relative time: "today", "yesterday", "X days ago", "X weeks ago", "X months ago"
  - Short formats: "Xd", "Xw", "Xmo", "Xy"
  - ISO format: "YYYY-MM-DD" (e.g., "2025-10-21")
  - Month-day format: "Oct 21"
  - Full date format: "Oct 21, 2025"
  - Slash formats: "MM/DD/YYYY" or "DD/MM/YYYY"
- **Returns**: Integer representing days since posted, or `None` if unable to parse

### 2. **Enhanced `parse_internship_table()` Function**
- **New Features**:
  - Automatically detects date column in the table header (looks for keywords: "date posted", "posted", "date added", "added", "date")
  - Extracts date information from each job posting
  - Parses dates using the new `parse_date_to_days()` function
  - Adds three new fields to each job dictionary:
    - `date_posted`: Raw date string (human-readable)
    - `date_posted_raw`: Original date string from source
    - `days_since_posted`: Normalized integer for filtering (e.g., 7, 30, 90)
  - Prints date information for each job when available

### 3. **New Function: `filter_jobs_by_date()`**
- **Location**: Lines 874-906
- **Purpose**: Filter job listings based on posting date
- **Parameters**:
  - `jobs`: List of job dictionaries
  - `max_days`: Maximum number of days since posted (e.g., 30 for last 30 days)
- **Behavior**: 
  - If `max_days` is `None`, returns all jobs
  - Jobs without date information are included (benefit of doubt)
  - Reports how many jobs were filtered out
- **Example Usage**:
  ```python
  recent_jobs = filter_jobs_by_date(all_jobs, max_days=30)  # Last 30 days
  ```

### 4. **Updated `scrape_github_internships()` Function** (scrape_github_internships.py)
- **New Parameter**: `max_days_old` - Filter to jobs posted within N days
- **Usage Examples**:
  ```python
  # Get all jobs (no date filter)
  jobs = scrape_github_internships()
  
  # Get jobs from last 30 days
  recent_jobs = scrape_github_internships(max_days_old=30)
  
  # Get incremental jobs from last 7 days
  new_jobs = scrape_github_internships(incremental=True, max_days_old=7)
  ```
- **Enhanced Logging**: Shows date filter information in console output

### 5. **Updated Job Dispatcher Functions** (dispatcher.py)
All dispatcher functions now support the `max_days_old` parameter:

- **`scrape_all_company_sites()`**: Added `max_days_old` parameter, passes it to GitHub scraper
- **`scrape_jobs()`**: Main async function with date filtering support
- **`scrape_jobs_incremental()`**: Incremental scraping with optional date filter
- **`scrape_jobs_full()`**: Full scraping with optional date filter

**Usage Examples**:
```python
from job_scrapers.dispatcher import scrape_jobs

# Get jobs from last 30 days
jobs = await scrape_jobs(max_days_old=30)

# Incremental scraping with 14-day filter
new_jobs = await scrape_jobs_incremental(max_days_old=14)

# Full scraping with 60-day filter
all_recent = await scrape_jobs_full(max_days_old=60)
```

### 6. **New Example File** (examples/date_filtering_example.py)
Created comprehensive examples demonstrating:
- Getting recent jobs (30 days)
- Comparing time periods (7, 30, 90 days)
- Finding fresh opportunities (7 days)
- Incremental scraping with date filter
- Analyzing posting patterns

Run examples with:
```bash
python examples/date_filtering_example.py
```

## Benefits

1. **Better Job Relevance**: Users can now filter to recently posted internships, avoiding outdated listings
2. **Flexible Filtering**: Supports multiple date filtering strategies (30 days, 60 days, 90 days, etc.)
3. **Robust Date Parsing**: Handles various date formats commonly used in job listings
4. **Backward Compatible**: Existing code continues to work without changes
5. **Database Ready**: Date information is stored with each job for future querying

## Example Workflows

### Scenario 1: Get Fresh Jobs Only
```python
# Get jobs posted in the last 2 weeks
fresh_jobs = scrape_github_internships(max_days_old=14)
```

### Scenario 2: Incremental Scraping with Date Filter
```python
# Get only new jobs from the last month
new_recent_jobs = scrape_github_internships(
    incremental=True,
    max_days_old=30
)
```

### Scenario 3: Manual Filtering After Scraping
```python
# Scrape all jobs first
all_jobs = scrape_github_internships()

# Then filter by different time periods as needed
last_week = filter_jobs_by_date(all_jobs, max_days=7)
last_month = filter_jobs_by_date(all_jobs, max_days=30)
last_quarter = filter_jobs_by_date(all_jobs, max_days=90)
```

## Job Dictionary Structure (Updated)

Each job now includes:
```python
{
    'company': 'Company Name',
    'title': 'Software Engineer Intern',
    'location': 'San Francisco, CA',
    'apply_link': 'https://...',
    'description': '...',
    'job_requirements': '...',
    'source': 'github_internships',
    'required_skills': ['Python', 'Java', ...],
    'date_posted': 'Oct 21',           # NEW: Human-readable date
    'date_posted_raw': 'Oct 21',       # NEW: Original date string
    'days_since_posted': 6             # NEW: Integer for filtering
}
```

## Integration Points

### Frontend Integration
The frontend can now:
- Display posting dates to users
- Add date range filters to the UI
- Sort jobs by posting date
- Show "Posted X days ago" labels

### API Integration
The backend API can:
- Accept `max_days_old` parameter in job search endpoints
- Return date information in job responses
- Enable date-based sorting and filtering

### Database Integration
The date information can be:
- Stored in the jobs database
- Used for index creation
- Used for automated cleanup of old jobs
- Used for analytics on job posting trends

## Testing the Feature

Run the scraper with date filtering:
```bash
cd /Users/sujannandikolsunilkumar/stack-auth-hackathon/Internship-App
python job_scrapers/scrape_github_internships.py
```

The output will show date information for each job:
```
📅 [GitHub] ByteDance - Software Engineer Intern: Posted 7 days ago (Oct 20)
✅ [GitHub] Added job: ByteDance - Software Engineer Intern (Posted: Oct 20) (Skills: ['Python', 'Java', 'Backend']...)
```

## Future Enhancements

Potential improvements:
1. Add more date format support (international formats)
2. Add timezone support for more accurate date calculations
3. Create date-based analytics dashboard
4. Auto-archive jobs older than X days
5. Send notifications for newly posted jobs
6. Add "urgent" flag for jobs closing soon

## Quick Start Guide

### Basic Usage (Python)

```python
# Import the scraper
from job_scrapers.scrape_github_internships import scrape_github_internships

# Get jobs from the last 30 days
recent_jobs = scrape_github_internships(max_days_old=30)

# Print results
for job in recent_jobs[:5]:
    print(f"{job['company']} - {job['title']}")
    print(f"Posted: {job.get('date_posted', 'Unknown')}")
    print(f"Days ago: {job.get('days_since_posted', 'N/A')}")
    print()
```

### Using the Dispatcher (Async)

```python
from job_scrapers.dispatcher import scrape_jobs
import asyncio

async def main():
    # Get fresh jobs from last 14 days
    jobs = await scrape_jobs(max_days_old=14)
    print(f"Found {len(jobs)} jobs from the last 2 weeks")

asyncio.run(main())
```

### Command Line Testing

```bash
# Test the scraper directly
cd /Users/sujannandikolsunilkumar/stack-auth-hackathon/Internship-App
python -c "from job_scrapers.scrape_github_internships import scrape_github_internships; jobs = scrape_github_internships(max_days_old=30, max_results=10); print(f'Found {len(jobs)} jobs')"
```

### Running the Examples

```bash
# Run all examples
python examples/date_filtering_example.py

# The examples demonstrate:
# - Basic date filtering (30 days)
# - Comparing multiple time periods
# - Finding fresh opportunities (7 days)
# - Incremental scraping with dates
# - Posting pattern analysis
```

## API Integration Example

To integrate with your FastAPI app, you can add a query parameter for date filtering:

```python
from fastapi import FastAPI, Query
from job_scrapers.dispatcher import scrape_jobs

app = FastAPI()

@app.get("/api/jobs")
async def get_jobs(
    max_days_old: int = Query(None, description="Filter jobs by days since posted"),
    incremental: bool = Query(False, description="Only return new jobs")
):
    """
    Get jobs with optional date filtering
    
    Examples:
    - GET /api/jobs - All jobs
    - GET /api/jobs?max_days_old=30 - Jobs from last 30 days
    - GET /api/jobs?max_days_old=7&incremental=true - New jobs from last week
    """
    jobs = await scrape_jobs(max_days_old=max_days_old, incremental=incremental)
    
    return {
        "count": len(jobs),
        "max_days_old": max_days_old,
        "jobs": jobs
    }
```

## Common Use Cases

### Use Case 1: Daily Fresh Job Updates
```python
# Run this daily to get new jobs posted in the last 24 hours
fresh_jobs = scrape_github_internships(incremental=True, max_days_old=1)
```

### Use Case 2: Weekly Job Digest
```python
# Run this weekly to get jobs from the past 7 days
weekly_jobs = scrape_github_internships(max_days_old=7)
```

### Use Case 3: Remove Stale Jobs from Database
```python
from job_scrapers.scrape_github_internships import filter_jobs_by_date
from job_database import get_all_jobs, remove_jobs

# Get all jobs from database
all_jobs = get_all_jobs()

# Keep only jobs from last 90 days
fresh_jobs = filter_jobs_by_date(all_jobs, max_days=90)
stale_jobs = [job for job in all_jobs if job not in fresh_jobs]

# Remove stale jobs
remove_jobs(stale_jobs)
```

## Notes

- Date parsing is robust but may occasionally fail for unusual formats
- Jobs without dates are included by default (fail-safe behavior)
- The `days_since_posted` field uses approximate conversions (1 month ≈ 30 days)
- All dates are calculated relative to the current system time
- The feature is backward compatible - existing code works without changes

