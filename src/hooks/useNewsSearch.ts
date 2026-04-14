import { useMemo } from 'react';
import { mockArticles } from '../data/mockArticles';
import { SearchFilters, SearchResult } from '../types';

export function useNewsSearch(
  keyword: string,
  filters: SearchFilters,
): { result: SearchResult | null } {
  const result = useMemo(() => {
    const q = keyword.trim();
    if (!q) return null;

    const now = new Date();
    const queryTokens = q.toLowerCase().split(/\s+/);

    const filtered = mockArticles.filter((article) => {
      const haystack = (article.title + ' ' + article.topic).toLowerCase();
      const matchesKeyword = queryTokens.every((token) =>
        haystack.includes(token),
      );
      if (!matchesKeyword) return false;

      const articleDate = new Date(article.publishedAt);
      if (filters.dateRange === 'today') {
        const todayStart = new Date(
          now.getFullYear(),
          now.getMonth(),
          now.getDate(),
        );
        if (articleDate < todayStart) return false;
      } else if (filters.dateRange === 'week') {
        const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
        if (articleDate < weekAgo) return false;
      } else if (filters.dateRange === 'month') {
        const monthAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
        if (articleDate < monthAgo) return false;
      }

      if (filters.biasLevel !== 'all' && article.biasLevel !== filters.biasLevel) {
        return false;
      }

      return true;
    });

    const byDate = (a: { publishedAt: string }, b: { publishedAt: string }) =>
      new Date(b.publishedAt).getTime() - new Date(a.publishedAt).getTime();

    return {
      keyword: q,
      leftArticles: filtered.filter((a) => a.bias === 'LEFT').sort(byDate),
      rightArticles: filtered.filter((a) => a.bias === 'RIGHT').sort(byDate),
    };
  }, [keyword, filters]);

  return { result };
}
