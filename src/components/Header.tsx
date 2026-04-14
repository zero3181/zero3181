export default function Header() {
  return (
    <header className="bg-gray-950 text-white shadow-lg">
      <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          {/* Split logo */}
          <div className="flex h-10 w-10 overflow-hidden rounded-md shadow-md">
            <div className="flex-1 bg-blue-600 flex items-center justify-center">
              <span className="text-white text-xs font-black">좌</span>
            </div>
            <div className="flex-1 bg-red-600 flex items-center justify-center">
              <span className="text-white text-xs font-black">우</span>
            </div>
          </div>
          <div>
            <h1 className="text-2xl font-black tracking-tight leading-none">
              <span className="text-blue-400">좌</span>
              <span className="text-gray-100">우</span>
              <span className="text-red-400">일보</span>
            </h1>
            <p className="text-gray-400 text-xs mt-0.5">
              같은 사건, 다른 시선 — 좌우 언론 비교
            </p>
          </div>
        </div>

        <nav className="hidden sm:flex items-center gap-1">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-blue-700/60 bg-blue-900/30 px-3 py-1 text-xs text-blue-300">
            <span className="h-1.5 w-1.5 rounded-full bg-blue-400" />
            진보·좌편향
          </span>
          <span className="text-gray-600 px-1">vs</span>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-red-700/60 bg-red-900/30 px-3 py-1 text-xs text-red-300">
            <span className="h-1.5 w-1.5 rounded-full bg-red-400" />
            보수·우편향
          </span>
        </nav>
      </div>
    </header>
  );
}
