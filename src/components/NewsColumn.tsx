import { Article, BiasType } from '../types';
import NewsCard from './NewsCard';

interface Props {
  side: 'left' | 'right';
  articles: Article[];
  keyword: string;
}

const config = {
  left: {
    bias: 'LEFT' as BiasType,
    label: '진보·좌편향 매체',
    emoji: '◀',
    headerGradient: 'from-blue-700 to-blue-600',
    columnBg: 'bg-blue-50/60',
    borderColor: 'border-blue-200',
    countColor: 'text-blue-200',
    emptyColor: 'text-blue-400',
    emptyBg: 'bg-blue-100/50',
  },
  right: {
    bias: 'RIGHT' as BiasType,
    label: '보수·우편향 매체',
    emoji: '▶',
    headerGradient: 'from-red-700 to-red-600',
    columnBg: 'bg-red-50/60',
    borderColor: 'border-red-200',
    countColor: 'text-red-200',
    emptyColor: 'text-red-400',
    emptyBg: 'bg-red-100/50',
  },
};

export default function NewsColumn({ side, articles, keyword }: Props) {
  const cfg = config[side];

  return (
    <div className={`flex flex-col rounded-2xl border ${cfg.borderColor} ${cfg.columnBg} overflow-hidden shadow-sm`}>
      {/* Column header */}
      <div className={`bg-gradient-to-r ${cfg.headerGradient} px-5 py-3.5 flex items-center justify-between`}>
        <div className="flex items-center gap-2">
          <span className="text-white text-sm">{cfg.emoji}</span>
          <h2 className="text-white font-bold text-sm tracking-wide">{cfg.label}</h2>
        </div>
        <span className={`text-sm font-semibold ${cfg.countColor}`}>
          {articles.length}건
        </span>
      </div>

      {/* Article list */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3 max-h-[70vh]">
        {articles.length === 0 ? (
          <div className={`flex flex-col items-center justify-center py-12 rounded-xl ${cfg.emptyBg}`}>
            <span className={`text-3xl mb-2 ${cfg.emptyColor}`}>📭</span>
            <p className={`text-sm font-medium ${cfg.emptyColor}`}>검색 결과가 없습니다</p>
            <p className="text-xs text-gray-400 mt-1">다른 키워드를 시도해보세요</p>
          </div>
        ) : (
          articles.map((article) => (
            <NewsCard
              key={article.id}
              article={article}
              bias={cfg.bias}
              keyword={keyword}
            />
          ))
        )}
      </div>
    </div>
  );
}
