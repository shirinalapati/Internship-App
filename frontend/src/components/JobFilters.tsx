import React, { useState } from 'react';
import { SlidersHorizontal, ChevronDown, X } from 'lucide-react';
import { cn } from '../lib/utils';
import TagAutocomplete from './ui/tag-autocomplete';
import { LOCATION_SUGGESTIONS, COMPANY_SUGGESTIONS } from '../lib/filterSuggestions';
import {
  CitizenshipPref,
  POSITION_OPTIONS,
  COMPANY_SIZE_OPTIONS,
  CITIZENSHIP_OPTIONS,
  BIG_COMPANIES,
} from '../lib/filterLabels';

export type { CitizenshipPref };

export interface JobFilterState {
  locations: string[];        // selected location tags
  positions: string[];        // category ids (see POSITION_OPTIONS)
  targetCompanies: string[];  // specific big companies to restrict results to
  companySizes: string[];     // 'large' | 'not_large'
  citizenship: CitizenshipPref;
  avoidCompanies: string[];   // company name tags to exclude
}

export const EMPTY_FILTERS: JobFilterState = {
  locations: [],
  positions: [],
  targetCompanies: [],
  companySizes: [],
  citizenship: 'any',
  avoidCompanies: [],
};

export function isFilterActive(f: JobFilterState): boolean {
  return Boolean(
    f.locations.length ||
    f.positions.length ||
    f.targetCompanies.length ||
    f.companySizes.length ||
    f.avoidCompanies.length ||
    f.citizenship !== 'any'
  );
}

/** Stable signature used to key the result cache per filter combination. */
export function filterSignature(f: JobFilterState): string {
  const norm = (arr: string[]) => [...arr].map(s => s.trim().toLowerCase()).filter(Boolean).sort().join('|');
  return [
    norm(f.locations),
    [...f.positions].sort().join('|'),
    norm(f.targetCompanies),
    [...f.companySizes].sort().join('|'),
    f.citizenship,
    norm(f.avoidCompanies),
  ].join('::');
}

interface JobFiltersProps {
  value: JobFilterState;
  onChange: (next: JobFilterState) => void;
  disabled?: boolean;
  /** When true the panel renders expanded with no collapse toggle (sidebar use). */
  alwaysOpen?: boolean;
}

const focusRing =
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ia focus-visible:ring-offset-2 focus-visible:ring-offset-bg';

