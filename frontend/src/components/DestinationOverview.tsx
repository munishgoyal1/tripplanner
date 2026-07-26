import { useEffect, useState } from "react";
import { fetchDestinationOverview, getCachedOverview } from "../api";
import type { DestinationOverview as Overview } from "../types";
import Lightbox from "./Lightbox";

interface Props {
  destination: string;
}

// "About the place" — an immersive hero gallery, a quick vibe summary distilled
// from reviews and history, traveler quotes, and fresh good news.
// We seed from the module cache so flipping between previously-loaded places
// (e.g. Dubai → Paris → Dubai) is instant, and we keep the prior content visible
// while the new destination loads so the panel never blanks out mid-switch.
export default function DestinationOverview({ destination }: Props) {
  const [data, setData] = useState<Overview | null>(() =>
    destination ? getCachedOverview(destination) : null,
  );
  const [loading, setLoading] = useState(false);
  const [lb, setLb] = useState(-1);

  useEffect(() => {
    if (!destination) {
      setData(null);
      return;
    }
    const cached = getCachedOverview(destination);
    if (cached) {
      setData(cached);
      setLoading(false);
      return;
    }
    // Keep showing whatever's on screen while we fetch — no flash of empty.
    let cancelled = false;
    setLoading(true);
    fetchDestinationOverview(destination)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch(() => {
        /* keep prior content on transient failure */
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [destination]);

  if (!destination) return null;
  // First-ever load (nothing in cache, nothing on screen): show a skeleton.
  if (loading && !data) {
    return (
      <div className="animate-pulse rounded-2xl bg-white p-4 text-sm text-slate-400 shadow-sm">
        Discovering what {destination} is like…
      </div>
    );
  }
  if (!data) return null;
  // We may be showing a previous destination's data while the new one loads —
  // dim slightly to hint a refresh is in flight without losing context.
  const stale = loading && data.destination.toLowerCase() !== destination.toLowerCase();

  const hasContent =
    data.photos.length > 0 ||
    !!data.summary ||
    data.reviews.length > 0 ||
    data.news.length > 0;
  if (!hasContent) return null;

  const [hero, ...rest] = data.photos;

  return (
    <div
      className={`border-b border-slate-100 transition-opacity duration-300 ${
        stale ? "opacity-70" : "opacity-100"
      }`}
    >
      {/* Immersive hero */}
      {hero && (
        <div className="relative">
          <button
            onClick={() => setLb(0)}
            className="block w-full"
            title="Open photos"
          >
            <img
              src={hero}
              alt={data.destination}
              className="h-52 w-full object-cover transition-transform duration-700 hover:scale-[1.03]"
            />
          </button>
          <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/75 via-black/35 to-transparent p-5">
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-white/70">
              Destination
            </p>
            <h3 className="display mt-0.5 text-2xl font-semibold leading-tight text-white drop-shadow">
              {data.destination}
            </h3>
            {data.rating != null && (
              <div className="mt-2 flex items-center gap-2">
                <span className="pill bg-amber-400/95 text-amber-950 shadow-sm">
                  ★ {data.rating.toFixed(1)}
                </span>
                {data.review_count ? (
                  <span className="text-xs text-white/85">
                    {data.review_count.toLocaleString()} reviews
                  </span>
                ) : null}
              </div>
            )}
          </div>
          {data.photos.length > 1 && (
            <button
              onClick={() => setLb(0)}
              className="absolute right-3 top-3 rounded-full bg-black/55 px-3 py-1 text-xs font-medium text-white backdrop-blur transition hover:bg-black/75"
            >
              📷 {data.photos.length} photos
            </button>
          )}
        </div>
      )}

      <div className="space-y-4 p-4">
        {!hero && (
          <h3 className="display text-lg font-semibold text-ink">
            About {data.destination}
          </h3>
        )}

        {/* Vibe / summary distilled from reviews + history */}
        {data.summary && (
          <p className="text-sm leading-relaxed text-slate-600">{data.summary}</p>
        )}

        {/* Thumbnail strip */}
        {rest.length > 0 && (
          <div className="flex gap-2 overflow-x-auto pb-1">
            {rest.map((p, i) => (
              <button
                key={i}
                onClick={() => setLb(i + 1)}
                className="flex-shrink-0 overflow-hidden rounded-2xl"
              >
                <img
                  src={p}
                  alt={data.destination}
                  className="h-20 w-28 object-cover transition-transform duration-300 hover:scale-110"
                />
              </button>
            ))}
          </div>
        )}

        {data.reviews.length > 0 && (
          <div>
            <h4 className="mb-2.5 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted">
              What travelers say
            </h4>
            <div className="space-y-3">
              {data.reviews.slice(0, 2).map((r, i) => (
                <blockquote
                  key={i}
                  className="border-l-2 border-slate-200 pl-3"
                >
                  <p className="text-xs italic text-slate-600">“{r.text}”</p>
                  <footer className="mt-1 text-[11px] text-muted">
                    — {r.author} · {r.place}
                    {r.rating != null && (
                      <span className="text-amber-600"> · ★ {r.rating}</span>
                    )}
                  </footer>
                </blockquote>
              ))}
            </div>
          </div>
        )}

        {data.news.length > 0 && (
          <div>
            <h4 className="mb-2.5 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted">
              Latest good news
            </h4>
            <div className="space-y-2">
              {data.news.map((n, i) => (
                <a
                  key={i}
                  href={n.url}
                  target="_blank"
                  rel="noreferrer"
                  className="block rounded-2xl border border-slate-100 px-3 py-2.5 transition hover:-translate-y-0.5 hover:border-brand/40 hover:bg-white hover:shadow-card"
                >
                  <div className="text-xs font-semibold text-brand">{n.title}</div>
                  {n.content && (
                    <p className="mt-1 line-clamp-2 text-[11px] text-muted">{n.content}</p>
                  )}
                </a>
              ))}
            </div>
          </div>
        )}

      </div>

      <Lightbox
        photos={data.photos}
        index={lb}
        alt={data.destination}
        onClose={() => setLb(-1)}
        onIndex={setLb}
      />
    </div>
  );
}
