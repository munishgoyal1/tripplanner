import { ChevronDown, ChevronUp, Route } from "lucide-react";
import type { MapDay } from "../types";

/** Per-day facts the itinerary knows: its date and how many planned stops are confirmed. */
export interface WorkspaceDayFacts {
  date: string;
  booked: number;
  planned: number;
}

interface Props {
  days: MapDay[];
  activeDay: number | null;
  sequenceOpen: boolean;
  onAllDays: () => void;
  onDay: (day: number) => void;
  onToggleSequence: () => void;
  dayFacts?: Record<number, WorkspaceDayFacts>;
}

function shortDate(date: string): string {
  const parsed = new Date(`${date}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return "";
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "UTC" }).format(parsed);
}

export default function WorkspaceDayBar({
  days,
  activeDay,
  sequenceOpen,
  onAllDays,
  onDay,
  onToggleSequence,
  dayFacts,
}: Props) {
  const selectedDay = activeDay == null ? null : days.find((day) => day.day === activeDay) ?? null;
  const sequenceAvailable = Boolean(selectedDay?.pin_ids.length);

  return (
    <nav
      aria-label="Trip days and stop sequence"
      className="relative z-30 flex h-8 shrink-0 items-center gap-2 border-b border-border bg-paper px-3"
    >
      <div className="flex min-w-0 items-center gap-0.5 overflow-x-auto" aria-label="Workspace day scope">
        <button
          type="button"
          onClick={onAllDays}
          className={`h-6 shrink-0 rounded px-2.5 text-[11px] font-semibold transition ${
            activeDay == null ? "bg-ink text-white" : "text-muted hover:bg-sand hover:text-ink"
          }`}
        >
          All days
        </button>
        {days.map((day) => {
          const label = day.label || `Day ${day.day}`;
          const selected = activeDay === day.day;
          const facts = dayFacts?.[day.day];
          const date = facts ? shortDate(facts.date) : "";
          return (
            <button
              key={day.day}
              type="button"
              onClick={() => onDay(day.day)}
              aria-label={label}
              title={facts ? `${label}${date ? ` · ${date}` : ""} · ${facts.booked} of ${facts.planned} planned stops confirmed` : label}
              className={`inline-flex h-6 shrink-0 items-center gap-1.5 rounded px-2.5 text-[11px] font-semibold transition ${
                selected ? "bg-ink text-white" : "text-muted hover:bg-sand hover:text-ink"
              }`}
            >
              <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: day.color }} aria-hidden />
              {label}
              {date && <span className={`font-normal ${selected ? "text-white/75" : "text-muted"}`} aria-hidden>{date}</span>}
              {facts && facts.planned > 0 && (
                <span
                  aria-hidden
                  className={`rounded px-1 text-[10px] font-semibold tabular-nums ${
                    selected
                      ? "bg-white/15 text-white"
                      : facts.booked === facts.planned
                        ? "bg-emerald-50 text-emerald-700"
                        : "bg-sand text-muted"
                  }`}
                >
                  {facts.booked}/{facts.planned}
                </span>
              )}
            </button>
          );
        })}
      </div>
      <span className="h-5 w-px shrink-0 bg-border" aria-hidden />
      <button
        type="button"
        onClick={onToggleSequence}
        aria-pressed={sequenceOpen}
        disabled={!sequenceAvailable}
        className={`inline-flex h-6 shrink-0 items-center gap-1 rounded px-2 text-[11px] font-semibold transition disabled:opacity-40 ${
          sequenceOpen ? "bg-ink text-white" : "text-muted hover:bg-sand hover:text-ink"
        }`}
        title={sequenceAvailable ? "Show this day's stop order" : "Choose a day with planned stops"}
      >
        <Route size={13} aria-hidden />
        Sequence
        {sequenceOpen ? <ChevronUp size={12} aria-hidden /> : <ChevronDown size={12} aria-hidden />}
      </button>
    </nav>
  );
}
