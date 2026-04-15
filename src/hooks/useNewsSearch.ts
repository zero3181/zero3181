import { useState, useEffect } from 'react';
import { fetchGoogleNews } from '../utils/googleNewsApi';
import { Article, SearchFilters, SearchResult } from '../types';

function applyFilters(articles: Article[], filters: SearchFilters): Article[] {
  const now = new Date();
  return articles.filter((a) => {
    const d = new Date(a.publishedAt);
    if (filters.dateRange === 'today') {
      const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      if (d < todayStart) return false;
    } else if (filters.dateRange === 'week') {
      if (d < new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)) return false;
    } else if (filters.dateRange === 'month') {
      if (d < new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000)) return false;
    }
    if (filters.biasLevel !== 'all' && a.biasLevel !== filters.biasLevel) return false;
    return true;
  });
}

export function useNewsSearch(
  keyword: string,
  filters: SearchFilters,
): { result: SearchResult | null; isLoading: boolean; error: string | null } {
  const [result, setResult]     = useState<SearchResult | null>(null);
  const [isLoading, setLoading] = useState(false);
  const [error, setError]       = useState<string | null>(null);

  useEffect(() => {
    const q = keyword.trim();
    if (!q) {
      setResult(null);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    Promise.all([fetchGoogleNews(q, 'LEFT'), fetchGoogleNews(q, 'RIGHT')])
      .then(([left, right]) => {
        if (cancelled) return;
        setResult({
          keyword: q,
          leftArticles:  applyFilters(left,  filters),
          rightArticles: applyFilters(right, filters),
        });
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [keyword, filters]);

  return { result, isLoading, error };
}
