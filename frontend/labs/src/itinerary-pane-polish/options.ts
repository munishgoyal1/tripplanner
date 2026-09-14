import { rankedOptions } from "../shared/OptionContrast";
import type { Chrome } from "./Workspace";

export const LAB_ID = "itinerary-pane-polish";

const cards = [
  {
    id: "crisp" as const,
    name: "Crisp workspace harmony",
    eyebrow: "Pane + workspace finish",
    chrome: "crisp" as Chrome,
    summary: "A flat, precise list pane, with the workspace around it tuned to the same finish.",
    delta: "Stops become hairline-separated list rows with line icons instead of emoji, bordered fact tags, and a sticky day header. The trip snapshot folds into Overview, Weather and Budget tabs. Workspace-wide it retunes the neutral tokens a touch cooler, flattens every pane header to one line, gives the day bar colour dots with an ink selection, and matches Details' tags. Unlike Warm editorial it removes decoration rather than adding it; unlike the pane-only options it changes chrome outside the itinerary.",
  },
  {
    id: "timeline" as const,
    name: "Quiet timeline",
    eyebrow: "Pane only",
    chrome: "today" as Chrome,
    summary: "One time gutter and one rail; travel becomes the line between stops.",
    delta: "Boxed stop cards are removed. Times sit in a left gutter, markers sit on a continuous day-coloured rail, and each travel-from-previous leg is drawn as the rail segment between two stops with a mode icon. Ratings, must-visit, cost and hours share one quiet line. Weather, budget and trip needs fold behind one summary row. Nothing outside the itinerary pane changes.",
  },
  {
    id: "warm" as const,
    name: "Warm editorial harmony",
    eyebrow: "Pane + workspace finish",
    chrome: "soft" as Chrome,
    summary: "Soft tiles, day-tinted covers and serif titles, echoed lightly across the workspace.",
    delta: "Each day opens with a softly tinted cover in its own colour, a large serif title and fact pills; stops are borderless rounded tiles with pill-shaped signals, and travel is a dotted connector with a pill. Workspace-wide, pane headers lose the two-line eyebrow for one serif label, panes get softer radii and shadow, the notification strip becomes an inline pill, and the day bar gains colour dots. It is the only option that adds warmth rather than removing chrome.",
  },
  {
    id: "agenda" as const,
    name: "Precise agenda",
    eyebrow: "Pane only",
    chrome: "today" as Chrome,
    summary: "A ledger: start and leave times in a column, status in a column, facts in between.",
    delta: "Every stop is a three-column ledger row — time block, content, booking status — with no card borders. Each day header carries a four-cell metric table (schedule, travel, stops, bookings), travel legs are slim rows showing buffer or conflict as a signed badge, and trip-level weather, budget and needs become one-line expandable rows. Nothing outside the itinerary pane changes.",
  },
  {
    id: "cards" as const,
    name: "Clean stop cards",
    eyebrow: "Pane only",
    chrome: "today" as Chrome,
    summary: "Today's card model, rebuilt with labelled fact grids and collapsible days.",
    delta: "Stops stay as cards but gain structure: a labelled fact grid (rating, must-visit meter, cost, hours) replaces the chip row, and travel becomes a connector pill between cards. Days are accordions — the focused day opens, the others collapse to their header facts — so length is controlled by folding days rather than by tightening rows. Nothing outside the itinerary pane changes.",
  },
];

export type OptionId = (typeof cards)[number]["id"];
export type OptionCard = (typeof cards)[number] & { label: string; score: number };

export const options: OptionCard[] = rankedOptions(LAB_ID)
  .map((ranked) => {
    const card = cards.find((candidate) => candidate.name === ranked.name);
    return card ? { ...card, label: ranked.label, score: ranked.score } : null;
  })
  .filter((card): card is OptionCard => card !== null);

type Visibility = "rest" | "tap" | "hover";

/**
 * Where every production fact lives in each option: visible at rest, one tap
 * away, or revealed on hover/focus. Nothing is ever "removed" — that is the
 * Lab's hard constraint, so it is not a column.
 */
