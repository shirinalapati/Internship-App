import React from 'react';
import { Job } from '../types';

interface JobCardProps {
  job: Job;
  isNewResult?: boolean;
}

const JobCard: React.FC<JobCardProps> = ({ job, isNewResult = false }) => {
  const getMatchScoreClass = (score: number) => {
    if (score >= 70) return 'high-score';
    if (score >= 40) return 'medium-score';
    return 'low-score';
  };

  const getMatchScoreLabel = (score: number) => {
    if (score >= 80) return 'excellent';
    if (score >= 60) return 'good';
    if (score >= 40) return 'moderate';
    return 'weak';
  };

  return (
    <div className={`job-card ${isNewResult ? 'new-result job-streaming' : ''}`}>
      <div className="job-header">
        <div>
          <h3 className="job-title">{job.title}</h3>
          <div className="job-company">{job.company}</div>
          <div className="job-location">
            <i className="fas fa-map-marker-alt"></i> {job.location}
          </div>
        </div>
        <div className={`match-score ${getMatchScoreClass(job.match_score || job.score || 0)}`}>
          {job.match_score || job.score || 0}% Match
        </div>
      </div>
      
      {job.description && (
        <div className="job-description">
          {job.description}
        </div>
      )}
      
      <div className="match-analysis">
        <h4><i className="fas fa-chart-line"></i> Match Analysis</h4>
        <div 
          className="match-details" 
          dangerouslySetInnerHTML={{ __html: job.match_description }}
        />
      </div>
      
      {(job.apply_link || job.url) && (
        <a 
          href={job.apply_link || job.url} 
          target="_blank" 
          rel="noopener noreferrer" 
          className="apply-btn"
        >
          <i className="fas fa-external-link-alt"></i> Apply Now
        </a>
      )}
    </div>
  );
};

export default JobCard;