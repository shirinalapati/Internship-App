import React from 'react';

interface ErrorMessageProps {
  error: string;
}

const ErrorMessage: React.FC<ErrorMessageProps> = ({ error }) => {
  return (
    <div className="error-message">
      <i className="fas fa-exclamation-triangle"></i>
      <h3>Upload Error</h3>
      <p>{error}</p>
    </div>
  );
};

export default ErrorMessage;