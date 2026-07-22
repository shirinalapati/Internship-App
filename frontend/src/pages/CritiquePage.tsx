import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth, SignInButton } from '@clerk/react';
import { Upload, CheckCircle2, Sparkles, Eye, PenLine, Download } from 'lucide-react';
import * as pdfjsLib from 'pdfjs-dist';
import Header from '../components/Header';
import Logo from '../components/Logo';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { DEPARTMENT_CATEGORIES } from '../components/ui/department-multi-select';
import { API_BASE_URL } from '../lib/api';
import classicThumb from '../assets/resume-templates/classic-thumb.png';
import modernThumb from '../assets/resume-templates/modern-thumb.png';

// pdfjs needs its worker script served as a real URL — webpack 5 (react-scripts 5)
// resolves this `new URL(..., import.meta.url)` pattern into a bundled asset at build
// time, so the worker ships with our own build instead of depending on a CDN at runtime.
pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url
).toString();

// ---------------------------------------------------------------------------
// Types — mirror resume_critique.critique_resume.critique_resume_to_json output
// ---------------------------------------------------------------------------

interface CritiqueBullet {
  id: string;
  text: string;
}
interface ExperienceEntry {
  company: string;
  location?: string;
  title: string;
  dates: string;
  bullets: CritiqueBullet[];
}
interface ProjectEntry {
  name: string;
  dates: string;
  bullets: CritiqueBullet[];
}
interface EducationEntry {
  school: string;
  location?: string;
  degree: string;
  dates: string;
}
interface CritiqueFlag {
  bullet_id: string;
  severity: 'red' | 'yellow' | 'green';
  comment: string;
}
// Mirrors resume_tailor.tailor_resume.get_bullet_page_positions's return shape —
// top_frac/left_frac are fractions (0.0-1.0) of the compiled PDF page's height/width,
// with top_frac increasing DOWN the page (0.0 = top edge). See that function's
// docstring for the full coordinate-convention writeup.
interface BulletPosition {
  bullet_id: string;
  top_frac: number;
  left_frac: number;
}
interface CritiqueResult {
  name: string;
  email?: string;
  phone?: string;
  website?: string;
  github?: string;
  linkedin?: string;
  education: EducationEntry[];
  experience: ExperienceEntry[];
  projects: ProjectEntry[];
  skills: Record<string, string>;
  detected_category: string;
  critiques: CritiqueFlag[];
  cached: boolean;
  // Real compiled PDF of the as-critiqued resume + per-bullet coordinates on it, so the
  // review pane can render the actual pdflatex output with dots overlaid instead of an
  // HTML mockup (issue #79). Optional because older cached critique entries (compiled
  // before this field existed) or a server-side compile failure won't have it.
  pdf_base64?: string;
  bullet_positions?: BulletPosition[];
}

const SEVERITY: Record<
  CritiqueFlag['severity'],
  { dot: string; ring: string; label: string; labelColor: string }
> = {
  green: { dot: 'hsl(142 72% 45%)', ring: 'hsl(142 72% 45% / 0.16)', label: 'Strong', labelColor: 'hsl(142 72% 38%)' },
  yellow: { dot: 'hsl(38 92% 55%)', ring: 'hsl(38 92% 55% / 0.18)', label: 'Needs work', labelColor: 'hsl(38 80% 40%)' },
  red: { dot: 'hsl(0 84% 60%)', ring: 'hsl(0 84% 60% / 0.16)', label: 'Rewrite', labelColor: 'hsl(0 72% 48%)' },
};

const contactLine = (r: CritiqueResult) =>
  [r.email, r.phone, r.website, r.github].filter(Boolean).join('  ·  ');

// ---------------------------------------------------------------------------
// Tailored-result / diff view — Current vs Tailored tabs + Single/Compare toggle
// ---------------------------------------------------------------------------

interface TailoredResult {
  structured: any;
  pdfBase64: string;
  rewrittenIds: string[];
}

interface DiffBullet {
  id: string;
  current: string;
  tailored: string;
  changed: boolean;
}
type DiffBlock =
  | { kind: 'header'; name: string; contact: string }
  | { kind: 'heading'; text: string }
  | { kind: 'entry'; title: string; date: string }
  | { kind: 'bullets'; items: DiffBullet[] };

function buildDiffBlocks(current: CritiqueResult, tailoredStructured: any, rewrittenIds: string[]): DiffBlock[] {
  const rewrittenSet = new Set(rewrittenIds);
  const blocks: DiffBlock[] = [{ kind: 'header', name: current.name, contact: contactLine(current) }];

  if (current.experience.length > 0) {
    blocks.push({ kind: 'heading', text: 'Experience' });
    current.experience.forEach((exp, i) => {
      const tExp = tailoredStructured?.experience?.[i];
      blocks.push({ kind: 'entry', title: `${exp.title} — ${exp.company}`, date: exp.dates });
      blocks.push({
        kind: 'bullets',
        items: exp.bullets.map((b, j) => ({
          id: b.id,
          current: b.text,
          tailored: tExp?.bullets?.[j]?.text ?? b.text,
          changed: rewrittenSet.has(b.id),
        })),
      });
    });
  }

  if (current.projects.length > 0) {
    blocks.push({ kind: 'heading', text: 'Projects' });
    current.projects.forEach((proj, i) => {
      const tProj = tailoredStructured?.projects?.[i];
      blocks.push({ kind: 'entry', title: proj.name, date: proj.dates });
      blocks.push({
        kind: 'bullets',
        items: proj.bullets.map((b, j) => ({
          id: b.id,
          current: b.text,
          tailored: tProj?.bullets?.[j]?.text ?? b.text,
          changed: rewrittenSet.has(b.id),
        })),
      });
    });
  }

  return blocks;
}

// Mirrors the real compiled PDF's US Letter proportions (612x792pt, ratio 0.773) AND its
// page-fill behavior (resume_tailor._lock_font grows font size to fill slack, shrinks to
// avoid overflow) so the on-screen mock resume reads as an actual page instead of a fixed-font
// column that leaves a blank void under short content or clips long content. We can't use CSS
// `zoom` to grow — zoom scales width too, and width is fixed by the frame, so growing that way
// would clip content on the sides. Instead we scale font sizes directly (via `fontScale`) and
// leave padding/width untouched, then measure and converge over a few passes.
const PAGE_WIDTH = 720;
const PAGE_HEIGHT = Math.round(PAGE_WIDTH * (11 / 8.5));
const FONT_SCALE_MIN = 0.65;
const FONT_SCALE_MAX = 1.6;
const FONT_SCALE_MAX_ITERATIONS = 4;

