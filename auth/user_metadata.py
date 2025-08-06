import json
import os
from datetime import datetime
from typing import Optional, Dict, Any

class UserMetadataStore:
    """Store and retrieve user metadata for Google OAuth users"""
    
    def __init__(self, storage_file: str = "user_metadata.json"):
        self.storage_file = storage_file
        self._ensure_storage_file()
    
    def _ensure_storage_file(self):
        """Ensure the storage file exists"""
        if not os.path.exists(self.storage_file):
            with open(self.storage_file, 'w') as f:
                json.dump({}, f)
    
    def _load_data(self) -> Dict[str, Any]:
        """Load user data from storage file"""
        try:
            with open(self.storage_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
    
    def _save_data(self, data: Dict[str, Any]):
        """Save user data to storage file"""
        with open(self.storage_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def store_user_metadata(self, user_id: str, user_info: Dict[str, Any]) -> bool:
        """Store user metadata from Google OAuth"""
        try:
            data = self._load_data()
            
            # Store user information
            data[user_id] = {
                "user_id": user_id,
                "email": user_info.get("email"),
                "name": user_info.get("name"),
                "picture": user_info.get("picture"),
                "provider": "google",
                "first_login": datetime.now().isoformat(),
                "last_login": datetime.now().isoformat(),
                "login_count": 1,
                "resume_uploads": [],
                "job_matches": []
            }
            
            self._save_data(data)
            print(f"✅ Stored metadata for user: {user_info.get('email', user_id)}")
            return True
            
        except Exception as e:
            print(f"❌ Error storing user metadata: {e}")
            return False
    
    def update_user_login(self, user_id: str) -> bool:
        """Update user's last login time"""
        try:
            data = self._load_data()
            
            if user_id in data:
                data[user_id]["last_login"] = datetime.now().isoformat()
                data[user_id]["login_count"] = data[user_id].get("login_count", 0) + 1
                self._save_data(data)
                return True
            
            return False
            
        except Exception as e:
            print(f"❌ Error updating user login: {e}")
            return False
    
    def get_user_metadata(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user metadata by user ID"""
        try:
            data = self._load_data()
            return data.get(user_id)
        except Exception as e:
            print(f"❌ Error getting user metadata: {e}")
            return None
    
    def add_resume_upload(self, user_id: str, resume_info: Dict[str, Any]) -> bool:
        """Add resume upload record to user metadata"""
        try:
            data = self._load_data()
            
            if user_id in data:
                if "resume_uploads" not in data[user_id]:
                    data[user_id]["resume_uploads"] = []
                
                # Extract enhanced metadata if available
                resume_metadata = {}
                if "metadata" in resume_info:
                    resume_metadata = resume_info["metadata"]
                
                resume_record = {
                    "timestamp": datetime.now().isoformat(),
                    "filename": resume_info.get("filename"),
                    "skills_extracted": resume_info.get("skills", []),
                    "file_size": resume_info.get("file_size"),
                    "metadata": {
                        "experience_level": resume_metadata.get("experience_level", "student"),
                        "education_level": resume_metadata.get("education_level", "undergraduate"),
                        "location_preferences": resume_metadata.get("location_preferences", []),
                        "industry_preferences": resume_metadata.get("industry_preferences", []),
                        "remote_preference": resume_metadata.get("remote_preference", False),
                        "relocation_willingness": resume_metadata.get("relocation_willingness", False),
                        "graduation_year": resume_metadata.get("graduation_year"),
                        "gpa": resume_metadata.get("gpa"),
                        "citizenship": resume_metadata.get("citizenship", "unknown")
                    }
                }
                
                data[user_id]["resume_uploads"].append(resume_record)
                self._save_data(data)
                return True
            
            return False
            
        except Exception as e:
            print(f"❌ Error adding resume upload: {e}")
            return False
    
    def add_job_match(self, user_id: str, job_match: Dict[str, Any]) -> bool:
        """Add job match record to user metadata"""
        try:
            data = self._load_data()
            
            if user_id in data:
                if "job_matches" not in data[user_id]:
                    data[user_id]["job_matches"] = []
                
                match_record = {
                    "timestamp": datetime.now().isoformat(),
                    "job_title": job_match.get("title"),
                    "company": job_match.get("company"),
                    "match_score": job_match.get("score"),
                    "skills_matched": job_match.get("skills_matched", [])
                }
                
                data[user_id]["job_matches"].append(match_record)
                self._save_data(data)
                return True
            
            return False
            
        except Exception as e:
            print(f"❌ Error adding job match: {e}")
            return False

# Global instance
user_metadata_store = UserMetadataStore() 