export type NodeKind = "hotel" | "place" | "terminal";
export type LegMode = "local" | "road" | "rail" | "flight";
export type ScenarioId = "road" | "rail" | "flight" | "departure" | "ordinary";
export type VariantId = "full-journey" | "journey-strip" | "layer-toggle";

export interface MapNode {
  id: string;
  kind: NodeKind;
  marker: string;
  name: string;
  detail: string;
  time: string;
  side: "origin" | "journey" | "destination";
  x: number;
  y: number;
}

export interface MapLeg {
  from: string;
  to: string;
  mode: LegMode;
  label: string;
}

export interface Scenario {
  id: ScenarioId;
  tab: string;
  day: string;
  route: string;
  summary: string;
  guard: boolean;
  travel: { label: string; duration: string; distance: string; detail: string };
  nodes: MapNode[];
  legs: MapLeg[];
  baselineNodeIds: string[];
  baselineNote: string;
  afterNote: string;
  framing: string;
  fit: { x: number; y: number; width: number; height: number };
}

export const variants: { id: VariantId; label: string; summary: string; delta: string }[] = [
  {
    id: "full-journey",
    label: "A · Connected day journey",
    summary: "One selected-day canvas keeps both city contexts, their local circuits, and the inter-city leg.",
    delta:
      "Changes only map geometry and framing: every transfer endpoint stays on one canvas in itinerary order. Unlike B, no separate summary strip is added; unlike C, no route-layer controls are added.",
  },
  {
    id: "journey-strip",
    label: "B · Journey strip + local map",
    summary: "The map stays at destination-city scale while a pinned strip carries the complete stay-to-stay journey.",
    delta:
      "Moves the inter-city leg off the canvas and into fixed chrome above it. Unlike A, the origin circuit and terminals never appear as map geometry; unlike C, the user cannot reveal them.",
  },
  {
    id: "layer-toggle",
    label: "C · Optional inter-city layer",
    summary: "Both scales render together, with independent controls to hide local or inter-city geometry.",
    delta:
      "Adds two persistent visibility controls to the dual-scale canvas. Unlike A, geometry can be switched off; unlike B, the inter-city leg stays real map geometry rather than a summary.",
  },
];