const JobFilters: React.FC<JobFiltersProps> = ({ value, onChange, disabled, alwaysOpen }) => {
  const [open, setOpen] = useState(false);
  const active = isFilterActive(value);
  const expanded = alwaysOpen || open;

  const activeCount =
    value.locations.length +
    value.positions.length +
    value.targetCompanies.length +
    value.companySizes.length +
    value.avoidCompanies.length +
    (value.citizenship !== 'any' ? 1 : 0);

  const toggleInArray = (arr: string[], id: string): string[] =>
    arr.includes(id) ? arr.filter(x => x !== id) : [...arr, id];

  const chip = (selected: boolean, label: string, onClick: () => void) => (
    <button
      key={label}
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'font-mono text-[11px] px-2.5 py-1 border transition-colors disabled:opacity-40',
        focusRing,
        selected
          ? 'border-ia bg-ia-subtle text-text-primary'
          : 'border-lp-border text-text-secondary hover:border-ia/50'
      )}
    >
      {label}
    </button>
  );

  const sectionLabel = (text: string) => (
    <div className="font-mono text-[10px] uppercase tracking-widest text-text-tertiary mb-2">
      {text}
    </div>
  );

  const clearBtn = (
    <span
      role="button"
      tabIndex={0}
      onClick={(e) => { e.stopPropagation(); onChange(EMPTY_FILTERS); }}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.stopPropagation(); onChange(EMPTY_FILTERS); } }}
      className="inline-flex items-center gap-1 font-mono text-[10px] text-text-tertiary hover:text-text-primary transition-colors"
    >
      <X className="h-3 w-3" /> Clear
    </span>
  );

  return (
    <div className="border border-lp-border bg-surface">
      {/* Header */}
      {alwaysOpen ? (
        <div className="flex items-center justify-between gap-3 p-3.5 border-b border-lp-border">
          <div className="flex items-center gap-3 min-w-0">
            <div className={cn(
              'flex-shrink-0 h-8 w-8 flex items-center justify-center transition-colors',
              active ? 'bg-ia text-bg' : 'bg-lp-border/20 text-text-tertiary'
            )}>
              <SlidersHorizontal className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <span className="text-sm font-semibold text-text-primary">Filters</span>
              <p className="text-xs mt-0.5 text-text-tertiary truncate">
                {active ? `${activeCount} applied` : 'Refine your matches'}
              </p>
            </div>
          </div>
          {active && clearBtn}
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setOpen(o => !o)}
          className={cn('w-full flex items-center justify-between gap-3 p-3.5 text-left', focusRing)}
        >
          <div className="flex items-center gap-3 min-w-0">
            <div className={cn(
              'flex-shrink-0 h-8 w-8 flex items-center justify-center transition-colors',
              active ? 'bg-ia text-bg' : 'bg-lp-border/20 text-text-tertiary'
            )}>
              <SlidersHorizontal className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <span className={cn('text-sm font-semibold', active ? 'text-text-primary' : 'text-text-secondary')}>
                Filters
              </span>
              <p className="text-xs mt-0.5 text-text-tertiary truncate">
                {active ? `${activeCount} filter${activeCount !== 1 ? 's' : ''} applied` : 'Narrow results by location, role, company & more'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            {active && clearBtn}
            <ChevronDown className={cn('h-4 w-4 text-text-tertiary transition-transform', open && 'rotate-180')} />
          </div>
        </button>
      )}

      {/* Body */}
      {expanded && (
        <div className={cn('p-4 space-y-5', !alwaysOpen && 'border-t border-lp-border')}>
          {/* Location */}
          <div>
            {sectionLabel('Location')}
            <TagAutocomplete
              value={value.locations}
              onChange={(locations) => onChange({ ...value, locations })}
              suggestions={LOCATION_SUGGESTIONS}
              placeholder="Type a city, state, or “Remote”…"
              disabled={disabled}
              ariaLabel="Add a location filter"
            />
            <p className="font-mono text-[10px] text-text-tertiary mt-1">Add multiple — results match any of them.</p>
          </div>

          {/* Position */}
          <div>
            {sectionLabel('Position')}
            <div className="flex flex-wrap gap-1.5">
              {POSITION_OPTIONS.map(opt =>
                chip(value.positions.includes(opt.id), opt.label, () =>
                  onChange({ ...value, positions: toggleInArray(value.positions, opt.id) })
                )
              )}
            </div>
          </div>

          {/* Big companies */}
          <div>
            {sectionLabel('Big companies')}
            <div className="flex flex-wrap gap-1.5">
              {BIG_COMPANIES.map(name =>
                chip(value.targetCompanies.includes(name), name, () =>
                  onChange({ ...value, targetCompanies: toggleInArray(value.targetCompanies, name) })
                )
              )}
            </div>
            <p className="font-mono text-[10px] text-text-tertiary mt-1">Pick specific employers to show only their roles.</p>
          </div>

          {/* Company size */}
          <div>
            {sectionLabel('Company size')}
            <div className="flex flex-wrap gap-1.5">
              {COMPANY_SIZE_OPTIONS.map(opt =>
                chip(value.companySizes.includes(opt.id), opt.label, () =>
                  onChange({ ...value, companySizes: toggleInArray(value.companySizes, opt.id) })
                )
              )}
            </div>
            <p className="font-mono text-[10px] text-text-tertiary mt-1">Best-effort — “Large” is matched against well-known enterprise employers.</p>
          </div>

          {/* Citizenship */}
          <div>
            {sectionLabel('U.S. citizenship')}
            <div className="flex flex-wrap gap-1.5">
              {CITIZENSHIP_OPTIONS.map(opt =>
                chip(value.citizenship === opt.id, opt.label, () =>
                  onChange({ ...value, citizenship: opt.id })
                )
              )}
            </div>
            {value.citizenship === 'exclude_citizen' && (
              <p className="font-mono text-[10px] text-text-tertiary mt-1">Hides roles requiring U.S. citizenship or that don’t offer sponsorship.</p>
            )}
            {value.citizenship === 'citizen_only' && (
              <p className="font-mono text-[10px] text-text-tertiary mt-1">Shows only roles that require U.S. citizenship.</p>
            )}
          </div>

          {/* Companies to avoid */}
          <div>
            {sectionLabel('Companies to avoid')}
            <TagAutocomplete
              value={value.avoidCompanies}
              onChange={(avoidCompanies) => onChange({ ...value, avoidCompanies })}
              suggestions={COMPANY_SUGGESTIONS}
              placeholder="Type a company to exclude…"
              disabled={disabled}
              ariaLabel="Add a company to avoid"
            />
            <p className="font-mono text-[10px] text-text-tertiary mt-1">These companies are excluded from results.</p>
          </div>
        </div>
      )}
    </div>
  );
};

export default JobFilters;