export const factMatrix: Array<{ group: string; fact: string; today: Visibility } & Record<OptionId, Visibility>> = [
  { group: "Trip", fact: "Destination, origin, dates, travellers, status", today: "rest", crisp: "rest", timeline: "rest", warm: "rest", agenda: "rest", cards: "rest" },
  { group: "Trip", fact: "Total cost, quote evidence, Recheck prices", today: "rest", crisp: "rest", timeline: "rest", warm: "rest", agenda: "rest", cards: "rest" },
  { group: "Trip", fact: "Trip summary text", today: "rest", crisp: "rest", timeline: "rest", warm: "rest", agenda: "rest", cards: "rest" },
  { group: "Trip", fact: "Readiness and days / stays / places / flights", today: "rest", crisp: "rest", timeline: "rest", warm: "rest", agenda: "rest", cards: "rest" },
  { group: "Trip", fact: "Per-day weather, source and packing advice", today: "rest", crisp: "tap", timeline: "tap", warm: "rest", agenda: "tap", cards: "rest" },
  { group: "Trip", fact: "Family pills and trip constraints", today: "rest", crisp: "rest", timeline: "tap", warm: "rest", agenda: "tap", cards: "rest" },
  { group: "Trip", fact: "Budget, per traveller, left, % used, all-in", today: "rest", crisp: "tap", timeline: "tap", warm: "rest", agenda: "tap", cards: "rest" },
  { group: "Checks", fact: "Verdict, counts, contradictions and Rearrange", today: "rest", crisp: "rest", timeline: "rest", warm: "rest", agenda: "rest", cards: "rest" },
  { group: "Checks", fact: "Every rule, gaps, holidays, Recheck place facts", today: "tap", crisp: "tap", timeline: "tap", warm: "tap", agenda: "tap", cards: "tap" },
  { group: "Day", fact: "Date, title, weather with rain chance", today: "rest", crisp: "rest", timeline: "rest", warm: "rest", agenda: "rest", cards: "rest" },
  { group: "Day", fact: "Day summary and travel rhythm", today: "rest", crisp: "rest", timeline: "rest", warm: "rest", agenda: "rest", cards: "rest" },
  { group: "Day", fact: "Schedule, day's travel, stops, confirmed / to book", today: "rest", crisp: "rest", timeline: "rest", warm: "rest", agenda: "rest", cards: "rest" },
  { group: "Day", fact: "Show day on map, Open route, Add / Reduce a day", today: "rest", crisp: "rest", timeline: "rest", warm: "rest", agenda: "rest", cards: "rest" },
  { group: "Day", fact: "Stops of a day that is not in focus", today: "rest", crisp: "rest", timeline: "rest", warm: "rest", agenda: "rest", cards: "tap" },
  { group: "Stop", fact: "Time, name, timing label, kind, duration, leave time", today: "rest", crisp: "rest", timeline: "rest", warm: "rest", agenda: "rest", cards: "rest" },
  { group: "Stop", fact: "Rating with review count", today: "rest", crisp: "rest", timeline: "rest", warm: "rest", agenda: "rest", cards: "rest" },
  { group: "Stop", fact: "Must-visit score", today: "rest", crisp: "rest", timeline: "rest", warm: "rest", agenda: "rest", cards: "rest" },
  { group: "Stop", fact: "Cost and opening hours", today: "rest", crisp: "rest", timeline: "rest", warm: "rest", agenda: "rest", cards: "rest" },
  { group: "Stop", fact: "Booking status toggle", today: "rest", crisp: "rest", timeline: "rest", warm: "rest", agenda: "rest", cards: "rest" },
  { group: "Stop", fact: "Concern", today: "rest", crisp: "rest", timeline: "rest", warm: "rest", agenda: "rest", cards: "rest" },
  { group: "Stop", fact: "Notes and insights", today: "tap", crisp: "tap", timeline: "tap", warm: "tap", agenda: "tap", cards: "tap" },
  { group: "Stop", fact: "Show on map and Remove", today: "hover", crisp: "hover", timeline: "hover", warm: "hover", agenda: "hover", cards: "hover" },
  { group: "Travel", fact: "Mode, distance, duration, route detail", today: "rest", crisp: "rest", timeline: "rest", warm: "rest", agenda: "rest", cards: "rest" },
  { group: "Travel", fact: "Estimated arrival with buffer or conflict", today: "rest", crisp: "rest", timeline: "rest", warm: "rest", agenda: "rest", cards: "rest" },
];
