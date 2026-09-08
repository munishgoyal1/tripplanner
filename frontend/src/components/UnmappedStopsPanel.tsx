import { AlertTriangle, MapPinOff } from "lucide-react";
import { useState } from "react";

import type { UnmappedStop } from "../types";

// Loudness follows what the traveller loses, not how unsure the geocoder was.
// An anchor is where they sleep or how they arrive, so it interrupts; a named
// place is a gap worth seeing; a label names nowhere and only answers the
// question "why isn't this on the map?" when it is asked.
const TIER_ORDER: Record<UnmappedStop["tier"], number> = { anchor: 0, place: 1, label: 2 };

export function reasonLabel(stop: UnmappedStop): string {
  if (stop.reason === "not_a_place") return "Not a place";
  if (stop.reason === "no_location") return "No location found";
  return stop.candidate ? `Found “${stop.candidate.name}” instead` : "No confident match";
}

export function loudStops(stops: UnmappedStop[]): UnmappedStop[] {
  return stops.filter((stop) => stop.tier === "anchor");
}

export default function UnmappedStopsPanel({
  stops,
  onConfirm,
  onFocus,
  busyName,
}: {
  stops: UnmappedStop[];
  onConfirm: (stop: UnmappedStop) => void;
  onFocus?: (stop: UnmappedStop) => void;
  busyName: string | null;
}) {
  const [open, setOpen] = useState(false);
  if (!stops.length) return null;

  const ordered = [...stops].sort(
    (left, right) =>
      TIER_ORDER[left.tier] - TIER_ORDER[right.tier] || (left.day ?? 0) - (right.day ?? 0),
  );
  const anchors = loudStops(ordered);
  const keyBreakdown =
    anchors.length > 0 && anchors.length < ordered.length
      ? ` · ${anchors.length} key`
      : "";

  return (
    <div className="border-t border-slate-200 bg-white/95 px-3 py-2 text-xs">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 text-left"
      >
        {anchors.length ? (
          <AlertTriangle size={13} className="shrink-0 text-amber-500" aria-hidden />
        ) : (
          <MapPinOff size={13} className="shrink-0 text-slate-400" aria-hidden />
        )}
        <span className={anchors.length ? "font-semibold text-amber-700" : "text-slate-500"}>
          {ordered.length} {ordered.length === 1 ? "stop" : "stops"} not on the map{keyBreakdown}
        </span>
        <span className="ml-auto text-slate-400">{open ? "Hide" : "Show"}</span>
      </button>

      {open && (
        <ul className="mt-2 space-y-1.5">
          {ordered.map((stop) => (
            <li
              key={`${stop.day ?? 0}-${stop.name}`}
              onClick={() => onFocus?.(stop)}
              className={`flex items-start gap-2 ${onFocus ? "cursor-pointer rounded-md hover:bg-slate-50" : ""}`}
            >
              <span
                className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${
                  stop.tier === "anchor"
                    ? "bg-amber-500"
                    : stop.tier === "place"
                      ? "bg-slate-400"
                      : "bg-slate-200"
                }`}
                aria-hidden
              />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium text-ink">
                  {stop.day ? `Day ${stop.day} · ` : ""}
                  {stop.name}
                </span>
                <span className="block text-slate-500">{reasonLabel(stop)}</span>
              </span>
              {stop.candidate && (
                <button
                  type="button"
                  disabled={busyName === stop.name}
                  onClick={(event) => {
                    event.stopPropagation();
                    onConfirm(stop);
                  }}
                  className="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 font-semibold text-slate-600 transition hover:bg-slate-200 disabled:opacity-50"
                >
                  {busyName === stop.name ? "Pinning…" : "Use it"}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
