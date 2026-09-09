import { ChevronDown, ChevronUp, Route } from "lucide-react";
import type { MapDay } from "../types";

interface Props {
  days: MapDay[];
  activeDay: number | null;
  sequenceOpen: boolean;
  onAllDays: () => void;
  onDay: (day: number) => void;
  onToggleSequence: () => void;
}

export default function WorkspaceDayBar({
  days,
  activeDay,
  sequenceOpen,
  onAllDays,
  onDay,
  onToggleSequence,
}: Props) {
  const selectedDay = activeDay == null ? null : days.find((day) => day.day === activeDay) ?? null;
  const sequenceAvailable = Boolean(selectedDay?.pin_ids.length);

  return (
    <nav
      aria-label="Trip days and stop sequence"
      className="relative z-30 flex h-8 shrink-0 items-center gap-2 border-b border-border bg-paper px-3"
    >
      <div className="flex min-w-0 items-center gap-0.5 overflow-x-auto rounded-full bg-sand p-0.5 ring-1 ring-inset ring-border" aria-label="Workspace day scope">
        <button
          type="button"
          onClick={onAllDays}
          className={`h-6 shrink-0 rounded-full px-2.5 text-[11px] font-semibold transition ${
            activeDay == null ? "bg-paper text-ink shadow-sm" : "text-muted hover:bg-paper hover:text-ink"
          }`}
        >
          All days
        </button>
        {days.map((day) => (
          <button
            key={day.day}
            type="button"
            onClick={() => onDay(day.day)}
            className={`h-6 shrink-0 rounded-full px-2.5 text-[11px] font-semibold transition ${
              activeDay === day.day ? "text-white shadow-sm" : "text-muted hover:bg-paper hover:text-ink"
            }`}
            style={activeDay === day.day ? { backgroundColor: day.color } : undefined}
          >
            {day.label || `Day ${day.day}`}
          </button>
        ))}
      </div>
      <span className="h-5 w-px shrink-0 bg-border" aria-hidden />
      <button
        type="button"
        onClick={onToggleSequence}
        aria-pressed={sequenceOpen}
        disabled={!sequenceAvailable}
        className={`inline-flex h-6 shrink-0 items-center gap-1 rounded-md px-2 text-[11px] font-semibold transition disabled:opacity-40 ${
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
