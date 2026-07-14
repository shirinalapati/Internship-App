import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@clerk/react';
import { API_BASE_URL } from '../lib/api';

export interface QuotaMetric {
  limit: number;
  used: number;
  remaining: number;
  reset_at: string | null;
  window_days: number;
}

export interface UsageData {
  tailor_resume: QuotaMetric;
  think_deeper: QuotaMetric;
  /** Consumed by API-key remote compiles (MCP /api/v1), not the in-app tailor feature. */
  remote_compile: QuotaMetric;
  /** Bullet-level resume feedback (/critique). Cache hits are free and don't count here. */
  critique: QuotaMetric;
}

export function useUsage() {
  const { isSignedIn, getToken } = useAuth();
  const [data, setData] = useState<UsageData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const fetchUsage = useCallback(async () => {
    if (!isSignedIn) return;
    setLoading(true);
    setError('');
    try {
      const token = await getToken();
      const res = await fetch(`${API_BASE_URL}/api/usage`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`Server error ${res.status}`);
      const json: UsageData = await res.json();
      setData(json);
    } catch (e: any) {
      setError(e.message ?? 'Failed to load usage.');
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isSignedIn]);

  useEffect(() => {
    fetchUsage();
  }, [fetchUsage]);

  return { data, loading, error, refetch: fetchUsage };
}
