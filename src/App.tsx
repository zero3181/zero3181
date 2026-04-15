import { useState, useCallback } from 'react';
import Header from './components/Header';
import SearchBar from './components/SearchBar';
import FilterPanel from './components/FilterPanel';
import NewsColumn from './components/NewsColumn';
import { useNewsSearch } from './hooks/useNewsSearch';
import { SearchFilters } from './types';

const DEFAULT_FILTERS: SearchFilters = {
  dateRange: 'all',
  biasLevel: 'all',
};

const TOPICS = ['부동산', '최저임금', '검찰', '기후', '북한', '의료', '경제'];

export default function App() {
  const [inputValue, setInputValue] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [filters, setFilters] = useState<SearchFilters>(DEFAULT_FILTERS);

  const { result, isLoading, error } = useNewsSearch(searchQuery, filters);

  const handleSearch = useCallback((q: string) => {
    setSearchQuery(q);
  }, []);

  const hasResults =
    result !== null &&
    (result.leftArticles.length > 0 || result.rightArticles.length > 0);

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <Header />

      <main className="flex-1">
        {/* Hero / Search area */}
        <section className="bg-gradient-to-b from-gray-950 to-gray-900 py-10 px-4">
          <div className="max-w-7xl mx-auto text-center mb-8">
            <p className="text-gray-300 text-base">
              같은 사건, 서로 다른 시선 — 좌·우 언론의 관점을 한 화면에서 비교하세요
            </p>
          </div>
          <SearchBar
            value={inputValue}
            onChange={setInputValue}
            onSearch={handleSearch}
          />
          <FilterPanel filters={filters} onChange={setFilters} />
        </section>

        <div className="max-w-7xl mx-auto px-4 py-8">
          {/* No search yet — landing */}
          {!searchQuery && (
            <div className="text-center py-16">
              <div className="inline-flex items-center gap-6 mb-8">
                <div className="w-20 h-20 rounded-2xl bg-blue-600 flex items-center justify-center shadow-lg">
                  <span className="text-white text-3xl font-black">좌</span>
                </div>
                <div className="flex flex-col gap-1">
                  <div className="h-1 w-10 rounded bg-blue-300" />
                  <div className="h-1 w-14 rounded bg-gray-400" />
                  <div className="h-1 w-10 rounded bg-red-300" />
                </div>
                <div className="w-20 h-20 rounded-2xl bg-red-600 flex items-center justify-center shadow-lg">
                  <span className="text-white text-3xl font-black">우</span>
                </div>
              </div>
              <h2 className="text-2xl font-bold text-gray-800 mb-2">
                뉴스 편향을 나란히 비교하세요
              </h2>
              <p className="text-gray-500 mb-8 max-w-md mx-auto text-sm leading-relaxed">
                검색어를 입력하면 진보·좌편향 매체와 보수·우편향 매체가
                <br />
                같은 이슈를 어떻게 다르게 보도했는지 한눈에 볼 수 있습니다.
              </p>

              {/* Topic chips */}
              <div className="mb-4">
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">
                  추천 검색어
                </p>
                <div className="flex flex-wrap justify-center gap-2">
                  {TOPICS.map((topic) => (
                    <button
                      key={topic}
                      onClick={() => {
                        setInputValue(topic);
                        handleSearch(topic);
                      }}
                      className="rounded-full border-2 border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:border-gray-800 hover:bg-gray-900 hover:text-white transition"
                    >
                      {topic}
                    </button>
                  ))}
                </div>
              </div>

              {/* Media legend */}
              <div className="mt-10 grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-xl mx-auto">
                <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 text-left">
                  <p className="text-xs font-bold text-blue-700 mb-2">진보·좌편향 매체</p>
                  <p className="text-xs text-blue-600 leading-relaxed">
                    경향신문, 한겨레, 오마이뉴스, JTBC, MBC, YTN, 뉴스타파, 서울신문
                  </p>
                </div>
                <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-left">
                  <p className="text-xs font-bold text-red-700 mb-2">보수·우편향 매체</p>
                  <p className="text-xs text-red-600 leading-relaxed">
                    조선일보, 중앙일보, 동아일보, TV조선, 채널A, 문화일보, 세계일보, 국민일보
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Search results */}
          {searchQuery && (
            <>
              {/* Results header */}
              <div className="flex items-center justify-between mb-5">
                <div>
                  <h2 className="text-lg font-bold text-gray-900">
                    <span className="text-gray-500 font-normal">"</span>
                    {searchQuery}
                    <span className="text-gray-500 font-normal">"</span> 검색 결과
                  </h2>
                  {result && !isLoading && (
                    <p className="text-sm text-gray-500 mt-0.5">
                      좌편향{' '}
                      <span className="font-semibold text-blue-600">
                        {result.leftArticles.length}건
                      </span>{' '}
                      · 우편향{' '}
                      <span className="font-semibold text-red-600">
                        {result.rightArticles.length}건
                      </span>
                    </p>
                  )}
                </div>
                <button
                  onClick={() => {
                    setSearchQuery('');
                    setInputValue('');
                  }}
                  className="text-xs text-gray-400 hover:text-gray-700 border border-gray-200 rounded-lg px-3 py-1.5 transition"
                >
                  검색 초기화
                </button>
              </div>

              {/* Loading */}
              {isLoading && (
                <div className="flex flex-col items-center justify-center py-20 gap-4">
                  <div className="flex gap-2">
                    <div className="h-3 w-3 rounded-full bg-blue-500 animate-bounce [animation-delay:-0.3s]" />
                    <div className="h-3 w-3 rounded-full bg-gray-400 animate-bounce [animation-delay:-0.15s]" />
                    <div className="h-3 w-3 rounded-full bg-red-500 animate-bounce" />
                  </div>
                  <p className="text-sm text-gray-500">
                    좌·우 언론사 기사를 불러오는 중…
                  </p>
                </div>
              )}

              {/* Error */}
              {!isLoading && error && (
                <div className="rounded-xl border border-orange-200 bg-orange-50 p-6 text-center">
                  <p className="font-medium text-orange-700 mb-1">뉴스를 불러오지 못했습니다</p>
                  <p className="text-sm text-orange-500">{error}</p>
                  <p className="text-xs text-gray-400 mt-3">
                    CORS 프록시 서버가 일시적으로 불안정할 수 있습니다. 잠시 후 다시 검색해주세요.
                  </p>
                </div>
              )}

              {/* Results */}
              {!isLoading && !error && !hasResults && result && (
                <div className="text-center py-16">
                  <span className="text-4xl mb-4 block">🔍</span>
                  <p className="text-gray-600 font-medium">
                    "{searchQuery}"에 대한 기사를 찾지 못했습니다
                  </p>
                  <p className="text-sm text-gray-400 mt-2">
                    다른 키워드로 검색해보세요
                  </p>
                </div>
              )}

              {!isLoading && !error && hasResults && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                  <NewsColumn
                    side="left"
                    articles={result!.leftArticles}
                    keyword={searchQuery}
                  />
                  <NewsColumn
                    side="right"
                    articles={result!.rightArticles}
                    keyword={searchQuery}
                  />
                </div>
              )}
            </>
          )}
        </div>
      </main>

      <footer className="border-t border-gray-200 bg-white py-6 text-center text-xs text-gray-400">
        <p className="font-semibold text-gray-600 mb-1">좌우일보</p>
        <p>
          본 서비스의 기사 데이터는 시연용 목업 데이터입니다.
          각 기사 링크 클릭 시 해당 언론사 홈페이지로 이동합니다.
        </p>
        <p className="mt-1">
          매체 분류 기준은 다양한 언론 연구 자료를 참고하였으며, 절대적 기준이 아닙니다.
        </p>
      </footer>
    </div>
  );
}
