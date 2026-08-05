import { Plane, TrainFront } from "lucide-react";
import type { MapLeg, MapNode } from "./scenarios";

const legColor: Record<MapLeg["mode"], string> = {
  local: "#0f766e",
  road: "#e11d48",
  rail: "#e11d48",
  flight: "#0284c7",
};

const legDash: Record<MapLeg["mode"], string | undefined> = {
  local: undefined,
  road: undefined,
  rail: "3 1.6",
  flight: "0.6 1.8",
};

function NodePin({ node, muted }: { node: MapNode; muted: boolean }) {
  const base = "absolute z-20 -translate-x-1/2 -translate-y-1/2";
  const tone = muted ? "opacity-95" : "";
  const label = (
    <span className="absolute left-1/2 top-[120%] w-36 -translate-x-1/2 bg-white/95 px-1.5 py-1 text-center shadow-card">
      <span className="block text-[9px] font-bold leading-tight text-ink">{node.name}</span>
      <span className="block truncate text-[8px] leading-tight text-slate-500">
        {node.time} · {node.detail}
      </span>
    </span>
  );

  if (node.kind === "terminal") {
    const Icon = node.marker === "A" ? Plane : TrainFront;
    return (
      <span className={`${base} ${tone}`} style={{ left: `${node.x}%`, top: `${node.y}%` }}>
        <span className="grid h-7 w-7 place-items-center rounded-md border-2 border-sky-600 bg-white text-sky-700 shadow-card">
          <Icon size={13} aria-hidden />
        </span>
        {label}
      </span>
    );
  }

  if (node.kind === "hotel") {
    return (
      <span className={`${base} ${tone}`} style={{ left: `${node.x}%`, top: `${node.y}%` }}>
        <span
          className={`grid h-9 w-9 place-items-center rounded-full border-4 border-white text-[10px] font-bold text-white shadow-pop ${
            node.side === "destination" ? "bg-brand" : "bg-teal-700"
          }`}
        >
          {node.marker}
        </span>
        {label}
      </span>
    );
  }

  return (
    <span className={`${base} ${tone}`} style={{ left: `${node.x}%`, top: `${node.y}%` }}>
      <span
        className="grid h-6 w-6 place-items-center rounded-full border-2 bg-white text-[9px] font-bold shadow-card"
        style={{ borderColor: node.side === "destination" ? "#e11d48" : "#0f766e", color: node.side === "destination" ? "#e11d48" : "#0f766e" }}
      >
        {node.marker}
      </span>
      {label}
    </span>
  );
}

interface JourneyMapProps {
  nodes: MapNode[];
  legs: MapLeg[];
  height: string;
  fit?: { x: number; y: number; width: number; height: number };
  fitLabel?: string;
  caption: string;
  muted?: boolean;
}

export function JourneyMap({ nodes, legs, height, fit, fitLabel, caption, muted = false }: JourneyMapProps) {
  const position = (id: string) => nodes.find((node) => node.id === id);
  const drawable = legs
    .map((leg) => ({ leg, from: position(leg.from), to: position(leg.to) }))
    .filter((entry): entry is { leg: MapLeg; from: MapNode; to: MapNode } => Boolean(entry.from && entry.to));

  return (
    <div className={`relative ${height} overflow-hidden bg-[#e8e2d4]`}>
      <div
        className="absolute inset-0 opacity-60"
        style={{
          backgroundImage:
            "linear-gradient(28deg,transparent 46%,#fff 47%,#fff 50%,transparent 51%),linear-gradient(104deg,transparent 47%,#fff 48%,#fff 51%,transparent 52%),linear-gradient(152deg,transparent 46%,#d9d2c2 47%,#d9d2c2 50%,transparent 51%)",
          backgroundSize: "190px 160px,250px 200px,130px 120px",
        }}
      />
      <div className="absolute inset-0 bg-[linear-gradient(120deg,rgba(240,253,250,.55),rgba(255,247,237,.5))]" />

      {fit && (
        <div
          className="absolute z-10 rounded-md border-2 border-dashed border-slate-500/70"
          style={{ left: `${fit.x}%`, top: `${fit.y}%`, width: `${fit.width}%`, height: `${fit.height}%` }}
        >
          {fitLabel && (
            <span className="absolute -top-2 left-2 bg-slate-700 px-1.5 py-0.5 text-[8px] font-bold uppercase text-white">
              {fitLabel}
            </span>
          )}
        </div>
      )}

      <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
        {drawable.map(({ leg, from, to }) => (
          <line
            key={`${leg.from}-${leg.to}-${leg.mode}`}
            x1={from.x}
            y1={from.y}
            x2={to.x}
            y2={to.y}
            stroke={legColor[leg.mode]}
            strokeWidth={leg.mode === "local" ? 0.5 : 0.9}
            strokeDasharray={legDash[leg.mode]}
            strokeLinecap="round"
          />
        ))}
      </svg>

      {drawable
        .filter(({ leg }) => leg.mode !== "local")
        .map(({ leg, from, to }) => (
          <span
            key={`label-${leg.from}-${leg.to}`}
            className="absolute z-20 -translate-x-1/2 -translate-y-1/2 whitespace-nowrap bg-white/95 px-1.5 py-0.5 text-[8px] font-bold text-ink shadow-card"
            style={{ left: `${(from.x + to.x) / 2}%`, top: `${(from.y + to.y) / 2}%` }}
          >
            {leg.label}
          </span>
        ))}

      {nodes.map((node) => (
        <NodePin key={node.id} node={node} muted={muted} />
      ))}

      <p className="absolute bottom-2 left-2 z-30 max-w-[92%] bg-white/95 px-2 py-1 text-[9px] font-medium text-slate-600 shadow-card">
        {caption}
      </p>
    </div>
  );
}