export const scenarios: Scenario[] = [
  {
    id: "road",
    tab: "Road transfer",
    day: "Day 4 · Transfer",
    route: "Jaipur → Udaipur by private car",
    summary:
      "A full-day drive with two authored on-route stops, then a short destination circuit after check-in.",
    guard: false,
    travel: { label: "Private car", duration: "6 hr 30 min", distance: "397 km", detail: "NH 48 via Bhilwara · same vehicle all day" },
    nodes: [
      { id: "h1", kind: "hotel", marker: "H1", name: "Rambagh Palace", detail: "Jaipur stay · check out", time: "08:30", side: "origin", x: 10, y: 24 },
      { id: "w1", kind: "place", marker: "1", name: "Chand Baori stepwell", detail: "Scenic stop · 45 min", time: "10:20", side: "journey", x: 32, y: 40 },
      { id: "w2", kind: "place", marker: "2", name: "Lunch · Deogarh Mahal", detail: "Meal stop · 60 min", time: "12:40", side: "journey", x: 54, y: 56 },
      { id: "h2", kind: "hotel", marker: "H2", name: "The Leela Palace", detail: "Udaipur stay · check in", time: "16:00", side: "destination", x: 72, y: 68 },
      { id: "p1", kind: "place", marker: "3", name: "Ambrai Ghat sunset", detail: "Lake view · 60 min", time: "18:15", side: "destination", x: 85, y: 80 },
    ],
    legs: [
      { from: "h1", to: "w1", mode: "road", label: "95 km · 1 hr 50 min" },
      { from: "w1", to: "w2", mode: "road", label: "148 km · 2 hr 20 min" },
      { from: "w2", to: "h2", mode: "road", label: "154 km · 2 hr 20 min" },
      { from: "h2", to: "p1", mode: "local", label: "Taxi · 12 min" },
      { from: "p1", to: "h2", mode: "local", label: "Taxi · 12 min" },
    ],
    baselineNodeIds: ["h2", "p1"],
    baselineNote: "Today the map keeps only the Udaipur circuit. The drive, both authored stops, and the Jaipur stay never reach the canvas.",
    afterNote: "The drive stays one continuous path from the Jaipur checkout through both authored stops to check-in, then the local circuit follows.",
    framing: "Frame the destination stay circuit; the full drive stays available in the same geometry.",
    fit: { x: 66, y: 62, width: 32, height: 34 },
  },
  {
    id: "rail",
    tab: "Rail transfer",
    day: "Day 4 · Transfer",
    route: "Jaipur → Udaipur by train",
    summary: "Station transfers on both sides of a long rail leg, with the same evening circuit after check-in.",
    guard: false,
    travel: { label: "Intercity train", duration: "7 hr 10 min", distance: "430 km", detail: "Jaipur Junction → Udaipur City · seats confirmed" },
    nodes: [
      { id: "h1", kind: "hotel", marker: "H1", name: "Rambagh Palace", detail: "Jaipur stay · check out", time: "08:10", side: "origin", x: 10, y: 24 },
      { id: "t1", kind: "terminal", marker: "R", name: "Jaipur Junction", detail: "Boarding · platform 4", time: "09:05", side: "journey", x: 24, y: 34 },
      { id: "t2", kind: "terminal", marker: "R", name: "Udaipur City station", detail: "Arrival · exit east", time: "16:15", side: "journey", x: 66, y: 64 },
      { id: "h2", kind: "hotel", marker: "H2", name: "The Leela Palace", detail: "Udaipur stay · check in", time: "17:00", side: "destination", x: 74, y: 70 },
      { id: "p1", kind: "place", marker: "1", name: "Ambrai Ghat sunset", detail: "Lake view · 60 min", time: "18:15", side: "destination", x: 86, y: 80 },
    ],
    legs: [
      { from: "h1", to: "t1", mode: "local", label: "Taxi · 20 min" },
      { from: "t1", to: "t2", mode: "rail", label: "Chetak Express · 430 km" },
      { from: "t2", to: "h2", mode: "local", label: "Taxi · 25 min" },
      { from: "h2", to: "p1", mode: "local", label: "Taxi · 12 min" },
      { from: "p1", to: "h2", mode: "local", label: "Taxi · 12 min" },
    ],
    baselineNodeIds: ["h2", "p1"],
    baselineNote: "Today both stations are filtered out as non-place stops, so the boarding and arrival transfers are invisible on the map.",
    afterNote: "Stations render as informational terminal pins, and the rail leg uses dashed treatment distinct from road and flight.",
    framing: "Frame the arrival station to stay circuit.",
    fit: { x: 58, y: 56, width: 40, height: 40 },
  },
  {
    id: "flight",
    tab: "Flight transfer",
    day: "Day 4 · Transfer",
    route: "Jaipur → Udaipur by air",
    summary: "Airport transfers on both sides of a short flight, then an afternoon destination stop.",
    guard: false,
    travel: { label: "Flight", duration: "1 hr 10 min", distance: "330 km air", detail: "JAI → UDR · transfers shown separately" },
    nodes: [
      { id: "h1", kind: "hotel", marker: "H1", name: "Rambagh Palace", detail: "Jaipur stay · check out", time: "07:40", side: "origin", x: 10, y: 24 },
      { id: "t1", kind: "terminal", marker: "A", name: "JAI · Jaipur airport", detail: "Departure terminal", time: "08:30", side: "journey", x: 24, y: 32 },
      { id: "t2", kind: "terminal", marker: "A", name: "UDR · Maharana Pratap", detail: "Arrival terminal", time: "11:05", side: "journey", x: 68, y: 62 },
      { id: "h2", kind: "hotel", marker: "H2", name: "The Leela Palace", detail: "Udaipur stay · check in", time: "12:30", side: "destination", x: 74, y: 70 },
      { id: "p1", kind: "place", marker: "1", name: "City Palace museum", detail: "Guided visit · 90 min", time: "15:00", side: "destination", x: 86, y: 80 },
    ],
    legs: [
      { from: "h1", to: "t1", mode: "local", label: "Taxi · 25 min" },
      { from: "t1", to: "t2", mode: "flight", label: "1 hr 10 min · 330 km air" },
      { from: "t2", to: "h2", mode: "local", label: "Taxi · 30 min" },
      { from: "h2", to: "p1", mode: "local", label: "Walk · 10 min" },
      { from: "p1", to: "h2", mode: "local", label: "Walk · 10 min" },
    ],
    baselineNodeIds: ["h2", "p1"],
    baselineNote: "Today both airports are filtered out, so an air transfer day looks like an ordinary Udaipur afternoon.",
    afterNote: "Airports render as informational pins and the air leg uses a dotted arc that cannot be mistaken for a drivable road.",
    framing: "Frame the arrival airport to stay circuit.",
    fit: { x: 60, y: 54, width: 38, height: 42 },
  },
  {
    id: "departure",
    tab: "Departure day",
    day: "Day 8 · Departure",
    route: "Udaipur stay → UDR airport",
    summary: "The edge case with no substantive destination stop left: the day ends at a terminal.",
    guard: false,
    travel: { label: "Departure transfer", duration: "3 hr 10 min", distance: "34 km", detail: "Checkout, one last stop, then airport" },
    nodes: [
      { id: "h1", kind: "hotel", marker: "H", name: "The Leela Palace", detail: "Udaipur stay · check out", time: "11:00", side: "origin", x: 18, y: 64 },
      { id: "p1", kind: "place", marker: "1", name: "Shilpgram craft village", detail: "Final stop · 60 min", time: "11:40", side: "origin", x: 38, y: 52 },
      { id: "t1", kind: "terminal", marker: "A", name: "UDR · Maharana Pratap", detail: "Departure terminal", time: "14:10", side: "journey", x: 60, y: 44 },
    ],
    legs: [
      { from: "h1", to: "p1", mode: "local", label: "Taxi · 15 min" },
      { from: "p1", to: "t1", mode: "local", label: "Taxi · 35 min" },
    ],
    baselineNodeIds: ["h1", "p1"],
    baselineNote: "Today the airport is filtered out, so the day stops at the craft village and the departure looks unplanned.",
    afterNote: "The terminal is retained and, because no destination stop remains, the day frames the origin stay-to-airport circuit.",
    framing: "Fallback framing: origin stay to terminal.",
    fit: { x: 8, y: 34, width: 62, height: 42 },
  },
  {
    id: "ordinary",
    tab: "Ordinary day (guard)",
    day: "Day 5 · Sightseeing",
    route: "Udaipur closed hotel circuit",
    summary: "The regression guard: an ordinary day must look exactly the same before and after this Lab.",
    guard: true,
    travel: { label: "Local circuit", duration: "9 hr 05 min", distance: "18 km", detail: "Hotel out and back · no inter-city travel" },
    nodes: [
      { id: "h1", kind: "hotel", marker: "H", name: "The Leela Palace", detail: "Udaipur stay · depart and return", time: "09:15", side: "destination", x: 24, y: 62 },
      { id: "p1", kind: "place", marker: "1", name: "City Palace museum", detail: "Guided visit · 120 min", time: "10:00", side: "destination", x: 44, y: 42 },
      { id: "p2", kind: "place", marker: "2", name: "Jagdish Temple", detail: "Short visit · 45 min", time: "12:45", side: "destination", x: 64, y: 50 },
      { id: "p3", kind: "place", marker: "3", name: "Ambrai Ghat sunset", detail: "Lake view · 60 min", time: "17:30", side: "destination", x: 54, y: 76 },
    ],
    legs: [
      { from: "h1", to: "p1", mode: "local", label: "Taxi · 14 min" },
      { from: "p1", to: "p2", mode: "local", label: "Walk · 8 min" },
      { from: "p2", to: "p3", mode: "local", label: "Walk · 12 min" },
      { from: "p3", to: "h1", mode: "local", label: "Taxi · 16 min" },
    ],
    baselineNodeIds: ["h1", "p1", "p2", "p3"],
    baselineNote: "A closed hotel circuit is already complete today.",
    afterNote: "Unchanged. No option in this Lab may open, re-frame, or re-style an ordinary sightseeing day.",
    framing: "Frame the complete closed circuit, exactly as today.",
    fit: { x: 14, y: 32, width: 62, height: 56 },
  },
];

