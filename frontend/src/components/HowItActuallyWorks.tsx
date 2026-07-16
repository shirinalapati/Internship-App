import React from 'react';

const TOKENS = ['name', 'email', 'Python', 'React', 'TypeScript', '2 yrs', 'FastAPI', 'SQL', 'Git', 'REST APIs'];
const SKILLS = new Set(['Python', 'React', 'TypeScript', 'FastAPI', 'SQL', 'Git', 'REST APIs']);

const CIRCUMFERENCE = 2 * Math.PI * 27; // ≈169.65
const OFFSET = CIRCUMFERENCE * (1 - 0.94); // 94% fill

const steps = [
  {
    n: '— i —',
    title: 'Parse',
    desc: 'Extract skills, frameworks, and stated experience levels from a PDF.',
    visual: (
      <div className="flex flex-wrap gap-1.5 mt-5">
        {TOKENS.map((token) => (
          <span
            key={token}
            className={`font-mono text-[10px] px-1.5 py-0.5 border ${
              SKILLS.has(token)
                ? 'border-text-primary text-text-primary'
                : 'border-lp-border text-text-tertiary'
            }`}
          >
            {token}
          </span>
        ))}
      </div>
    ),
  },
  {
    n: '— ii —',
    title: 'Rank',
    desc: 'Score every live posting against your profile. Skill coverage, level fit, location preference.',
    visual: (
      <div className="flex items-center gap-4 mt-5">
        <svg viewBox="0 0 60 60" className="w-14 h-14 flex-shrink-0" aria-hidden="true">
          <circle
            cx="30" cy="30" r="27" fill="none" strokeWidth="3"
            style={{ stroke: 'var(--lp-border)' }}
          />
          <circle
            cx="30" cy="30" r="27" fill="none" strokeWidth="3"
            style={{ stroke: 'var(--lp-text-primary)' }}
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={OFFSET}
            transform="rotate(-90 30 30)"
          />
        </svg>
        <div>
          <div className="font-serif text-2xl text-text-primary">94 / 100</div>
          <div className="font-mono text-[10px] text-text-tertiary mt-0.5">
            Ramp · 4 of 5 skills · NY
          </div>
        </div>
      </div>
    ),
  },
  {
    n: '— iii —',
    title: 'Read',
    desc: 'Open the top ten with one-line reasoning on why you\'re a fit, then apply with a résumé that\'s actually ready to land the interview.',
    visual: (
      <div className="mt-5 space-y-1.5">
        {[['Ramp', '94'], ['Linear', '88'], ['Vercel', '81']].map(([co, score]) => (
          <div key={co} className="font-mono text-xs text-text-secondary flex justify-between">
            <span>{co}</span>
            <span className="text-text-primary">{score}</span>
          </div>
        ))}
      </div>
    ),
  },
];

export function HowItActuallyWorks({ activeJobs }: { activeJobs: number | null }) {
  const jobCount = activeJobs != null ? activeJobs.toLocaleString() : '—';
  return (
    <section className="py-14 border-b border-lp-border" id="how-it-works">
      {/* Kicker */}
      <div className="flex items-center gap-3 mb-6">
        <span className="block w-8 h-px bg-text-tertiary flex-shrink-0" />
        <span className="font-mono text-[10px] uppercase tracking-widest text-text-secondary">
          The method
        </span>
      </div>

      <h2 className="font-serif text-3xl text-text-primary mb-4">How it actually works.</h2>
      <p className="text-sm text-text-secondary leading-relaxed max-w-xl mb-10">
        It reads your resume like a person would, then scores all {jobCount} live postings against
        your skills — so you know which ones are worth your time, and what to fix so more of
        them call you back.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
        {steps.map((step, i) => (
          <div
            key={step.n}
            className={i > 0 ? 'md:border-l md:border-lp-border md:pl-8' : ''}
          >
            <div className="font-mono text-[10px] text-text-tertiary tracking-widest mb-3">
              {step.n}
            </div>
            <h3 className="font-serif text-xl text-text-primary mb-2">{step.title}</h3>
            <p className="text-xs text-text-secondary leading-relaxed">{step.desc}</p>
            {step.visual}
          </div>
        ))}
      </div>
    </section>
  );
}
