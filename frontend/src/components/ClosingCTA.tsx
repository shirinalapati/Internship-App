import React from 'react';
import { Link } from 'react-router-dom';

export function ClosingCTA({ activeJobs }: { activeJobs: number | null }) {
  const count = activeJobs != null ? `${activeJobs.toLocaleString()} live internships` : 'Live internships';
  return (
    <section className="py-16 md:py-20">
      <h2 className="font-serif text-3xl md:text-4xl text-text-primary leading-[1.15] mb-8 max-w-lg">
        {count}. Scored by your shot at getting hired —{' '}
        <em className="italic">in 30 seconds.</em>
      </h2>
      <div className="flex items-center gap-5">
        <Link
          to="/find"
          className="inline-block bg-text-primary text-bg px-5 py-2.5 font-mono text-xs tracking-wide hover:opacity-80 transition-opacity focus:outline-none focus-visible:ring-2 focus-visible:ring-text-primary focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
        >
          Upload My Résumé
        </Link>
        <span className="font-mono text-[11px] text-text-tertiary">$0, and it stays that way</span>
      </div>
    </section>
  );
}
