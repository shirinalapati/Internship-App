# Examples Directory

This directory contains example scripts demonstrating various features of the Internship App scraping system.

## Available Examples

### 1. Date Filtering Example (`date_filtering_example.py`)

Demonstrates the date filtering feature for job scraping.

**What it demonstrates:**
- Getting jobs from specific time periods (7, 30, 90 days)
- Comparing job counts across different time periods
- Finding fresh job opportunities
- Incremental scraping with date filters
- Analyzing job posting patterns

**How to run:**
```bash
cd /Users/sujannandikolsunilkumar/stack-auth-hackathon/Internship-App
python examples/date_filtering_example.py
```

**Example output:**
```
🚀 Date Filtering Feature Examples
================================================================================

Running all examples...

================================================================================
EXAMPLE 1: Get jobs posted in the last 30 days
================================================================================
🔍 [GitHub Internships] Starting full scrape (last 30 days) from Summer 2026 Tech Internships repository...
✅ Found 50 jobs posted in the last 30 days

1. ByteDance - Software Engineer Intern
   📅 Posted: Oct 20
   📍 Location: San Francisco, CA
   🔗 Apply: https://...
...
```

## Running Examples

All examples can be run from the project root:

```bash
# Navigate to project root
cd /Users/sujannandikolsunilkumar/stack-auth-hackathon/Internship-App

# Run an example
python examples/date_filtering_example.py
```

## Prerequisites

Make sure you have the required dependencies installed:

```bash
# Install dependencies
pip install -r requirements.txt

# Or if using a virtual environment
source venv/bin/activate
pip install -r requirements.txt
```

## Creating New Examples

To create a new example:

1. Create a new Python file in the `examples/` directory
2. Add appropriate imports from the project modules
3. Add clear documentation and comments
4. Update this README with information about the new example

### Example Template

```python
#!/usr/bin/env python3
"""
Brief description of what this example demonstrates.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from job_scrapers.scrape_github_internships import scrape_github_internships

def main():
    """
    Main function demonstrating the feature.
    """
    print("🚀 Example Name")
    print("=" * 80)
    
    # Your example code here
    jobs = scrape_github_internships(max_results=10)
    print(f"Found {len(jobs)} jobs")

if __name__ == "__main__":
    main()
```

## Getting Help

For more information about specific features:
- See the `changes/` directory for detailed documentation
- Check the main `README.md` in the project root
- Review the source code in `job_scrapers/` for implementation details

## Contributing

Feel free to add new examples that demonstrate useful features or workflows!

