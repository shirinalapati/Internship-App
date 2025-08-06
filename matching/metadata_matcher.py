import re
from typing import Dict, List, Tuple, Any

def extract_resume_metadata(resume_skills: List[str], resume_text: str = "") -> Dict[str, Any]:
    """
    Extract metadata from resume including experience level, education, location preferences, etc.
    """
    metadata = {
        "experience_level": "student",  # Default for internship matching
        "education_level": "undergraduate",
        "location_preferences": [],
        "industry_preferences": [],
        "remote_preference": False,
        "relocation_willingness": False,
        "graduation_year": None,
        "gpa": None,
        "citizenship": "unknown"
    }
    
    # Extract experience level
    experience_indicators = {
        "senior": ["senior", "lead", "principal", "staff", "architect", "manager"],
        "mid": ["mid-level", "intermediate", "3+ years", "5+ years"],
        "junior": ["junior", "entry-level", "0-2 years", "recent graduate"],
        "student": ["student", "intern", "internship", "co-op", "undergraduate", "graduate"]
    }
    
    text_lower = resume_text.lower()
    for level, indicators in experience_indicators.items():
        for indicator in indicators:
            if indicator in text_lower:
                metadata["experience_level"] = level
                break
    
    # Extract education level
    education_indicators = {
        "phd": ["phd", "doctorate", "doctoral"],
        "masters": ["masters", "ms", "ma", "mba"],
        "bachelors": ["bachelors", "bs", "ba", "undergraduate"],
        "associate": ["associate", "aa", "as"]
    }
    
    for level, indicators in education_indicators.items():
        for indicator in indicators:
            if indicator in text_lower:
                metadata["education_level"] = level
                break
    
    # Extract location preferences
    location_patterns = [
        r"location[:\s]+([^,\n]+)",
        r"based in ([^,\n]+)",
        r"willing to relocate to ([^,\n]+)",
        r"prefer ([^,\n]+) area"
    ]
    
    for pattern in location_patterns:
        matches = re.findall(pattern, text_lower)
        if matches:
            metadata["location_preferences"].extend(matches)
    
    # Extract industry preferences
    industry_keywords = [
        "tech", "software", "finance", "healthcare", "e-commerce", "ai", "machine learning",
        "data science", "cybersecurity", "cloud", "mobile", "web", "gaming", "automotive"
    ]
    
    for keyword in industry_keywords:
        if keyword in text_lower:
            metadata["industry_preferences"].append(keyword)
    
    # Check for remote preferences
    remote_indicators = ["remote", "work from home", "wfh", "virtual", "online"]
    for indicator in remote_indicators:
        if indicator in text_lower:
            metadata["remote_preference"] = True
            break
    
    # Check for relocation willingness
    relocation_indicators = ["willing to relocate", "open to relocation", "can relocate"]
    for indicator in relocation_indicators:
        if indicator in text_lower:
            metadata["relocation_willingness"] = True
            break
    
    # Extract graduation year
    year_pattern = r"(20\d{2})"
    year_matches = re.findall(year_pattern, text_lower)
    if year_matches:
        metadata["graduation_year"] = max(year_matches)  # Take the latest year
    
    # Extract GPA if mentioned
    gpa_pattern = r"gpa[:\s]*(\d+\.\d+)"
    gpa_matches = re.findall(gpa_pattern, text_lower)
    if gpa_matches:
        metadata["gpa"] = float(gpa_matches[0])
    
    # Extract citizenship/visa status
    citizenship_indicators = {
        "us_citizen": ["us citizen", "american citizen", "citizen"],
        "permanent_resident": ["permanent resident", "green card"],
        "international": ["international student", "f1 visa", "h1b", "visa sponsorship"]
    }
    
    for status, indicators in citizenship_indicators.items():
        for indicator in indicators:
            if indicator in text_lower:
                metadata["citizenship"] = status
                break
    
    return metadata

