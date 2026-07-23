import React, { useEffect, useState } from 'react';
import { useAuth, SignInButton } from '@clerk/react';
import { Link } from 'react-router-dom';
import Header from '../components/Header';
import JobCard from '../components/JobCard';
import { Job } from '../types';
import { Clock, ChevronDown, ChevronUp, Upload, SlidersHorizontal } from 'lucide-react';
import { describeStoredFilters, StoredFilters } from '../lib/filterLabels';

const getApiBaseUrl = (): string => {
  if (typeof window !== 'undefined') {
    const { hostname } = window.location;
    const isLocalhost = hostname === 'localhost' || hostname === '127.0.0.1';
    if (isLocalhost) {
      return (process.env.REACT_APP_API_URL ?? 'http://localhost:8000').replace(/\/+$/, '');
    }
    return '';
  }
  return process.env.NODE_ENV === 'development' ? 'http://localhost:8000' : '';
};

const API_BASE_URL = getApiBaseUrl();

interface HistoryEntry {
  id: number;
  resume_hash: string;
  results: Job[];
  skills: string[];
  filters: StoredFilters | null;
  created_at: string;
  expires_at: string;
}

const HistoryPage: React.FC = () => {
  const { isLoaded, isSignedIn, getToken } = useAuth();
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [expandedId, setExpandedId] = useState<number | null>(null);

  useEffect(() => {
    if (!isLoaded || !isSignedIn) return;

    const fetchHistory = async () => {
      setLoading(true);
      setError('');
      try {
        const token = await getToken();
        const res = await fetch(`${API_BASE_URL}/api/user-history`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) throw new Error(`Server error ${res.status}`);
        const data: HistoryEntry[] = await res.json();
        setHistory(data);
      } catch (e: any) {
        setError(e.message ?? 'Failed to load history.');
      } finally {
        setLoading(false);
      }
    };

    fetchHistory();
  }, [isLoaded, isSignedIn, getToken]);

  const formatDate = (iso: string) => {
    // Backend returns UTC timestamps without a timezone suffix — append Z so
    // the browser correctly interprets them as UTC before converting to local.
    const normalized = iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z';
    return new Date(normalized).toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const isExpired = (expires_at: string) => new Date(expires_at) < new Date();

  const analysisLabel = (hash: string) =>
    hash.endsWith('_deep') ? 'Think Deeper' : 'Quick';

  // ── Not loaded yet ──────────────────────────────────────────────────────────
  if (!isLoaded) {
    return (
      <div className="min-h-screen bg-bg text-text-primary">
        <Header />
        <div className="flex items-center justify-center h-64">
          <div className="h-8 w-8 border-2 border-text-primary border-t-transparent animate-spin" />
        </div>
      </div>
    );
  }

  // ── Not signed in ──────────────────────────────────────────────────────────
  if (!isSignedIn) {
    return (
      <div className="min-h-screen bg-bg text-text-primary">
        <Header />
        <div className="max-w-[860px] mx-auto px-6 py-24">
          <div className="flex flex-col gap-2 mb-6">
            <span className="block w-8 h-px bg-text-tertiary" />
            <span className="font-mono text-[10px] uppercase tracking-widest text-text-secondary">
              Sign in required
            </span>
          </div>
          <h2 className="font-serif text-3xl text-text-primary mb-3">
            Your history lives here.
          </h2>
          <p className="font-mono text-xs text-text-tertiary mb-8 max-w-sm">
            Sign in to see your past resume analyses — saved automatically so
            you never have to re-upload.
          </p>
          <SignInButton mode="modal">
            <button className="inline-block bg-text-primary text-bg px-5 py-2.5 font-mono text-xs tracking-wide hover:opacity-80 transition-opacity focus:outline-none focus-visible:ring-2 focus-visible:ring-text-primary focus-visible:ring-offset-2 focus-visible:ring-offset-bg">
              Sign in →
            </button>
          </SignInButton>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-bg text-text-primary">
      <Header />

      <main className="max-w-[860px] mx-auto px-6 py-12">
        {/* Page header */}
        <div className="mb-10 pb-6 border-b border-lp-border">
          <div className="flex flex-col gap-2 mb-4">
            <span className="block w-8 h-px bg-text-tertiary" />
            <span className="font-mono text-[10px] uppercase tracking-widest text-text-secondary">
              Past analyses
            </span>
          </div>
          <h1 className="font-serif text-3xl text-text-primary">
            Your resume history.
          </h1>
          <p className="font-mono text-xs text-text-tertiary mt-2">
            All previous scans — click any entry to expand its matched jobs.
          </p>
        </div>

        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center h-40">
            <div className="h-8 w-8 border-2 border-text-primary border-t-transparent animate-spin" />
          </div>
        )}

        {/* Error */}
        {!loading && error && (
          <div className="border border-lp-border bg-surface p-5">
            <p className="font-mono text-xs text-text-secondary">{error}</p>
          </div>
        )}

        {/* Empty state */}
        {!loading && !error && history.length === 0 && (
          <div className="py-24">
            <Upload className="h-8 w-8 text-text-tertiary mb-6" />
            <h3 className="font-serif text-2xl text-text-primary mb-2">
              No analyses yet.
            </h3>
            <p className="font-mono text-xs text-text-tertiary mb-8">
              Upload your resume on the Find page and your results will be
              saved here automatically.
            </p>
            <Link
              to="/find"
              className="inline-block bg-text-primary text-bg px-5 py-2.5 font-mono text-xs tracking-wide hover:opacity-80 transition-opacity focus:outline-none focus-visible:ring-2 focus-visible:ring-text-primary focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
            >
              Upload Resume →
            </Link>
          </div>
        )}

        {/* History list */}
        {!loading && !error && history.length > 0 && (
          <div className="flex flex-col gap-3">
            {history.map((entry) => {
              const expanded = expandedId === entry.id;
              const expired = isExpired(entry.expires_at);
              const mode = analysisLabel(entry.resume_hash);
              const filterGroups = describeStoredFilters(entry.filters);

              const gradientBar = mode === 'Think Deeper'
                ? 'bg-gradient-to-b from-red-500/60 to-transparent'
                : 'bg-gradient-to-b from-emerald-500/60 to-transparent';

              return (
                <div
                  key={entry.id}
                  className="border border-lp-border bg-surface flex"
                >
                  {/* Mode accent — left edge gradient strip */}
                  <div className={`w-0.5 shrink-0 ${gradientBar}`} />

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    {/* Row header — always visible */}
                    <button
                      type="button"
                      className="w-full text-left px-5 py-4 focus:outline-none focus-visible:ring-2 focus-visible:ring-text-primary focus-visible:ring-inset"
                      onClick={() => setExpandedId(expanded ? null : entry.id)}
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex flex-col gap-1.5 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-serif text-base text-text-primary">
                              {entry.results.length} job
                              {entry.results.length !== 1 ? 's' : ''} matched
                            </span>
                            <span className="font-mono text-[10px] uppercase tracking-widest border border-lp-border px-1.5 py-0.5 text-text-secondary">
                              {mode}
                            </span>
                            {expired && (
                              <span className="font-mono text-[10px] uppercase tracking-widest border border-lp-border px-1.5 py-0.5 text-text-tertiary">
                                Cache expired
                              </span>
                            )}
                          </div>

                          {/* Skills */}
                          {entry.skills.length > 0 && (
                            <div className="flex flex-wrap gap-1.5 mt-0.5">
                              {entry.skills.slice(0, 8).map((s) => (
                                <span
                                  key={s}
                                  className="font-mono text-[10px] px-1.5 py-0.5 border border-lp-border text-text-secondary"
                                >
                                  {s}
                                </span>
                              ))}
                              {entry.skills.length > 8 && (
                                <span className="font-mono text-[10px] text-text-tertiary px-1 py-0.5">
                                  +{entry.skills.length - 8} more
                                </span>
                              )}
                            </div>
                          )}

                          {/* Filters used */}
                          {filterGroups.length > 0 && (
                            <div className="flex flex-wrap items-center gap-1.5 mt-1">
                              <span className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-widest text-text-tertiary">
                                <SlidersHorizontal className="h-3 w-3" /> Filters
                              </span>
                              {filterGroups.map((g) => (
                                <span
                                  key={g.label}
                                  className="font-mono text-[10px] px-1.5 py-0.5 border border-lp-border text-text-secondary"
                                >
                                  <span className="text-text-tertiary">{g.label}:</span> {g.values.join(', ')}
                                </span>
                              ))}
                            </div>
                          )}

                          {/* Timestamp */}
                          <div className="flex items-center gap-1 font-mono text-[10px] text-text-tertiary mt-0.5">
                            <Clock className="h-3 w-3" />
                            {formatDate(entry.created_at)}
                          </div>
                        </div>

                        <div className="text-text-tertiary pt-1 shrink-0">
                          {expanded ? (
                            <ChevronUp className="h-4 w-4" />
                          ) : (
                            <ChevronDown className="h-4 w-4" />
                          )}
                        </div>
                      </div>
                    </button>

                    {/* Expanded job list */}
                    {expanded && (
                      <div className="px-5 pb-5 pt-0 space-y-3">
                        <div className="border-t border-lp-border pt-4">
                          {entry.results.length === 0 ? (
                            <p className="font-mono text-xs text-text-tertiary text-center py-4">
                              No job matches were stored for this analysis.
                            </p>
                          ) : (
                            entry.results.map((job, idx) => (
                              <JobCard key={idx} job={job} />
                            ))
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
};

export default HistoryPage;
