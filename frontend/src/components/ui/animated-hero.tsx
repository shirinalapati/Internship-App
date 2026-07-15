import React from 'react';
import { Link } from 'react-router-dom';
import heroData from '../../data/landing-hero.json';

function Hero() {
  const { sampleRole } = heroData;

  return (
    <section className="py-16 md:py-20 border-b border-lp-border">
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_288px] gap-10 lg:gap-16 items-start">
        {/* Left: text */}
        <div>
          {/* Kicker */}
          <div className="flex items-center gap-3 mb-7">
            <span className="block w-8 h-px bg-text-tertiary flex-shrink-0" />
            <span className="font-mono text-[10px] uppercase tracking-widest text-text-secondary">
              An honest shot at getting hired
            </span>
          </div>

          <h1 className="font-serif text-[2.6rem] md:text-5xl text-text-primary leading-[1.1] mb-5">
            An AI that's <em className="italic">working</em> to get you hired.
          </h1>

          <p className="text-sm text-text-secondary leading-relaxed max-w-md mb-8">
            We rank your shot at every live internship, flag what's actually holding your
            résumé back, and rewrite it until it's ready to land interviews. Free, built by a
            CS student at SJSU — no keyword roulette, no recruiter middleware, no ads.
          </p>

          <div className="flex items-center gap-5">
            <Link
              to="/find"
              className="inline-block bg-text-primary text-bg px-5 py-2.5 font-mono text-xs tracking-wide hover:opacity-80 transition-opacity focus:outline-none focus-visible:ring-2 focus-visible:ring-text-primary focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
            >
              Upload My Résumé
            </Link>
            <span className="font-mono text-[11px] text-text-tertiary">~30s</span>
          </div>
        </div>

        {/* Right: sample clip card */}
        <aside className="border border-lp-border bg-surface p-5 self-start">
          <div className="font-mono text-[10px] uppercase tracking-widest text-text-tertiary mb-3">
            Sample · 94 of 100
          </div>
          <div className="font-serif text-lg text-text-primary leading-snug mb-1">
            {sampleRole.title}
          </div>
          <div className="font-mono text-[11px] text-text-secondary mb-4">
            {sampleRole.company} · {sampleRole.location} · {sampleRole.term}
          </div>
          <div className="font-serif text-5xl text-text-primary leading-none mb-3">
            {sampleRole.score}
            <sup className="font-mono text-sm align-super">/100</sup>
          </div>
          <div className="flex gap-1.5 flex-wrap mb-3">
            {sampleRole.matchedSkills.map((s) => (
              <span
                key={s}
                className="font-mono text-[10px] px-1.5 py-0.5 border border-lp-border text-text-secondary"
              >
                {s}
              </span>
            ))}
          </div>
          <p className="text-[11px] text-text-secondary leading-relaxed border-t border-lp-border pt-3">
            {sampleRole.explanation}
          </p>
        </aside>
      </div>
    </section>
  );
}

export { Hero };
