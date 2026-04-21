import { useEffect, useCallback } from 'react';
import type { Photo } from '../types';

interface Props {
  photos: Photo[];
  currentIndex: number;
  onClose: () => void;
  onNavigate: (index: number) => void;
}

export default function PhotoModal({ photos, currentIndex, onClose, onNavigate }: Props) {
  const photo = photos[currentIndex];

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      if (e.key === 'ArrowLeft' && currentIndex > 0) onNavigate(currentIndex - 1);
      if (e.key === 'ArrowRight' && currentIndex < photos.length - 1) onNavigate(currentIndex + 1);
    },
    [currentIndex, photos.length, onClose, onNavigate]
  );

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  return (
    <div
      className="fixed inset-0 z-50 bg-black/95 flex items-center justify-center"
      onClick={onClose}
    >
      <button
        onClick={onClose}
        className="absolute top-4 right-4 text-white/70 hover:text-white text-3xl leading-none z-10"
        aria-label="Close"
      >
        ×
      </button>

      {currentIndex > 0 && (
        <button
          onClick={(e) => { e.stopPropagation(); onNavigate(currentIndex - 1); }}
          className="absolute left-4 top-1/2 -translate-y-1/2 text-white/70 hover:text-white text-4xl z-10 p-2"
          aria-label="Previous"
        >
          ‹
        </button>
      )}

      {currentIndex < photos.length - 1 && (
        <button
          onClick={(e) => { e.stopPropagation(); onNavigate(currentIndex + 1); }}
          className="absolute right-4 top-1/2 -translate-y-1/2 text-white/70 hover:text-white text-4xl z-10 p-2"
          aria-label="Next"
        >
          ›
        </button>
      )}

      <div
        className="max-w-4xl w-full mx-4 flex flex-col items-center gap-4"
        onClick={(e) => e.stopPropagation()}
      >
        <img
          src={photo.url}
          alt={photo.caption}
          className="w-full max-h-[75vh] object-contain rounded-lg"
          loading="lazy"
        />
        <div className="text-center">
          <p className="text-white font-medium">{photo.caption}</p>
          <p className="text-slate-400 text-sm mt-1">{photo.date}</p>
        </div>
        <div className="flex gap-2">
          {photos.map((_, i) => (
            <button
              key={i}
              onClick={() => onNavigate(i)}
              className={`w-2 h-2 rounded-full transition-colors ${
                i === currentIndex ? 'bg-amber-400' : 'bg-slate-600 hover:bg-slate-400'
              }`}
              aria-label={`Go to photo ${i + 1}`}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
