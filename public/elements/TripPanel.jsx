// TripPanel — interactive right-rail trip panel (Chainlit custom element).
//
// This is the ONLY frontend file. It renders the JSON view-model produced by
// the pure-Python `multiagent.web.trip_view.build_view()` (same shape the
// `GET /trip/view` API returns), so the backend stays fully decoupled: a
// future standalone React/HTML app can reuse the same contract and drop this
// file in unchanged.
//
// Props (see trip_view.build_view):
//   has_trip, title, destination, focus {kind,name}|null, is_fallback,
//   empty_message, overview {...}, items [{kind,name,selected,rating,
//   review_count,summary,website,photos[],reviews[]}]
//
// Backend round-trips (Chainlit @cl.action_callback in web/app.py):
//   focus_item  {kind, name}            -> zoom onto one place ("View")
//   focus_item  {kind: "overview"}      -> back to the whole trip
//   select_item {kind, name}            -> add place to the trip ("Add to trip")

export default function TripPanel() {
  const v = props || {};

  if (!v.has_trip) {
    return (
      <div className="p-4 text-sm text-muted-foreground leading-relaxed">
        {v.empty_message || "No active trip yet."}
      </div>
    );
  }

  const o = v.overview || {};
  const counts = o.counts || {};
  const focused = v.focus && v.focus.name;

  const focus = (kind, name) => callAction({ name: "focus_item", payload: { kind, name } });
  const back = () => callAction({ name: "focus_item", payload: { kind: "overview" } });
  const select = (kind, name) => callAction({ name: "select_item", payload: { kind, name } });

  return (
    <div className="flex flex-col gap-3 p-3">
      {/* Header */}
      <div className="rounded-lg border bg-card p-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-lg font-semibold">{v.title}</h2>
          {o.status ? (
            <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs capitalize text-primary">
              {o.status}
            </span>
          ) : null}
        </div>
        <div className="mt-1 text-xs text-muted-foreground">
          {o.departure_date || "?"} &rarr; {o.return_date || "?"}
          {o.travelers ? ` \u00b7 ${o.travelers}` : ""}
          {o.origin ? ` \u00b7 from ${o.origin}` : ""}
        </div>
        {o.notes ? <div className="mt-1 text-xs italic text-muted-foreground">{o.notes}</div> : null}
        <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs">
          <span>✈️ {counts.flights || 0} flights</span>
          <span>🏨 {counts.hotels || 0} hotels</span>
          <span>🎯 {counts.activities || 0} activities</span>
          <span>📅 {counts.days || 0} day plans</span>
        </div>
        {o.total_cost ? (
          <div className="mt-2 text-sm font-medium">Total estimate: {o.total_cost_display}</div>
        ) : null}
      </div>

      {/* Focus / fallback banners */}
      {focused ? (
        <button
          onClick={back}
          className="self-start rounded-md border bg-background px-3 py-1.5 text-xs font-medium hover:bg-accent"
        >
          &larr; Back to whole trip
        </button>
      ) : null}
      {v.is_fallback ? (
        <div className="rounded-md bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
          📸 Popular spots in <strong>{v.destination}</strong> — tap <em>Add to trip</em> on the
          ones you like and I'll build your itinerary around them.
        </div>
      ) : null}

      {/* Item cards */}
      {(v.items || []).length === 0 ? (
        <div className="p-2 text-sm text-muted-foreground">No places to show yet.</div>
      ) : (
        <div className="flex flex-col gap-3">
          {(v.items || []).map((it, idx) => (
            <ItemCard
              key={`${it.kind}-${it.name}-${idx}`}
              item={it}
              expanded={!!focused}
              onView={() => focus(it.kind, it.name)}
              onSelect={() => select(it.kind, it.name)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ItemCard({ item, expanded, onView, onSelect }) {
  const photos = item.photos || [];
  const reviews = item.reviews || [];
  const icon = item.kind === "hotel" ? "🏨" : "🎯";

  return (
    <div className="overflow-hidden rounded-lg border bg-card">
      {/* Photo strip */}
      {photos.length > 0 ? (
        <div className={expanded ? "grid grid-cols-2 gap-1" : "h-32 w-full"}>
          {(expanded ? photos : photos.slice(0, 1)).map((url, i) => (
            <img
              key={i}
              src={url}
              alt={item.name}
              className={expanded ? "h-28 w-full object-cover" : "h-32 w-full object-cover"}
              loading="lazy"
            />
          ))}
        </div>
      ) : null}

      <div className="p-3">
        <div className="flex items-start justify-between gap-2">
          <div className="font-medium leading-tight">
            {icon} {item.name}
          </div>
          {item.selected ? (
            <span className="shrink-0 rounded-full bg-green-500/15 px-2 py-0.5 text-xs text-green-600 dark:text-green-400">
              ✓ Added
            </span>
          ) : null}
        </div>

        {item.rating ? (
          <div className="mt-1 text-xs text-muted-foreground">
            ⭐ {item.rating}
            {item.review_count ? ` (${item.review_count.toLocaleString()} reviews)` : ""}
          </div>
        ) : null}

        {item.summary ? (
          <p className={`mt-1 text-xs text-muted-foreground ${expanded ? "" : "line-clamp-2"}`}>
            {item.summary}
          </p>
        ) : null}

        {expanded && reviews.length > 0 ? (
          <div className="mt-2 flex flex-col gap-2">
            {reviews.map((r, i) => (
              <div key={i} className="rounded-md bg-muted/50 p-2 text-xs">
                <span>{"⭐".repeat(Math.round(r.rating || 0))}</span>{" "}
                <span className="italic text-muted-foreground">{r.author}</span>
                <div className="mt-0.5">{r.text}</div>
              </div>
            ))}
          </div>
        ) : null}

        <div className="mt-2 flex flex-wrap gap-2">
          {!expanded ? (
            <button
              onClick={onView}
              className="rounded-md border bg-background px-2.5 py-1 text-xs font-medium hover:bg-accent"
            >
              View photos &amp; reviews
            </button>
          ) : null}
          {!item.selected ? (
            <button
              onClick={onSelect}
              className="rounded-md bg-primary px-2.5 py-1 text-xs font-medium text-primary-foreground hover:opacity-90"
            >
              Add to trip
            </button>
          ) : null}
          {item.website ? (
            <a
              href={item.website}
              target="_blank"
              rel="noreferrer"
              className="rounded-md border bg-background px-2.5 py-1 text-xs font-medium hover:bg-accent"
            >
              Website ↗
            </a>
          ) : null}
        </div>
      </div>
    </div>
  );
}
