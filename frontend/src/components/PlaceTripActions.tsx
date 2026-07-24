import { ChevronDown, Trash2 } from "lucide-react";
import { useState } from "react";
import type { DeselectItemOptions, SelectItemOptions } from "../api";
import type { PlaceOccurrence } from "../types";

interface Props {
  kind: string;
  name: string;
  occurrences: PlaceOccurrence[];
  availableDays: number[];
  preferredDay?: number | null;
  onMove: (
    kind: string,
    name: string,
    options: SelectItemOptions,
  ) => void | Promise<boolean>;
  onRemove: (
    kind: string,
    name: string,
    options: DeselectItemOptions,
  ) => void | Promise<boolean>;
}

function occurrenceKey(occurrence: PlaceOccurrence): string {
  return `${occurrence.day}:${occurrence.stop}`;
}

export default function PlaceTripActions({
  kind,
  name,
  occurrences,
  availableDays,
  preferredDay,
  onMove,
  onRemove,
}: Props) {
  const [manageOpen, setManageOpen] = useState(false);
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const orderedOccurrences = [...occurrences].sort((left, right) => {
    if (left.day === preferredDay) return -1;
    if (right.day === preferredDay) return 1;
    return left.day - right.day || left.stop - right.stop;
  });

  const move = async (occurrence: PlaceOccurrence | undefined, day: number) => {
    if (occurrence?.day === day) return;
    const key = `move:${occurrence ? occurrenceKey(occurrence) : "unscheduled"}`;
    setPendingKey(key);
    try {
      const moved = await onMove(kind, name, {
        day,
        source_day: occurrence?.day,
        source_stop: occurrence?.stop,
      });
      if (moved !== false) setManageOpen(false);
    } finally {
      setPendingKey(null);
    }
  };

  const remove = async (options: DeselectItemOptions, key: string) => {
    setPendingKey(`remove:${key}`);
    try {
      const removed = await onRemove(kind, name, options);
      if (removed !== false) setManageOpen(false);
    } finally {
      setPendingKey(null);
    }
  };

  if (kind === "hotel") {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <span className="pill bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200">
          ✓ In trip
        </span>
        <button
          type="button"
          disabled={pendingKey != null}
          onClick={() => void remove({ all_occurrences: true }, "all")}
          aria-label={`Remove ${name} from trip`}
          className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold text-rose-700 ring-1 ring-rose-200 transition hover:bg-rose-50 disabled:opacity-50"
        >
          <Trash2 size={13} aria-hidden />
          {pendingKey ? "Removing…" : "Remove"}
        </button>
      </div>
    );
  }

  if (occurrences.length <= 1) {
    const occurrence = occurrences[0];
    return (
      <div className="flex flex-wrap items-center gap-2">
        <span className="pill bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200">
          ✓ In trip{occurrence ? ` · Day ${occurrence.day}` : ""}
        </span>
        {availableDays.length > 0 && (
          <select
            value={occurrence?.day ?? ""}
            disabled={pendingKey != null}
            onChange={(event) => void move(occurrence, Number(event.target.value))}
            aria-label={`Change ${name} day`}
            className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 disabled:opacity-50"
          >
            {!occurrence && <option value="">Choose day</option>}
            {availableDays.map((day) => (
              <option key={day} value={day}>Day {day}</option>
            ))}
          </select>
        )}
        <button
          type="button"
          disabled={pendingKey != null}
          onClick={() => void remove({ all_occurrences: true }, "all")}
          aria-label={`Remove ${name} from trip`}
          className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold text-rose-700 ring-1 ring-rose-200 transition hover:bg-rose-50 disabled:opacity-50"
        >
          <Trash2 size={13} aria-hidden />
          {pendingKey?.startsWith("move:")
            ? "Moving…"
            : pendingKey === "remove:all" ? "Removing…" : "Remove"}
        </button>
      </div>
    );
  }

  return (
    <div className="relative">
      <button
        type="button"
        disabled={pendingKey != null}
        onClick={() => setManageOpen((open) => !open)}
        aria-expanded={manageOpen}
        className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-700 ring-1 ring-emerald-200 transition hover:bg-emerald-100 disabled:opacity-50"
      >
        ✓ In trip · {occurrences.length} visits <ChevronDown size={13} aria-hidden />
      </button>
      {manageOpen && (
        <div className="absolute bottom-full left-0 z-30 mb-2 w-72 overflow-hidden rounded-xl border border-slate-200 bg-white p-2 shadow-pop">
          <p className="px-1 pb-1 text-[11px] font-semibold uppercase text-slate-400">
            Manage visits
          </p>
          <div className="space-y-1.5">
            {orderedOccurrences.map((occurrence) => {
              const key = occurrenceKey(occurrence);
              const validDays = availableDays.filter(
                (day) => day === occurrence.day || !occurrences.some((other) => other !== occurrence && other.day === day),
              );
              return (
                <div key={key} className="flex items-center gap-2 rounded-lg bg-slate-50 p-1.5">
                  <span className="min-w-0 flex-1 text-xs font-medium text-slate-700">
                    Day {occurrence.day}{occurrence.time ? ` · ${occurrence.time}` : ""}
                  </span>
                  <select
                    value={occurrence.day}
                    disabled={pendingKey != null}
                    onChange={(event) => void move(occurrence, Number(event.target.value))}
                    aria-label={`Change ${name} visit on Day ${occurrence.day}`}
                    className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700 disabled:opacity-50"
                  >
                    {validDays.map((day) => (
                      <option key={day} value={day}>Day {day}</option>
                    ))}
                  </select>
                  <button
                    type="button"
                    disabled={pendingKey != null}
                    onClick={() => void remove({
                      day: occurrence.day,
                      stop: occurrence.stop,
                      all_occurrences: false,
                    }, key)}
                    aria-label={`Remove ${name} from Day ${occurrence.day}`}
                    className="grid h-7 w-7 place-items-center rounded-full text-rose-600 hover:bg-rose-100 disabled:opacity-50"
                  >
                    <Trash2 size={13} aria-hidden />
                  </button>
                </div>
              );
            })}
          </div>
          <button
            type="button"
            disabled={pendingKey != null}
            onClick={() => void remove({ all_occurrences: true }, "all")}
            className="mt-2 flex w-full items-center gap-2 border-t border-slate-100 px-2 pt-2 text-left text-xs font-semibold text-rose-700 disabled:opacity-50"
          >
            <Trash2 size={13} aria-hidden /> Remove everywhere
          </button>
        </div>
      )}
    </div>
  );
}
