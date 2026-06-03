import { useEffect } from "react";

interface Props {
  photos: string[];
  index: number;
  alt?: string;
  onClose: () => void;
  onIndex: (i: number) => void;
}

// Full-screen immersive photo viewer. Click the backdrop or press Esc to
// close; arrow keys or the on-screen chevrons move through the gallery.
export default function Lightbox({ photos, index, alt, onClose, onIndex }: Props) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight") onIndex((index + 1) % photos.length);
      if (e.key === "ArrowLeft") onIndex((index - 1 + photos.length) % photos.length);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [index, photos.length, onClose, onIndex]);

  if (index < 0 || !photos[index]) return null;

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 backdrop-blur-sm"
    >
      <button
        onClick={onClose}
        className="absolute right-5 top-5 grid h-10 w-10 place-items-center rounded-full bg-white/10 text-2xl text-white hover:bg-white/20"
        aria-label="Close"
      >
        ✕
      </button>

      {photos.length > 1 && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onIndex((index - 1 + photos.length) % photos.length);
          }}
          className="absolute left-4 grid h-12 w-12 place-items-center rounded-full bg-white/10 text-3xl text-white hover:bg-white/20"
          aria-label="Previous"
        >
          ‹
        </button>
      )}

      <img
        src={photos[index]}
        alt={alt || "photo"}
        onClick={(e) => e.stopPropagation()}
        className="max-h-[88vh] max-w-[92vw] rounded-2xl object-contain shadow-2xl"
      />

      {photos.length > 1 && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onIndex((index + 1) % photos.length);
          }}
          className="absolute right-4 grid h-12 w-12 place-items-center rounded-full bg-white/10 text-3xl text-white hover:bg-white/20"
          aria-label="Next"
        >
          ›
        </button>
      )}

      {photos.length > 1 && (
        <div className="absolute bottom-6 left-1/2 -translate-x-1/2 rounded-full bg-white/10 px-3 py-1 text-xs text-white/80">
          {index + 1} / {photos.length}
        </div>
      )}
    </div>
  );
}
