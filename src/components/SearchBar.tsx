import { FormEvent, useRef } from 'react';

interface Props {
  value: string;
  onChange: (v: string) => void;
  onSearch: (q: string) => void;
}

const SUGGESTED = ['부동산', '최저임금', '검찰', '기후', '북한', '의료', '경제'];

export default function SearchBar({ value, onChange, onSearch }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const q = value.trim();
    if (q) onSearch(q);
  }

  return (
    <div className="w-full max-w-2xl mx-auto">
      <form onSubmit={handleSubmit} className="relative">
        <input
          ref={inputRef}
          type="search"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="검색어를 입력하세요 (예: 부동산, 최저임금, 검찰…)"
          className="w-full rounded-2xl border border-gray-300 bg-white px-5 py-4 pr-32 text-base shadow-md placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200 transition"
          autoFocus
        />
        <button
          type="submit"
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded-xl bg-gray-900 px-5 py-2.5 text-sm font-bold text-white hover:bg-gray-700 active:scale-95 transition"
        >
          비교 검색
        </button>
      </form>

      {/* Suggested keywords */}
      <div className="mt-3 flex flex-wrap justify-center gap-2">
        {SUGGESTED.map((kw) => (
          <button
            key={kw}
            type="button"
            onClick={() => {
              onChange(kw);
              onSearch(kw);
            }}
            className="rounded-full border border-gray-300 bg-white px-3 py-1 text-xs text-gray-600 hover:border-gray-500 hover:text-gray-900 transition"
          >
            {kw}
          </button>
        ))}
      </div>
    </div>
  );
}
