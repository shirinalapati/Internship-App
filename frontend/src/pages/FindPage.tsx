import React, { useState, useEffect } from 'react';
import { useAuth, useClerk } from '@clerk/react';
import { Link } from 'react-router-dom';
import Header from '../components/Header';
import JobCard from '../components/JobCard';
import { Job } from '../types';
import { ThinkDeeperToggle } from '../components/ui/think-deeper-toggle';
import JobFilters, { JobFilterState, EMPTY_FILTERS, isFilterActive, filterSignature } from '../components/JobFilters';
import { DepartmentMultiSelect } from '../components/ui/department-multi-select';
import { Upload, AlertCircle, CheckCircle2, ArrowUp, ArrowDown, ChevronLeft, ChevronRight, Clock, RefreshCcw } from 'lucide-react';

// For SSE streaming, we need to bypass the CRA proxy in development
// because it buffers responses. In production, use relative URLs.
// Priority:
// 1. On localhost (dev): use REACT_APP_API_URL if set, otherwise http://localhost:8000
// 2. On any non-localhost host (prod/staging): ALWAYS use relative URLs (empty string),
//    even if REACT_APP_API_URL was accidentally baked into the bundle.
// 3. In non-browser environments: fall back to localhost in development only.
const getApiBaseUrl = (): string => {
  if (typeof window !== 'undefined') {
    const { hostname } = window.location;
    const isLocalhost = hostname === 'localhost' || hostname === '127.0.0.1';
    const envUrl = process.env.REACT_APP_API_URL?.trim();

    if (isLocalhost) {
      if (envUrl) return envUrl.replace(/\/+$/, '');
      return 'http://localhost:8000';
    }

    return '';
  }

  if (process.env.NODE_ENV === 'development') return 'http://localhost:8000';
  return '';
};

const API_BASE_URL = getApiBaseUrl();

// sessionStorage keys — used to persist the pending resume across OAuth redirects
const PENDING_RESUME_DATA_KEY = 'iam_pending_resume_data';
const PENDING_RESUME_META_KEY = 'iam_pending_resume_meta';

const PROGRESS_MILESTONES = [
  { label: 'Started', threshold: 25 },
  { label: 'Analyzing', threshold: 50 },
  { label: 'Matching', threshold: 75 },
  { label: 'Complete', threshold: 100 },
];

// Convert the frontend filter state into the snake_case payload the backend expects.
const buildFiltersPayload = (f: JobFilterState) => ({
  locations: f.locations,
  positions: f.positions,
  target_companies: f.targetCompanies,
  company_sizes: f.companySizes,
  citizenship: f.citizenship,
  avoid_companies: f.avoidCompanies,
});

// Small, URL-safe string hash (djb2) used to namespace the result cache per filter set.
const cheapHash = (s: string): string => {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0;
  return h.toString(16);
};

