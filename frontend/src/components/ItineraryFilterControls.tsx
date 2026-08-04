import { BusFront, Hotel, Plane, TrainFront } from "lucide-react";
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
}

export default function ItineraryFilterControls({ filters, onToggle, target }: Props) {
  const controls = (
    <div role="group" aria-label="Filter itinerary and map" className="flex min-w-0 items-center gap-1">
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
            className={`grid h-7 w-7 shrink-0 place-items-center rounded-[5px] transition ${
              active
                ? "bg-ink text-white shadow-sm"
                : "text-slate-500 hover:bg-slate-100 hover:text-ink"
            }`}
          >
            <Icon size={14} aria-hidden />
          </button>
        );
      })}
    </div>
  );
  return target
    ? createPortal(controls, target)
    : <div className="border-b border-slate-100 bg-white px-3 py-1.5">{controls}</div>;
}