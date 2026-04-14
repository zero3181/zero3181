export type BiasType = 'LEFT' | 'RIGHT';
export type DateRangeFilter = 'today' | 'week' | 'month' | 'all';
export type BiasLevelFilter = 'all' | 'moderate' | 'extreme';

export interface Media {
  id: number;
  name: string;
  bias: BiasType;
  url: string;
}

export interface Article {
  id: string;
  mediaId: number;
  mediaName: string;
  title: string;
  url: string;
  publishedAt: string;
  topic: string;
  bias: BiasType;
  biasLevel: 'moderate' | 'extreme';
}

export interface SearchFilters {
  dateRange: DateRangeFilter;
  biasLevel: BiasLevelFilter;
}

export interface SearchResult {
  keyword: string;
  leftArticles: Article[];
  rightArticles: Article[];
}
