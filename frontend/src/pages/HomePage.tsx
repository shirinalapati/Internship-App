import React, { useState } from 'react';
import axios from 'axios';
import Header from '../components/Header';
import ResumeUploadForm from '../components/ResumeUploadForm';
import LoadingSpinner from '../components/LoadingSpinner';
import ErrorMessage from '../components/ErrorMessage';
import JobCard from '../components/JobCard';
import { Job, User } from '../types';

interface HomePageProps {
  user?: User;
}

const HomePage: React.FC<HomePageProps> = ({ user }) => {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState<string>('');
  const [isLoading, setIsLoading] = useState(false);
  const [hasResults, setHasResults] = useState(false);
  const [skillsFound, setSkillsFound] = useState<string[]>([]);
  const [progress, setProgress] = useState(0);
  const [currentStep, setCurrentStep] = useState('');
  const [useStreaming, setUseStreaming] = useState(true);

  const handleFileUploadStreaming = async (file: File) => {
    setIsLoading(true);
    setError('');
    setHasResults(false);
    setJobs([]);
    setSkillsFound([]);
    setProgress(0);
    setCurrentStep('Starting...');

    try {
      const formData = new FormData();
      formData.append('resume', file);

      const response = await fetch('/api/match-stream', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('No response body');
      }

      const decoder = new TextDecoder();
      const processedJobs: Job[] = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              
              if (data.error) {
                setError(data.error);
                setIsLoading(false);
                return;
              }

              if (data.progress) {
                setProgress(data.progress);
              }

              if (data.message) {
                setCurrentStep(data.message);
              }

              if (data.skills) {
                setSkillsFound(data.skills);
              }

              if (data.job_result) {
                processedJobs.push(data.job_result);
                // Sort jobs by match score and update display
                const sortedJobs = [...processedJobs].sort((a, b) => (b.match_score || 0) - (a.match_score || 0));
                setJobs(sortedJobs);
                setHasResults(true);
              }

              if (data.complete) {
                setCurrentStep('Complete!');
                setProgress(100);
                setIsLoading(false);
                
                if (data.final_results) {
                  setJobs(data.final_results);
                }
                
                if (data.matches_found === 0) {
                  setError('No matching opportunities found for your skills.');
                }
                break;
              }
            } catch (parseError) {
              console.error('Error parsing SSE data:', parseError);
            }
          }
        }
      }
    } catch (err: any) {
      console.error('Streaming error:', err);
      setError(err.message || 'An error occurred while processing your resume.');
      setIsLoading(false);
    }
  };

  const handleFileUpload = async (file: File) => {
    if (useStreaming) {
      return handleFileUploadStreaming(file);
    }

    // Fallback to original method
    setIsLoading(true);
    setError('');
    setHasResults(false);
    setJobs([]);
    setSkillsFound([]);

    try {
      const formData = new FormData();
      formData.append('resume', file);

      const response = await axios.post('/api/match', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        timeout: 120000, // 120 second timeout (2 minutes)
      });

      const data = response.data;
      
      if (data.success) {
        setJobs(data.jobs || []);
        setSkillsFound(data.skills_found || []);
        setHasResults(true);
        
        if (data.jobs && data.jobs.length === 0) {
          setError(data.message || 'No matching opportunities found.');
        }
      } else {
        setError(data.message || 'An error occurred while processing your resume.');
      }
      
    } catch (err: any) {
      console.error('Upload error:', err);
      setError(err.response?.data?.detail || err.message || 'An error occurred while processing your resume.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="container">
      <Header user={user} />
      
      <div className="upload-options">
        <div className="streaming-toggle">
          <label>
            <input
              type="checkbox"
              checked={useStreaming}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setUseStreaming(e.target.checked)}
            />
            <span>Real-time progress updates</span>
          </label>
        </div>
      </div>
      
      <ResumeUploadForm onSubmit={handleFileUpload} isLoading={isLoading} />
      
      {isLoading && (
        <div className="progress-section">
          <div className="progress-container">
            <div className="progress-bar">
              <div 
                className="progress-fill" 
                style={{ width: `${progress}%` }}
              ></div>
            </div>
            <div className="progress-text">
              {progress}% - {currentStep}
            </div>
          </div>
        </div>
      )}
      
      <LoadingSpinner show={isLoading && !useStreaming} />
      
      {error && <ErrorMessage error={error} />}
      
      {skillsFound.length > 0 && (
        <div className="skills-section">
          <h3>🎯 Skills Detected in Your Resume:</h3>
          <div className="skills-list">
            {skillsFound.map((skill, index) => (
              <span key={index} className="skill-tag">{skill}</span>
            ))}
          </div>
        </div>
      )}
      
      {hasResults && (
        <div className="results-section">
          <h2 className="results-title">
            <i className="fas fa-bullseye"></i> 
            {jobs.length > 0 ? `Found ${jobs.length} Matching Opportunities` : 'No Matches Found'}
          </h2>
          
          {jobs.length === 0 ? (
            <div className="error-message">
              <i className="fas fa-search"></i>
              <h3>No Matching Internships</h3>
              <p>We couldn't find any internships that match your skills. Try updating your resume with more technical skills or check back later for new opportunities.</p>
            </div>
          ) : (
            jobs.map((job, index) => (
              <JobCard 
                key={`${job.company}-${job.title}-${index}`} 
                job={job} 
                isNewResult={isLoading && useStreaming}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
};

export default HomePage;