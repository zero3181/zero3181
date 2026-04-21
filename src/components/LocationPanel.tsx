import { useState } from 'react';
import type { TravelLocation } from '../types';
import { travelLocations } from '../data/travels';
import type { Continent } from '../types';
import PhotoModal from './PhotoModal';

const CONTINENTS: Continent[] = ['All', 'Asia', 'Europe', 'Americas', 'Africa', 'Oceania'];

interface Props {
  selectedLocation: TravelLocation | null;
  onLocationSelect: (location: TravelLocation) => void;
}

export default function LocationPanel({ selectedLocation, onLocationSelect }: Props) {
  const [filter, setFilter] = useState<Continent>('All');
  const [photoModal, setPhotoModal] = useState<{ index: number } | null>(null);

  const filtered =
    filter === 'All'
      ? travelLocations
      : travelLocations.filter((l) => l.continent === filter);

  if (selectedLocation) {
    return (
      <div className="h-full flex flex-col bg-slate-800">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-700">
          <button
            onClick={() => onLocationSelect(null as unknown as TravelLocation)}
            className="text-slate-400 hover:text-white transition-colors text-lg leading-none"
            aria-label="Back to list"
          >
            ←
          </button>
          <div>
            <h2 className="text-white font-semibold text-base leading-tight">
              {selectedLocation.city}
            </h2>
            <p className="text-slate-400 text-xs">
              {selectedLocation.country} · {selectedLocation.visitDate}
            </p>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          <div className="px-4 py-3">
            <p className="text-slate-300 text-sm leading-relaxed">
              {selectedLocation.description}
            </p>
          </div>

          <div className="px-4 pb-4">
            <p className="text-slate-500 text-xs mb-3 uppercase tracking-wider">
              Photos · {selectedLocation.photos.length}장
            </p>
            <div className="grid grid-cols-2 gap-2">
              {selectedLocation.photos.map((photo, i) => (
                <button
                  key={photo.id}
                  onClick={() => setPhotoModal({ index: i })}
                  className="relative aspect-[4/3] overflow-hidden rounded-lg group"
                >
                  <img
                    src={`https://picsum.photos/seed/${photo.id}/400/300`}
                    alt={photo.caption}
                    className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                    loading="lazy"
                  />
                  <div className="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition-colors duration-200 flex items-end">
                    <p className="text-white text-xs px-2 py-1.5 opacity-0 group-hover:opacity-100 transition-opacity duration-200 line-clamp-2">
                      {photo.caption}
                    </p>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>

        {photoModal && (
          <PhotoModal
            photos={selectedLocation.photos}
            currentIndex={photoModal.index}
            onClose={() => setPhotoModal(null)}
            onNavigate={(i) => setPhotoModal({ index: i })}
          />
        )}
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-slate-800">
      <div className="px-4 py-3 border-b border-slate-700">
        <h2 className="text-white font-semibold text-base">여행지 목록</h2>
        <div className="flex gap-1.5 mt-2 flex-wrap">
          {CONTINENTS.map((c) => (
            <button
              key={c}
              onClick={() => setFilter(c)}
              className={`px-2.5 py-1 rounded-full text-xs transition-colors ${
                filter === c
                  ? 'bg-teal-600 text-white'
                  : 'bg-slate-700 text-slate-400 hover:bg-slate-600 hover:text-white'
              }`}
            >
              {c}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {filtered.map((location) => (
          <button
            key={location.id}
            onClick={() => onLocationSelect(location)}
            className="w-full flex items-start gap-3 px-4 py-3 hover:bg-slate-700/50 transition-colors border-b border-slate-700/30 text-left"
          >
            <div className="w-16 h-12 rounded-lg overflow-hidden flex-shrink-0 mt-0.5">
              <img
                src={`https://picsum.photos/seed/${location.id}1/160/120`}
                alt={location.city}
                className="w-full h-full object-cover"
                loading="lazy"
              />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-white text-sm font-medium leading-tight">
                {location.city}
              </p>
              <p className="text-slate-400 text-xs mt-0.5">
                {location.country}
              </p>
              <p className="text-slate-500 text-xs mt-1">
                {location.visitDate} · {location.photos.length}장의 사진
              </p>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
