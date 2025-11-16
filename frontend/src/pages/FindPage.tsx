import React, { useState } from 'react';
import { useUser } from '@stackframe/react';
import Header from '../components/Header';
import JobCard from '../components/JobCard';
import { Job } from '../types';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Progress } from '../components/ui/progress';
import { Upload, FileCheck, AlertCircle, Sparkles, CheckCircle2, ArrowUp, ArrowDown, ChevronLeft, ChevronRight, Clock } from 'lucide-react';
import { cn } from '../lib/utils';

const FindPage: React.FC = () => {
  const user = useUser();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState<string>('');
  const [isLoading, setIsLoading] = useState(false);
  const [hasResults, setHasResults] = useState(false);
  const [skillsFound, setSkillsFound] = useState<string[]>([]);
  const [progress, setProgress] = useState(0);
  const [currentStep, setCurrentStep] = useState('');
  const [useStreaming, setUseStreaming] = useState(true);
  const [thinkDeeper, setThinkDeeper] = useState(true);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  // Pagination and filtering state
  const [currentPage, setCurrentPage] = useState(1);
  const [sortOrder, setSortOrder] = useState<'desc' | 'asc' | 'recent'>('desc'); // desc = highest first, asc = lowest first, recent = most recent
  const itemsPerPage = 10;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
    }
  };

  const handleFileUploadStreaming = async (file: File) => {
    console.log('🚀 Starting file upload:', file.name);
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
      formData.append('think_deeper', thinkDeeper.toString());

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
                const sortedJobs = [...processedJobs].sort((a, b) => (b.match_score || 0) - (a.match_score || 0));
                setJobs(sortedJobs);
                setHasResults(true);
              }

              if (data.complete) {
                setCurrentStep('Complete!');
                setProgress(100);
                setIsLoading(false);

                console.log('🎉 Streaming complete! Final data:', data);

                if (data.final_results && Array.isArray(data.final_results)) {
                  console.log(`📊 Setting ${data.final_results.length} final results:`, data.final_results);
                  setJobs(data.final_results);
                  setHasResults(true);
                } else {
                  console.warn('⚠️ No final_results in completion data:', data);
                }

                if (data.matches_found === 0) {
                  setError('No matching opportunities found for your skills.');
                } else if (data.total_results) {
                  console.log(`✅ Successfully matched ${data.matches_found} jobs, showing ${data.total_results} results`);
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

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (selectedFile) {
      handleFileUploadStreaming(selectedFile);
    }
  };

  // Reset pagination when new results come in
  React.useEffect(() => {
    if (jobs.length > 0) {
      setCurrentPage(1);
    }
  }, [jobs.length]);

  // Sorting and pagination logic
  const sortedJobs = React.useMemo(() => {
    const sorted = [...jobs].sort((a, b) => {
      if (sortOrder === 'recent') {
        // Sort by first_seen timestamp (most recent first)
        const dateA = a.first_seen ? new Date(a.first_seen).getTime() : 0;
        const dateB = b.first_seen ? new Date(b.first_seen).getTime() : 0;
        return dateB - dateA; // Newest first
      } else {
        // Sort by match score
        const scoreA = a.match_score || a.score || 0;
        const scoreB = b.match_score || b.score || 0;
        return sortOrder === 'desc' ? scoreB - scoreA : scoreA - scoreB;
      }
    });
    return sorted;
  }, [jobs, sortOrder]);

  const totalPages = Math.ceil(sortedJobs.length / itemsPerPage);

  const currentPageJobs = React.useMemo(() => {
    const startIndex = (currentPage - 1) * itemsPerPage;
    const endIndex = startIndex + itemsPerPage;
    return sortedJobs.slice(startIndex, endIndex);
  }, [sortedJobs, currentPage, itemsPerPage]);

  const handleSortChange = (newOrder: 'desc' | 'asc' | 'recent') => {
    setSortOrder(newOrder);
    setCurrentPage(1); // Reset to first page when sorting changes
  };

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
    // Scroll to top of results when page changes
    document.getElementById('results-section')?.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <div className="min-h-screen bg-background">
      <Header />

      <main className="container py-8 space-y-8">
        {/* Header Section */}
        <div className="text-center space-y-4">
          <h1 className="text-4xl md:text-5xl font-bold tracking-tight">
            Upload Your Resume
          </h1>
          <p className="text-xl text-muted-foreground max-w-2xl mx-auto">
            AI-powered matching that analyzes your resume and finds the best opportunities tailored to your skills
          </p>
        </div>

        {/* Upload Section */}
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

                <div className="flex flex-col gap-3">
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      id="thinkDeeper"
                      checked={thinkDeeper}
                      onChange={(e) => setThinkDeeper(e.target.checked)}
                      className="rounded border-gray-300"
                    />
                    <label htmlFor="thinkDeeper" className="text-sm text-muted-foreground cursor-pointer">
                      Think Deeper (AI-powered analysis)
                    </label>
                  </div>
                </div>

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

        {/* Progress Section */}
        {isLoading && (
          <Card className="max-w-2xl mx-auto">
            <CardContent className="pt-6">
              <div className="space-y-4">
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium">{currentStep}</span>
                  <span className="text-muted-foreground">{progress}%</span>
                </div>
                <Progress value={progress} className="h-2" />
              </div>
            </CardContent>
          </Card>
        )}

        {/* Error Message */}
        {error && (
          <Card className="max-w-2xl mx-auto border-destructive">
            <CardContent className="pt-6">
              <div className="flex items-start gap-3">
                <AlertCircle className="h-5 w-5 text-destructive flex-shrink-0 mt-0.5" />
                <div>
                  <h3 className="font-semibold text-destructive">Error</h3>
                  <p className="text-sm text-muted-foreground mt-1">{error}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Skills Section */}
        {skillsFound.length > 0 && (
          <Card className="max-w-4xl mx-auto">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <CheckCircle2 className="h-5 w-5 text-green-600" />
                Skills Detected in Your Resume
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-2">
                {skillsFound.map((skill, index) => (
                  <Badge key={index} variant="secondary" className="px-3 py-1">
                    {skill}
                  </Badge>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Filter Controls */}
        {hasResults && jobs.length > 0 && (
          <Card className="max-w-4xl mx-auto">
            <CardContent className="pt-6">
              <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">Sort by:</span>
                  <div className="flex gap-2">
                    <Button
                      variant={sortOrder === 'desc' ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => handleSortChange('desc')}
                      className="flex items-center gap-2"
                    >
                      <ArrowDown className="h-4 w-4" />
                      Highest Match
                    </Button>
                    <Button
                      variant={sortOrder === 'asc' ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => handleSortChange('asc')}
                      className="flex items-center gap-2"
                    >
                      <ArrowUp className="h-4 w-4" />
                      Lowest Match
                    </Button>
                    <Button
                      variant={sortOrder === 'recent' ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => handleSortChange('recent')}
                      className="flex items-center gap-2"
                    >
                      <Clock className="h-4 w-4" />
                      Most Recent
                    </Button>
                  </div>
                </div>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <span>
                    Showing {Math.min((currentPage - 1) * itemsPerPage + 1, sortedJobs.length)}-
                    {Math.min(currentPage * itemsPerPage, sortedJobs.length)} of {sortedJobs.length} results
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Debug Section - Remove in production */}
        {process.env.NODE_ENV === 'development' && (jobs.length > 0 || hasResults) && (
          <Card className="max-w-4xl mx-auto bg-muted/50">
            <CardHeader>
              <CardTitle className="text-lg">Debug Information</CardTitle>
            </CardHeader>
            <CardContent className="text-sm space-y-2">
              <p><strong>Has Results:</strong> {hasResults.toString()}</p>
              <p><strong>Jobs Count:</strong> {jobs.length}</p>
              <p><strong>Skills Found:</strong> {skillsFound.length}</p>
              <p><strong>Current Step:</strong> {currentStep}</p>
              <p><strong>Progress:</strong> {progress}%</p>
              {jobs.length > 0 && (
                <details className="mt-2">
                  <summary className="cursor-pointer font-medium">Job Scores</summary>
                  <div className="mt-2 space-y-1">
                    {jobs.map((job, index) => (
                      <p key={index} className="text-xs">
                        {index + 1}. {job.company} - {job.title}: {job.match_score || job.score || 0}%
                      </p>
                    ))}
                  </div>
                </details>
              )}
            </CardContent>
          </Card>
        )}

        {/* Results Section */}
        {hasResults && (
          <div className="space-y-6" id="results-section">
            <div className="text-center">
              <h2 className="text-3xl font-bold">
                {jobs.length > 0 ? `Found ${jobs.length} Matching Opportunities` : 'No Matches Found'}
              </h2>
              <p className="text-muted-foreground mt-2">
                {jobs.length > 0 ? 'AI-powered career fit analysis • Sorted by compatibility score' : 'Try updating your resume with more technical skills'}
              </p>
              {jobs.length > 0 && (
                <div className="flex justify-center gap-4 mt-4">
                  <Badge variant="secondary" className="px-3 py-1">
                    <Sparkles className="h-4 w-4 mr-1" />
                    Intelligent Matching
                  </Badge>
                  <Badge variant="outline" className="px-3 py-1">
                    All {jobs.length} Results
                  </Badge>
                </div>
              )}
            </div>

            <div className="grid gap-6 max-w-4xl mx-auto">
              {jobs.length > 0 ? (
                currentPageJobs.map((job, index) => (
                  <JobCard
                    key={`${job.company}-${job.title}-${(currentPage - 1) * itemsPerPage + index}`}
                    job={job}
                    isNewResult={isLoading && useStreaming}
                  />
                ))
              ) : (
                <Card className="max-w-2xl mx-auto">
                  <CardContent className="pt-6 text-center">
                    <AlertCircle className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                    <h3 className="text-lg font-semibold mb-2">No Matches Found</h3>
                    <p className="text-muted-foreground">
                      We couldn't find any internships matching your current skills.
                      Try updating your resume with more technical skills or relevant experience.
                    </p>
                  </CardContent>
                </Card>
              )}
            </div>

            {/* Pagination Controls */}
            {jobs.length > itemsPerPage && (
              <Card className="max-w-4xl mx-auto">
                <CardContent className="pt-6">
                  <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
                    <div className="flex items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handlePageChange(currentPage - 1)}
                        disabled={currentPage === 1}
                        className="flex items-center gap-2"
                      >
                        <ChevronLeft className="h-4 w-4" />
                        Previous
                      </Button>

                      <div className="flex items-center gap-1">
                        {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
                          let pageNum: number;
                          if (totalPages <= 5) {
                            pageNum = i + 1;
                          } else if (currentPage <= 3) {
                            pageNum = i + 1;
                          } else if (currentPage >= totalPages - 2) {
                            pageNum = totalPages - 4 + i;
                          } else {
                            pageNum = currentPage - 2 + i;
                          }

                          return (
                            <Button
                              key={pageNum}
                              variant={currentPage === pageNum ? 'default' : 'outline'}
                              size="sm"
                              onClick={() => handlePageChange(pageNum)}
                              className="w-10 h-10"
                            >
                              {pageNum}
                            </Button>
                          );
                        })}
                      </div>

                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handlePageChange(currentPage + 1)}
                        disabled={currentPage === totalPages}
                        className="flex items-center gap-2"
                      >
                        Next
                        <ChevronRight className="h-4 w-4" />
                      </Button>
                    </div>

                    <div className="text-sm text-muted-foreground">
                      Page {currentPage} of {totalPages}
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        )}
      </main>
    </div>
  );
};

export default FindPage;