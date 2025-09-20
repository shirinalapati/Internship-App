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
  const [jobs] = useState<Job[]>([]);
  const [error, setError] = useState<string>('');
  const [isLoading, setIsLoading] = useState(false);
  const [hasResults, setHasResults] = useState(false);

  const handleFileUpload = async (file: File) => {
    setIsLoading(true);
    setError('');
    setHasResults(false);

    try {
      const formData = new FormData();
      formData.append('resume', file);

      await axios.post('/match', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        timeout: 60000, // 60 second timeout
      });

      // Since the backend returns HTML, we need to handle this differently
      // For now, we'll redirect to maintain compatibility with the existing backend
      window.location.href = '/match';
      
    } catch (err: any) {
      setError(err.response?.data?.detail || 'An error occurred while processing your resume.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="container">
      <Header user={user} />
      
      <ResumeUploadForm onSubmit={handleFileUpload} isLoading={isLoading} />
      
      <LoadingSpinner show={isLoading} />
      
      {error && <ErrorMessage error={error} />}
      
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
              <JobCard key={index} job={job} />
            ))
          )}
        </div>
      )}
    </div>
  );
};

export default HomePage;