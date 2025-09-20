import React from 'react';

interface LoadingSpinnerProps {
  show: boolean;
}

const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({ show }) => {
  if (!show) return null;

  return (
    <div className="loading show">
      <div className="spinner"></div>
      <p>Analyzing your resume and finding the best matches...</p>
      <p><small>This may take up to 30 seconds</small></p>
    </div>
  );
};

export default LoadingSpinner;