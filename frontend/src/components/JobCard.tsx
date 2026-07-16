import React, { useState } from 'react';
import { Job } from '../types';
import { ExternalLink, ChevronDown, ChevronUp, AlertTriangle, Target, CheckCircle2, Bookmark, BookmarkCheck } from 'lucide-react';

interface JobCardProps {
  job: Job;
  isNewResult?: boolean;
  resumeFile?: File | null;
  apiBaseUrl?: string;
  authToken?: string | null;
  isSaved?: boolean;
  onSavedChange?: (jobHash: string, saved: boolean) => void;
}

const JobCard: React.FC<JobCardProps> = ({ job, isNewResult = false, resumeFile, apiBaseUrl = '', authToken, isSaved = false, onSavedChange }) => {
  const [showReasoning, setShowReasoning] = useState(false);
  const [isTailoring, setIsTailoring] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [tailorError, setTailorError] = useState('');
  const [saveError, setSaveError] = useState('');
  const [templateId, setTemplateId] = useState<'classic' | 'modern'>('classic');

  const formatRelativeReset = (date: Date): string => {
    const diffMs = date.getTime() - Date.now();
    const diffDays = Math.ceil(diffMs / 86400000);
    if (diffDays <= 0) return 'soon';
    if (diffDays === 1) return 'tomorrow';
    return `in ${diffDays} days`;
  };

  const handleTailorResume = async () => {
    if (!resumeFile) return;
    setIsTailoring(true);
    setTailorError('');
    try {
      const formData = new FormData();
      formData.append('resume', resumeFile);
      formData.append('job_title', job.title || '');
      formData.append('company', job.company || '');
      // job_hash lets the backend look up the FULL job description; job_description
      // is sent as a fallback for results that predate job_hash.
      formData.append('job_hash', job.job_hash || '');
      formData.append('job_description', job.description || '');
      formData.append('template_id', templateId);

      const response = await fetch(`${apiBaseUrl}/api/tailor-resume`, {
        method: 'POST',
        body: formData,
        headers: authToken ? { Authorization: `Bearer ${authToken}` } : undefined,
      });

      if (!response.ok) {
        if (response.status === 429) {
          let resetMsg = '';
          try {
            const body = await response.json();
            const resetAt = body?.detail?.reset_at ? new Date(body.detail.reset_at) : null;
            if (resetAt) resetMsg = ` Resets ${formatRelativeReset(resetAt)}.`;
          } catch {}
          throw new Error(`You've hit the weekly limit for tailor resumes.${resetMsg}`);
        }
        const errText = await response.text();
        throw new Error(errText || `Server error ${response.status}`);
      }

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `resume_tailored_${job.company}_${job.title}.pdf`.replace(/[^\w\-_.]/g, '_');
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err: any) {
      setTailorError(err.message || 'Failed to tailor resume. Please try again.');
    } finally {
      setIsTailoring(false);
    }
  };

  const handleSaveToggle = async () => {
    if (!job.job_hash || !authToken || !onSavedChange) return;
    setIsSaving(true);
    setSaveError('');
    try {
      const response = await fetch(`${apiBaseUrl}/api/saved-jobs${isSaved ? `/${job.job_hash}` : ''}`, {
        method: isSaved ? 'DELETE' : 'POST',
        headers: {
          Authorization: `Bearer ${authToken}`,
          ...(isSaved ? {} : { 'Content-Type': 'application/json' }),
        },
        body: isSaved ? undefined : JSON.stringify({ job_hash: job.job_hash, job_snapshot: job }),
      });
      if (!response.ok) {
        throw new Error(isSaved ? 'Could not remove saved job.' : 'Could not save job.');
      }
      onSavedChange(job.job_hash, !isSaved);
    } catch (err: any) {
      setSaveError(err.message || 'Could not update saved job.');
    } finally {
      setIsSaving(false);
    }
  };

  const score = job.match_score || job.score || 0;
  const hasReasoning = job.ai_reasoning && job.ai_reasoning.reasoning;

  const getTimeAgo = (dateString?: string): string => {
    if (!dateString) return '';
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMs <= 0) return 'just now';
    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins} min ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) return `${diffDays}d ago`;
    const weeks = Math.floor(diffDays / 7);
    if (diffDays < 30) return `${weeks}w ago`;
    const months = Math.floor(diffDays / 30);
    return `${months}mo ago`;
  };

  const isNewJob = (dateString?: string): boolean => {
    if (!dateString) return false;
    return (new Date().getTime() - new Date(dateString).getTime()) / 3600000 <= 48;
  };

  const timeAgo = getTimeAgo(job.first_seen);
  const showNewIndicator = isNewJob(job.first_seen);

  const CUE_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
    '🎯': Target,
    '✅': CheckCircle2,
    '⚠️': AlertTriangle,
    '⚠': AlertTriangle,
  };

  const formatMatchDescription = (desc: string) => {
    if (!desc) return [];
    return desc
      .split('\n')
      .map((line, index) => {
        const trimmed = line.trim();
        if (!trimmed) return null;

        // Detect leading status emoji and map to Lucide icon
        const cueKey = Object.keys(CUE_ICONS).find(k => trimmed.startsWith(k));
        const Icon = cueKey ? CUE_ICONS[cueKey] : null;
        const text = cueKey ? trimmed.slice(cueKey.length).trimStart() : trimmed;

        // Render **bold** spans as JSX — no dangerouslySetInnerHTML
        const parts = text.split(/(\*\*.*?\*\*)/g);
        const content = parts.map((part, i) => {
          if (part.startsWith('**') && part.endsWith('**')) {
            return <strong key={i} className="font-semibold">{part.slice(2, -2)}</strong>;
          }
          return part;
        });

        return (
          <p
            key={index}
            className={`text-sm text-text-secondary flex items-start gap-1.5${trimmed.startsWith('•') ? ' ml-2' : ''}`}
          >
            {Icon && <Icon className="h-3.5 w-3.5 mt-0.5 shrink-0 text-ia" />}
            <span>{content}</span>
          </p>
        );
      })
      .filter(Boolean);
  };

  const scoreColor = score >= 90 ? 'text-emerald-400' : score >= 80 ? 'text-ia' : 'text-text-secondary';
  const barColor = score >= 90 ? 'bg-emerald-400' : score >= 80 ? 'bg-ia' : 'bg-slate-500';

  return (
    <div className="bg-surface border border-lp-border p-5">
      {/* Header row */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-text-primary text-base font-semibold leading-snug">{job.title}</span>
            {showNewIndicator && (
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse flex-shrink-0" />
            )}
          </div>
          <div className="text-text-secondary text-sm">{job.company}</div>
          <div className="flex items-center gap-2 mt-1 text-text-tertiary text-xs">
            {job.location && <span>{job.location}</span>}
            {timeAgo && <span>· {timeAgo}</span>}
          </div>
        </div>

        {/* Score */}
        <div className="shrink-0 text-right">
          <div className={`font-serif text-2xl leading-none ${scoreColor}`}>{score}%</div>
          <div className="text-text-tertiary text-[10px] mt-0.5">match</div>
          <div className="w-16 h-0.5 bg-lp-border rounded-full overflow-hidden mt-1.5 ml-auto">
            <div className={`h-full rounded-full ${barColor}`} style={{ width: `${score}%` }} />
          </div>
        </div>
      </div>

      {/* Required skills */}
      {job.required_skills && job.required_skills.length > 0 && (
        <div className="mt-3 pt-3 border-t border-lp-border">
          <div className="text-text-tertiary text-[10px] uppercase tracking-wider mb-1.5">Required skills</div>
          <div className="flex flex-wrap gap-1">
            {job.required_skills.slice(0, 8).map((skill, i) => (
              <span key={i} className="text-[10px] px-1.5 py-0.5 bg-ia-subtle text-ia-pill rounded font-mono">
                {skill}
              </span>
            ))}
            {job.required_skills.length > 8 && (
              <span className="text-[10px] px-1.5 py-0.5 bg-surface text-text-tertiary rounded font-mono border border-lp-border">
                +{job.required_skills.length - 8}
              </span>
            )}
          </div>
        </div>
      )}

      {/* Why it fits */}
      {job.match_description && (
        <div className="mt-3 pt-3 border-t border-lp-border">
          <div className="text-text-tertiary text-[10px] uppercase tracking-wider mb-1.5">Why it fits</div>
          <div className="space-y-1">{formatMatchDescription(job.match_description)}</div>
        </div>
      )}

      {/* Reasoning (Think Deeper) */}
      {hasReasoning && (
        <div className="mt-3 pt-3 border-t border-lp-border">
          <button
            type="button"
            onClick={() => setShowReasoning(!showReasoning)}
            aria-expanded={showReasoning}
            className="flex items-center gap-1.5 text-text-tertiary text-[10px] uppercase tracking-wider hover:text-text-secondary transition-colors w-full text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ia focus-visible:ring-offset-2 focus-visible:ring-offset-bg rounded"
          >
            <span>Reasoning</span>
            {showReasoning ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          </button>

          {showReasoning && job.ai_reasoning && (
            <div className="mt-3 space-y-3">
              {(job.ai_reasoning.resume_complexity || job.ai_reasoning.experience_match) && (
                <div className="flex items-center gap-2 flex-wrap">
                  {job.ai_reasoning.resume_complexity && (
                    <span className="text-[10px] px-1.5 py-0.5 bg-ia-subtle text-ia-pill rounded font-mono">
                      {job.ai_reasoning.resume_complexity}
                      {job.ai_reasoning.complexity_score !== undefined && ` (${job.ai_reasoning.complexity_score}/100)`}
                    </span>
                  )}
                  {job.ai_reasoning.experience_match && (
                    <span className="text-[10px] px-1.5 py-0.5 bg-ia-subtle text-ia-pill rounded font-mono">
                      {job.ai_reasoning.experience_match} fit
                    </span>
                  )}
                </div>
              )}

              <p className="text-sm text-text-secondary leading-relaxed">{job.ai_reasoning.reasoning}</p>

              {job.ai_reasoning.skill_matches && job.ai_reasoning.skill_matches.length > 0 && (
                <div>
                  <div className="text-text-tertiary text-[10px] uppercase tracking-wider mb-1">Your matching skills</div>
                  <div className="flex flex-wrap gap-1">
                    {job.ai_reasoning.skill_matches.map((s, i) => (
                      <span key={i} className="text-[10px] px-1.5 py-0.5 bg-surface border border-lp-border text-text-secondary font-mono">
                        {s}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {job.ai_reasoning.skill_gaps && job.ai_reasoning.skill_gaps.length > 0 && (
                <div>
                  <div className="text-text-tertiary text-[10px] uppercase tracking-wider mb-1">Skills to develop</div>
                  <div className="flex flex-wrap gap-1">
                    {job.ai_reasoning.skill_gaps.slice(0, 5).map((s, i) => (
                      <span key={i} className="text-[10px] px-1.5 py-0.5 bg-surface text-text-tertiary rounded font-mono border border-lp-border">
                        {s}
                      </span>
                    ))}
                    {job.ai_reasoning.skill_gaps.length > 5 && (
                      <span className="text-[10px] px-1.5 py-0.5 bg-surface text-text-tertiary rounded font-mono border border-lp-border">
                        +{job.ai_reasoning.skill_gaps.length - 5}
                      </span>
                    )}
                  </div>
                </div>
              )}

              {job.ai_reasoning.red_flags && job.ai_reasoning.red_flags.length > 0 && (
                <div>
                  <div className="text-text-tertiary text-[10px] uppercase tracking-wider mb-1 flex items-center gap-1">
                    <AlertTriangle className="h-3 w-3" />
                    Considerations
                  </div>
                  <ul className="space-y-1">
                    {job.ai_reasoning.red_flags.map((flag, i) => (
                      <li key={i} className="text-sm text-red-500 flex items-start gap-2">
                        <span className="text-red-400 mt-1 shrink-0">·</span>
                        {flag}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Actions */}
      {((job.apply_link || job.url) || resumeFile || (authToken && onSavedChange && job.job_hash)) && (
        <div className="mt-4 pt-4 border-t border-lp-border flex flex-wrap gap-3 items-center">
          {authToken && onSavedChange && job.job_hash && (
            <button
              onClick={handleSaveToggle}
              disabled={isSaving}
              className="inline-flex items-center gap-1.5 border border-lp-border px-3 py-1.5 text-xs font-mono text-text-secondary hover:text-text-primary transition-colors disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-text-primary focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
            >
              {isSaved ? <BookmarkCheck className="h-3.5 w-3.5" /> : <Bookmark className="h-3.5 w-3.5" />}
              {isSaving ? 'Saving...' : isSaved ? 'Saved' : 'Save'}
            </button>
          )}
          {(job.apply_link || job.url) && (
            <button
              onClick={() => window.open(job.apply_link || job.url, '_blank', 'noopener,noreferrer')}
              className="inline-flex items-center gap-1.5 bg-text-primary text-bg px-3 py-1.5 text-xs font-mono hover:opacity-80 transition-opacity focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-text-primary focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              Apply Now
            </button>
          )}
          {resumeFile && (
            <div className="flex items-center gap-2">
              <div className="inline-flex border border-text-primary/20 text-[10px] font-mono">
                {(['classic', 'modern'] as const).map((id) => (
                  <button
                    key={id}
                    type="button"
                    onClick={() => setTemplateId(id)}
                    disabled={isTailoring}
                    aria-pressed={templateId === id}
                    className={`px-2 py-1 capitalize transition-colors disabled:opacity-50 ${
                      templateId === id
                        ? 'bg-text-primary text-bg'
                        : 'text-text-primary/60 hover:text-text-primary'
                    }`}
                  >
                    {id}
                  </button>
                ))}
              </div>
              <button
                onClick={handleTailorResume}
                disabled={isTailoring}
                className="text-ia hover:text-ia-hover text-xs font-medium transition-colors disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ia focus-visible:ring-offset-2 focus-visible:ring-offset-bg rounded"
              >
                {isTailoring ? 'Tailoring...' : 'Tailor Resume for This Job'}
              </button>
            </div>
          )}
          {tailorError && (
              <div className="w-full border border-red-500/40 bg-red-500/5 px-3 py-2">
                <p className="font-mono text-xs text-red-500">{tailorError}</p>
              </div>
            )}
          {saveError && (
            <div className="w-full border border-red-500/40 bg-red-500/5 px-3 py-2">
              <p className="font-mono text-xs text-red-500">{saveError}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default JobCard;
