/** Print-first map art for the Trip Book.
 *
 * Everything is one SVG, including the numbers, so a page keeps its circuit and
 * its sequence when the book is rasterised into a PDF or printed in mono.
 */

export interface CircuitStop {
  marker: string;
  name: string;
  detail: string;
  x: number;
  y: number;
  /** Which side the printed label sits on, authored per stop to avoid collisions. */
  side: "left" | "right";
}

export const dayCircuit: CircuitStop[] = [
  { marker: "H", name: "Wilde Aldgate", detail: "07:40 out · 19:20 back", x: 58, y: 44, side: "right" },
  { marker: "1", name: "Tower of London", detail: "09:10 · taxi 18 min", x: 44, y: 62, side: "left" },
  { marker: "2", name: "Dishoom Shoreditch", detail: "12:05 · walk 14 min", x: 70, y: 25, side: "right" },
  { marker: "3", name: "Young V&A", detail: "14:00 · metro 26 min", x: 100, y: 14, side: "left" },
  { marker: "4", name: "Sky Garden", detail: "17:10 · metro 31 min", x: 22, y: 50, side: "right" },
];

const dayColors = ["#0877b9", "#0f766e", "#d63c75", "#b45309", "#4f46e5", "#0891b2", "#be123c", "#475569"];

export const tripAreas = [
  { day: 1, label: "Arrival · Aldgate", x: 62, y: 45 },
  { day: 2, label: "Westminster & parks", x: 44, y: 53 },
  { day: 3, label: "Tower & Shoreditch", x: 70, y: 38 },
  { day: 4, label: "South Kensington", x: 33, y: 60 },
  { day: 5, label: "Greenwich", x: 89, y: 61 },
  { day: 6, label: "Oxford day trip", x: 13, y: 21 },
  { day: 7, label: "Camden & Regent's", x: 50, y: 28 },
  { day: 8, label: "Heathrow departure", x: 16, y: 66 },
];

export function dayColor(day: number): string {
  return dayColors[(day - 1) % dayColors.length];
}

/** One 4:3 drawing surface, so the inset and the page figure stay the same map
 * at two sizes rather than two differently zoomed maps. */
const VIEW_BOX = "0 0 120 90";

function Basemap({ mono }: { mono: boolean }) {
  return (
    <g>
      <rect x="-2" y="-2" width="124" height="94" fill={mono ? "#f5f5f4" : "#f3f7f6"} />
      <path d="M-2 22 L26 16 L34 30 L8 37 Z" fill={mono ? "#ececeb" : "#e6efe7"} />
      <path d="M78 8 L104 3 L112 19 L86 25 Z" fill={mono ? "#ececeb" : "#e6efe7"} />
      <path d="M-2 68 C22 60 44 78 68 71 C92 64 106 74 122 69 L122 92 L-2 92 Z" fill={mono ? "#e6e6e5" : "#cfe0ea"} />
      {[14, 30, 46, 58].map((y) => (
        <line key={y} x1="-2" y1={y} x2="122" y2={y + 3} stroke="#ffffff" strokeWidth="1.6" />
      ))}
      {[20, 42, 64, 86, 106].map((x) => (
        <line key={x} x1={x} y1="-2" x2={x - 6} y2="92" stroke="#ffffff" strokeWidth="1.2" />
      ))}
    </g>
  );
}

function Furniture({ mono, caption }: { mono: boolean; caption: string }) {
  const ink = mono ? "#475569" : "#334155";
  return (
    <g>
      <path d="M113 3 L115.4 9 L113 7.6 L110.6 9 Z" fill={ink} />
      <text x="113" y="13.5" textAnchor="middle" fontSize="3.4" fontWeight="700" fill={ink}>N</text>
      <g transform="translate(4 82)">
        <line x1="0" y1="0" x2="18" y2="0" stroke={ink} strokeWidth="0.9" />
        <line x1="0" y1="-1.8" x2="0" y2="1.8" stroke={ink} strokeWidth="0.9" />
        <line x1="18" y1="-1.8" x2="18" y2="1.8" stroke={ink} strokeWidth="0.9" />
        <text x="20.5" y="1.4" fontSize="3.4" fill={ink}>1 km</text>
      </g>
      <text x="116" y="86" textAnchor="end" fontSize="3.4" fill={ink}>{caption}</text>
    </g>
  );
}

