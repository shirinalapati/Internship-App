// Shared filter metadata + display helpers used by both the JobFilters control
// (on the Find page) and the read-only "Filters used" summary on the History page.
// Keeping the option lists and label maps in one place ensures the two stay in sync.

export type CitizenshipPref = 'any' | 'citizen_only' | 'exclude_citizen';

export interface Option<T extends string = string> {
  id: T;
  label: string;
}

// Position category ids MUST match POSITION_KEYWORDS keys in matching/job_filters.py
export const POSITION_OPTIONS: Option[] = [
  { id: 'software_engineer', label: 'Software Engineer' },
  { id: 'frontend', label: 'Frontend' },
  { id: 'backend', label: 'Backend' },
  { id: 'fullstack', label: 'Full Stack' },
  { id: 'data_science', label: 'Data Science / Analytics' },
  { id: 'data_engineering', label: 'Data Engineering' },
  { id: 'machine_learning', label: 'ML / AI' },
  { id: 'mobile', label: 'Mobile' },
  { id: 'cloud', label: 'Cloud' },
  { id: 'devops', label: 'DevOps / SRE' },
  { id: 'security', label: 'Security' },
  { id: 'qa', label: 'QA / Test' },
  { id: 'hardware', label: 'Hardware / Embedded' },
];

// Only large/enterprise employers can be identified reliably, so size collapses
// to two honest buckets.
export const COMPANY_SIZE_OPTIONS: Option[] = [
  { id: 'not_large', label: 'Startup / Mid-size' },
  { id: 'large', label: 'Large / Enterprise' },
];

export const CITIZENSHIP_OPTIONS: Option<CitizenshipPref>[] = [
  { id: 'any', label: 'All jobs' },
  { id: 'exclude_citizen', label: 'No U.S.-citizen-only jobs' },
  { id: 'citizen_only', label: 'U.S.-citizen jobs only' },
];

// Curated quick-pick list of well-known large employers, shown as toggle chips so
// users can restrict results to specific big companies without typing.
export const BIG_COMPANIES: string[] = [
  'Google', 'Meta', 'Amazon', 'Apple', 'Microsoft', 'Netflix', 'Nvidia',
  'Salesforce', 'Adobe', 'Intel', 'IBM', 'Oracle', 'Uber', 'Airbnb', 'Tesla',
  'Stripe', 'Snowflake', 'Databricks', 'Palantir', 'LinkedIn', 'Spotify',
  'JPMorgan Chase', 'Goldman Sachs', 'Capital One',
];

const POSITION_LABELS: Record<string, string> = Object.fromEntries(
  POSITION_OPTIONS.map((o) => [o.id, o.label])
);
const COMPANY_SIZE_LABELS: Record<string, string> = Object.fromEntries(
  COMPANY_SIZE_OPTIONS.map((o) => [o.id, o.label])
);
const CITIZENSHIP_LABELS: Record<string, string> = Object.fromEntries(
  CITIZENSHIP_OPTIONS.map((o) => [o.id, o.label])
);

// Shape of the filters payload persisted alongside a resume analysis (snake_case,
// mirrors buildFiltersPayload on the Find page and normalize_filters on the backend).
export interface StoredFilters {
  locations?: string[];
  positions?: string[];
  company_sizes?: string[];
  citizenship?: string;
  avoid_companies?: string[];
  target_companies?: string[];
}

export interface FilterGroup {
  label: string;
  values: string[];
}

/** Turn a stored filters payload into human-readable groups for the History page. */
export function describeStoredFilters(f: StoredFilters | null | undefined): FilterGroup[] {
  if (!f) return [];
  const groups: FilterGroup[] = [];

  if (f.locations?.length) groups.push({ label: 'Location', values: f.locations });
  if (f.positions?.length) {
    groups.push({ label: 'Position', values: f.positions.map((p) => POSITION_LABELS[p] ?? p) });
  }
  if (f.target_companies?.length) {
    groups.push({ label: 'Companies', values: f.target_companies });
  }
  if (f.company_sizes?.length) {
    groups.push({ label: 'Company size', values: f.company_sizes.map((s) => COMPANY_SIZE_LABELS[s] ?? s) });
  }
  if (f.citizenship && f.citizenship !== 'any') {
    groups.push({ label: 'Citizenship', values: [CITIZENSHIP_LABELS[f.citizenship] ?? f.citizenship] });
  }
  if (f.avoid_companies?.length) {
    groups.push({ label: 'Avoiding', values: f.avoid_companies });
  }

  return groups;
}
