import { Article, BiasType } from '../types';

interface Props {
  article: Article;
  bias: BiasType;
  keyword: string;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}분 전`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}시간 전`;
  return d.toLocaleDateString('ko-KR', { month: 'long', day: 'numeric' });
}

function highlight(text: string, keyword: string): string {
  if (!keyword.trim()) return text;
  const escaped = keyword.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return text.replace(
    new RegExp(`(${escaped})`, 'gi'),
    '<mark class="bg-yellow-200 text-yellow-900 rounded px-0.5">$1</mark>',
  );
}

const borderColor: Record<BiasType, string> = {
  LEFT: 'border-l-blue-500',
  RIGHT: 'border-l-red-500',
};

const badgeColor: Record<BiasType, string> = {
  LEFT: 'bg-blue-100 text-blue-700',
  RIGHT: 'bg-red-100 text-red-700',
};

export default function NewsCard({ article, bias, keyword }: Props) {
  return (
    <a
      href={article.url}
      target="_blank"
      rel="noopener noreferrer"
      className={`group block rounded-xl border border-gray-100 border-l-4 ${borderColor[bias]} bg-white p-4 shadow-sm hover:shadow-md hover:-translate-y-0.5 transition-all duration-200`}
    >
      {/* Media + time */}
      <div className="flex items-center justify-between mb-2">
        <span
          className={`inline-block rounded-full px-2 py-0.5 text-xs font-semibold ${badgeColor[bias]}`}
        >
          {article.mediaName}
        </span>
        <span className="text-xs text-gray-400">{formatDate(article.publishedAt)}</span>
      </div>

      {/* Title */}
      <p
        className="text-sm font-medium text-gray-800 leading-snug line-clamp-3 group-hover:text-gray-950 transition-colors"
        dangerouslySetInnerHTML={{ __html: highlight(article.title, keyword) }}
      />

      {/* Topic tag + link icon */}
      <div className="mt-3 flex items-center justify-between">
        <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500">
          #{article.topic}
        </span>
        <span className="text-gray-400 text-xs group-hover:text-gray-600 transition-colors">
          원문 →
        </span>
      </div>

      {article.biasLevel === 'extreme' && (
        <div className="mt-2 text-xs text-orange-600 font-medium">
          ⚠ 강경 편향 보도
        </div>
      )}
    </a>
  );
}
