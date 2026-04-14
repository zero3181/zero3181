import { SearchFilters, DateRangeFilter, BiasLevelFilter } from '../types';

interface Props {
  filters: SearchFilters;
  onChange: (f: SearchFilters) => void;
}

const DATE_OPTIONS: { label: string; value: DateRangeFilter }[] = [
  { label: '전체', value: 'all' },
  { label: '오늘', value: 'today' },
  { label: '1주일', value: 'week' },
  { label: '1개월', value: 'month' },
];

const BIAS_OPTIONS: { label: string; value: BiasLevelFilter }[] = [
  { label: '전체', value: 'all' },
  { label: '중도 편향', value: 'moderate' },
  { label: '강경 편향', value: 'extreme' },
];

export default function FilterPanel({ filters, onChange }: Props) {
  return (
    <div className="flex flex-wrap items-center justify-center gap-4 mt-5">
      {/* Date range */}
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
          기간
        </span>
        <div className="flex rounded-lg border border-gray-200 overflow-hidden bg-white shadow-sm">
          {DATE_OPTIONS.map(({ label, value }) => (
            <button
              key={value}
              onClick={() => onChange({ ...filters, dateRange: value })}
              className={`px-3 py-1.5 text-xs font-medium transition ${
                filters.dateRange === value
                  ? 'bg-gray-900 text-white'
                  : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Bias level */}
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
          편향 강도
        </span>
        <div className="flex rounded-lg border border-gray-200 overflow-hidden bg-white shadow-sm">
          {BIAS_OPTIONS.map(({ label, value }) => (
            <button
              key={value}
              onClick={() => onChange({ ...filters, biasLevel: value })}
              className={`px-3 py-1.5 text-xs font-medium transition ${
                filters.biasLevel === value
                  ? 'bg-gray-900 text-white'
                  : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
