import { BusFront, Hotel, Plane, TrainFront } from "lucide-react";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import type { ItineraryFilter } from "../lib/itineraryFilters";

const FILTERS = [
  { value: "flight", label: "Flights", Icon: Plane },
  { value: "road", label: "Inter-city Road", Icon: BusFront },
  { value: "train", label: "Inter-city Train", Icon: TrainFront },
  { value: "hotel", label: "Hotels", Icon: Hotel },
] as const;

interface Props {
  filters: readonly ItineraryFilter[];
  onToggle: (filter: ItineraryFilter) => void;
  target?: HTMLElement | null;
  /** Rendered after the filters in the pane header, such as trip readiness. */
  trailing?: ReactNode;
}

export default function ItineraryFilterControls({ filters, onToggle, target, trailing }: Props) {
  const controls = (
    <div role="group" aria-label="Filter itinerary and map" className="flex min-w-0 items-center gap-0.5 rounded-md border border-border bg-paper p-0.5">
      {FILTERS.map(({ value, label, Icon }) => {
        const active = filters.includes(value);
        return (
          <button
            key={value}
            type="button"
            onClick={() => onToggle(value)}
            aria-label={`Filter by ${label}`}
            aria-pressed={active}
            title={label}
            className={`grid h-7 w-7 shrink-0 place-items-center rounded transition ${
              active
                ? "bg-ink text-white"
                : "text-muted hover:bg-sand hover:text-ink"
            }`}
          >
            <Icon size={14} aria-hidden />
          </button>
        );
      })}
    </div>
  );
  return target
    ? createPortal(<>{controls}{trailing}</>, target)
    : <div className="flex items-center justify-between gap-2 border-b border-border bg-paper px-3 py-1.5">{controls}{trailing}</div>;
}