function ResumeDiffPage({
  blocks,
  variant,
  showChanges,
  compact,
}: {
  blocks: DiffBlock[];
  variant: 'current' | 'tailored';
  showChanges: boolean;
  compact?: boolean;
}) {
  const accent = variant === 'tailored' ? 'hsl(142 72% 45%)' : 'hsl(38 92% 55%)';
  const tint = variant === 'tailored' ? 'hsl(142 72% 45% / 0.10)' : 'hsl(38 92% 55% / 0.11)';
  const tagColor = variant === 'tailored' ? 'hsl(142 72% 34%)' : 'hsl(38 78% 38%)';
  const tagText = variant === 'tailored' ? 'rewritten' : 'flagged';
  const baseFs = compact ? 11 : 13;

  const contentRef = useRef<HTMLDivElement>(null);
  const [fontScale, setFontScale] = useState(1);
  const iterationRef = useRef(0);

  // Resets the search whenever the underlying content changes (new resume, new critiques).
  React.useLayoutEffect(() => {
    iterationRef.current = 0;
    setFontScale(1);
  }, [blocks]);

  // Converges fontScale toward whatever fills PAGE_HEIGHT as closely as possible, in a few
  // measure-and-correct passes (font-size changes don't scale height linearly — margins and
  // gaps stay fixed — so one shot rarely lands exactly on target).
  React.useLayoutEffect(() => {
    const el = contentRef.current;
    if (!el || iterationRef.current >= FONT_SCALE_MAX_ITERATIONS) return;
    const measuredHeight = el.scrollHeight;
    const ratio = PAGE_HEIGHT / measuredHeight;
    if (Math.abs(ratio - 1) < 0.02) return;
    const next = Math.min(FONT_SCALE_MAX, Math.max(FONT_SCALE_MIN, fontScale * ratio));
    if (Math.abs(next - fontScale) < 0.01) return;
    iterationRef.current += 1;
    setFontScale(next);
  }, [blocks, fontScale]);

  const sz = (px: number) => px * fontScale;

  return (
    <div
      style={{
        width: PAGE_WIDTH,
        height: PAGE_HEIGHT,
        background: '#FDFCFA',
        border: '1px solid rgba(31,27,22,0.08)',
        borderRadius: 2,
        boxShadow: '0 1px 2px rgba(31,27,22,0.08), 0 16px 48px rgba(31,27,22,0.12)',
        boxSizing: 'border-box',
        overflow: 'hidden',
      }}
    >
    <div
      ref={contentRef}
      style={{
        padding: '52px 60px 60px',
        boxSizing: 'border-box',
        fontFamily: "'Source Serif 4', Georgia, serif",
        color: '#1a1a1a',
      }}
    >
      {blocks.map((block, i) => {
        if (block.kind === 'header') {
          return (
            <div key={i} style={{ textAlign: 'center' }}>
              <div style={{ fontSize: sz(25), fontWeight: 700, letterSpacing: '0.01em' }}>{block.name}</div>
              <div style={{ fontSize: sz(12), color: '#444', marginTop: 6 }}>{block.contact}</div>
            </div>
          );
        }
        if (block.kind === 'heading') {
          return (
            <div
              key={i}
              style={{
                fontSize: sz(12), fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase',
                borderBottom: '1px solid #1a1a1a', paddingBottom: 4, margin: '26px 0 11px',
              }}
            >
              {block.text}
            </div>
          );
        }
        if (block.kind === 'entry') {
          return (
            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginTop: 14 }}>
              <div style={{ fontSize: sz(13.5), fontWeight: 700 }}>{block.title}</div>
              <div style={{ fontSize: sz(12), fontStyle: 'italic', color: '#444', whiteSpace: 'nowrap', paddingLeft: 14 }}>{block.date}</div>
            </div>
          );
        }
        // bullets
        return (
          <ul key={i} style={{ listStyle: 'none', margin: '7px 0 0', padding: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
            {block.items.map((it) => {
              const changed = it.changed && showChanges;
              const text = variant === 'tailored' ? it.tailored : it.current;
              return (
                <li
                  key={it.id}
                  style={
                    changed
                      ? { position: 'relative', paddingLeft: 18, paddingTop: 4, paddingBottom: 4, paddingRight: 10, fontSize: sz(baseFs), lineHeight: 1.5, background: tint, boxShadow: `inset 2px 0 0 ${accent}`, borderRadius: 4 }
                      : { position: 'relative', paddingLeft: 16, fontSize: sz(baseFs), lineHeight: 1.5 }
                  }
                >
                  <span style={{ position: 'absolute', left: changed ? 8 : 2, top: changed ? 4 : 0, color: '#666' }}>•</span>
                  {text}
                  {changed && (
                    <span style={{ marginLeft: 6, fontFamily: "'Source Sans 3', sans-serif", fontSize: sz(9.5), fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: tagColor, verticalAlign: '1.5px', whiteSpace: 'nowrap' }}>
                      {tagText}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        );
      })}
    </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tailor-résumé fan/notes trigger — replaces the old purple "Generate my
// improved resume" CTA (GitHub #79: "use this design choice from claude
// design: E · Ink pill, emerald accent bar"). Floats bottom-right over the
// resume preview pane. State machine: idle -> fan -> notes -> (generating
// driven by the real `generating` prop, not a local timer).
// ---------------------------------------------------------------------------

const TAILOR_ACCENT = 'hsl(142 72% 45%)'; // matches this file's existing "tailored" green accent
const TAILOR_EASE = 'cubic-bezier(.22,.61,.36,1)';

type TailorTemplateId = 'classic' | 'modern';

const TAILOR_TEMPLATES: { id: TailorTemplateId; label: string; thumb: string }[] = [
  { id: 'modern', label: 'Modern', thumb: modernThumb },
  { id: 'classic', label: 'Classic', thumb: classicThumb },
];

function TailorTrigger({
  mode,
  onModeChange,
  sel,
  onSelChange,
  extraContext,
  onExtraContextChange,
  generating,
  rewritableCount,
  onGenerate,
}: {
  mode: 'idle' | 'fan' | 'notes';
  onModeChange: (m: 'idle' | 'fan' | 'notes') => void;
  sel: TailorTemplateId;
  onSelChange: (t: TailorTemplateId) => void;
  extraContext: string;
  onExtraContextChange: (v: string) => void;
  generating: boolean;
  rewritableCount: number;
  onGenerate: () => void;
}) {
  const fanOpen = mode === 'fan';
  const panelOpen = mode === 'notes' || generating;
  const selLabel = sel === 'classic' ? 'Classic' : 'Modern';
  const selThumb = sel === 'classic' ? classicThumb : modernThumb;

  const fanCardStyle = (dx: number, dy: number, rot: number, delay: string): React.CSSProperties => ({
    position: 'absolute',
    right: 0,
    bottom: 0,
    width: 172,
    background: '#1E293B',
    border: '1px solid rgba(148,163,184,0.2)',
    borderRadius: 12,
    overflow: 'hidden',
    boxShadow: '0 18px 40px rgba(0,0,0,0.5)',
    transformOrigin: 'bottom right',
    opacity: fanOpen ? 1 : 0,
    transform: fanOpen ? `translate(${dx}px,${dy}px) rotate(${rot}deg)` : 'translate(0,0) scale(0.5)',
    pointerEvents: fanOpen ? 'auto' : 'none',
    transition: `opacity .25s ease ${delay}, transform .4s ${TAILOR_EASE} ${delay}`,
  });

  return (
    <div
      onMouseEnter={() => { if (mode === 'idle') onModeChange('fan'); }}
      onMouseLeave={() => { if (mode === 'fan') onModeChange('idle'); }}
      style={{ position: 'absolute', right: 28, bottom: 28, zIndex: 5 }}
    >
      {/* fan cards */}
      {TAILOR_TEMPLATES.map((t) => {
        const isClassic = t.id === 'classic';
        const style = isClassic ? fanCardStyle(-4, -16, -4, '.02s') : fanCardStyle(-192, -34, 3, '.09s');
        return (
          <div key={t.id} style={style}>
            <img
              src={t.thumb}
              alt={`${t.label} template preview`}
              style={{ display: 'block', width: '100%', height: 116, objectFit: 'cover', objectPosition: 'top center' }}
            />
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 11px' }}>
              <span style={{ fontSize: 13, fontWeight: 700, color: '#F1F5F9' }}>{t.label}</span>
              <button
                type="button"
                onClick={() => { onSelChange(t.id); onModeChange('notes'); }}
                style={
                  isClassic
                    ? { height: 28, padding: '0 11px', border: 'none', borderRadius: 999, background: '#F1F5F9', color: '#0F172A', fontSize: '11.5px', fontWeight: 600, cursor: 'pointer', boxShadow: `inset 3px 0 0 ${TAILOR_ACCENT}` }
                    : { height: 28, padding: '0 11px', border: '1px solid rgba(148,163,184,0.3)', borderRadius: 999, background: 'transparent', color: '#E2E8F0', fontSize: '11.5px', fontWeight: 600, cursor: 'pointer' }
                }
              >
                Use →
              </button>
            </div>
          </div>
        );
      })}

      {/* resting pill */}
      <div
        role="button"
        tabIndex={0}
        onClick={() => onModeChange('fan')}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 9,
          height: 46,
          padding: '0 20px',
          borderRadius: 999,
          background: '#F1F5F9',
          color: '#0F172A',
          fontWeight: 600,
          fontSize: 14,
          fontFamily: "'Source Sans 3', sans-serif",
          boxShadow: `inset 3px 0 0 ${TAILOR_ACCENT}, 0 8px 22px rgba(0,0,0,0.4)`,
          cursor: 'pointer',
          opacity: fanOpen || panelOpen ? 0 : 1,
          transform: fanOpen || panelOpen ? 'scale(0.9)' : 'scale(1)',
          pointerEvents: fanOpen || panelOpen ? 'none' : 'auto',
          transition: `opacity .18s ease, transform .25s ${TAILOR_EASE}`,
        }}
      >
        <span>✦</span>
        <span>Tailor résumé</span>
      </div>

      {/* notes panel */}
      <div
        style={{
          position: 'absolute',
          right: 0,
          bottom: 0,
          width: 400,
          background: '#1E293B',
          border: '1px solid rgba(148,163,184,0.2)',
          borderRadius: 16,
          boxShadow: '0 24px 60px rgba(0,0,0,0.55)',
          padding: '16px 18px 18px',
          boxSizing: 'border-box',
          fontFamily: "'Source Sans 3', sans-serif",
          transformOrigin: 'bottom right',
          opacity: panelOpen ? 1 : 0,
          transform: panelOpen ? 'scale(1)' : 'scale(0.6)',
          pointerEvents: panelOpen ? 'auto' : 'none',
          transition: `opacity .22s ease, transform .32s ${TAILOR_EASE}`,
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 11,
            paddingBottom: 14,
            marginBottom: 14,
            borderBottom: '1px solid rgba(148,163,184,0.14)',
          }}
        >
          <img
            src={selThumb}
            alt={`${selLabel} template`}
            style={{ width: 40, height: 52, objectFit: 'cover', objectPosition: 'top center', borderRadius: 5, border: `2px solid ${TAILOR_ACCENT}`, flex: 'none' }}
          />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2, flex: 1 }}>
            <span style={{ fontSize: '10.5px', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#64748B' }}>
              Tailoring into
            </span>
            <span style={{ fontSize: 15, fontWeight: 700, color: '#F1F5F9' }}>{selLabel} style</span>
          </div>
          <button
            type="button"
            onClick={() => onModeChange('fan')}
            disabled={generating}
            style={{ height: 30, padding: '0 12px', border: '1px solid rgba(148,163,184,0.3)', borderRadius: 999, background: 'transparent', color: '#CBD5E1', fontSize: 12, fontWeight: 600, cursor: generating ? 'default' : 'pointer', flex: 'none', opacity: generating ? 0.5 : 1 }}
          >
            Change
          </button>
          <button
            type="button"
            aria-label="Close"
            onClick={() => onModeChange('idle')}
            disabled={generating}
            style={{ width: 28, height: 28, border: 'none', borderRadius: 8, background: 'transparent', color: '#64748B', fontSize: 13, cursor: generating ? 'default' : 'pointer', flex: 'none', opacity: generating ? 0.5 : 1 }}
          >
            ✕
          </button>
        </div>

        {!generating && (
          <div>
            <label htmlFor="tailor-extra-context" style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#CBD5E1', marginBottom: 7 }}>
              Anything we should know before we rewrite? <span style={{ color: '#64748B', fontWeight: 400 }}>(optional)</span>
            </label>
            <textarea
              id="tailor-extra-context"
              rows={4}
              value={extraContext}
              onChange={(e) => onExtraContextChange(e.target.value)}
              placeholder="e.g. I'm targeting backend / infra internships. Keep the Datadog caching bullet, it's my strongest."
              style={{
                width: '100%',
                boxSizing: 'border-box',
                background: '#0F172A',
                border: '1px solid rgba(148,163,184,0.2)',
                borderRadius: 8,
                padding: '10px 12px',
                fontFamily: "'Source Sans 3', sans-serif",
                fontSize: '12.5px',
                lineHeight: 1.5,
                color: '#E2E8F0',
                resize: 'vertical',
                outline: 'none',
                minHeight: 86,
              }}
            />
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 14, marginTop: 12 }}>
              <span style={{ fontSize: 12, color: '#64748B' }}>
                {rewritableCount} bullet{rewritableCount === 1 ? '' : 's'} rewritten · rest stays as-is
              </span>
              <button
                type="button"
                onClick={onGenerate}
                style={{
                  flex: 'none',
                  height: 42,
                  padding: '0 20px',
                  border: 'none',
                  borderRadius: 999,
                  background: '#F1F5F9',
                  color: '#0F172A',
                  fontFamily: "'Source Sans 3', sans-serif",
                  fontSize: '13.5px',
                  fontWeight: 700,
                  cursor: 'pointer',
                  boxShadow: `inset 3px 0 0 ${TAILOR_ACCENT}`,
                }}
              >
                Generate — {selLabel}
              </button>
            </div>
          </div>
        )}

        {generating && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '14px 4px 6px' }}>
            <span
              style={{
                width: 20,
                height: 20,
                borderRadius: 999,
                border: '2.5px solid rgba(148,163,184,0.25)',
                borderTopColor: TAILOR_ACCENT,
                animation: 'spin4c .7s linear infinite',
                flex: 'none',
                display: 'inline-block',
              }}
            />
            <span style={{ fontSize: '13.5px', color: '#CBD5E1' }}>
              Rewriting {rewritableCount} bullet{rewritableCount === 1 ? '' : 's'} in {selLabel} style…
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

const ZOOM_MIN = 0.4;
const ZOOM_MAX = 1.1;
const ZOOM_STEP = 0.1;

function ZoomControl({ zoom, onChange }: { zoom: number; onChange: (z: number) => void }) {
  // "Outline mono" — no fill, just an ink border + JetBrains Mono numerals, matching the
  // page's own eyebrow-label styling ("RESUME FEEDBACK", "CURRENT — before critique") instead
  // of a generic solid-purple button pill. Approved via Lavish review (option D).
  return (
    <div
      className="inline-flex items-center"
      style={{
        gap: 2,
        borderRadius: 7,
        padding: 2,
        background: 'transparent',
        border: '1px solid var(--lp-text-primary)',
      }}
    >
      <button
        type="button"
        aria-label="Zoom out"
        onClick={() => onChange(Math.max(ZOOM_MIN, +(zoom - ZOOM_STEP).toFixed(2)))}
        disabled={zoom <= ZOOM_MIN}
        style={{ width: 20, height: 20, display: 'grid', placeItems: 'center', border: 'none', background: 'transparent', cursor: zoom <= ZOOM_MIN ? 'default' : 'pointer', color: 'var(--lp-text-primary)', opacity: zoom <= ZOOM_MIN ? 0.4 : 1, fontFamily: "'JetBrains Mono', monospace", fontSize: 13, lineHeight: 1, fontWeight: 700 }}
      >
        −
      </button>
      <span className="tabular-nums" style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10.5, width: 32, textAlign: 'center', color: 'var(--lp-text-primary)', fontWeight: 700 }}>
        {Math.round(zoom * 100)}%
      </span>
      <button
        type="button"
        aria-label="Zoom in"
        onClick={() => onChange(Math.min(ZOOM_MAX, +(zoom + ZOOM_STEP).toFixed(2)))}
        disabled={zoom >= ZOOM_MAX}
        style={{ width: 20, height: 20, display: 'grid', placeItems: 'center', border: 'none', background: 'transparent', cursor: zoom >= ZOOM_MAX ? 'default' : 'pointer', color: 'var(--lp-text-primary)', opacity: zoom >= ZOOM_MAX ? 0.4 : 1, fontFamily: "'JetBrains Mono', monospace", fontSize: 13, lineHeight: 1, fontWeight: 700 }}
      >
        +
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Staggered "rise" reveal — sequential animation-delay down the page.
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Real-PDF critique review pane — renders the actual pdflatex-compiled resume
// to a <canvas> via pdfjs-dist and overlays severity dots at the backend's
// per-bullet fractional coordinates (see get_bullet_page_positions). This
// replaces the old hand-built HTML mockup so line-wrapping, margins, and dot
// positions always match the real compiled page (addresses issue #79).
// ---------------------------------------------------------------------------

// Matches the mock's old PAGE_WIDTH so the page reads at the same on-screen size
// users are already used to; the real page's aspect ratio (612x792pt, US Letter)
// is preserved by pdfjs's own viewport math, not hardcoded here.
const PDF_PAGE_WIDTH = 720;

// How far LEFT of a bullet's text-start x-coordinate to place its severity dot —
// mirrors the old mock's dot offset (it sat in the ~42px left margin outside the
// bullet's own padding). Compiled resumes use a 0.5in (36pt) page margin, which at
// PDF_PAGE_WIDTH's scale renders as roughly 40-45px, so this comfortably keeps the
// dot inside the page rather than clipping off its left edge.
const DOT_LEFT_OFFSET_PX = 32;

function BulletPositionMarker({
  position,
  flag,
  hovered,
  onHover,
}: {
  position: BulletPosition;
  flag?: CritiqueFlag;
  hovered: string | null;
  onHover: (id: string | null) => void;
}) {
  if (!flag) return null;
  const on = hovered === position.bullet_id;
  const sev = SEVERITY[flag.severity];
  const topPct = position.top_frac * 100;
  const leftPct = position.left_frac * 100;

  return (
    <>
      <span
        onMouseEnter={() => onHover(position.bullet_id)}
        onMouseLeave={() => onHover(null)}
        style={{
          position: 'absolute',
          left: `calc(${leftPct}% - ${DOT_LEFT_OFFSET_PX}px)`,
          top: `calc(${topPct}% - 2px)`,
          width: 24,
          height: 22,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'pointer',
          transition: 'transform 0.15s ease',
          transform: on ? 'scale(1.25)' : 'scale(1)',
          zIndex: 20,
        }}
      >
        <span
          style={{
            width: 9,
            height: 9,
            borderRadius: '50%',
            background: sev.dot,
            boxShadow: `0 0 0 3px ${sev.ring}`,
          }}
        />
      </span>
      <span
        aria-hidden="true"
        style={{
          position: 'absolute',
          left: 'calc(100% + 8px)',
          top: `calc(${topPct}% + 8px)`,
          width: 84,
          height: 1,
          background: sev.dot,
          opacity: on ? 0.45 : 0,
          transition: 'opacity 0.16s ease',
          pointerEvents: 'none',
        }}
      />
      <div
        role="tooltip"
        style={{
          position: 'absolute',
          left: 'calc(100% + 100px)',
          top: `calc(${topPct}% - 12px)`,
          width: 264,
          boxSizing: 'border-box',
          background: '#FFFFFF',
          border: '1px solid rgba(31,27,22,0.12)',
          borderTop: `2px solid ${sev.dot}`,
          borderRadius: 10,
          padding: '11px 14px 12px',
          boxShadow: '0 2px 6px rgba(31,27,22,0.06), 0 14px 36px rgba(31,27,22,0.12)',
          pointerEvents: 'none',
          zIndex: 30,
          fontFamily: "'Source Sans 3', system-ui, sans-serif",
          opacity: on ? 1 : 0,
          transform: on ? 'translateX(0)' : 'translateX(-8px)',
          transition: 'opacity 0.16s ease, transform 0.18s ease',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 5 }}>
          <span style={{ width: 7, height: 7, borderRadius: '50%', background: sev.dot }} />
          <span
            style={{
              fontSize: '10.5px',
              fontWeight: 700,
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
              color: sev.labelColor,
            }}
          >
            {sev.label}
          </span>
        </div>
        <p style={{ margin: 0, fontSize: 13, lineHeight: 1.5, color: '#5A5247' }}>{flag.comment}</p>
      </div>
    </>
  );
}

function CritiqueResumePdfPage({
  pdfBase64,
  bulletPositions,
  flagByBulletId,
  hovered,
  onHover,
}: {
  pdfBase64?: string;
  bulletPositions: BulletPosition[];
  flagByBulletId: Record<string, CritiqueFlag>;
  hovered: string | null;
  onHover: (id: string | null) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [renderSize, setRenderSize] = useState<{ width: number; height: number } | null>(null);
  const [renderError, setRenderError] = useState('');

  useEffect(() => {
    if (!pdfBase64) return;
    let cancelled = false;
    let task: ReturnType<typeof pdfjsLib.getDocument> | null = null;

    (async () => {
      try {
        const byteChars = atob(pdfBase64);
        const bytes = new Uint8Array(byteChars.length);
        for (let i = 0; i < byteChars.length; i++) bytes[i] = byteChars.charCodeAt(i);

        task = pdfjsLib.getDocument({ data: bytes });
        const pdf = await task.promise;
        const page = await pdf.getPage(1);
        if (cancelled) return;

        const baseViewport = page.getViewport({ scale: 1 });
        const cssScale = PDF_PAGE_WIDTH / baseViewport.width;
        const dpr = window.devicePixelRatio || 1;
        const renderViewport = page.getViewport({ scale: cssScale * dpr });

        const canvas = canvasRef.current;
        const ctx = canvas?.getContext('2d');
        if (!canvas || !ctx) return;

        canvas.width = renderViewport.width;
        canvas.height = renderViewport.height;
        canvas.style.width = `${cssScale * baseViewport.width}px`;
        canvas.style.height = `${cssScale * baseViewport.height}px`;

        await page.render({ canvasContext: ctx, viewport: renderViewport }).promise;
        if (cancelled) return;
        setRenderSize({ width: cssScale * baseViewport.width, height: cssScale * baseViewport.height });
      } catch (e: any) {
        if (!cancelled) setRenderError(e?.message || 'Failed to render the resume preview.');
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [pdfBase64]);

  const fallbackHeight = Math.round(PDF_PAGE_WIDTH * (11 / 8.5));

  if (!pdfBase64) {
    return (
      <div
        style={{
          width: PDF_PAGE_WIDTH,
          height: fallbackHeight,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          textAlign: 'center',
          padding: 32,
          background: '#FDFCFA',
          border: '1px solid rgba(31,27,22,0.08)',
          borderRadius: 2,
          boxShadow: '0 1px 2px rgba(31,27,22,0.08), 0 16px 48px rgba(31,27,22,0.14)',
          color: '#5A5247',
          fontSize: 13,
          boxSizing: 'border-box',
        }}
      >
        We couldn't generate a preview of your resume just now. Your feedback below is still accurate — try
        re-uploading if you'd like to see the annotated page.
      </div>
    );
  }

  return (
    <div
      style={{
        position: 'relative',
        width: renderSize?.width ?? PDF_PAGE_WIDTH,
        height: renderSize?.height ?? fallbackHeight,
        background: '#FDFCFA',
        border: '1px solid rgba(31,27,22,0.08)',
        borderRadius: 2,
        boxShadow: '0 1px 2px rgba(31,27,22,0.08), 0 16px 48px rgba(31,27,22,0.14)',
        boxSizing: 'border-box',
        animation: 'rise 0.5s ease 0.1s both',
      }}
    >
      <canvas ref={canvasRef} style={{ display: 'block', borderRadius: 2 }} />
      {renderError && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 32,
            textAlign: 'center',
            fontSize: 13,
            color: '#a33',
          }}
        >
          {renderError}
        </div>
      )}
      {renderSize &&
        bulletPositions.map((pos) => (
          <BulletPositionMarker
            key={pos.bullet_id}
            position={pos}
            flag={flagByBulletId[pos.bullet_id]}
            hovered={hovered}
            onHover={onHover}
          />
        ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

// Survives a refresh (cleared when the tab closes) — holds only the JSON results,
// never the raw File object, so re-detecting industry after a refresh still needs a re-upload.
const SESSION_KEY = 'critique_session_v1';

interface PersistedCritiqueSession {
  result: CritiqueResult | null;
  tailoredResult: TailoredResult | null;
  category: string;
  extraContext: string;
  activeTab: 'current' | 'tailored';
  viewMode: 'single' | 'compare';
}

const loadPersistedSession = (): PersistedCritiqueSession | null => {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
};

const CritiquePage: React.FC = () => {
  const { isLoaded, isSignedIn, getToken } = useAuth();
  const persisted = React.useMemo(loadPersistedSession, []);
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<CritiqueResult | null>(persisted?.result ?? null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [hovered, setHovered] = useState<string | null>(null);
  const [category, setCategory] = useState(persisted?.category ?? '');
  const [editingCategory, setEditingCategory] = useState(false);
  const [extraContext, setExtraContext] = useState(persisted?.extraContext ?? '');
  const [generating, setGenerating] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [tailoredResult, setTailoredResult] = useState<TailoredResult | null>(persisted?.tailoredResult ?? null);
  const [activeTab, setActiveTab] = useState<'current' | 'tailored'>(persisted?.activeTab ?? 'current');
  const [viewMode, setViewMode] = useState<'single' | 'compare'>(persisted?.viewMode ?? 'compare');
  const [singleZoom, setSingleZoom] = useState(0.9);
  const [currentZoom, setCurrentZoom] = useState(0.635);
  const [tailoredZoom, setTailoredZoom] = useState(0.635);
  const [devPasteText, setDevPasteText] = useState('');
  const [tailorMode, setTailorMode] = useState<'idle' | 'fan' | 'notes'>('idle');
  const [tailorTemplate, setTailorTemplate] = useState<TailorTemplateId>('classic');
  const fileInputRef = useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    if (!result) {
      sessionStorage.removeItem(SESSION_KEY);
      return;
    }
    const snapshot: PersistedCritiqueSession = {
      result, tailoredResult, category, extraContext, activeTab, viewMode,
    };
    try {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify(snapshot));
    } catch {
      // Quota exceeded or storage unavailable (private browsing) — degrade to no persistence.
    }
  }, [result, tailoredResult, category, extraContext, activeTab, viewMode]);

  const flagByBulletId = React.useMemo(() => {
    const map: Record<string, CritiqueFlag> = {};
    (result?.critiques ?? []).forEach((c) => { map[c.bullet_id] = c; });
    return map;
  }, [result]);

  const submitResume = useCallback(async (f: File, targetCategory?: string) => {
    setLoading(true);
    setError('');
    try {
      const token = await getToken();
      const formData = new FormData();
      formData.append('resume', f);
      if (targetCategory) formData.append('target_category', targetCategory);
      const res = await fetch(`${API_BASE_URL}/api/critique-resume`, {
        method: 'POST',
        body: formData,
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      });
      if (!res.ok) {
        if (res.status === 429) {
          const body = await res.json().catch(() => null);
          throw new Error(body?.detail?.message || "You've hit the weekly critique limit.");
        }
        const text = await res.text();
        throw new Error(text || `Server error ${res.status}`);
      }
      const data: CritiqueResult = await res.json();
      setResult(data);
      setCategory(data.detected_category);
      setFile(f);
    } catch (e: any) {
      setError(e.message ?? 'Failed to critique resume.');
    } finally {
      setLoading(false);
    }
  }, [getToken]);

  const submitResumeText = useCallback(async (text: string) => {
    setLoading(true);
    setError('');
    try {
      const token = await getToken();
      const res = await fetch(`${API_BASE_URL}/api/dev/critique-resume-text`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ resume_text: text }),
      });
      if (!res.ok) {
        const errText = await res.text();
        throw new Error(errText || `Server error ${res.status}`);
      }
      const data: CritiqueResult = await res.json();
      setResult(data);
      setCategory(data.detected_category);
    } catch (e: any) {
      setError(e.message ?? 'Failed to critique resume.');
    } finally {
      setLoading(false);
    }
  }, [getToken]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) submitResume(f);
  };

  const handleDrop = (e: React.DragEvent<HTMLLabelElement>) => {
    e.preventDefault();
    setIsDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) submitResume(f);
  };

  const handleDragOver = (e: React.DragEvent<HTMLLabelElement>) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => setIsDragging(false);

  const handleCategoryChange = (newCategory: string) => {
    setEditingCategory(false);
    if (!file || newCategory === category) return;
    setCategory(newCategory);
    submitResume(file, newCategory);
  };

  // Issue #81 — the critique review/compare screens had no way to leave except the
  // browser's own back button. Resets to the pre-upload state; sessionStorage clears
  // itself via the persistence effect above once `result` goes null.
  const handleBack = () => {
    setFile(null);
    setResult(null);
    setTailoredResult(null);
    setError('');
    setCategory('');
    setExtraContext('');
    setTailorMode('idle');
  };

  const handleGenerate = async () => {
    if (!result) return;
    const rewritable = result.critiques.filter((c) => c.severity !== 'green');
    if (rewritable.length === 0) {
      setError('Nothing flagged to rewrite — your resume is already strong as-is.');
      return;
    }
    setGenerating(true);
    setError('');
    try {
      const token = await getToken();
      // Only the fields the rewrite prompt needs — drop critiques/cached so the model
      // isn't shown its own critique output nested inside the "resume data" it edits.
      const { critiques: _critiques, cached: _cached, ...resumeOnly } = result;

      const res = await fetch(`${API_BASE_URL}/api/critique-resume/rewrite`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          structured_resume: resumeOnly,
          critiques: rewritable,
          extra_context: extraContext,
          template_id: tailorTemplate,
        }),
      });
      if (!res.ok) {
        if (res.status === 429) {
          const body = await res.json().catch(() => null);
          throw new Error(body?.detail?.message || "You've hit the weekly tailor limit.");
        }
        const text = await res.text();
        throw new Error(text || `Server error ${res.status}`);
      }
      const data = await res.json();
      setTailoredResult({
        structured: data.structured_resume,
        pdfBase64: data.pdf_base64,
        rewrittenIds: data.rewritten_bullet_ids ?? [],
      });
      setActiveTab('tailored');
      setViewMode('compare');
    } catch (e: any) {
      setError(e.message ?? 'Failed to generate improved resume.');
    } finally {
      setGenerating(false);
    }
  };

  const downloadTailoredPdf = () => {
    if (!tailoredResult) return;
    const byteChars = atob(tailoredResult.pdfBase64);
    const byteNumbers = new Array(byteChars.length);
    for (let i = 0; i < byteChars.length; i++) byteNumbers[i] = byteChars.charCodeAt(i);
    const blob = new Blob([new Uint8Array(byteNumbers)], { type: 'application/pdf' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `resume_tailored_${(result?.name || 'resume').replace(/[^\w-]/g, '_')}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  if (!isLoaded) {
    return <div className="min-h-screen bg-bg" />;
  }

  if (!isSignedIn) {
    return (
      <div className="min-h-screen bg-bg text-text-primary">
        <Header />
        <main className="max-w-[860px] mx-auto px-6 py-12">
          <div className="pt-6 pb-10 border-b border-lp-border">
            <div className="flex items-center gap-3 mb-6">
              <span className="block w-8 h-px bg-text-tertiary flex-shrink-0" />
              <span className="font-mono text-[10px] uppercase tracking-widest text-text-secondary">
                Resume feedback
              </span>
            </div>
            <h1 className="font-serif text-3xl md:text-4xl text-text-primary mb-3">
              Find out why your resume isn't getting callbacks.
            </h1>
            <p className="text-sm text-text-secondary max-w-lg mb-8">
              Critique reads your resume the way recruiters actually screen it and flags the handful
              of lines holding you back — sign in to try it.
            </p>
            <SignInButton mode="modal">
              <button className="inline-block bg-text-primary text-bg px-5 py-2.5 font-mono text-xs tracking-wide hover:opacity-80 transition-opacity">
                Sign in →
              </button>
            </SignInButton>
          </div>
        </main>
      </div>
    );
  }

  if (!result) {
    return (
      <div className="min-h-screen bg-bg text-text-primary">
        <Header />
        <main className="max-w-[860px] mx-auto px-6 py-12 space-y-0">
          {/* Hero */}
          <div className="pt-6 pb-10 border-b border-lp-border">
            <div className="flex items-center gap-3 mb-6">
              <span className="block w-8 h-px bg-text-tertiary flex-shrink-0" />
              <span className="font-mono text-[10px] uppercase tracking-widest text-text-secondary">
                Resume feedback
              </span>
            </div>
            <h1 className="font-serif text-3xl md:text-4xl text-text-primary mb-2">
              Get told exactly what's costing you callbacks.
            </h1>
            <p className="text-sm text-text-secondary max-w-lg">
              Most resumes don't fail on one big thing — they fail on 2 or 3 vague lines a recruiter
              skims past in six seconds. Critique reads your resume the same way a recruiter would,
              flags only the handful of lines worth your attention — both good and bad — and tells you
              exactly why.
            </p>
          </div>

          {/* Upload card */}
          <div className="py-8 border-b border-lp-border">
            <div className="max-w-2xl">
              <div className="flex items-center gap-2 mb-5">
                <Upload className="h-4 w-4 text-text-secondary" />
                <span className="font-mono text-[10px] uppercase tracking-widest text-text-secondary">
                  Upload Your Resume
                </span>
              </div>
              <label
                className={`flex flex-col items-center justify-center w-full h-32 border border-dashed cursor-pointer transition-colors ${
                  isDragging ? 'border-text-primary bg-ia-subtle' : 'border-lp-border hover:border-text-secondary'
                }`}
                onDrop={handleDrop}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
              >
                <div className="flex flex-col items-center justify-center pt-5 pb-6">
                  {loading ? (
                    <>
                      <Sparkles className="h-6 w-6 mb-2 text-text-primary animate-spin" />
                      <p className="text-sm text-text-primary">Reading your resume…</p>
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
                      <p className="font-mono text-[10px] text-text-tertiary mt-0.5">PDF only</p>
                    </>
                  )}
                </div>
                <input type="file" accept=".pdf" className="hidden" onChange={handleFileChange} disabled={loading} />
              </label>
              {process.env.NODE_ENV !== 'production' && (
                <details className="mt-3">
                  <summary className="font-mono text-[10px] uppercase tracking-widest text-text-tertiary cursor-pointer">
                    Dev: paste resume text instead
                  </summary>
                  <div className="mt-2 flex flex-col gap-2">
                    <textarea
                      value={devPasteText}
                      onChange={(e) => setDevPasteText(e.target.value)}
                      placeholder="Paste plain resume text here — bypasses PDF upload for local testing."
                      className="w-full h-28 border border-lp-border p-2 text-xs font-mono"
                      disabled={loading}
                    />
                    <Button
                      variant="outline"
                      size="sm"
                      className="self-start"
                      disabled={loading || !devPasteText.trim()}
                      onClick={() => submitResumeText(devPasteText)}
                    >
                      Critique pasted text
                    </Button>
                  </div>
                </details>
              )}
            </div>
          </div>

          {/* What you get */}
          <div className="py-8 border-b border-lp-border grid grid-cols-1 sm:grid-cols-3 gap-6">
            <div className="flex flex-col gap-2">
              <Eye className="h-4 w-4 text-text-secondary" />
              <p className="text-sm text-text-primary font-medium">Sparse, honest feedback</p>
              <p className="text-xs text-text-tertiary leading-relaxed">
                Only the bullets that need work get flagged — red for critical, yellow for needs work,
                green for "do more of this." Unmarked lines are already fine.
              </p>
            </div>
            <div className="flex flex-col gap-2">
              <Sparkles className="h-4 w-4 text-text-secondary" />
              <p className="text-sm text-text-primary font-medium">Calibrated to your field</p>
              <p className="text-xs text-text-tertiary leading-relaxed">
                We detect your target industry from the resume itself (editable if we're wrong) and
                critique against what recruiters in that field actually screen for.
              </p>
            </div>
            <div className="flex flex-col gap-2">
              <PenLine className="h-4 w-4 text-text-secondary" />
              <p className="text-sm text-text-primary font-medium">Turn it into a rewrite</p>
              <p className="text-xs text-text-tertiary leading-relaxed">
                Add optional context about what you're targeting, and we'll rewrite the flagged lines
                into a fresh PDF — keeping everything that already works.
              </p>
            </div>
          </div>

          {error && (
            <div className="py-8 border-b border-lp-border max-w-2xl">
              <div className="border border-lp-border p-4">
                <p className="font-mono text-[10px] uppercase tracking-widest text-red-500 mb-1">Error</p>
                <p className="text-text-secondary text-sm">{error}</p>
              </div>
            </div>
          )}
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-bg text-text-primary font-sans" style={{ fontFamily: "'Source Sans 3', system-ui, sans-serif" }}>
      <style>{`@keyframes rise { from { opacity: 0; transform: translateY(7px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes pulseDot { 0%, 100% { transform: scale(1); opacity: 1; } 50% { transform: scale(1.55); opacity: 0.4; } }
        @keyframes spin4c { to { transform: rotate(360deg); } }
        @media (prefers-reduced-motion: reduce) {
          [style*="animation: rise"], [style*="animation:rise"] { animation: none !important; opacity: 1 !important; transform: none !important; }
          [style*="pulseDot"] { animation: none !important; }
        }`}</style>

      {/* Focused-task header — compact, but keeps site nav reachable instead of stranding
          the user once they've uploaded (see issue #81). */}
      <header className="flex items-center justify-between px-9 py-4 border-b border-lp-border">
        <div className="flex items-center gap-6">
          <Link to="/" className="flex items-center gap-3.5 no-underline">
            <Logo size={24} />
            <div className="w-px h-5" style={{ background: 'rgba(31,27,22,0.15)' }} />
            <div className="text-sm font-semibold tracking-wide text-text-primary">Critique</div>
          </Link>
          <nav className="hidden sm:flex items-center gap-4">
            <Link to="/find" className="font-mono text-xs text-text-secondary hover:text-text-primary transition-colors">
              Find
            </Link>
            <Link to="/saved" className="font-mono text-xs text-text-secondary hover:text-text-primary transition-colors">
              Saved
            </Link>
            <Link to="/history" className="font-mono text-xs text-text-secondary hover:text-text-primary transition-colors">
              History
            </Link>
            <Link to="/usage" className="font-mono text-xs text-text-secondary hover:text-text-primary transition-colors">
              Usage
            </Link>
          </nav>
        </div>
        {file && (
          <div className="flex items-center gap-3.5">
            <div
              className="flex items-center gap-2 px-3 py-[5px] rounded-full border border-lp-border"
              style={{ background: 'var(--lp-surface)' }}
            >
              <CheckCircle2 className="w-3 h-3" style={{ color: 'hsl(142 72% 45%)' }} />
              <span className="font-mono text-[11.5px] text-text-secondary">{file.name}</span>
            </div>
            <button
              onClick={() => fileInputRef.current?.click()}
              className="text-[13px] font-semibold text-text-secondary hover:text-text-primary underline decoration-[rgba(31,27,22,0.25)] underline-offset-[3px]"
            >
              Upload a different resume
            </button>
          </div>
        )}
        <input ref={fileInputRef} type="file" accept=".pdf" className="hidden" onChange={handleFileChange} />
      </header>

      {error && (
        <div className="max-w-[860px] mx-auto px-6 pt-4">
          <div className="border border-lp-border bg-surface p-3 text-sm text-text-secondary">{error}</div>
        </div>
      )}

      {/* Content row — critique review state (before a tailored version exists) */}
      {result && !tailoredResult && (
        <div className="flex items-start gap-9 px-8 pt-11" style={{ justifyContent: 'safe center', paddingBottom: 110 }}>
          {/* Left column: three independent boxes */}
          <aside className="w-[248px] flex-none sticky top-9 flex flex-col gap-4">
            <div
              className="rounded-[10px] border border-lp-border p-[16px_18px]"
              style={{ background: 'var(--lp-surface)', animation: 'rise 0.5s ease 0.15s both' }}
            >
              <div className="text-[11px] font-bold tracking-[0.09em] uppercase text-text-tertiary mb-2.5">
                Detected industry
              </div>
              {editingCategory ? (
                <select
                  autoFocus
                  defaultValue={category}
                  onChange={(e) => handleCategoryChange(e.target.value)}
                  onBlur={() => setEditingCategory(false)}
                  className="w-full text-xs border border-lp-border rounded px-2 py-1 bg-card text-text-primary"
                >
                  {DEPARTMENT_CATEGORIES.map((c) => (
                    <option key={c.id} value={c.id}>{c.label}</option>
                  ))}
                </select>
              ) : (
                <div className="flex items-center justify-between gap-2.5">
                  <Badge variant="secondary">
                    {DEPARTMENT_CATEGORIES.find((c) => c.id === category)?.label ?? category}
                  </Badge>
                  <button
                    onClick={() => setEditingCategory(true)}
                    className="text-xs font-semibold text-text-tertiary hover:text-text-primary underline underline-offset-[3px]"
                  >
                    Change
                  </button>
                </div>
              )}
              <p className="mt-2.5 text-xs leading-relaxed text-text-tertiary">
                Feedback is calibrated to what recruiters in this field look for.
              </p>
            </div>

            <div
              className="rounded-[10px] border border-lp-border p-[16px_18px]"
              style={{ background: 'var(--lp-surface)', animation: 'rise 0.5s ease 0.28s both' }}
            >
              <div className="text-[11px] font-bold tracking-[0.09em] uppercase text-text-tertiary mb-3">Legend</div>
              <div className="flex flex-col gap-[9px]">
                <div className="flex items-center gap-2.5">
                  <span className="w-[9px] h-[9px] rounded-full flex-none" style={{ background: 'hsl(0 84% 60%)' }} />
                  <span className="text-[13px] text-text-primary">Critical — rewrite this</span>
                </div>
                <div className="flex items-center gap-2.5">
                  <span className="w-[9px] h-[9px] rounded-full flex-none" style={{ background: 'hsl(38 92% 55%)' }} />
                  <span className="text-[13px] text-text-primary">Needs work</span>
                </div>
                <div className="flex items-center gap-2.5">
                  <span className="w-[9px] h-[9px] rounded-full flex-none" style={{ background: 'hsl(142 72% 45%)' }} />
                  <span className="text-[13px] text-text-primary">Strong — do more of this</span>
                </div>
              </div>
              <p className="mt-3 text-xs leading-relaxed text-text-tertiary">
                Hover a dot to read the note. Unmarked lines are fine as they are.
              </p>
            </div>
          </aside>

          {/* Resume page — the ACTUAL compiled PDF (real pdflatex output, not a mockup),
              rendered to canvas via pdfjs-dist with severity dots overlaid at the
              backend's real per-bullet coordinates. See CritiqueResumePdfPage above. */}
          <main className="w-[720px] flex-none" style={{ position: 'relative' }}>
            <CritiqueResumePdfPage
              pdfBase64={result.pdf_base64}
              bulletPositions={result.bullet_positions ?? []}
              flagByBulletId={flagByBulletId}
              hovered={hovered}
              onHover={setHovered}
            />

            {/* Issue #81 — floating back button, symmetric with the Tailor résumé pill
                on the opposite corner. Resets to the pre-upload state. */}
            <button
              type="button"
              onClick={handleBack}
              style={{
                position: 'absolute',
                left: 28,
                bottom: 28,
                zIndex: 5,
                display: 'flex',
                alignItems: 'center',
                gap: 9,
                height: 46,
                padding: '0 20px',
                borderRadius: 999,
                background: '#F1F5F9',
                color: '#0F172A',
                fontWeight: 600,
                fontSize: 14,
                fontFamily: "'Source Sans 3', sans-serif",
                border: 'none',
                boxShadow: `inset 3px 0 0 ${TAILOR_ACCENT}, 0 8px 22px rgba(0,0,0,0.4)`,
                cursor: 'pointer',
              }}
            >
              <span aria-hidden="true">←</span>
              <span>Back</span>
            </button>

            <TailorTrigger
              mode={tailorMode}
              onModeChange={setTailorMode}
              sel={tailorTemplate}
              onSelChange={setTailorTemplate}
              extraContext={extraContext}
              onExtraContextChange={setExtraContext}
              generating={generating}
              rewritableCount={result.critiques.filter((c) => c.severity !== 'green').length}
              onGenerate={handleGenerate}
            />
          </main>

          {/* Right rail reserved for hover comments */}
          <div className="w-[300px] flex-none" aria-hidden="true" />
        </div>
      )}

      {/* Result state — a tailored version exists: Current/Tailored tabs + Single/Compare */}
      {result && tailoredResult && (
        <div className="max-w-[1060px] mx-auto px-6" style={{ paddingTop: 26, paddingBottom: 100 }}>
          <div
            className="flex items-end justify-between gap-5 flex-wrap"
            style={{ borderBottom: '1px solid rgba(31,27,22,0.14)', marginBottom: 8 }}
          >
            <div className="flex items-end gap-0.5">
              <button
                onClick={() => setActiveTab('current')}
                className="inline-flex items-center gap-2 text-sm"
                style={{
                  padding: '10px 16px 11px',
                  background: 'none', border: 'none',
                  borderBottom: activeTab === 'current' && viewMode === 'single' ? '2px solid var(--lp-text-primary)' : '2px solid transparent',
                  marginBottom: -1,
                  fontWeight: activeTab === 'current' && viewMode === 'single' ? 700 : 600,
                  color: activeTab === 'current' && viewMode === 'single' ? 'var(--lp-text-primary)' : 'var(--lp-text-tertiary)',
                  cursor: 'pointer',
                }}
              >
                Current Resume
              </button>
              <button
                onClick={() => setActiveTab('tailored')}
                className="inline-flex items-center gap-2 text-sm"
                style={{
                  padding: '10px 16px 11px',
                  background: 'none', border: 'none',
                  borderBottom: activeTab === 'tailored' && viewMode === 'single' ? '2px solid var(--lp-text-primary)' : '2px solid transparent',
                  marginBottom: -1,
                  fontWeight: activeTab === 'tailored' && viewMode === 'single' ? 700 : 600,
                  color: activeTab === 'tailored' && viewMode === 'single' ? 'var(--lp-text-primary)' : 'var(--lp-text-tertiary)',
                  cursor: 'pointer',
                }}
              >
                <span>Tailored Resume</span>
                <span style={{ position: 'relative', display: 'inline-flex', width: 7, height: 7 }}>
                  <span style={{ position: 'absolute', inset: 0, borderRadius: '50%', background: 'hsl(142 72% 45%)', animation: 'pulseDot 1.8s ease-in-out infinite' }} />
                  <span style={{ position: 'absolute', inset: 0, borderRadius: '50%', background: 'hsl(142 72% 45%)' }} />
                </span>
              </button>
            </div>

            <div className="flex items-center gap-3" style={{ paddingBottom: 9 }}>
              <div className="inline-flex" style={{ padding: 3, background: '#E4E1D8', border: '1px solid rgba(31,27,22,0.10)', borderRadius: 9 }}>
                <button
                  onClick={() => setViewMode('single')}
                  className="text-[13px] font-semibold"
                  style={{
                    padding: '6px 14px', borderRadius: 6, border: 'none',
                    background: viewMode === 'single' ? '#FDFCFA' : 'transparent',
                    boxShadow: viewMode === 'single' ? '0 1px 2px rgba(31,27,22,0.12)' : 'none',
                    color: viewMode === 'single' ? 'var(--lp-text-primary)' : 'var(--lp-text-secondary)',
                    cursor: 'pointer',
                  }}
                >
                  Single
                </button>
                <button
                  onClick={() => setViewMode('compare')}
                  className="text-[13px] font-semibold"
                  style={{
                    padding: '6px 14px', borderRadius: 6, border: 'none',
                    background: viewMode === 'compare' ? '#FDFCFA' : 'transparent',
                    boxShadow: viewMode === 'compare' ? '0 1px 2px rgba(31,27,22,0.12)' : 'none',
                    color: viewMode === 'compare' ? 'var(--lp-text-primary)' : 'var(--lp-text-secondary)',
                    cursor: 'pointer',
                  }}
                >
                  Compare
                </button>
              </div>
              <button
                onClick={downloadTailoredPdf}
                className="inline-flex items-center gap-2 text-[13px] font-semibold"
                style={{ height: 34, padding: '0 15px', background: 'var(--lp-surface)', border: '1px solid rgba(31,27,22,0.16)', borderRadius: 9, color: 'var(--lp-text-primary)', cursor: 'pointer' }}
              >
                <Download className="h-3.5 w-3.5" />
                Download PDF
              </button>
            </div>
          </div>

          <div className="flex items-center gap-3.5 flex-wrap" style={{ minHeight: 22, marginBottom: 22 }}>
            <div className="text-[13px]" style={{ color: 'var(--lp-text-secondary)' }}>
              {viewMode === 'compare'
                ? `${tailoredResult.rewrittenIds.length} bullet${tailoredResult.rewrittenIds.length === 1 ? '' : 's'} rewritten to lead with outcomes and add metrics — everything else kept as-is.`
                : activeTab === 'tailored'
                  ? 'Your tailored resume — rewritten lines are highlighted in green.'
                  : `Your original resume — the ${tailoredResult.rewrittenIds.length} line${tailoredResult.rewrittenIds.length === 1 ? '' : 's'} the critique flagged are highlighted.`}
            </div>
            {viewMode === 'compare' && (
              <div className="flex items-center gap-3.5 text-xs" style={{ color: 'var(--lp-text-tertiary)' }}>
                <span className="inline-flex items-center gap-1.5">
                  <span style={{ width: 16, height: 10, borderRadius: 2, background: 'hsl(38 92% 55% / 0.18)', boxShadow: 'inset 2px 0 0 hsl(38 92% 55%)' }} />
                  original line
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span style={{ width: 16, height: 10, borderRadius: 2, background: 'hsl(142 72% 45% / 0.16)', boxShadow: 'inset 2px 0 0 hsl(142 72% 45%)' }} />
                  rewritten line
                </span>
              </div>
            )}
          </div>

          {viewMode === 'single' ? (
            <div className="flex flex-col items-center" style={{ gap: 11, animation: 'rise 0.4s ease both' }}>
              <ZoomControl zoom={singleZoom} onChange={setSingleZoom} />
              <div style={{ zoom: singleZoom }}>
                <ResumeDiffPage
                  blocks={buildDiffBlocks(result, tailoredResult.structured, tailoredResult.rewrittenIds)}
                  variant={activeTab}
                  showChanges
                />
              </div>
            </div>
          ) : (
            <div className="flex justify-center items-start gap-[30px]" style={{ animation: 'rise 0.4s ease both' }}>
              <div className="flex flex-col" style={{ gap: 11 }}>
                <div className="flex items-center justify-between gap-2" style={{ paddingLeft: 2 }}>
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-bold uppercase" style={{ letterSpacing: '0.1em', color: 'var(--lp-text-tertiary)' }}>Current</span>
                    <span className="text-[11px]" style={{ color: 'var(--lp-text-tertiary)' }}>— before critique</span>
                  </div>
                  <ZoomControl zoom={currentZoom} onChange={setCurrentZoom} />
                </div>
                <div style={{ zoom: currentZoom, borderRadius: 2 }}>
                  <ResumeDiffPage
                    blocks={buildDiffBlocks(result, tailoredResult.structured, tailoredResult.rewrittenIds)}
                    variant="current"
                    showChanges
                  />
                </div>
              </div>
              <div className="flex flex-col" style={{ gap: 11 }}>
                <div className="flex items-center justify-between gap-2" style={{ paddingLeft: 2 }}>
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-bold uppercase" style={{ letterSpacing: '0.1em', color: 'hsl(142 72% 34%)' }}>Tailored ✨</span>
                    <span className="text-[11px]" style={{ color: 'var(--lp-text-tertiary)' }}>— rewritten from your feedback</span>
                  </div>
                  <ZoomControl zoom={tailoredZoom} onChange={setTailoredZoom} />
                </div>
                <div style={{ zoom: tailoredZoom, borderRadius: 2, boxShadow: '0 0 0 2px hsl(142 72% 45% / 0.28)' }}>
                  <ResumeDiffPage
                    blocks={buildDiffBlocks(result, tailoredResult.structured, tailoredResult.rewrittenIds)}
                    variant="tailored"
                    showChanges
                  />
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default CritiquePage;
