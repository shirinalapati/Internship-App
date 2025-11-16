"""
Job Database Module - SQLAlchemy-based persistent storage for job data
Provides deduplication, historical tracking, and efficient querying
"""
import os
import hashlib
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.sql import func

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./jobs.db")
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Job(Base):
    """Job model for storing internship listings"""
    __tablename__ = "jobs"
    
    id = Column(Integer, primary_key=True, index=True)
    job_hash = Column(String(64), unique=True, index=True, nullable=False)
    company = Column(String(255), nullable=False, index=True)
    title = Column(String(500), nullable=False, index=True)
    location = Column(String(255), nullable=False)
    apply_link = Column(Text, nullable=False)
    description = Column(Text)
    required_skills = Column(Text)  # JSON string
    job_requirements = Column(Text)
    source = Column(String(100), default='github_internships')
    job_metadata = Column(Text)  # JSON string for additional data
    
    # Timestamps
    first_seen = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    
    # Add composite indexes for common queries
    __table_args__ = (
        Index('idx_company_title', 'company', 'title'),
        Index('idx_active_seen', 'is_active', 'last_seen'),
        Index('idx_source_active', 'source', 'is_active'),
    )

class CacheMetadata(Base):
    """Metadata for tracking cache operations"""
    __tablename__ = "cache_metadata"
    
    id = Column(Integer, primary_key=True, index=True)
    cache_type = Column(String(100), nullable=False, index=True)  # 'daily', 'weekly', 'full'
    last_updated = Column(DateTime, default=datetime.utcnow, nullable=False)
    job_count = Column(Integer, default=0)
    new_jobs_added = Column(Integer, default=0)
    status = Column(String(50), default='success')  # 'success', 'partial', 'failed'
    cache_metadata = Column(Text)  # JSON string for additional info

# Database initialization
def init_database():
    """Initialize database tables"""
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Database initialized successfully")
        return True
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return False

def get_db() -> Session:
    """Get database session"""
    db = SessionLocal()
    try:
        return db
    finally:
        pass  # Don't close here, let caller handle

def close_db(db: Session):
    """Close database session"""
    db.close()

def generate_job_hash(company: str, title: str, location: str, apply_link: str) -> str:
    """
    Generate unique hash for job deduplication
    Uses company + title + location + domain from apply_link
    """
    # Extract domain from apply_link for more stable hashing
    try:
        from urllib.parse import urlparse
        domain = urlparse(apply_link).netloc
    except:
        domain = apply_link[:50]  # Fallback
    
    # Create normalized string for hashing
    hash_string = f"{company.lower().strip()}|{title.lower().strip()}|{location.lower().strip()}|{domain.lower()}"
    
    # Generate SHA-256 hash
    return hashlib.sha256(hash_string.encode('utf-8')).hexdigest()

def mark_old_jobs_inactive(max_days_old: int = 30, db: Session = None) -> int:
    """
    Mark jobs as inactive if their posting date is older than max_days_old.
    This ensures old jobs don't persist even if they're still in the GitHub repo.

    Args:
        max_days_old: Maximum age in days for a job to remain active (default: 30)
        db: Database session (optional)

    Returns:
        Number of jobs marked inactive
    """
    if db is None:
        db = get_db()
        should_close = True
    else:
        should_close = False

    try:
        # Get all active jobs
        active_jobs = db.query(Job).filter(Job.is_active == True).all()

        inactive_count = 0
        for job in active_jobs:
            try:
                # Parse metadata to get days_since_posted
                if job.job_metadata:
                    metadata = json.loads(job.job_metadata)
                    days_since_posted = metadata.get('days_since_posted')

                    # Mark inactive if posting date is too old
                    if days_since_posted is not None and days_since_posted > max_days_old:
                        job.is_active = False
                        inactive_count += 1
            except (json.JSONDecodeError, TypeError):
                # Skip jobs with invalid metadata
                continue

        if inactive_count > 0:
            print(f"📅 Marked {inactive_count} jobs inactive based on posting date (>{max_days_old} days old)")

        return inactive_count

    except Exception as e:
        print(f"❌ Error marking old jobs inactive: {e}")
        return 0
    finally:
        if should_close:
            close_db(db)

