#!/usr/bin/env python3
"""
Example script demonstrating the date filtering feature for job scraping.

This script shows various ways to filter jobs by posting date.
"""

import sys
import os

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from job_scrapers.scrape_github_internships import scrape_github_internships, filter_jobs_by_date

def example_1_get_recent_jobs():
    """
    Example 1: Get jobs posted in the last 30 days
    """
    print("=" * 80)
    print("EXAMPLE 1: Get jobs posted in the last 30 days")
    print("=" * 80)
    
    jobs = scrape_github_internships(max_results=50, max_days_old=30)
    
    print(f"\n✅ Found {len(jobs)} jobs posted in the last 30 days\n")
    
    # Show first 5 jobs with date information
    for i, job in enumerate(jobs[:5], 1):
        print(f"{i}. {job['company']} - {job['title']}")
        print(f"   📅 Posted: {job.get('date_posted', 'Unknown')}")
        print(f"   📍 Location: {job['location']}")
        print(f"   🔗 Apply: {job['apply_link']}")
        print()

def example_2_compare_time_periods():
    """
    Example 2: Compare jobs across different time periods
    """
    print("=" * 80)
    print("EXAMPLE 2: Compare jobs across different time periods")
    print("=" * 80)
    
    # Scrape all jobs first
    all_jobs = scrape_github_internships(max_results=100)
    
    # Filter by different time periods
    last_week = filter_jobs_by_date(all_jobs, max_days=7)
    last_month = filter_jobs_by_date(all_jobs, max_days=30)
    last_quarter = filter_jobs_by_date(all_jobs, max_days=90)
    
    print(f"\n📊 Job Statistics by Time Period:")
    print(f"   • Last 7 days:    {len(last_week)} jobs")
    print(f"   • Last 30 days:   {len(last_month)} jobs")
    print(f"   • Last 90 days:   {len(last_quarter)} jobs")
    print(f"   • All jobs:       {len(all_jobs)} jobs")
    print()

def example_3_find_fresh_opportunities():
    """
    Example 3: Find very fresh job postings (last 7 days)
    """
    print("=" * 80)
    print("EXAMPLE 3: Find very fresh job postings (last 7 days)")
    print("=" * 80)
    
    fresh_jobs = scrape_github_internships(max_results=50, max_days_old=7)
    
    print(f"\n🆕 Found {len(fresh_jobs)} fresh jobs posted in the last week\n")
    
    # Sort by days since posted (most recent first)
    fresh_jobs.sort(key=lambda x: x.get('days_since_posted', 999))
    
    # Show first 5 with detailed date info
    for i, job in enumerate(fresh_jobs[:5], 1):
        days = job.get('days_since_posted')
        days_text = f"{days} days ago" if days else "Recently"
        
        print(f"{i}. {job['company']} - {job['title']}")
        print(f"   ⏰ {days_text}")
        print(f"   📍 {job['location']}")
        print(f"   💼 Skills: {', '.join(job.get('required_skills', [])[:3])}")
        print()

def example_4_incremental_with_date_filter():
    """
    Example 4: Incremental scraping with date filter
    """
    print("=" * 80)
    print("EXAMPLE 4: Incremental scraping with date filter (new jobs from last 14 days)")
    print("=" * 80)
    
    # This will only return jobs that are:
    # 1. Not in the database yet (incremental=True)
    # 2. Posted within the last 14 days (max_days_old=14)
    new_recent_jobs = scrape_github_internships(
        incremental=True,
        max_days_old=14
    )
    
    print(f"\n✅ Found {len(new_recent_jobs)} new jobs from the last 2 weeks\n")
    
    # Group by company
    companies = {}
    for job in new_recent_jobs:
        company = job['company']
        if company not in companies:
            companies[company] = []
        companies[company].append(job)
    
    print(f"📊 New jobs by company:")
    for company, jobs in sorted(companies.items()):
        print(f"   • {company}: {len(jobs)} positions")
    print()

def example_5_analyze_posting_patterns():
    """
    Example 5: Analyze job posting patterns
    """
    print("=" * 80)
    print("EXAMPLE 5: Analyze job posting patterns")
    print("=" * 80)
    
    all_jobs = scrape_github_internships(max_results=200)
    
    # Count jobs by time period
    time_buckets = {
        'Last 7 days': 0,
        '8-14 days ago': 0,
        '15-30 days ago': 0,
        '31-60 days ago': 0,
        '60+ days ago': 0,
        'Unknown': 0
    }
    
    for job in all_jobs:
        days = job.get('days_since_posted')
        if days is None:
            time_buckets['Unknown'] += 1
        elif days <= 7:
            time_buckets['Last 7 days'] += 1
        elif days <= 14:
            time_buckets['8-14 days ago'] += 1
        elif days <= 30:
            time_buckets['15-30 days ago'] += 1
        elif days <= 60:
            time_buckets['31-60 days ago'] += 1
        else:
            time_buckets['60+ days ago'] += 1
    
    print(f"\n📈 Posting Pattern Analysis (from {len(all_jobs)} jobs):")
    for period, count in time_buckets.items():
        percentage = (count / len(all_jobs)) * 100 if all_jobs else 0
        bar = '█' * int(percentage / 2)
        print(f"   {period:20} {count:4} jobs {bar} ({percentage:.1f}%)")
    print()

def main():
    """
    Run all examples
    """
    print("\n")
    print("🚀 Date Filtering Feature Examples")
    print("=" * 80)
    print()
    
    examples = [
        ("Get Recent Jobs (30 days)", example_1_get_recent_jobs),
        ("Compare Time Periods", example_2_compare_time_periods),
        ("Find Fresh Opportunities (7 days)", example_3_find_fresh_opportunities),
        ("Incremental with Date Filter", example_4_incremental_with_date_filter),
        ("Analyze Posting Patterns", example_5_analyze_posting_patterns),
    ]
    
    print("Available examples:")
    for i, (name, _) in enumerate(examples, 1):
        print(f"  {i}. {name}")
    print(f"  0. Run all examples")
    print()
    
    # For automated demo, run all examples
    print("Running all examples...\n")
    
    for name, func in examples:
        try:
            func()
            print()
        except Exception as e:
            print(f"❌ Error in {name}: {e}\n")
    
    print("=" * 80)
    print("✅ All examples completed!")
    print("=" * 80)

if __name__ == "__main__":
    main()