const FindPage: React.FC = () => {
  const { getToken, isSignedIn } = useAuth();
  const { openSignIn } = useClerk();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState<string>('');
  const [quotaError, setQuotaError] = useState<{ message: string; reset_at: string | null } | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [hasResults, setHasResults] = useState(false);
  const [skillsFound, setSkillsFound] = useState<string[]>([]);
  const [progress, setProgress] = useState(0);
  const [currentStep, setCurrentStep] = useState('');
  const [useStreaming] = useState(true);
  const [thinkDeeper, setThinkDeeper] = useState(true);
  const [filters, setFilters] = useState<JobFilterState>(EMPTY_FILTERS);
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fromCache, setFromCache] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [authToken, setAuthToken] = useState<string | null>(null);
  const [cooldown, setCooldown] = useState(0);
  const [pendingAnalysis, setPendingAnalysis] = useState(false);
  const [savedJobHashes, setSavedJobHashes] = useState<string[]>([]);

  // Auto-submit after sign-in — handles both paths:
  //   A) In-page modal (no redirect): isSignedIn flips true while pendingAnalysis is set
  //   B) OAuth redirect (page reload): sessionStorage has the saved file, isSignedIn is true on mount
  useEffect(() => {
    if (!isSignedIn) return;

    const storedData = sessionStorage.getItem(PENDING_RESUME_DATA_KEY);
    if (storedData) {
      try {
        const meta = JSON.parse(sessionStorage.getItem(PENDING_RESUME_META_KEY) || '{}');
        sessionStorage.removeItem(PENDING_RESUME_DATA_KEY);
        sessionStorage.removeItem(PENDING_RESUME_META_KEY);

        const base64 = storedData.split(',')[1];
        const byteString = atob(base64);
        const arr = new Uint8Array(byteString.length);
        for (let i = 0; i < byteString.length; i++) arr[i] = byteString.charCodeAt(i);
        const file = new File([arr], meta.name || 'resume', {
          type: meta.type || 'application/pdf',
          lastModified: meta.lastModified || Date.now(),
        });
        const restoredThinkDeeper: boolean = meta.thinkDeeper ?? true;
        const restoredFilters: JobFilterState = meta.filters ?? EMPTY_FILTERS;
        const restoredCategories: string[] = Array.isArray(meta.categories) ? meta.categories : [];

        setSelectedFile(file);
        setThinkDeeper(restoredThinkDeeper);
        setFilters(restoredFilters);
        setSelectedCategories(restoredCategories);
        handleFileUploadStreaming(file, restoredThinkDeeper, restoredFilters, restoredCategories);
      } catch (e) {
        sessionStorage.removeItem(PENDING_RESUME_DATA_KEY);
        sessionStorage.removeItem(PENDING_RESUME_META_KEY);
      }
      return;
    }

    if (pendingAnalysis && selectedFile) {
      setPendingAnalysis(false);
      handleFileUploadStreaming(selectedFile);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isSignedIn, pendingAnalysis]);

  const [currentPage, setCurrentPage] = useState(1);
  const [sortOrder, setSortOrder] = useState<'desc' | 'asc' | 'recent'>('desc');
  const itemsPerPage = 10;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) setSelectedFile(file);
  };

  const handleDrop = (e: React.DragEvent<HTMLLabelElement>) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) setSelectedFile(file);
  };

  const handleDragOver = (e: React.DragEvent<HTMLLabelElement>) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => setIsDragging(false);

  const startCooldown = (seconds: number) => {
    // Skip the per-upload waiting time when usage tracking is disabled (dev testing).
    // Mirrors the backend TRACK_USAGE switch; default on unless explicitly "false".
    if (process.env.REACT_APP_TRACK_USAGE === 'false') return;
    setCooldown(seconds);
    const timer = setInterval(() => {
      setCooldown(prev => {
        if (prev <= 1) { clearInterval(timer); return 0; }
        return prev - 1;
      });
    }, 1000);
  };

  const hashFile = async (file: File): Promise<string> => {
    if (crypto?.subtle?.digest) {
      const buffer = await file.arrayBuffer();
      const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
      return Array.from(new Uint8Array(hashBuffer))
        .map(b => b.toString(16).padStart(2, '0')).join('');
    }
    return `${file.name}-${file.size}-${file.lastModified}`;
  };

  const loadSavedJobHashes = async (token: string | null) => {
    if (!token) {
      setSavedJobHashes([]);
      return;
    }
    try {
      const res = await fetch(`${API_BASE_URL}/api/saved-jobs?hashes_only=true`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) return;
      const data = await res.json();
      setSavedJobHashes(Array.isArray(data.job_hashes) ? data.job_hashes : []);
    } catch {
      // Saved-state failure should not block matching.
    }
  };

  const handleSavedChange = (jobHash: string, saved: boolean) => {
    setSavedJobHashes(prev => {
      if (saved && !prev.includes(jobHash)) return [...prev, jobHash];
      if (!saved) return prev.filter(h => h !== jobHash);
      return prev;
    });
  };

  const handleFileUploadStreaming = async (file: File, thinkDeeperOverride?: boolean, filtersOverride?: JobFilterState, categoriesOverride?: string[]) => {
    const useThinkDeeper = thinkDeeperOverride ?? thinkDeeper;
    const activeFilters = filtersOverride ?? filters;
    const filtersActive = isFilterActive(activeFilters);
    // Department selection is part of the cache identity: a different selection
    // must be a fresh search, not the previous selection's cached results.
    const useCategories = categoriesOverride ?? selectedCategories;
    setFromCache(false);
    const baseHash = await hashFile(file);
    // Namespace the cache key by filter combination so a filtered search never
    // returns the unfiltered (or differently-filtered) cached result.
    const resumeHash = filtersActive ? `${baseHash}-${cheapHash(filterSignature(activeFilters))}` : baseHash;

    const token = await getToken();
    setAuthToken(token);
    await loadSavedJobHashes(token);

    if (token) {
      try {
        const catParam = `&categories=${encodeURIComponent(useCategories.join(','))}`;
        const res = await fetch(`${API_BASE_URL}/api/resume-cache/${resumeHash}?think_deeper=${useThinkDeeper}${catParam}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        const data = await res.json();
        if (data.hit) {
          setJobs(data.results);
          setSkillsFound(data.skills);
          setHasResults(true);
          setFromCache(true);
          return;
        }
      } catch (e) {
        // cache check failed — fall through to full pipeline
      }
    }

    setIsLoading(true);
    setError('');
    setQuotaError(null);
    setHasResults(false);
    setJobs([]);
    setSkillsFound([]);
    setProgress(0);
    setCurrentStep('Starting...');

    try {
      const formData = new FormData();
      formData.append('resume', file);
      formData.append('think_deeper', useThinkDeeper.toString());
      formData.append('resume_hash', resumeHash);
      if (filtersActive) {
        formData.append('filters', JSON.stringify(buildFiltersPayload(activeFilters)));
      }
      formData.append('categories', useCategories.join(','));

      const response = await fetch(`${API_BASE_URL}/api/match-stream`, {
        method: 'POST',
        body: formData,
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      });

      if (!response.ok) {
        if (response.status === 429) {
          try {
            const body = await response.json();
            if (body?.detail?.error === 'weekly_quota_exceeded') {
              setQuotaError({ message: body.detail.message, reset_at: body.detail.reset_at ?? null });
              setIsLoading(false);
              return;
            }
          } catch {}
          startCooldown(120);
        } else {
          setError(`HTTP error! status: ${response.status}`);
        }
        setIsLoading(false);
        return;
      }

      startCooldown(60);

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      const processedJobs: Job[] = [];
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        buffer += chunk;
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.trim().startsWith('data: ')) {
            try {
              const jsonStr = line.trim().slice(6);
              const data = JSON.parse(jsonStr);

              if (data.error) {
                const isBusy = typeof data.error === 'string' &&
                  (data.error.toLowerCase().includes('busy') ||
                   data.error.toLowerCase().includes('rate limit') ||
                   data.error.toLowerCase().includes('try again'));
                if (isBusy) {
                  startCooldown(30);
                } else {
                  setError(data.error);
                }
                setIsLoading(false);
                return;
              }

              if (data.progress !== undefined) setProgress(data.progress);
              if (data.message) setCurrentStep(data.message);
              if (data.skills) setSkillsFound(data.skills);

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

                if (data.final_results && Array.isArray(data.final_results)) {
                  setJobs(data.final_results);
                  setHasResults(true);
                }

                if (data.matches_found === 0) {
                  setError('No matching opportunities found for your skills.');
                }
                break;
              }
            } catch (parseError) {
              // ignore malformed SSE frames
            }
          }
        }
      }
    } catch (err: any) {
      setError(err.message || 'An error occurred while processing your resume.');
      setIsLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) return;

    if (!isSignedIn) {
      setPendingAnalysis(true);

      const reader = new FileReader();
      reader.onload = () => {
        try {
          sessionStorage.setItem(PENDING_RESUME_DATA_KEY, reader.result as string);
          sessionStorage.setItem(PENDING_RESUME_META_KEY, JSON.stringify({
            name: selectedFile.name,
            type: selectedFile.type,
            lastModified: selectedFile.lastModified,
            thinkDeeper,
            filters,
            categories: selectedCategories,
          }));
        } catch (e) {
          // sessionStorage quota exceeded — modal flow still works
        }
      };
      reader.readAsDataURL(selectedFile);

      openSignIn({
        afterSignInUrl: window.location.href,
        afterSignUpUrl: window.location.href,
      });
      return;
    }

    handleFileUploadStreaming(selectedFile);
  };

  const handleTryAgain = () => {
    setError('');
    setHasResults(false);
    setJobs([]);
    setSkillsFound([]);
    setProgress(0);
    setCurrentStep('');
    setSelectedFile(null);
  };

  React.useEffect(() => {
    if (jobs.length > 0) setCurrentPage(1);
  }, [jobs.length]);

  const sortedJobs = React.useMemo(() => {
    const sorted = [...jobs].sort((a, b) => {
      if (sortOrder === 'recent') {
        const dateA = a.first_seen ? new Date(a.first_seen).getTime() : 0;
        const dateB = b.first_seen ? new Date(b.first_seen).getTime() : 0;
        return dateB - dateA;
      }
      const scoreA = a.match_score || a.score || 0;
      const scoreB = b.match_score || b.score || 0;
      return sortOrder === 'desc' ? scoreB - scoreA : scoreA - scoreB;
    });
    return sorted;
  }, [jobs, sortOrder]);

  const totalPages = Math.ceil(sortedJobs.length / itemsPerPage);

  const currentPageJobs = React.useMemo(() => {
    const startIndex = (currentPage - 1) * itemsPerPage;
    return sortedJobs.slice(startIndex, startIndex + itemsPerPage);
  }, [sortedJobs, currentPage, itemsPerPage]);

  const handleSortChange = (newOrder: 'desc' | 'asc' | 'recent') => {
    setSortOrder(newOrder);
    setCurrentPage(1);
  };

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
    document.getElementById('results-section')?.scrollIntoView({ behavior: 'smooth' });
  };

  const isNoResultsError = error === 'No matching opportunities found for your skills.';

  const focusRing = 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-text-primary focus-visible:ring-offset-2 focus-visible:ring-offset-bg';

  const sortBtn = (order: 'desc' | 'asc' | 'recent', label: React.ReactNode) => (
    <button
      onClick={() => handleSortChange(order)}
      className={`inline-flex items-center gap-1.5 font-mono text-xs transition-colors pb-0.5 ${focusRing} ${
        sortOrder === order
          ? 'text-text-primary border-b border-text-primary'
          : 'text-text-secondary hover:text-text-primary border-b border-transparent'
      }`}
    >
      {label}
    </button>
  );

  const pageBtn = (page: number, active: boolean) => (
    <button
      key={page}
      onClick={() => handlePageChange(page)}
      className={`w-8 h-8 font-mono text-xs transition-colors ${focusRing} ${
        active
          ? 'bg-text-primary text-bg'
          : 'border border-lp-border text-text-secondary hover:text-text-primary'
      }`}
    >
      {page}
    </button>
  );

  return (
    <div className="min-h-screen bg-bg text-text-primary">
      <Header />

      <main className="max-w-[1080px] mx-auto px-6 py-12 space-y-0">

        {/* Hero */}
        <div className="pt-6 pb-10 border-b border-lp-border">
          <div className="flex items-center gap-3 mb-6">
            <span className="block w-8 h-px bg-text-tertiary flex-shrink-0" />
            <span className="font-mono text-[10px] uppercase tracking-widest text-text-secondary">
              Resume matcher
            </span>
          </div>
          <h1 className="font-serif text-3xl md:text-4xl text-text-primary mb-2">
            Upload your resume to begin.
          </h1>
          <p className="text-sm text-text-secondary">
            PDF or image — we'll handle the rest
          </p>
        </div>

        {/* Upload card + filters sidebar */}
        <div className="py-8 border-b border-lp-border">
          <div className="flex flex-col lg:flex-row lg:gap-10 lg:items-start">
          <div className="flex-1 min-w-0 lg:max-w-2xl">
            <div className="flex items-center gap-2 mb-5">
              <Upload className="h-4 w-4 text-text-secondary" />
              <span className="font-mono text-[10px] uppercase tracking-widest text-text-secondary">
                Upload Your Resume
              </span>
            </div>
            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Drop zone */}
              <label
                className={`flex flex-col items-center justify-center w-full h-32 border border-dashed cursor-pointer transition-colors ${
                  isDragging
                    ? 'border-text-primary bg-ia-subtle'
                    : selectedFile
                    ? 'border-text-primary bg-ia-subtle'
                    : 'border-lp-border hover:border-text-secondary'
                }`}
                onDrop={handleDrop}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
              >
                <div className="flex flex-col items-center justify-center pt-5 pb-6">
                  {selectedFile ? (
                    <>
                      <CheckCircle2 className="h-6 w-6 mb-2 text-text-primary" />
                      <p className="text-sm text-text-primary">{selectedFile.name}</p>
                      <p className="font-mono text-[10px] text-text-tertiary mt-0.5">Click to change file</p>
                    </>
                  ) : isDragging ? (
                    <>
                      <Upload className="h-6 w-6 mb-2 text-text-primary" />
                      <p className="text-sm text-text-primary">Drop it here</p>
                    </>
                  ) : (
                    <>
                      <Upload className="h-6 w-6 mb-2 text-text-tertiary" />
                      <p className="text-sm text-text-secondary">
                        Tap to upload
                        <span className="hidden sm:inline"> or drag and drop</span>
                      </p>
                      <p className="font-mono text-[10px] text-text-tertiary mt-0.5">PDF, PNG, JPG (MAX. 10MB)</p>
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

              {/* Think Deeper toggle */}
              <ThinkDeeperToggle checked={thinkDeeper} onChange={setThinkDeeper} />

              {/* Department / category filter */}
              <DepartmentMultiSelect selected={selectedCategories} onChange={setSelectedCategories} />

              <button
                type="submit"
                className={`w-full md:w-auto px-8 py-2.5 bg-text-primary text-bg font-mono text-xs tracking-wide hover:opacity-80 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed ${focusRing}`}
                disabled={!selectedFile || isLoading || cooldown > 0}
              >
                {isLoading ? (
                  'Analyzing...'
                ) : cooldown > 0 ? (
                  <span className="inline-flex items-center gap-2">
                    <Clock className="h-4 w-4" />
                    Please wait {cooldown}s
                  </span>
                ) : selectedFile && !isSignedIn ? (
                  'Sign in to analyze →'
                ) : (
                  'See My Matches →'
                )}
              </button>
            </form>
          </div>

            {/* Filters — right sidebar (stacks below upload on mobile) */}
            <aside className="w-full lg:w-80 lg:flex-shrink-0 mt-8 lg:mt-0">
              <JobFilters value={filters} onChange={setFilters} disabled={isLoading} alwaysOpen />
            </aside>
          </div>
        </div>

        {/* Progress */}
        {isLoading && (
          <div className="py-8 border-b border-lp-border max-w-2xl">
            <div className="flex items-center gap-4 mb-5">
              <div className="flex-1">
                <p className="text-text-primary text-sm leading-tight">
                  {currentStep || 'Processing...'}
                </p>
                <p className="font-mono text-[10px] text-text-tertiary mt-0.5">
                  Please wait while we analyze your resume
                </p>
              </div>
              <div className="text-right shrink-0">
                <div className="font-serif text-3xl text-text-primary leading-none">{progress}%</div>
              </div>
            </div>

            <div className="w-full h-px bg-lp-border overflow-hidden">
              <div
                className="h-full bg-text-primary transition-all duration-700 ease-out"
                style={{ width: `${progress}%` }}
              />
            </div>

            <div className="flex justify-between mt-2">
              {PROGRESS_MILESTONES.map(({ label, threshold }) => (
                <span
                  key={label}
                  className={`font-mono text-[10px] transition-colors ${
                    progress >= threshold ? 'text-text-primary' : 'text-text-tertiary'
                  }`}
                >
                  {progress >= threshold ? '—' : '·'} {label}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Quota exceeded error */}
        {quotaError && (
          <div className="py-8 border-b border-lp-border max-w-2xl">
            <div className="border border-red-500/40 bg-red-500/5 p-4">
              <p className="font-mono text-[10px] uppercase tracking-widest text-red-500 mb-1">Weekly limit reached</p>
              <p className="text-sm text-text-secondary mb-2">{quotaError.message}</p>
              {quotaError.reset_at && (
                <p className="font-mono text-xs text-text-tertiary mb-3">
                  Resets {(() => {
                    const d = new Date(quotaError.reset_at.endsWith('Z') ? quotaError.reset_at : quotaError.reset_at + 'Z');
                    const days = Math.ceil((d.getTime() - Date.now()) / 86400000);
                    const abs = d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
                    return days <= 0 ? `today · ${abs}` : days === 1 ? `tomorrow · ${abs}` : `in ${days} days · ${abs}`;
                  })()}
                </p>
              )}
              <Link to="/usage" className="font-mono text-xs text-red-500 hover:opacity-70 transition-opacity">
                View usage →
              </Link>
            </div>
          </div>
        )}

        {/* Error */}
        {error && !isNoResultsError && (
          <div className="py-8 border-b border-lp-border max-w-2xl">
            <div className="border border-lp-border p-4 flex items-start gap-3">
              <AlertCircle className="h-4 w-4 text-red-500 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-mono text-[10px] uppercase tracking-widest text-red-500 mb-1">Error</p>
                <p className="text-text-secondary text-sm">{error}</p>
              </div>
            </div>
          </div>
        )}

        {/* Detected skills */}
        {skillsFound.length > 0 && (
          <div className="py-6 border-b border-lp-border">
            <div className="font-mono text-[10px] uppercase tracking-widest text-text-tertiary mb-3">
              Skills detected in your resume
            </div>
            <div className="flex flex-wrap gap-1.5">
              {skillsFound.map((skill, i) => (
                <span key={i} className="font-mono text-[10px] px-1.5 py-0.5 border border-lp-border text-text-secondary">
                  {skill}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Sort controls */}
        {hasResults && jobs.length > 0 && (
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 py-5 border-b border-lp-border">
            <div className="flex items-center gap-4 flex-wrap">
              <span className="font-mono text-[10px] uppercase tracking-widest text-text-tertiary">Sort</span>
              {sortBtn('desc', <><ArrowDown className="h-3 w-3" /> Highest</>)}
              {sortBtn('asc', <><ArrowUp className="h-3 w-3" /> Lowest</>)}
              {sortBtn('recent', <><Clock className="h-3 w-3" /> Recent</>)}
            </div>
            <div className="flex items-center gap-2 font-mono text-[10px] text-text-tertiary">
              {fromCache && (
                <span className="border border-lp-border px-1.5 py-0.5 text-text-secondary">
                  cached
                </span>
              )}
              <span>
                {Math.min((currentPage - 1) * itemsPerPage + 1, sortedJobs.length)}–
                {Math.min(currentPage * itemsPerPage, sortedJobs.length)} of {sortedJobs.length}
              </span>
            </div>
          </div>
        )}

        {/* Debug — dev only */}
        {process.env.NODE_ENV === 'development' && (jobs.length > 0 || hasResults) && (
          <div className="py-5 border-b border-lp-border bg-surface p-4 text-xs text-text-secondary space-y-1">
            <p className="font-mono text-[10px] uppercase tracking-widest text-text-tertiary mb-2">Debug</p>
            <p>Has Results: {hasResults.toString()}</p>
            <p>Jobs Count: {jobs.length}</p>
            <p>Skills Found: {skillsFound.length}</p>
            <p>Current Step: {currentStep}</p>
            <p>Progress: {progress}%</p>
            {jobs.length > 0 && (
              <details className="mt-2">
                <summary className="cursor-pointer text-text-secondary">Job Scores</summary>
                <div className="mt-2 space-y-1">
                  {jobs.map((job, index) => (
                    <p key={index} className="text-[10px] font-mono">
                      {index + 1}. {job.company} — {job.title}: {job.match_score || job.score || 0}%
                    </p>
                  ))}
                </div>
              </details>
            )}
          </div>
        )}

        {/* Results */}
        {hasResults && (
          <div className="space-y-0" id="results-section">
            <div className="py-8 border-b border-lp-border">
              <div className="flex items-center gap-3 mb-2">
                <span className="block w-8 h-px bg-text-tertiary flex-shrink-0" />
                <span className="font-mono text-[10px] uppercase tracking-widest text-text-secondary">
                  Results
                </span>
              </div>
              <h2 className="font-serif text-2xl md:text-3xl text-text-primary">
                {jobs.length > 0
                  ? `${jobs.length} internship${jobs.length !== 1 ? 's' : ''} matched.`
                  : 'No matches found.'}
              </h2>
              {jobs.length > 0 && (
                <p className="font-mono text-[11px] text-text-tertiary mt-1">
                  Ranked by compatibility score
                </p>
              )}
            </div>

            <div className="space-y-0 divide-y divide-lp-border">
              {jobs.length > 0 ? (
                currentPageJobs.map((job, index) => (
                  <div key={`${job.company}-${job.title}-${(currentPage - 1) * itemsPerPage + index}`} className="py-4">
                    <JobCard
                      job={job}
                      isNewResult={isLoading && useStreaming}
                      resumeFile={selectedFile}
                      apiBaseUrl={API_BASE_URL}
                      authToken={authToken}
                      isSaved={!!job.job_hash && savedJobHashes.includes(job.job_hash)}
                      onSavedChange={handleSavedChange}
                    />
                  </div>
                ))
              ) : isNoResultsError ? (
                <div className="py-12 border-b border-lp-border">
                  <h3 className="font-serif text-xl text-text-primary mb-2">
                    No matches found yet.
                  </h3>
                  <p className="text-sm text-text-secondary leading-relaxed mb-5 max-w-md">
                    We scanned our database but couldn't find a strong fit. This usually means your
                    resume is missing technical keywords or project details.
                  </p>
                  {skillsFound.length > 0 && (
                    <div className="mb-6">
                      <p className="font-mono text-[10px] uppercase tracking-widest text-text-tertiary mb-2">
                        Skills we detected
                      </p>
                      <div className="flex flex-wrap gap-1.5">
                        {skillsFound.map((skill, i) => (
                          <span key={i} className="font-mono text-[10px] px-1.5 py-0.5 border border-lp-border text-text-secondary">
                            {skill}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                  <ul className="text-sm text-text-secondary space-y-1.5 mb-6 max-w-xs">
                    <li className="flex items-start gap-2">
                      <span className="text-text-tertiary mt-0.5 shrink-0">—</span>
                      Add specific tech stacks, languages, and frameworks
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="text-text-tertiary mt-0.5 shrink-0">—</span>
                      Include project names with measurable outcomes
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="text-text-tertiary mt-0.5 shrink-0">—</span>
                      List coursework or certifications relevant to your field
                    </li>
                  </ul>
                  <button
                    onClick={handleTryAgain}
                    className={`inline-flex items-center gap-2 px-6 py-2.5 bg-text-primary text-bg font-mono text-xs tracking-wide hover:opacity-80 transition-opacity ${focusRing}`}
                  >
                    <RefreshCcw className="h-4 w-4" />
                    Try Again
                  </button>
                </div>
              ) : null}
            </div>

            {/* Pagination */}
            {jobs.length > itemsPerPage && (
              <div className="flex flex-col sm:flex-row items-center justify-between gap-4 py-6 border-t border-lp-border">
                <div className="flex items-center gap-1.5">
                  <button
                    onClick={() => handlePageChange(currentPage - 1)}
                    disabled={currentPage === 1}
                    className={`inline-flex items-center gap-1 px-3 py-2 font-mono text-xs border border-lp-border text-text-secondary hover:text-text-primary transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${focusRing}`}
                  >
                    <ChevronLeft className="h-3.5 w-3.5" />
                    Prev
                  </button>

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
                      return pageBtn(pageNum, currentPage === pageNum);
                    })}
                  </div>

                  <button
                    onClick={() => handlePageChange(currentPage + 1)}
                    disabled={currentPage === totalPages}
                    className={`inline-flex items-center gap-1 px-3 py-2 font-mono text-xs border border-lp-border text-text-secondary hover:text-text-primary transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${focusRing}`}
                  >
                    Next
                    <ChevronRight className="h-3.5 w-3.5" />
                  </button>
                </div>

                <span className="font-mono text-[10px] text-text-tertiary">
                  Page {currentPage} of {totalPages}
                </span>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
};

export default FindPage;