def bulk_insert_jobs(jobs: List[Dict], db: Session = None) -> Dict:
    """
    Bulk insert jobs with deduplication
    Returns summary of operations
    """
    if db is None:
        db = get_db()
        should_close = True
    else:
        should_close = False
    
    try:
        new_jobs = 0
        updated_jobs = 0
        existing_hashes = set()
        
        # Get existing job hashes for deduplication
        existing_jobs = db.query(Job.job_hash).all()
        existing_hashes = {job.job_hash for job in existing_jobs}
        
        jobs_to_add = []
        jobs_to_update = {}  # Change to dict to store job_hash -> job_data mapping

        for job_data in jobs:
            # Generate hash for this job
            job_hash = generate_job_hash(
                job_data.get('company', ''),
                job_data.get('title', ''),
                job_data.get('location', ''),
                job_data.get('apply_link', '')
            )

            if job_hash not in existing_hashes:
                # New job - store date information in metadata
                metadata = job_data.get('metadata', {})
                # Add date information to metadata for tracking
                metadata['days_since_posted'] = job_data.get('days_since_posted')
                metadata['date_posted'] = job_data.get('date_posted')
                metadata['date_posted_raw'] = job_data.get('date_posted_raw')

                job = Job(
                    job_hash=job_hash,
                    company=job_data.get('company', ''),
                    title=job_data.get('title', ''),
                    location=job_data.get('location', ''),
                    apply_link=job_data.get('apply_link', ''),
                    description=job_data.get('description', ''),
                    required_skills=json.dumps(job_data.get('required_skills', [])),
                    job_requirements=job_data.get('job_requirements', ''),
                    source=job_data.get('source', 'github_internships'),
                    job_metadata=json.dumps(metadata)
                )
                jobs_to_add.append(job)
                new_jobs += 1
            else:
                # Existing job - store for updating with fresh metadata
                jobs_to_update[job_hash] = job_data
                updated_jobs += 1
        
        # Bulk insert new jobs
        if jobs_to_add:
            db.bulk_save_objects(jobs_to_add)

        # Update existing jobs with fresh metadata and last_seen
        # IMPORTANT: This updates the days_since_posted so old jobs get marked correctly
        if jobs_to_update:
            for job_hash, job_data in jobs_to_update.items():
                # Prepare fresh metadata with updated posting date
                metadata = job_data.get('metadata', {})
                metadata['days_since_posted'] = job_data.get('days_since_posted')
                metadata['date_posted'] = job_data.get('date_posted')
                metadata['date_posted_raw'] = job_data.get('date_posted_raw')

                # Update both last_seen AND metadata
                db.query(Job).filter(Job.job_hash == job_hash).update(
                    {
                        Job.last_seen: datetime.utcnow(),
                        Job.job_metadata: json.dumps(metadata)
                    },
                    synchronize_session=False
                )
        
        # Mark jobs not seen in this scrape as inactive (older than 3 days)
        cutoff_date = datetime.utcnow() - timedelta(days=3)
        inactive_count = db.query(Job).filter(
            Job.last_seen < cutoff_date,
            Job.is_active == True
        ).update(
            {Job.is_active: False},
            synchronize_session=False
        )

        # IMPORTANT: Also mark jobs inactive based on posting date (>30 days old)
        # This ensures old jobs don't persist even if they're still in the GitHub repo
        date_based_inactive_count = mark_old_jobs_inactive(max_days_old=30, db=db)

        db.commit()
        
        summary = {
            'new_jobs': new_jobs,
            'updated_jobs': updated_jobs,
            'inactive_jobs': inactive_count,
            'date_based_inactive_jobs': date_based_inactive_count,
            'total_processed': len(jobs)
        }

        total_inactive = inactive_count + date_based_inactive_count
        print(f"✅ Database operation: {new_jobs} new, {updated_jobs} updated, {total_inactive} marked inactive ({inactive_count} by last_seen, {date_based_inactive_count} by posting date)")
        return summary
        
    except Exception as e:
        db.rollback()
        print(f"❌ Database error during bulk insert: {e}")
        return {'error': str(e)}
    finally:
        if should_close:
            close_db(db)

def get_active_jobs(limit: Optional[int] = None, offset: int = 0, max_days_old: int = 30) -> List[Dict]:
    """
    Get active jobs from database, filtered by posting date.

    Args:
        limit: Maximum number of jobs to return
        offset: Number of jobs to skip
        max_days_old: Maximum age in days for jobs to include (default: 30)

    Returns:
        List of job dictionaries
    """
    db = get_db()
    try:
        query = db.query(Job).filter(Job.is_active == True).order_by(Job.last_seen.desc())

        if limit:
            query = query.offset(offset).limit(limit)

        jobs = query.all()

        result = []
        filtered_count = 0
        for job in jobs:
            # Parse metadata to check posting date
            try:
                metadata = json.loads(job.job_metadata) if job.job_metadata else {}
                days_since_posted = metadata.get('days_since_posted')

                # Filter out jobs older than max_days_old
                if days_since_posted is not None and days_since_posted > max_days_old:
                    filtered_count += 1
                    continue  # Skip this job

            except (json.JSONDecodeError, TypeError):
                # If metadata is invalid, include the job (better to show than hide)
                pass

            job_dict = {
                'id': job.id,
                'company': job.company,
                'title': job.title,
                'location': job.location,
                'apply_link': job.apply_link,
                'description': job.description,
                'required_skills': json.loads(job.required_skills) if job.required_skills else [],
                'job_requirements': job.job_requirements,
                'source': job.source,
                'metadata': metadata if 'metadata' in locals() else {},
                'first_seen': job.first_seen,
                'last_seen': job.last_seen
            }
            result.append(job_dict)

        if filtered_count > 0:
            print(f"🔍 Filtered out {filtered_count} jobs older than {max_days_old} days from cache")

        return result
        
    except Exception as e:
        print(f"❌ Error getting active jobs: {e}")
        return []
    finally:
        close_db(db)

