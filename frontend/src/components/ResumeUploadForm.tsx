import React, { useState } from 'react';
import { Button } from './ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Upload, FileCheck, Sparkles } from 'lucide-react';
import { cn } from '../lib/utils';

interface ResumeUploadFormProps {
  onSubmit: (file: File) => void;
  isLoading: boolean;
}

const ResumeUploadForm: React.FC<ResumeUploadFormProps> = ({ onSubmit, isLoading }) => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (selectedFile) {
      onSubmit(selectedFile);
    }
  };

  return (
    <Card className="max-w-2xl mx-auto">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Upload className="h-5 w-5" />
          Upload Your Resume
        </CardTitle>
        <CardDescription>
          Upload your resume (PDF or image) to get personalized internship recommendations
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="flex flex-col items-center gap-4">
            <label className={cn(
              "flex flex-col items-center justify-center w-full h-32 border-2 border-dashed rounded-lg cursor-pointer transition-colors",
              selectedFile ? "border-primary bg-primary/5" : "border-muted-foreground/25 hover:bg-accent"
            )}>
              <div className="flex flex-col items-center justify-center pt-5 pb-6">
                {selectedFile ? (
                  <>
                    <FileCheck className="h-8 w-8 mb-2 text-primary" />
                    <p className="text-sm font-medium">{selectedFile.name}</p>
                    <p className="text-xs text-muted-foreground">Click to change file</p>
                  </>
                ) : (
                  <>
                    <Upload className="h-8 w-8 mb-2 text-muted-foreground" />
                    <p className="text-sm font-medium">Click to upload</p>
                    <p className="text-xs text-muted-foreground">PDF, PNG, JPG (MAX. 10MB)</p>
                  </>
                )}
              </div>
              <input
                type="file"
                className="hidden"
                accept=".pdf,.png,.jpg,.jpeg"
                onChange={handleFileChange}
              />
            </label>

            <Button 
              type="submit" 
              className="w-full md:w-auto px-8"
              disabled={!selectedFile || isLoading}
            >
              {isLoading ? (
                <>
                  <Sparkles className="h-4 w-4 mr-2 animate-spin" />
                  Analyzing...
                </>
              ) : (
                <>
                  <Sparkles className="h-4 w-4 mr-2" />
                  Find Matches
                </>
              )}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
};

export default ResumeUploadForm;