def extract_job_metadata(job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract metadata from job posting including location, experience requirements, etc.
    """
    metadata = {
        "location": "",
        "experience_level": "entry",
        "education_required": "bachelors",
        "remote_option": False,
        "relocation_assistance": False,
        "industry": "",
        "company_size": "unknown",
        "salary_range": "",
        "citizenship_requirement": "any",
        "start_date": "",
        "duration": ""
    }
    
    title = job.get("title", "").lower()
    description = job.get("description", "").lower()
    company = job.get("company", "").lower()
    
    # Extract location
    location_patterns = [
        r"location[:\s]+([^,\n]+)",
        r"based in ([^,\n]+)",
        r"([^,\n]+), ([A-Z]{2})",  # City, State format
        r"remote", r"virtual", r"work from home"
    ]
    
    for pattern in location_patterns:
        matches = re.findall(pattern, description)
        if matches:
            if "remote" in pattern or "virtual" in pattern or "work from home" in pattern:
                metadata["remote_option"] = True
            else:
                metadata["location"] = matches[0] if isinstance(matches[0], str) else " ".join(matches[0])
            break
    
    # Determine experience level from title and description
    senior_indicators = ["senior", "lead", "principal", "staff", "architect", "manager"]
    mid_indicators = ["mid-level", "intermediate", "3+ years", "5+ years"]
    junior_indicators = ["junior", "entry-level", "0-2 years", "recent graduate"]
    intern_indicators = ["intern", "internship", "co-op", "student"]
    
    for indicator in senior_indicators:
        if indicator in title or indicator in description:
            metadata["experience_level"] = "senior"
            break
    else:
        for indicator in mid_indicators:
            if indicator in title or indicator in description:
                metadata["experience_level"] = "mid"
                break
        else:
            for indicator in junior_indicators:
                if indicator in title or indicator in description:
                    metadata["experience_level"] = "junior"
                    break
            else:
                for indicator in intern_indicators:
                    if indicator in title or indicator in description:
                        metadata["experience_level"] = "intern"
                        break
    
    # Extract education requirements
    education_patterns = {
        "phd": ["phd", "doctorate", "doctoral"],
        "masters": ["masters", "ms", "ma", "mba"],
        "bachelors": ["bachelors", "bs", "ba", "degree"],
        "high_school": ["high school", "diploma"]
    }
    
    for level, indicators in education_patterns.items():
        for indicator in indicators:
            if indicator in description:
                metadata["education_required"] = level
                break
    
    # Extract industry
    industry_keywords = {
        "tech": ["software", "technology", "tech", "programming"],
        "finance": ["finance", "banking", "investment", "trading"],
        "healthcare": ["healthcare", "medical", "pharmaceutical"],
        "e-commerce": ["e-commerce", "retail", "shopping"],
        "ai": ["ai", "artificial intelligence", "machine learning"],
        "data": ["data science", "analytics", "big data"],
        "cybersecurity": ["security", "cybersecurity", "infosec"],
        "cloud": ["cloud", "aws", "azure", "gcp"],
        "mobile": ["mobile", "ios", "android", "app"],
        "web": ["web", "frontend", "backend", "full-stack"]
    }
    
    for industry, keywords in industry_keywords.items():
        for keyword in keywords:
            if keyword in title or keyword in description:
                metadata["industry"] = industry
                break
    
    # Check for relocation assistance
    relocation_indicators = ["relocation assistance", "relocation package", "help with relocation"]
    for indicator in relocation_indicators:
        if indicator in description:
            metadata["relocation_assistance"] = True
            break
    
    # Extract citizenship requirements
    citizenship_patterns = {
        "us_citizen": ["us citizen", "american citizen", "citizenship required"],
        "permanent_resident": ["permanent resident", "green card"],
        "any": ["any", "all", "international welcome"]
    }
    
    for requirement, indicators in citizenship_patterns.items():
        for indicator in indicators:
            if indicator in description:
                metadata["citizenship_requirement"] = requirement
                break
    
    # Extract start date and duration
    date_patterns = [
        r"summer (\d{4})",
        r"fall (\d{4})",
        r"spring (\d{4})",
        r"(\d{1,2}) months",
        r"(\d{1,2}) weeks"
    ]
    
    for pattern in date_patterns:
        matches = re.findall(pattern, description)
        if matches:
            if "summer" in pattern or "fall" in pattern or "spring" in pattern:
                metadata["start_date"] = matches[0]
            else:
                metadata["duration"] = f"{matches[0]} months" if "months" in pattern else f"{matches[0]} weeks"
    
    return metadata

def calculate_metadata_match_score(resume_metadata: Dict[str, Any], job_metadata: Dict[str, Any]) -> Tuple[int, str]:
    """
    Calculate a match score based on metadata compatibility.
    Returns: (score, description)
    """
    score = 0
    descriptions = []
    
    # Experience level matching (40% weight)
    experience_compatibility = {
        "student": {"intern": 100, "junior": 80, "mid": 40, "senior": 0},
        "junior": {"intern": 60, "junior": 100, "mid": 80, "senior": 40},
        "mid": {"intern": 20, "junior": 60, "mid": 100, "senior": 80},
        "senior": {"intern": 0, "junior": 20, "mid": 60, "senior": 100}
    }
    
    resume_exp = resume_metadata.get("experience_level", "student")
    job_exp = job_metadata.get("experience_level", "intern")
    
    exp_score = experience_compatibility.get(resume_exp, {}).get(job_exp, 50)
    score += exp_score * 0.4
    
    if exp_score >= 80:
        descriptions.append("✅ Experience level matches well")
    elif exp_score >= 60:
        descriptions.append("⚠️ Experience level is acceptable")
    elif exp_score >= 40:
        descriptions.append("⚠️ Experience level may be challenging")
    else:
        descriptions.append("❌ Experience level mismatch")
    
    # Location matching (25% weight)
    location_score = 0
    resume_locations = resume_metadata.get("location_preferences", [])
    job_location = job_metadata.get("location", "")
    job_remote = job_metadata.get("remote_option", False)
    resume_remote = resume_metadata.get("remote_preference", False)
    
    if job_remote and resume_remote:
        location_score = 100
        descriptions.append("✅ Remote work preference matches")
    elif job_remote:
        location_score = 80
        descriptions.append("✅ Job offers remote option")
    elif resume_remote:
        location_score = 60
        descriptions.append("⚠️ You prefer remote but job is on-site")
    elif resume_locations and job_location:
        # Check if any resume location matches job location
        for resume_loc in resume_locations:
            if resume_loc.lower() in job_location.lower() or job_location.lower() in resume_loc.lower():
                location_score = 100
                descriptions.append("✅ Location preference matches")
                break
        else:
            location_score = 50
            descriptions.append("⚠️ Location preferences don't match")
    else:
        location_score = 70  # Neutral score when location info is missing
        descriptions.append("ℹ️ Location compatibility unclear")
    
    score += location_score * 0.25
    
    # Industry matching (20% weight)
    industry_score = 0
    resume_industries = resume_metadata.get("industry_preferences", [])
    job_industry = job_metadata.get("industry", "")
    
    if resume_industries and job_industry:
        for resume_industry in resume_industries:
            if resume_industry.lower() in job_industry.lower() or job_industry.lower() in resume_industry.lower():
                industry_score = 100
                descriptions.append("✅ Industry preference matches")
                break
        else:
            industry_score = 60
            descriptions.append("⚠️ Industry preferences don't match")
    else:
        industry_score = 70  # Neutral score when industry info is missing
        descriptions.append("ℹ️ Industry compatibility unclear")
    
    score += industry_score * 0.20
    
    # Citizenship/visa matching (15% weight)
    citizenship_score = 0
    resume_citizenship = resume_metadata.get("citizenship", "unknown")
    job_citizenship = job_metadata.get("citizenship_requirement", "any")
    
    citizenship_compatibility = {
        "us_citizen": {"us_citizen": 100, "permanent_resident": 100, "any": 100},
        "permanent_resident": {"us_citizen": 80, "permanent_resident": 100, "any": 100},
        "international": {"us_citizen": 0, "permanent_resident": 0, "any": 100}
    }
    
    citizenship_score = citizenship_compatibility.get(resume_citizenship, {}).get(job_citizenship, 70)
    score += citizenship_score * 0.15
    
    if citizenship_score >= 80:
        descriptions.append("✅ Citizenship/visa requirements compatible")
    elif citizenship_score >= 60:
        descriptions.append("⚠️ Citizenship/visa requirements may be challenging")
    else:
        descriptions.append("❌ Citizenship/visa requirements incompatible")
    
    final_score = round(score)
    
    return final_score, "\n".join(descriptions)

def combine_match_scores(skill_score: int, metadata_score: int, skill_weight: float = 0.7, metadata_weight: float = 0.3) -> int:
    """
    Combine skill matching score with metadata matching score.
    Default weights: 70% skills, 30% metadata
    """
    combined_score = (skill_score * skill_weight) + (metadata_score * metadata_weight)
    return round(combined_score) 