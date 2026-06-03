import { useEffect, useState } from "react";
import { fetchDestinationOverview } from "../api";
import type { DestinationOverview as Overview } from "../types";
import Lightbox from "./Lightbox";

interface Props {
  destination: string;
  onFocus: (kind: string, name: string) => void;
}

// "About the place" — an immersive hero gallery, a quick vibe summary distilled
// from reviews & history, key attractions, traveler quotes and fresh good news.
export default function DestinationOverview({ destination, onFocus }: Props) {
  const [data, setData] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(false);
  const [lb, setLb] = useState(-1);

  useEffect(() => {
    if (!destination) {
      setData(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    fetchDestinationOverview(destination)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch(() => {
        if (!cancelled) setData(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [destination]);

  if (!destination) return null;
  if (loading && !data) {
    return (
      <div className="animate-pulse rounded-2xl bg-white p-4 text-sm text-slate-400 shadow-sm">
        Discovering what {destination} is like…
      </div>
    );
  }
  if (!data) return null;

  const hasContent =
    data.photos.length > 0 ||
    data.key_attractions.length > 0 ||
    data.reviews.length > 0 ||
    data.news.length > 0;
  if (!hasContent) return null;

  const [hero, ...rest] = data.photos;

  return (
    <div className="overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-slate-100">
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
              className="h-52 w-full object-cover transition-transform duration-500 hover:scale-105"
            />
          </button>
          <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 to-transparent p-4">
            <h3 className="text-xl font-semibold text-white drop-shadow">
              {data.destination}
            </h3>
            {data.rating != null && (
              <div className="mt-0.5 flex items-center gap-2 text-sm text-white/90">
                <span className="rounded-full bg-amber-400/90 px-2 py-0.5 text-xs font-semibold text-amber-950">
                  ★ {data.rating.toFixed(1)}
                </span>
                {data.review_count ? (
                  <span className="text-xs text-white/80">
                    {data.review_count.toLocaleString()} reviews
                  </span>
                ) : null}
              </div>
            )}
          </div>
          {data.photos.length > 1 && (
            <button
              onClick={() => setLb(0)}
              className="absolute right-3 top-3 rounded-full bg-black/40 px-3 py-1 text-xs font-medium text-white backdrop-blur hover:bg-black/60"
            >
              📷 {data.photos.length} photos
            </button>
          )}
        </div>
      )}

      <div className="space-y-4 p-4">
        {!hero && (
          <h3 className="text-lg font-semibold text-ink">About {data.destination}</h3>
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
                className="flex-shrink-0 overflow-hidden rounded-xl"
              >
                <img
                  src={p}
                  alt={data.destination}
                  className="h-24 w-32 object-cover transition-transform duration-300 hover:scale-110"
                />
              </button>
            ))}
          </div>
        )}

        {data.key_attractions.length > 0 && (
          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
              Key attractions
            </div>
            <div className="grid grid-cols-2 gap-2">
              {data.key_attractions.map((a, i) => (
                <button
                  key={i}
                  onClick={() => onFocus("attraction", a.name)}
                  title="See photos, reviews and details"
                  className="group flex items-center gap-3 overflow-hidden rounded-xl border border-slate-200 p-2 text-left transition hover:border-brand hover:shadow-sm"
                >
                  {a.photo ? (
                    <img
                      src={a.photo}
                      alt={a.name}
                      className="h-12 w-12 flex-shrink-0 rounded-lg object-cover"
                    />
                  ) : (
                    <span className="grid h-12 w-12 flex-shrink-0 place-items-center rounded-lg bg-slate-100 text-lg">
                      📍
                    </span>
                  )}
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium text-ink group-hover:text-brand">
                      {a.name}
                    </span>
                    {a.rating != null && (
                      <span className="text-xs text-amber-500">
                        ★ {a.rating.toFixed(1)}
                        {a.review_count != null && (
                          <span className="text-slate-400"> ({a.review_count})</span>
                        )}
                      </span>
                    )}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}

        {data.reviews.length > 0 && (
          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
              What travelers say
            </div>
            <div className="space-y-2">
              {data.reviews.slice(0, 4).map((r, i) => (
                <div
                  key={i}
                  className="rounded-xl border border-slate-100 bg-slate-50 px-3 py-2"
                >
                  <p className="text-xs text-slate-600">“{r.text}”</p>
                  <p className="mt-1 text-[11px] text-slate-400">
                    {r.author} · {r.place}
                    {r.rating != null && <span className="text-amber-500"> · ★ {r.rating}</span>}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        {data.news.length > 0 && (
          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
              Latest good news
            </div>
            <div className="space-y-2">
              {data.news.map((n, i) => (
                <a
                  key={i}
                  href={n.url}
                  target="_blank"
                  rel="noreferrer"
                  className="block rounded-xl border border-slate-100 px-3 py-2 transition hover:border-brand hover:bg-slate-50"
                >
                  <div className="text-xs font-medium text-brand">{n.title}</div>
                  {n.content && (
                    <p className="mt-0.5 line-clamp-2 text-[11px] text-slate-500">{n.content}</p>
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
