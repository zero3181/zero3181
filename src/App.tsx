import { useState } from 'react';
import Header from './components/Header';
import WorldMap from './components/WorldMap';
import LocationPanel from './components/LocationPanel';
import type { TravelLocation } from './types';
import { travelLocations } from './data/travels';

export default function App() {
  const [selectedLocation, setSelectedLocation] = useState<TravelLocation | null>(null);
  const [panelOpen, setPanelOpen] = useState(true);

  const handleLocationSelect = (location: TravelLocation | null) => {
    setSelectedLocation(location);
    if (location) setPanelOpen(true);
  };

  return (
    <div className="flex flex-col h-screen bg-slate-900 overflow-hidden">
      <Header />

      <div className="flex flex-1 min-h-0">
        <div className="flex-1 relative min-w-0">
          <WorldMap
            locations={travelLocations}
            selectedLocation={selectedLocation}
            onLocationSelect={handleLocationSelect}
          />

          <button
            onClick={() => setPanelOpen((v) => !v)}
            className="absolute top-3 right-3 z-20 bg-slate-800/90 hover:bg-slate-700 text-white px-3 py-1.5 rounded-lg text-xs border border-slate-600/50 transition-colors hidden lg:flex items-center gap-1.5"
          >
            {panelOpen ? '▶ 목록 닫기' : '◀ 목록 열기'}
          </button>
        </div>

        <div
          className={`
            transition-all duration-300 ease-in-out flex-shrink-0
            ${panelOpen ? 'w-80' : 'w-0'}
            border-l border-slate-700/50 overflow-hidden
            hidden lg:block
          `}
        >
          <div className="w-80 h-full">
            <LocationPanel
              selectedLocation={selectedLocation}
              onLocationSelect={handleLocationSelect}
            />
          </div>
        </div>
      </div>

      <div className="lg:hidden border-t border-slate-700/50 h-64 flex-shrink-0">
        <LocationPanel
          selectedLocation={selectedLocation}
          onLocationSelect={handleLocationSelect}
        />
      </div>
    </div>
  );
}
