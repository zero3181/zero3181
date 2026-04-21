import { useState, useCallback } from 'react';
import { ComposableMap, Geographies, Geography, Marker, ZoomableGroup } from 'react-simple-maps';
import type { TravelLocation } from '../types';
import { visitedCountryCodes } from '../data/travels';

const GEO_URL = 'https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json';

interface Props {
  locations: TravelLocation[];
  selectedLocation: TravelLocation | null;
  onLocationSelect: (location: TravelLocation) => void;
}

interface TooltipState {
  name: string;
  x: number;
  y: number;
}

export default function WorldMap({ locations, selectedLocation, onLocationSelect }: Props) {
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);
  const [zoom, setZoom] = useState(1);
  const [center, setCenter] = useState<[number, number]>([10, 20]);

  const handleMoveEnd = useCallback(
    ({ zoom: z, coordinates }: { zoom: number; coordinates: [number, number] }) => {
      setZoom(z);
      setCenter(coordinates);
    },
    []
  );

  return (
    <div className="relative w-full h-full bg-[#0a1628] overflow-hidden select-none">
      <ComposableMap
        projection="geoMercator"
        projectionConfig={{ scale: 140, center: [10, 20] }}
        style={{ width: '100%', height: '100%' }}
      >
        <ZoomableGroup
          zoom={zoom}
          center={center}
          minZoom={0.6}
          maxZoom={10}
          onMoveEnd={handleMoveEnd}
        >
          <Geographies geography={GEO_URL}>
            {({ geographies }) =>
              geographies.map((geo) => {
                const isVisited = visitedCountryCodes.has(geo.id);
                return (
                  <Geography
                    key={geo.rsmKey}
                    geography={geo}
                    fill={isVisited ? '#0f766e' : '#1e3a5f'}
                    stroke="#0a1628"
                    strokeWidth={0.4}
                    style={{
                      default: { outline: 'none' },
                      hover: {
                        outline: 'none',
                        fill: isVisited ? '#14b8a6' : '#1e40af',
                        cursor: 'default',
                      },
                      pressed: { outline: 'none' },
                    }}
                  />
                );
              })
            }
          </Geographies>

          {locations.map((location) => {
            const isSelected = selectedLocation?.id === location.id;
            return (
              <Marker
                key={location.id}
                coordinates={location.coordinates}
                onClick={() => onLocationSelect(location)}
                onMouseEnter={(e: React.MouseEvent) => {
                  const rect = (e.target as SVGElement)
                    .closest('svg')
                    ?.getBoundingClientRect();
                  if (rect) {
                    setTooltip({
                      name: `${location.city}, ${location.country}`,
                      x: e.clientX - rect.left,
                      y: e.clientY - rect.top,
                    });
                  }
                }}
                onMouseLeave={() => setTooltip(null)}
              >
                <circle
                  r={isSelected ? 7 / Math.sqrt(zoom) : 5 / Math.sqrt(zoom)}
                  fill={isSelected ? '#f59e0b' : '#fbbf24'}
                  stroke="#fff"
                  strokeWidth={1.5 / Math.sqrt(zoom)}
                  style={{ cursor: 'pointer' }}
                />
                {isSelected && (
                  <circle
                    r={12 / Math.sqrt(zoom)}
                    fill="none"
                    stroke="#f59e0b"
                    strokeWidth={1 / Math.sqrt(zoom)}
                    opacity={0.6}
                  />
                )}
              </Marker>
            );
          })}
        </ZoomableGroup>
      </ComposableMap>

      {tooltip && (
        <div
          className="absolute pointer-events-none z-10 bg-slate-800/95 text-white text-xs px-2.5 py-1.5 rounded-lg shadow-lg border border-slate-600/50 whitespace-nowrap"
          style={{ left: tooltip.x + 12, top: tooltip.y - 32 }}
        >
          {tooltip.name}
        </div>
      )}

      <div className="absolute bottom-4 right-4 flex flex-col gap-1.5 z-10">
        <button
          onClick={() => setZoom((z) => Math.min(z * 1.5, 10))}
          className="w-8 h-8 bg-slate-800/90 hover:bg-slate-700 text-white rounded-lg border border-slate-600/50 flex items-center justify-center text-lg font-light transition-colors"
          aria-label="Zoom in"
        >
          +
        </button>
        <button
          onClick={() => setZoom((z) => Math.max(z / 1.5, 0.6))}
          className="w-8 h-8 bg-slate-800/90 hover:bg-slate-700 text-white rounded-lg border border-slate-600/50 flex items-center justify-center text-lg font-light transition-colors"
          aria-label="Zoom out"
        >
          −
        </button>
        <button
          onClick={() => { setZoom(1); setCenter([10, 20]); }}
          className="w-8 h-8 bg-slate-800/90 hover:bg-slate-700 text-white rounded-lg border border-slate-600/50 flex items-center justify-center text-xs transition-colors"
          aria-label="Reset view"
        >
          ⊙
        </button>
      </div>

      <div className="absolute bottom-4 left-4 flex items-center gap-4 text-xs text-slate-400 z-10">
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-3 rounded-sm bg-[#0f766e]" />
          방문
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-2.5 h-2.5 rounded-full bg-amber-400" />
          도시
        </span>
      </div>
    </div>
  );
}