function Marker({ stop, color, size = 1 }: { stop: CircuitStop; color: string; size?: number }) {
  const r = 4.6 * size;
  const hotel = stop.marker === "H";
  return (
    <g>
      {hotel ? (
        <rect x={stop.x - r} y={stop.y - r} width={r * 2} height={r * 2} rx={1.4} fill="#ffffff" stroke={color} strokeWidth="2.2" />
      ) : (
        <circle cx={stop.x} cy={stop.y} r={r} fill={color} stroke="#ffffff" strokeWidth="1.6" />
      )}
      <text
        x={stop.x}
        y={stop.y + 1.9 * size}
        textAnchor="middle"
        fontSize={5.4 * size}
        fontWeight="700"
        fill={hotel ? color : "#ffffff"}
      >
        {stop.marker}
      </text>
    </g>
  );
}

/**
 * The day circuit exactly as the itinerary states it: out of the hotel, through
 * the numbered stops in order, and back to the same hotel.
 */
export function DayCircuitMap({
  mono = false,
  labels = false,
  caption = "Day 3 · 16.8 km",
  className = "",
}: {
  mono?: boolean;
  labels?: boolean;
  caption?: string;
  className?: string;
}) {
  const line = mono ? "#334155" : dayColor(3);
  const closed = [...dayCircuit, dayCircuit[0]];
  const points = closed.map((stop) => `${stop.x},${stop.y}`).join(" ");

  return (
    <svg viewBox={VIEW_BOX} className={className} role="img" aria-label="Day 3 circuit map with numbered stops">
      <Basemap mono={mono} />
      <polyline points={points} fill="none" stroke="#ffffff" strokeWidth="3.6" strokeLinejoin="round" strokeLinecap="round" />
      <polyline points={points} fill="none" stroke={line} strokeWidth="1.7" strokeLinejoin="round" strokeLinecap="round" />
      {dayCircuit.map((stop) => (
        <Marker key={stop.marker} stop={stop} color={line} />
      ))}
      {labels &&
        dayCircuit.map((stop) => {
          const left = stop.side === "left";
          const x = left ? stop.x - 7.5 : stop.x + 7.5;
          // Halo first, so a label crossing the route line still reads in print.
          return (
            <g key={`label-${stop.marker}`} textAnchor={left ? "end" : "start"} paintOrder="stroke" stroke="#ffffff" strokeWidth="1.4" strokeLinejoin="round">
              <text x={x} y={stop.y - 0.4} fontSize="3.5" fontWeight="700" fill="#0f172a">{stop.name}</text>
              <text x={x} y={stop.y + 3.6} fontSize="2.9" fill="#64748b">{stop.detail}</text>
            </g>
          );
        })}
      <Furniture mono={mono} caption={caption} />
    </svg>
  );
}

/** One page-sized picture of where the whole trip happens, day by day. */
export function TripOverviewMap({ mono = false, className = "" }: { mono?: boolean; className?: string }) {
  return (
    <svg viewBox={VIEW_BOX} className={className} role="img" aria-label="Trip overview map with one marker per day">
      <Basemap mono={mono} />
      <ellipse cx="56" cy="45" rx="46" ry="34" fill="none" stroke={mono ? "#94a3b8" : "#a8bfcd"} strokeWidth="0.7" strokeDasharray="3 2.4" />
      <text x="56" y="8" textAnchor="middle" fontSize="3.4" fill={mono ? "#64748b" : "#5b7d90"}>Greater London</text>
      {tripAreas.map((area) => {
        const color = mono ? "#334155" : dayColor(area.day);
        return (
          <g key={area.day}>
            <circle cx={area.x} cy={area.y} r="4.4" fill={color} stroke="#ffffff" strokeWidth="1.5" />
            <text x={area.x} y={area.y + 1.8} textAnchor="middle" fontSize="5" fontWeight="700" fill="#ffffff">{area.day}</text>
          </g>
        );
      })}
      <g>
        <path d="M62 39.4 L63.3 42.1 L66.2 42.5 L64.1 44.6 L64.6 47.5 L62 46.1 L59.4 47.5 L59.9 44.6 L57.8 42.5 L60.7 42.1 Z" fill="#0f172a" stroke="#ffffff" strokeWidth="0.8" />
        <text x="62" y="53" textAnchor="middle" fontSize="3.4" fontWeight="700" fill="#0f172a">Base hotel</text>
      </g>
      <Furniture mono={mono} caption="8 days · one base" />
    </svg>
  );
}
