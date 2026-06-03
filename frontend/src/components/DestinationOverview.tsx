import { useEffect, useState } from "react";
import { fetchDestinationOverview } from "../api";
import type { DestinationOverview as Overview } from "../types";

interface Props {
  destination: string;
  onFocus: (kind: string, name: string) => void;
}

// "About the place" — Google photos, key attractions, reviews and fresh news.
// Shown above the itinerary while the user is still browsing a destination.
export default function DestinationOverview({ destination, onFocus }: Props) {
  const [data, setData] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(false);

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
      <div className="rounded-xl bg-white p-4 text-sm text-slate-400 shadow-sm">
        Loading what {destination} is like…
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

  return (
    <div className="space-y-3 rounded-xl bg-white p-4 shadow-sm">
      <h3 className="text-sm font-semibold text-ink">About {data.destination}</h3>
      {data.summary && <p className="text-sm text-slate-600">{data.summary}</p>}

      {data.photos.length > 0 && (
        <div className="flex gap-2 overflow-x-auto">
          {data.photos.map((p, i) => (
            <img
              key={i}
              src={p}
              alt={data.destination}
              className="h-28 w-40 flex-shrink-0 rounded-lg object-cover"
            />
          ))}
        </div>
      )}

      {data.key_attractions.length > 0 && (
        <div>
          <div className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-400">
            Key attractions
          </div>
          <div className="grid grid-cols-2 gap-2">
            {data.key_attractions.map((a, i) => (
              <button
                key={i}
                onClick={() => onFocus("attraction", a.name)}
                title="See photos, reviews and details"
                className="flex flex-col rounded-lg border border-slate-200 p-2 text-left hover:border-brand hover:bg-slate-50"
              >
                <span className="truncate text-sm font-medium text-ink">{a.name}</span>
                {a.rating != null && (
                  <span className="text-xs text-amber-500">
                    ★ {a.rating.toFixed(1)}
                    {a.review_count != null && (
                      <span className="text-slate-400"> ({a.review_count})</span>
                    )}
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>
      )}

      {data.reviews.length > 0 && (
        <div>
          <div className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-400">
            What travelers say
          </div>
          <div className="space-y-1">
            {data.reviews.slice(0, 4).map((r, i) => (
              <p key={i} className="text-xs text-slate-500">
                “{r.text}” — {r.author}
                <span className="text-slate-400"> · {r.place}</span>
              </p>
            ))}
          </div>
        </div>
      )}

      {data.news.length > 0 && (
        <div>
          <div className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-400">
            Latest news
          </div>
          <ul className="space-y-1">
            {data.news.map((n, i) => (
              <li key={i} className="text-xs">
                <a
                  href={n.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-brand hover:underline"
                >
                  {n.title}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
