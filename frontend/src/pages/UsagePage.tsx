import React from 'react';
import { useAuth, SignInButton } from '@clerk/react';
import Header from '../components/Header';
import { useUsage, QuotaMetric } from '../hooks/useUsage';

function formatReset(resetAt: string | null): string {
  if (!resetAt) return '—';
  const normalized = resetAt.endsWith('Z') || resetAt.includes('+') ? resetAt : resetAt + 'Z';
  const date = new Date(normalized);
  const now = new Date();
  const diffMs = date.getTime() - now.getTime();
  const diffDays = Math.ceil(diffMs / 86400000);
  const abs = date.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
  if (diffDays <= 0) return `today · ${abs}`;
  if (diffDays === 1) return `tomorrow · ${abs}`;
  return `in ${diffDays} days · ${abs}`;
}

interface QuotaCardProps {
  label: string;
  metric: QuotaMetric;
  note?: React.ReactNode;
}

function QuotaCard({ label, metric, note }: QuotaCardProps) {
  const pct = Math.min((metric.used / metric.limit) * 100, 100);
  const atLimit = metric.remaining === 0;

  return (
    <div className="border border-lp-border bg-surface p-6">
      <div className="font-mono text-[10px] uppercase tracking-widest text-text-tertiary mb-4">
        {label}
      </div>

      {/* Counter */}
      <div className="flex items-baseline gap-1.5 mb-5">
        <span className={`font-serif text-4xl leading-none ${atLimit ? 'text-red-500' : 'text-text-primary'}`}>
          {metric.used}
        </span>
        <span className="font-mono text-sm text-text-tertiary">/ {metric.limit}</span>
      </div>

      {/* Progress bar */}
      <div className="w-full h-px bg-lp-border mb-5 overflow-hidden">
        <div
          className={`h-full transition-all duration-500 ${atLimit ? 'bg-red-500' : 'bg-text-primary'}`}
          style={{ width: `${pct}%` }}
        />
      </div>

      {/* Three-column metadata */}
      <div className="grid grid-cols-3 gap-4">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-widest text-text-tertiary mb-1">Used</div>
          <div className="font-serif text-lg text-text-primary leading-none">{metric.used}</div>
        </div>
        <div>
          <div className="font-mono text-[10px] uppercase tracking-widest text-text-tertiary mb-1">Remaining</div>
          <div className={`font-serif text-lg leading-none ${atLimit ? 'text-red-500' : 'text-text-primary'}`}>
            {metric.remaining}
          </div>
        </div>
        <div>
          <div className="font-mono text-[10px] uppercase tracking-widest text-text-tertiary mb-1">Renews</div>
          <div className="font-mono text-xs text-text-secondary leading-snug">
            {formatReset(metric.reset_at)}
          </div>
        </div>
      </div>

      {note && (
        <div className="mt-5 pt-4 border-t border-lp-border">
          <p className="font-mono text-[11px] leading-relaxed text-text-tertiary">{note}</p>
        </div>
      )}
    </div>
  );
}

const UsagePage: React.FC = () => {
  const { isLoaded, isSignedIn } = useAuth();
  const { data, loading, error } = useUsage();

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
            Sign in to view your usage.
          </h2>
          <p className="font-mono text-xs text-text-tertiary mb-8 max-w-sm">
            Your weekly quotas are tied to your account.
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
              Account / Usage
            </span>
          </div>
          <h1 className="font-serif text-3xl text-text-primary">Your usage.</h1>
          <p className="font-mono text-xs text-text-tertiary mt-2">
            Tracked weekly. Resets every seven days from your first request.
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

        {/* Usage cards */}
        {!loading && !error && data && (
          <div className="flex flex-col gap-4">
            <QuotaCard label="Tailored resumes" metric={data.tailor_resume} />
            <QuotaCard label="Think Deeper matches" metric={data.think_deeper} />
            <QuotaCard
              label="Critique"
              metric={data.critique}
              note="Re-viewing a resume you've already critiqued (same file, same industry) is free and doesn't count against this — only a fresh critique does."
            />
            <QuotaCard
              label="Remote compiles — API key"
              metric={data.remote_compile}
              note={
                <>
                  Consumed by your <span className="text-text-secondary">API key</span> when
                  the full MCP agent falls back to server-side resume compilation — separate
                  from the in-app Tailored Resumes quota above. Installing TeX locally, or
                  using Docker, keeps compiles off this quota. Manage keys on the{' '}
                  <a href="/developer" className="underline hover:text-text-primary">Developer page</a>.
                </>
              }
            />

            {/* Explainer */}
            <div className="border border-lp-border bg-surface p-6">
              <div className="font-mono text-[10px] uppercase tracking-widest text-text-tertiary mb-3">
                About these limits
              </div>
              <p className="text-sm text-text-secondary leading-relaxed mb-5">
                Resume tailoring is capped at{' '}
                <span className="font-medium text-text-primary">5/week</span>, Think
                Deeper matches at{' '}
                <span className="font-medium text-text-primary">20/week</span>, and Critique at{' '}
                <span className="font-medium text-text-primary">3/week</span> per account.
                Remote compiles via your API key are capped at{' '}
                <span className="font-medium text-text-primary">15/week</span> — local
                (Docker) compiles are unlimited. Quick matches remain{' '}
                <span className="font-medium text-text-primary">unlimited</span>. Counters
                reset 7 days after each individual use.
              </p>
              <a
                href="mailto:nandikolsujan@gmail.com?subject=Usage%20Limit%20Request&body=Hi%2C%0A%0AI%27d%20like%20to%20request%20higher%20usage%20limits%20for%20my%20account.%0A%0AThanks"
                className="inline-block bg-text-primary text-bg px-5 py-2.5 font-mono text-xs tracking-wide hover:opacity-80 transition-opacity focus:outline-none focus-visible:ring-2 focus-visible:ring-text-primary focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
              >
                Need higher limits? Contact us →
              </a>
            </div>
          </div>
        )}
      </main>
    </div>
  );
};

export default UsagePage;
