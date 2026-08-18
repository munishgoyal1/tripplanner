import { rankedOptions } from "../shared/OptionContrast";

/** Rows of itinerary the control covers while nobody is using it. The whole
 * argument is about resting cost, so every option states one. */
export const TODAY_FOOTPRINT = "No feedback surface exists today.";

const optionCards = [
  {
    id: "toolbar-pill" as const,
    name: "Toolbar rating pill",
    summary: "A thumbs pair in the workspace toolbar that opens a compact rating popover.",
    cost: "Always one tap from every pane; the popover stays small so it never covers the plan.",
    resting: "One 96px control in the toolbar",
    reach: "Every pane",
  },
  {
    id: "itinerary-footer" as const,
    name: "Itinerary footer card",
    summary: "A calm card after the last day, where reading the plan naturally ends.",
    cost: "Perfectly timed, but only reachable once the itinerary is scrolled to the bottom.",
    resting: "One card below the last day",
    reach: "Itinerary only",
  },
  {
    id: "assistant-ask" as const,
    name: "Assistant-led ask",
    summary: "The planner asks once in the conversation right after it delivers the trip.",
    cost: "Easiest to answer because it reads as a reply, but it scrolls away with the thread.",
    resting: "One message in the transcript",
    reach: "Assistant only",
  },
  {
    id: "per-day" as const,
    name: "Per-day thumbs",
    summary: "Each day header carries its own thumbs pair, rolling up to one trip rating.",
    cost: "The most actionable signal, at the price of a control on every single day.",
    resting: "One control per day header",
    reach: "Itinerary only",
  },
  {
    id: "floating-tab" as const,
    name: "Floating feedback tab",
    summary: "A discreet anchored pill floats above the workspace and opens a sheet.",
    cost: "Always visible on any surface, but it reads as a bolted-on survey widget.",
    resting: "A floating pill over the plan",
    reach: "Every pane",
  },
];

export type OptionId = (typeof optionCards)[number]["id"];

// Letter and order come from the contrast table's scores, so the cards below
// the table cannot disagree with it about which option is A.
export const options: ((typeof optionCards)[number] & { label: string })[] = rankedOptions(
  "trip-feedback",
)
  .map((entry) => {
    const card = optionCards.find((candidate) => candidate.name === entry.name);
    return card ? { ...card, label: entry.label } : null;
  })
  .filter((card): card is (typeof optionCards)[number] & { label: string } => card !== null);
