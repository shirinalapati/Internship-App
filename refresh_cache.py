#!/usr/bin/env python3
"""
Cache Refresh Utility Script

This script provides easy command-line access to refresh the job cache.
It can perform full refreshes, incremental updates, and apply date filters.

Usage:
    python refresh_cache.py                    # Smart refresh (auto-detect incremental vs full)
    python refresh_cache.py --full             # Force full refresh
    python refresh_cache.py --incremental      # Force incremental refresh (new jobs only)
    python refresh_cache.py --days 30          # Refresh with jobs from last 30 days
    python refresh_cache.py --full --days 30   # Full refresh with 30-day filter
"""

import argparse
import asyncio
import sys
from job_cache import clear_cache, set_cached_jobs, get_cache_info, init_redis
from job_scrapers.dispatcher import scrape_jobs, scrape_jobs_full, scrape_jobs_incremental

def print_header():
    """Print a nice header"""
    print("\n" + "=" * 80)
    print("🔄 JOB CACHE REFRESH UTILITY")
    print("=" * 80 + "\n")

def print_cache_status():
    """Print current cache status"""
    print("📊 Current Cache Status:")
    print("-" * 80)
    
    cache_info = get_cache_info()
    
    # Database info
    if cache_info.get('database', {}).get('status') == 'active':
        db_info = cache_info['database']
        print(f"  📦 Database:")
        print(f"     • Active Jobs: {db_info.get('active_jobs', 0)}")
        print(f"     • Total Jobs: {db_info.get('total_jobs', 0)}")
        print(f"     • New (24h): {db_info.get('new_jobs_24h', 0)}")
    else:
        print(f"  📦 Database: Not available")
    
    # Redis info
    if cache_info.get('redis', {}).get('status') == 'active':
        redis_info = cache_info['redis']
        print(f"  ⚡ Redis:")
        print(f"     • Cached Jobs: {redis_info.get('job_count', 0)}")
        print(f"     • Expires In: {redis_info.get('hours_remaining', 0):.1f} hours")
    else:
        print(f"  ⚡ Redis: Not available")
    
    print("-" * 80 + "\n")

async def refresh_cache_smart(max_days_old=None):
    """Smart cache refresh - auto-detects incremental vs full"""
    date_msg = f" (last {max_days_old} days)" if max_days_old else ""
    print(f"🔄 Performing smart refresh{date_msg}...")
    print("   (Automatically determines if incremental or full scrape is needed)\n")
    
    jobs = await scrape_jobs(max_days_old=max_days_old)
    
    if jobs:
        result = set_cached_jobs(jobs, cache_type='manual_refresh')
        print(f"\n✅ Refresh Complete!")
        print(f"   • New Jobs: {result.get('new_jobs', 0)}")
        print(f"   • Total Jobs Processed: {len(jobs)}")
        print(f"   • Database: {'✓' if result.get('database_success') else '✗'}")
        print(f"   • Redis: {'✓' if result.get('redis_success') else '✗'}")
        return True
    else:
        print("\n📝 No new jobs found")
        return False

async def refresh_cache_full(max_days_old=None):
    """Full cache refresh - scrapes all jobs"""
    date_msg = f" (last {max_days_old} days)" if max_days_old else ""
    print(f"🔄 Performing full refresh{date_msg}...")
    print("   (Scraping all jobs from scratch)\n")
    
    # Clear Redis cache first
    print("🗑️  Clearing Redis cache...")
    clear_cache()
    
    jobs = await scrape_jobs_full(max_days_old=max_days_old)
    
    if jobs:
        result = set_cached_jobs(jobs, cache_type='full_manual')
        print(f"\n✅ Full Refresh Complete!")
        print(f"   • New Jobs: {result.get('new_jobs', 0)}")
        print(f"   • Total Jobs Processed: {len(jobs)}")
        print(f"   • Database: {'✓' if result.get('database_success') else '✗'}")
        print(f"   • Redis: {'✓' if result.get('redis_success') else '✗'}")
        return True
    else:
        print("\n❌ No jobs scraped")
        return False

async def refresh_cache_incremental(max_days_old=None):
    """Incremental cache refresh - only new jobs"""
    date_msg = f" (last {max_days_old} days)" if max_days_old else ""
    print(f"🔄 Performing incremental refresh{date_msg}...")
    print("   (Only scraping new jobs not in database)\n")
    
    jobs = await scrape_jobs_incremental(max_days_old=max_days_old)
    
    if jobs:
        result = set_cached_jobs(jobs, cache_type='incremental_manual')
        print(f"\n✅ Incremental Refresh Complete!")
        print(f"   • New Jobs: {result.get('new_jobs', 0)}")
        print(f"   • Total Jobs Processed: {len(jobs)}")
        print(f"   • Database: {'✓' if result.get('database_success') else '✗'}")
        print(f"   • Redis: {'✓' if result.get('redis_success') else '✗'}")
        return True
    else:
        print("\n📝 No new jobs found (this is normal for incremental refresh)")
        return False

def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description='Refresh the job cache with various options',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python refresh_cache.py                    # Smart refresh
  python refresh_cache.py --full             # Full refresh
  python refresh_cache.py --incremental      # Incremental refresh
  python refresh_cache.py --days 30          # Jobs from last 30 days
  python refresh_cache.py --full --days 30   # Full refresh with 30-day filter
  python refresh_cache.py --incremental --days 7  # New jobs from last week
        """
    )
    
    parser.add_argument(
        '--full',
        action='store_true',
        help='Force full cache refresh (scrape all jobs)'
    )
    
    parser.add_argument(
        '--incremental',
        action='store_true',
        help='Force incremental refresh (only new jobs)'
    )
    
    parser.add_argument(
        '--days',
        type=int,
        metavar='N',
        help='Only get jobs posted within last N days (e.g., 30)'
    )
    
    parser.add_argument(
        '--status-only',
        action='store_true',
        help='Only show cache status, don\'t refresh'
    )
    
    args = parser.parse_args()
    
    # Print header
    print_header()
    
    # Initialize cache system
    print("🔧 Initializing cache system...")
    init_redis()
    print()
    
    # Show current status
    print_cache_status()
    
    # If status-only, exit
    if args.status_only:
        print("✅ Status check complete\n")
        return 0
    
    # Validate arguments
    if args.full and args.incremental:
        print("❌ Error: Cannot use --full and --incremental together")
        return 1
    
    # Perform refresh based on arguments
    try:
        if args.full:
            success = asyncio.run(refresh_cache_full(max_days_old=args.days))
        elif args.incremental:
            success = asyncio.run(refresh_cache_incremental(max_days_old=args.days))
        else:
            success = asyncio.run(refresh_cache_smart(max_days_old=args.days))
        
        # Show final status
        print("\n" + "=" * 80)
        print("📊 Final Cache Status:")
        print("=" * 80 + "\n")
        print_cache_status()
        
        if success:
            print("✅ Cache refresh completed successfully!\n")
            return 0
        else:
            print("⚠️  Cache refresh completed with no new jobs\n")
            return 0
            
    except KeyboardInterrupt:
        print("\n\n❌ Refresh cancelled by user")
        return 1
    except Exception as e:
        print(f"\n\n❌ Error during refresh: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())

