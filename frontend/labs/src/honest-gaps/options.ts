import { rankedOptions } from "../shared/OptionContrast";

const optionCards = [
  {
    id: "inbox" as const,
    name: "Decision inbox",
    summary: "A pinned bar above the days counts every open decision and expands into one list to clear them.",
    delta: "Only this option gathers every gap into one list above the itinerary; placeholder rows are drawn dashed and link back to it.",
    home: "Itinerary, top",
  },
  {
    id: "slots" as const,
    name: "Inline slots",
    summary: "Each placeholder becomes a dashed slot inside its own day, with suggestions right there.",
    delta: "Only this option resolves a gap inside the day it belongs to; there is no trip-level list, just a count on each day header.",
    home: "Inside each day",
  },
  {
    id: "checklist" as const,
    name: "Readiness checklist",
    summary: "Details gains a Plan readiness checklist grouped by Stay, Meals, Journeys and Prices.",
    delta: "Only this option leaves itinerary rows almost unchanged (a hollow marker) and moves every gap into the Details pane.",
    home: "Details pane",
  },
  {
    id: "assistant" as const,
    name: "Assistant follow-up",
    summary: "The Assistant posts one message listing the gaps as tappable chips after it delivers the plan.",
    delta: "Only this option changes no pane: the gaps live in the conversation, and the itinerary still shows placeholders as ordinary stops.",
    home: "Conversation",
  },
];

export type OptionId = (typeof optionCards)[number]["id"];

// Letters and order come from the contrast table's scores so the cards and the
// table cannot disagree about which option is A.
export const options: ((typeof optionCards)[number] & { label: string })[] = rankedOptions("honest-gaps")
  .map((entry) => {
    const card = optionCards.find((candidate) => candidate.name === entry.name);
    return card ? { ...card, label: entry.label } : null;
  })
  .filter((card): card is (typeof optionCards)[number] & { label: string } => card !== null);
