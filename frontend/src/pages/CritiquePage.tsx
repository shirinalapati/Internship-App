import React, { useCallback, useRef, useState } from 'react';
import { useAuth, SignInButton } from '@clerk/react';
import { Upload } from 'lucide-react';
import Logo from '../components/Logo';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { DEPARTMENT_CATEGORIES } from '../components/ui/department-multi-select';
import { API_BASE_URL } from '../lib/api';

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
// Staggered "rise" reveal — sequential animation-delay down the page.
// ---------------------------------------------------------------------------

function useRiseDelay(step = 0.08, start = 0.1) {
  const counter = useRef(start);
  counter.current = start;
  return () => {
    const d = counter.current;
    counter.current += step;
    return d;
  };
}

function CommentBox({
  bulletId,
  hovered,
  flag,
}: {
  bulletId: string;
  hovered: string | null;
  flag?: CritiqueFlag;
}) {
  if (!flag) return null;
  const on = hovered === bulletId;
  const sev = SEVERITY[flag.severity];
  return (
    <>
      <span
        aria-hidden="true"
        style={{
          position: 'absolute',
          left: 'calc(100% + 8px)',
          top: 10,
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
          top: -10,
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

function CritiqueBulletLi({
  bullet,
  flag,
  hovered,
  onHover,
  delay,
}: {
  bullet: CritiqueBullet;
  flag?: CritiqueFlag;
  hovered: string | null;
  onHover: (id: string | null) => void;
  delay: number;
}) {
  const sev = flag ? SEVERITY[flag.severity] : null;
  return (
    <li
      style={{
        position: 'relative',
        paddingLeft: 16,
        fontSize: '13.5px',
        lineHeight: 1.5,
        animation: `rise 0.5s ease ${delay}s both`,
      }}
    >
      <span style={{ position: 'absolute', left: 2, color: '#666' }}>•</span>
      {bullet.text}
      {sev && (
        <>
          <span
            data-id={bullet.id}
            onMouseEnter={() => onHover(bullet.id)}
            onMouseLeave={() => onHover(null)}
            style={{
              position: 'absolute',
              left: -42,
              top: 0,
              width: 24,
              height: 22,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
              transition: 'transform 0.15s ease',
              transform: hovered === bullet.id ? 'scale(1.25)' : 'scale(1)',
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
          <CommentBox bulletId={bullet.id} hovered={hovered} flag={flag} />
        </>
      )}
    </li>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const CritiquePage: React.FC = () => {
  const { isLoaded, isSignedIn, getToken } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<CritiqueResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [hovered, setHovered] = useState<string | null>(null);
  const [category, setCategory] = useState('');
  const [editingCategory, setEditingCategory] = useState(false);
  const [extraContext, setExtraContext] = useState('');
  const [generating, setGenerating] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const nextDelay = useRiseDelay();

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

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) submitResume(f);
  };

  const handleCategoryChange = (newCategory: string) => {
    setEditingCategory(false);
    if (!file || newCategory === category) return;
    setCategory(newCategory);
    submitResume(file, newCategory);
  };

  const handleGenerate = async () => {
    if (!file || !result) return;
    setGenerating(true);
    setError('');
    try {
      const token = await getToken();
      const flagged = result.critiques
        .map((c) => {
          const allBullets = [
            ...result.experience.flatMap((e) => e.bullets),
            ...result.projects.flatMap((p) => p.bullets),
          ];
          const bullet = allBullets.find((b) => b.id === c.bullet_id);
          return bullet ? `- "${bullet.text}" — ${c.comment}` : null;
        })
        .filter(Boolean)
        .join('\n');
      const categoryLabel = DEPARTMENT_CATEGORIES.find((c) => c.id === category)?.label ?? category;
      const jobDescription =
        `Target industry: ${categoryLabel}\n\n` +
        `Feedback to address:\n${flagged}\n\n` +
        (extraContext.trim() ? `Additional context from candidate: ${extraContext.trim()}\n\n` : '') +
        'Rewrite the flagged bullets using this feedback; keep everything already working as-is.';

      const formData = new FormData();
      formData.append('resume', file);
      formData.append('job_title', 'Critique-based rewrite');
      formData.append('company', categoryLabel);
      formData.append('job_description', jobDescription);

      const res = await fetch(`${API_BASE_URL}/api/tailor-resume`, {
        method: 'POST',
        body: formData,
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      });
      if (!res.ok) {
        if (res.status === 429) {
          const body = await res.json().catch(() => null);
          throw new Error(body?.detail?.message || "You've hit the weekly tailor limit.");
        }
        const text = await res.text();
        throw new Error(text || `Server error ${res.status}`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `resume_improved_${(result.name || 'resume').replace(/[^\w-]/g, '_')}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      setError(e.message ?? 'Failed to generate improved resume.');
    } finally {
      setGenerating(false);
    }
  };

  if (!isLoaded) {
    return <div className="min-h-screen bg-bg" />;
  }

  if (!isSignedIn) {
    return (
      <div className="min-h-screen bg-bg text-text-primary font-sans">
        <header className="flex items-center justify-between px-9 py-4 border-b border-lp-border">
          <div className="flex items-center gap-3.5">
            <Logo size={24} />
            <div className="w-px h-5 bg-[rgba(31,27,22,0.15)]" />
            <div className="text-sm font-semibold tracking-wide">Critique</div>
          </div>
        </header>
        <div className="max-w-[860px] mx-auto px-6 py-24">
          <h2 className="font-serif text-3xl text-text-primary mb-3">Sign in to use Critique.</h2>
          <p className="font-mono text-xs text-text-tertiary mb-8 max-w-sm">
            Upload a resume and get bullet-level feedback tied to your account's weekly limit.
          </p>
          <SignInButton mode="modal">
            <button className="inline-block bg-text-primary text-bg px-5 py-2.5 font-mono text-xs tracking-wide hover:opacity-80 transition-opacity">
              Sign in →
            </button>
          </SignInButton>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-bg text-text-primary font-sans" style={{ fontFamily: "'Source Sans 3', system-ui, sans-serif" }}>
      <style>{`@keyframes rise { from { opacity: 0; transform: translateY(7px); } to { opacity: 1; transform: translateY(0); } }
        @media (prefers-reduced-motion: reduce) { [style*="animation: rise"] { animation: none !important; opacity: 1 !important; transform: none !important; } }`}</style>

      {/* Header */}
      <header className="flex items-center justify-between px-9 py-4 border-b border-lp-border">
        <div className="flex items-center gap-3.5">
          <Logo size={24} />
          <div className="w-px h-5" style={{ background: 'rgba(31,27,22,0.15)' }} />
          <div className="text-sm font-semibold tracking-wide">Critique</div>
        </div>
        {file && (
          <div className="flex items-center gap-3.5">
            <div
              className="flex items-center gap-2 px-3 py-[5px] rounded-full border border-lp-border"
              style={{ background: 'var(--lp-surface)' }}
            >
              <span className="w-1.5 h-1.5 rounded-full" style={{ background: 'hsl(142 72% 45%)' }} />
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

      {/* Upload prompt — before any resume is critiqued */}
      {!result && (
        <div className="flex flex-col items-center justify-center px-8 py-24 gap-4">
          <label
            className="flex flex-col items-center justify-center w-full max-w-md h-40 border-2 border-dashed rounded-lg cursor-pointer transition-colors"
            style={{ borderColor: 'rgba(31,27,22,0.2)', background: 'var(--lp-surface)' }}
          >
            <div className="flex flex-col items-center gap-2">
              <Upload className="h-8 w-8 text-text-tertiary" />
              <p className="text-sm font-medium text-text-primary">
                {loading ? 'Reading your resume…' : 'Click to upload a resume'}
              </p>
              <p className="text-xs text-text-tertiary">PDF only</p>
            </div>
            <input type="file" accept=".pdf" className="hidden" onChange={handleFileChange} disabled={loading} />
          </label>
        </div>
      )}

      {/* Content row */}
      {result && (
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

            <div
              className="rounded-[10px] border border-lp-border p-[16px_18px]"
              style={{ background: 'var(--lp-surface)', animation: 'rise 0.5s ease 0.41s both' }}
            >
              <div className="text-[11px] font-bold tracking-[0.09em] uppercase text-text-tertiary mb-2">
                Turn this feedback into a new resume
              </div>
              <p className="mb-3 text-[12.5px] leading-relaxed text-text-secondary">
                We'll rewrite the flagged lines, keep everything that already works, and give you a fresh PDF to review.
              </p>
              <label htmlFor="extra-context" className="block text-xs font-semibold text-text-secondary mb-1.5">
                Anything we should know? <span className="font-normal text-text-tertiary">(optional)</span>
              </label>
              <textarea
                id="extra-context"
                rows={3}
                value={extraContext}
                onChange={(e) => setExtraContext(e.target.value)}
                placeholder="e.g. I'm targeting backend roles; the RISE Lab work was mostly data cleaning…"
                className="w-full box-border bg-card border border-lp-border rounded-lg px-[11px] py-[9px] text-[12.5px] leading-relaxed text-text-primary resize-y outline-none focus:border-text-primary"
              />
              <div className="mt-3">
                <Button className="w-full" onClick={handleGenerate} disabled={generating}>
                  {generating ? 'Generating…' : 'Generate my improved resume'}
                </Button>
              </div>
            </div>
          </aside>

          {/* Resume page */}
          <main className="w-[720px] flex-none">
            <div
              className="box-border"
              style={{
                background: '#FDFCFA',
                border: '1px solid rgba(31,27,22,0.08)',
                borderRadius: 2,
                boxShadow: '0 1px 2px rgba(31,27,22,0.08), 0 16px 48px rgba(31,27,22,0.14)',
                padding: '56px 64px 64px',
                minHeight: 920,
                fontFamily: "'Source Serif 4', Georgia, serif",
                color: '#1a1a1a',
              }}
            >
              {/* Resume header */}
              <div style={{ textAlign: 'center', animation: `rise 0.5s ease ${nextDelay()}s both` }}>
                <div style={{ fontSize: 26, fontWeight: 700, letterSpacing: '0.01em' }}>{result.name}</div>
                <div style={{ fontSize: '12.5px', color: '#444', marginTop: 6 }}>{contactLine(result)}</div>
              </div>

              {result.education.length > 0 && (
                <>
                  <div
                    style={{
                      fontSize: 12, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase',
                      borderBottom: '1px solid #1a1a1a', paddingBottom: 4, margin: '30px 0 12px',
                      animation: `rise 0.5s ease ${nextDelay()}s both`,
                    }}
                  >
                    Education
                  </div>
                  {result.education.map((ed, i) => (
                    <div key={i} style={{ animation: `rise 0.5s ease ${nextDelay()}s both`, marginBottom: 8 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                        <div style={{ fontSize: '13.5px', fontWeight: 700 }}>{ed.school}</div>
                        <div style={{ fontSize: '12.5px', fontStyle: 'italic', color: '#444' }}>{ed.dates}</div>
                      </div>
                      <div style={{ fontSize: 13, marginTop: 2 }}>{ed.degree}</div>
                    </div>
                  ))}
                </>
              )}

              {result.experience.length > 0 && (
                <>
                  <div
                    style={{
                      fontSize: 12, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase',
                      borderBottom: '1px solid #1a1a1a', paddingBottom: 4, margin: '28px 0 12px',
                      animation: `rise 0.5s ease ${nextDelay()}s both`,
                    }}
                  >
                    Experience
                  </div>
                  {result.experience.map((exp, i) => (
                    <div key={i} style={{ marginTop: i === 0 ? 0 : 18 }}>
                      <div style={{ animation: `rise 0.5s ease ${nextDelay()}s both` }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                          <div style={{ fontSize: '13.5px', fontWeight: 700 }}>{exp.title} — {exp.company}</div>
                          <div style={{ fontSize: '12.5px', fontStyle: 'italic', color: '#444' }}>{exp.dates}</div>
                        </div>
                        {exp.location && (
                          <div style={{ fontSize: '12.5px', fontStyle: 'italic', color: '#444', marginTop: 1 }}>{exp.location}</div>
                        )}
                      </div>
                      <ul style={{ listStyle: 'none', margin: '8px 0 0', padding: 0, display: 'flex', flexDirection: 'column', gap: 7 }}>
                        {exp.bullets.map((b) => (
                          <CritiqueBulletLi
                            key={b.id}
                            bullet={b}
                            flag={flagByBulletId[b.id]}
                            hovered={hovered}
                            onHover={setHovered}
                            delay={nextDelay()}
                          />
                        ))}
                      </ul>
                    </div>
                  ))}
                </>
              )}

              {result.projects.length > 0 && (
                <>
                  <div
                    style={{
                      fontSize: 12, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase',
                      borderBottom: '1px solid #1a1a1a', paddingBottom: 4, margin: '28px 0 12px',
                      animation: `rise 0.5s ease ${nextDelay()}s both`,
                    }}
                  >
                    Projects
                  </div>
                  {result.projects.map((proj, i) => (
                    <div key={i} style={{ marginTop: i === 0 ? 0 : 18 }}>
                      <div style={{ animation: `rise 0.5s ease ${nextDelay()}s both` }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                          <div style={{ fontSize: '13.5px', fontWeight: 700 }}>{proj.name}</div>
                          <div style={{ fontSize: '12.5px', fontStyle: 'italic', color: '#444' }}>{proj.dates}</div>
                        </div>
                      </div>
                      <ul style={{ listStyle: 'none', margin: '8px 0 0', padding: 0, display: 'flex', flexDirection: 'column', gap: 7 }}>
                        {proj.bullets.map((b) => (
                          <CritiqueBulletLi
                            key={b.id}
                            bullet={b}
                            flag={flagByBulletId[b.id]}
                            hovered={hovered}
                            onHover={setHovered}
                            delay={nextDelay()}
                          />
                        ))}
                      </ul>
                    </div>
                  ))}
                </>
              )}

              {Object.keys(result.skills).length > 0 && (
                <>
                  <div
                    style={{
                      fontSize: 12, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase',
                      borderBottom: '1px solid #1a1a1a', paddingBottom: 4, margin: '28px 0 12px',
                      animation: `rise 0.5s ease ${nextDelay()}s both`,
                    }}
                  >
                    Skills
                  </div>
                  <div style={{ fontSize: '13.5px', lineHeight: 1.6, animation: `rise 0.5s ease ${nextDelay()}s both` }}>
                    {Object.entries(result.skills).map(([label, value], i, arr) => (
                      <React.Fragment key={label}>
                        <span style={{ fontWeight: 700 }}>{label}:</span> {value}
                        {i < arr.length - 1 && <>{'  ·  '}</>}
                      </React.Fragment>
                    ))}
                  </div>
                </>
              )}
            </div>
          </main>

          {/* Right rail reserved for hover comments */}
          <div className="w-[300px] flex-none" aria-hidden="true" />
        </div>
      )}
    </div>
  );
};

export default CritiquePage;
