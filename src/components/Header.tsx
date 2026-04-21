import { stats } from '../data/travels';

export default function Header() {
  return (
    <header className="bg-slate-900/95 backdrop-blur border-b border-slate-700/50 px-4 py-3 flex items-center justify-between z-50 relative">
      <div className="flex items-center gap-3">
        <span className="text-2xl">✈</span>
        <div>
          <h1 className="text-white font-bold text-lg leading-none tracking-wide">
            My Travel Story
          </h1>
          <p className="text-slate-400 text-xs mt-0.5">세계를 담은 나의 여행기</p>
        </div>
      </div>

      <div className="flex items-center gap-6">
        <Stat value={stats.countries} label="Countries" />
        <Stat value={stats.cities} label="Cities" />
        <Stat value={stats.photos} label="Photos" />
      </div>
    </header>
  );
}

function Stat({ value, label }: { value: number; label: string }) {
  return (
    <div className="text-center hidden sm:block">
      <div className="text-amber-400 font-bold text-lg leading-none">{value}</div>
      <div className="text-slate-400 text-xs mt-0.5">{label}</div>
    </div>
  );
}
