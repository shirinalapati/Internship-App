import React, { useState, useRef } from 'react';

interface ResumeUploadFormProps {
  onSubmit: (file: File) => void;
  isLoading: boolean;
}

const ResumeUploadForm: React.FC<ResumeUploadFormProps> = ({ onSubmit, isLoading }) => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (selectedFile && !isLoading) {
      onSubmit(selectedFile);
    }
  };

  return (
    <div className="upload-section">
      <h1>🚀 Find Your Perfect Internship</h1>
      <p className="subtitle">Upload your resume and let AI match you with the best internship opportunities</p>
      
      <form className="upload-form" onSubmit={handleSubmit}>
        <label htmlFor="resume" className="file-input-wrapper">
          <input
            type="file"
            id="resume"
            ref={fileInputRef}
            className="file-input"
            accept=".pdf,.png,.jpg,.jpeg"
            onChange={handleFileChange}
            required
          />
          <i className="fas fa-upload"></i> 
          {selectedFile ? selectedFile.name : 'Choose Resume File'}
        </label>
        
        <button 
          type="submit" 
          className="upload-btn" 
          disabled={!selectedFile || isLoading}
        >
          {isLoading ? (
            <>
              <i className="fas fa-spinner fa-spin"></i> Processing...
            </>
          ) : (
            <>
              <i className="fas fa-search"></i> Find Matches
            </>
          )}
        </button>
        
        <div className="file-info">
          <p>Supported formats: PDF, PNG, JPG, JPEG</p>
          <p>Maximum file size: 10MB</p>
        </div>
      </form>
    </div>
  );
};

export default ResumeUploadForm;