export function legsWithin(scenario: Scenario, nodeIds: string[]): MapLeg[] {
  return scenario.legs.filter((leg) => nodeIds.includes(leg.from) && nodeIds.includes(leg.to));
}

export function baselineNodes(scenario: Scenario): MapNode[] {
  return scenario.nodes.filter((node) => scenario.baselineNodeIds.includes(node.id));
}

export interface ImprovementRow {
  label: string;
  before: string;
  after: string;
  gain: boolean;
}

export function improvementRows(scenario: Scenario): ImprovementRow[] {
  const baselineIds = scenario.baselineNodeIds;
  const baselineLegs = legsWithin(scenario, baselineIds).length;
  const terminals = scenario.nodes.filter((node) => node.kind === "terminal").length;
  const cities = new Set(scenario.nodes.map((node) => (node.side === "destination" ? "destination" : "origin")));
  const baselineCities = new Set(
    baselineNodes(scenario).map((node) => (node.side === "destination" ? "destination" : "origin")),
  );

  return [
    {
      label: "Itinerary stops reaching the map",
      before: `${baselineIds.length} of ${scenario.nodes.length}`,
      after: `${scenario.nodes.length} of ${scenario.nodes.length}`,
      gain: baselineIds.length < scenario.nodes.length,
    },
    {
      label: "Route legs drawn",
      before: `${baselineLegs}`,
      after: `${scenario.legs.length}`,
      gain: baselineLegs < scenario.legs.length,
    },
    {
      label: "Airport or station pins",
      before: terminals > 0 ? "Filtered out" : "None in this day",
      after: terminals > 0 ? `${terminals} informational pins` : "None in this day",
      gain: terminals > 0,
    },
    {
      label: "City contexts on the canvas",
      before: `${baselineCities.size}`,
      after: `${cities.size}`,
      gain: baselineCities.size < cities.size,
    },
  ];
}
