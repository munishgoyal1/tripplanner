import type { Day, Stop } from "./tripFixture";
import { days } from "./tripFixture";

/**
 * A calm, vector stand-in for the Google canvas. It exists so a Lab can be judged
 * on the chrome placed over a map, not on map tiles the experiment cannot change.
 */
export function StylizedMap({
  activeDay,
  selectedId,
  onSelect,
  className = "",
}: {
  activeDay: number | null;
  selectedId?: string | null;
  onSelect?: (stop: Stop, day: Day) => void;
  className?: string;
}) {
  const shown = activeDay == null ? days : days.filter((day) => day.day === activeDay);

  return (
    <div className={`relative h-full w-full overflow-hidden bg-[#eef3f1] ${className}`}>
      <svg
        className="absolute inset-0 h-full w-full"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        aria-hidden
      >
        <rect width="100" height="100" fill="#eef3f1" />
        <path d="M0 78 L38 70 L62 79 L100 71 L100 100 L0 100 Z" fill="#cfe0ea" />
        <path d="M0 12 L26 8 L34 20 L12 26 Z" fill="#e2ebe4" />
        <path d="M62 10 L86 6 L94 22 L70 28 Z" fill="#e2ebe4" />
        <path d="M40 34 L58 30 L64 44 L44 48 Z" fill="#e6eee8" />
        {[18, 34, 50, 64].map((y) => (
          <line key={y} x1="0" y1={y} x2="100" y2={y + 4} stroke="#ffffff" strokeWidth="1.4" vectorEffect="non-scaling-stroke" />
        ))}
        {[16, 34, 52, 70, 86].map((x) => (
          <line key={x} x1={x} y1="0" x2={x - 5} y2="100" stroke="#ffffff" strokeWidth="1.1" vectorEffect="non-scaling-stroke" />
        ))}
        {shown.map((day) => (
          <polyline
            key={day.day}
            points={day.stops.map((stop) => `${stop.x},${stop.y}`).join(" ")}
            fill="none"
            stroke={day.color}
            strokeWidth="2.5"
            strokeLinejoin="round"
            strokeLinecap="round"
            strokeOpacity={activeDay == null ? 0.35 : 0.85}
            vectorEffect="non-scaling-stroke"
          />
        ))}
      </svg>

      {shown.map((day) =>
        day.stops.map((stop) => {
          const selected = selectedId === stop.id;
          return (
            <button
              key={`${day.day}-${stop.id}`}
              type="button"
              onClick={() => onSelect?.(stop, day)}
              style={{
                left: `${stop.x}%`,
                top: `${stop.y}%`,
                borderColor: day.color,
                backgroundColor: selected ? day.color : "#ffffff",
                color: selected ? "#ffffff" : day.color,
              }}
              className={`absolute grid h-6 w-6 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border-2 text-[10px] font-bold tabular-nums shadow-sm transition hover:scale-110 ${
                selected ? "z-20 scale-110 ring-4 ring-white/70" : "z-10"
              }`}
              title={`${stop.name}${stop.time ? ` · ${stop.time}` : ""}`}
              aria-label={`${stop.name} on day ${day.day}`}
            >
              {stop.marker ?? "•"}
            </button>
          );
        }),
      )}

      <div className="pointer-events-none absolute bottom-2 right-2 rounded bg-white/80 px-1.5 py-0.5 text-[9px] font-medium text-slate-500">
        Illustrative map surface
      </div>
    </div>
  );
}
