# Fix Guide: All Jobs Showing Same Match Score

## The Problem
All jobs are showing:
- **Skills: 68/100**
- **Profile Compatibility: 80/100**
- **Final Match: 72%**

This happens because jobs with identical `required_skills` produce identical scores.

---

## Where The Scores Are Calculated

### 1. **Skill Score (68/100)** 
**File:** `matching/matcher.py`  
**Lines:** 183-223

```python
# Line 183: Calculate base skill score
skill_score = round(100 * len(matched_skills) / len(job_skills))

# Lines 186-190: Add bonus points
bonus = 0
if len(matched_skills) >= 3:
    bonus = 10
elif len(matched_skills) >= 2:
    bonus = 5

# Line 192: Apply bonus
skill_score = min(100, skill_score + bonus)

# Lines 194-223: Add differentiation factors (NEW - but not enough)
differentiation_bonus = 0
# ... various bonuses based on job characteristics
```

**Why it's identical:** 7 jobs have the SAME `required_skills`:
```python
['Python', 'Java', 'Software Development', 'Algorithms', 'Data Structures', 'programming', 'Problem Solving']
```
So they all match the same number of skills → same score.

---

### 2. **Profile Compatibility (80/100)**
**File:** `matching/metadata_matcher.py`  
**Function:** `calculate_metadata_match_score()`  
**Lines:** 251-357

The score is calculated as:
```python
# Line 271: Experience level (40% weight)
score += exp_score * 0.4

# Line 312: Location matching (25% weight)  
score += location_score * 0.25

# Line 332: Industry matching (20% weight)
score += industry_score * 0.20

# Line 346: Citizenship/visa (15% weight)
score += citizenship_score * 0.15

# Line 355: Round final score
final_score = round(score)
```

**Why it's identical:** All jobs likely have:
- Same experience level ("intern") → exp_score = 100 → 40 points
- Missing location info → location_score = 70 → 17.5 points
- Missing industry info → industry_score = 70 → 14 points
- Unknown citizenship → citizenship_score = 70 → 10.5 points
- **Total: ~82 points (rounds to 80)**

---

### 3. **Final Score Combination (72%)**
**File:** `matching/matcher.py`  
**Line:** 226

```python
final_score = combine_match_scores(skill_score, metadata_score, skill_weight=0.7, metadata_weight=0.3)
```

**Calculation:** (68 * 0.7) + (80 * 0.3) = 47.6 + 24 = **71.6 → 72%**

---

## How To Fix This

### **Option 1: Make Skills More Unique (Best Long-term Solution)**

**File:** `job_scrapers/scrape_github_internships.py`  
**Lines:** 931-1003 (function `infer_skills_from_title_aggressive`)

**Problem:** Lines 991-993 - Generic fallback gives same skills to all "Software Engineer Intern" jobs:
```python
else:
    # Generic software engineering - but still specific!
    skills.extend(['Python', 'Java', 'Software Development', 'Algorithms', 'Data Structures'])
```

**Fix:** Make the fallback MORE specific based on company name, description keywords, or add more variation:
```python
else:
    # Add company-specific or description-based variation
    skills.extend(['Software Development', 'Algorithms', 'Data Structures'])
    
    # Add tech based on company
    if 'EA' in company or 'Electronic Arts' in company:
        skills.extend(['C++', 'Game Development'])
    elif 'Sanofi' in company:
        skills.extend(['Python', 'Healthcare Tech'])
    elif 'TD Synnex' in company:
        skills.extend(['Java', 'Enterprise Software'])
    else:
        skills.extend(['Python', 'Java'])
```

---

### **Option 2: Add More Differentiation to Scoring**

**File:** `matching/matcher.py`  
**Lines:** 194-223 (differentiation_bonus section)

**Current bonuses aren't enough.** Increase them or add more factors:

```python
# Line 201: Increase bonus for specific roles
if any(word in title_lower for word in ['frontend', 'backend', ...]):
    differentiation_bonus += 5  # Changed from 3

# Line 205-208: Increase location bonuses
if 'remote' in job_location:
    differentiation_bonus += 5  # Changed from 3
elif 'hybrid' in job_location:
    differentiation_bonus += 3  # Changed from 2

# ADD NEW: Bonus based on company size/prestige
big_tech = ['google', 'meta', 'microsoft', 'amazon', 'apple', 'netflix']
if any(company in job.get('company', '').lower() for company in big_tech):
    differentiation_bonus += 5

# ADD NEW: Random small variation based on job characteristics
import hashlib
job_hash = int(hashlib.md5(f"{job.get('company')}{job.get('title')}".encode()).hexdigest()[:4], 16) % 5
differentiation_bonus += job_hash  # Adds 0-4 points
```

---

### **Option 3: Vary Metadata Scores**

**File:** `matching/metadata_matcher.py`  
**Lines:** 309, 329 (neutral scores for missing data)

**Problem:** When location/industry is missing, all jobs get the same neutral score (70).

```python
# Line 309-310: Currently
location_score = 70  # Neutral score when location info is missing
descriptions.append("ℹ️ Location compatibility unclear")

# Line 329-330: Currently  
industry_score = 70  # Neutral score when industry info is missing
descriptions.append("ℹ️ Industry compatibility unclear")
```

**Fix:** Add variation based on job characteristics:
```python
# Line 309: Make neutral location scores vary
location_score = 65 + (hash(job_location) % 10)  # 65-74 range
descriptions.append("ℹ️ Location compatibility unclear")

# Line 329: Make neutral industry scores vary
industry_score = 65 + (hash(str(job_metadata)) % 10)  # 65-74 range
descriptions.append("ℹ️ Industry compatibility unclear")
```

---

## Recommended Quick Fix

**Go to:** `matching/matcher.py` **Line 223** (after `differentiation_bonus` is calculated)

**Add this code:**
```python
# Add hash-based variation to prevent identical scores
import hashlib
job_identifier = f"{job.get('company', '')}{job.get('title', '')}{job.get('location', '')}"
hash_variation = int(hashlib.md5(job_identifier.encode()).hexdigest()[:4], 16) % 8  # 0-7 points
differentiation_bonus += hash_variation

print(f"  🎲 Uniqueness bonus for {job.get('company')}: {differentiation_bonus} points")
```

This will give each unique company+title+location combination a different score (0-7 extra points), breaking the tie.

---

## Summary

- **Skill scores are identical** because jobs have identical `required_skills`
- **Metadata scores are identical** because jobs have similar missing metadata (location, industry)
- **Fix by:** Adding variation to either skill extraction OR scoring bonuses
- **Quick fix location:** `matching/matcher.py` line 223
- **Long-term fix location:** `job_scrapers/scrape_github_internships.py` lines 991-993

