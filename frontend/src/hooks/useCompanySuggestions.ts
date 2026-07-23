import { useState, useEffect } from 'react';
import { API_BASE_URL } from '../lib/api';
import { COMPANY_SUGGESTIONS } from '../lib/filterSuggestions';

/**
 * Company names to power the avoid/target-company filter autocompletes,
 * sourced from GET /api/companies — the real, currently-scraped company
 * strings (cached server-side, refreshed on every scrape). Matching against
 * these exact spellings instead of a hand-typed guess avoids canonicalization
 * mismatches (e.g. "JPMorgan Chase" vs the scraped "JP Morgan Chase").
 *
 * Falls back to the static curated list if the fetch fails or the backend
 * has no active jobs yet, so the input is never empty.
 */
export function useCompanySuggestions() {
  const [companies, setCompanies] = useState<string[]>(COMPANY_SUGGESTIONS);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/companies`);
        if (!res.ok) throw new Error(`Server error ${res.status}`);
        const json = await res.json();
        if (!cancelled && Array.isArray(json.companies) && json.companies.length > 0) {
          setCompanies(json.companies);
        }
      } catch {
        // Keep the static fallback already in state — no need to surface
        // this as an error, the input still works with curated suggestions.
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  return { companies, loading };
}