def get_new_jobs_since(hours: int = 24, max_days_old: int = 30) -> List[Dict]:
    """
    Get jobs added in the last N hours, filtered by posting date.

    Args:
        hours: Get jobs added within the last N hours
        max_days_old: Maximum age in days for jobs to include (default: 30)

    Returns:
        List of job dictionaries
    """
    db = get_db()
    try:
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)

        jobs = db.query(Job).filter(
            Job.first_seen >= cutoff_time,
            Job.is_active == True
        ).order_by(Job.first_seen.desc()).all()

        result = []
        filtered_count = 0
        for job in jobs:
            # Parse metadata to check posting date
            try:
                metadata = json.loads(job.job_metadata) if job.job_metadata else {}
                days_since_posted = metadata.get('days_since_posted')

                # Filter out jobs older than max_days_old
                if days_since_posted is not None and days_since_posted > max_days_old:
                    filtered_count += 1
                    continue  # Skip this job

            except (json.JSONDecodeError, TypeError):
                # If metadata is invalid, include the job
                pass

            job_dict = {
                'id': job.id,
                'company': job.company,
                'title': job.title,
                'location': job.location,
                'apply_link': job.apply_link,
                'description': job.description,
                'required_skills': json.loads(job.required_skills) if job.required_skills else [],
                'job_requirements': job.job_requirements,
                'source': job.source,
                'metadata': metadata if 'metadata' in locals() else {},
                'first_seen': job.first_seen,
                'last_seen': job.last_seen
            }
            result.append(job_dict)

        if filtered_count > 0:
            print(f"🔍 Filtered out {filtered_count} jobs older than {max_days_old} days from new jobs")

        return result
        
    except Exception as e:
        print(f"❌ Error getting new jobs: {e}")
        return []
    finally:
        close_db(db)

def get_database_stats() -> Dict:
    """Get database statistics"""
    db = get_db()
    try:
        total_jobs = db.query(func.count(Job.id)).scalar()
        active_jobs = db.query(func.count(Job.id)).filter(Job.is_active == True).scalar()
        
        # Jobs by source
        sources = db.query(Job.source, func.count(Job.id)).filter(
            Job.is_active == True
        ).group_by(Job.source).all()
        
        # Recent activity
        last_24h = datetime.utcnow() - timedelta(hours=24)
        new_last_24h = db.query(func.count(Job.id)).filter(
            Job.first_seen >= last_24h
        ).scalar()
        
        # Latest cache operation
        latest_cache = db.query(CacheMetadata).order_by(
            CacheMetadata.last_updated.desc()
        ).first()
        
        return {
            'total_jobs': total_jobs,
            'active_jobs': active_jobs,
            'inactive_jobs': total_jobs - active_jobs,
            'sources': dict(sources),
            'new_jobs_24h': new_last_24h,
            'latest_cache': {
                'type': latest_cache.cache_type if latest_cache else None,
                'updated': latest_cache.last_updated if latest_cache else None,
                'job_count': latest_cache.job_count if latest_cache else 0
            }
        }
        
    except Exception as e:
        print(f"❌ Error getting database stats: {e}")
        return {}
    finally:
        close_db(db)

def record_cache_operation(cache_type: str, job_count: int, new_jobs: int, status: str = 'success', metadata: Dict = None):
    """Record cache operation metadata"""
    db = get_db()
    try:
        cache_record = CacheMetadata(
            cache_type=cache_type,
            job_count=job_count,
            new_jobs_added=new_jobs,
            status=status,
            cache_metadata=json.dumps(metadata or {})
        )
        
        db.add(cache_record)
        db.commit()
        
        print(f"✅ Cache operation recorded: {cache_type} - {new_jobs} new jobs")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error recording cache operation: {e}")
    finally:
        close_db(db)

def cleanup_old_metadata(days: int = 30):
    """Clean up old cache metadata entries"""
    db = get_db()
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        deleted = db.query(CacheMetadata).filter(
            CacheMetadata.last_updated < cutoff_date
        ).delete()
        
        db.commit()
        print(f"✅ Cleaned up {deleted} old cache metadata entries")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error cleaning up metadata: {e}")
    finally:
        close_db(db)

# Initialize database on import
if __name__ == "__main__":
    init_database()
    stats = get_database_stats()
    print(f"Database stats: {stats}")