import { rankedOptions } from "../shared/OptionContrast";

/** Today's Account settings drawer is max-w-sm, so every option is measured against it. */
export const TODAY_WIDTH = 384;

const optionCards = [
  {
    id: "wide-drawer" as const,
    name: "Wider drawer",
    summary: "The same right-side drawer, widened to a two-column editing surface.",
    cost: "Familiar and cheap, but a drawer still overlays the trip you were reading.",
    width: 960,
  },
  {
    id: "full-page" as const,
    name: "Full profile page",
    summary: "A dedicated page with a section rail and a genuinely wide canvas.",
    cost: "The most room by far; it leaves the workspace instead of floating over it.",
    width: 1240,
  },
  {
    id: "workspace-modal" as const,
    name: "Centered workspace",
    summary: "A large centered dialog with its own rail, floating above the trip.",
    cost: "Roomy without losing your place, but modal focus traps still fight long forms.",
    width: 1100,
  },
  {
    id: "two-pane" as const,
    name: "People-first two pane",
    summary: "A category rail plus a detail pane, with travellers as the primary object.",
    cost: "Best for families; slightly indirect for a single traveller editing one field.",
    width: 1080,
  },
  {
    id: "expandable" as const,
    name: "Expand on demand",
    summary: "The compact drawer stays for quick edits and expands to full width when needed.",
    cost: "No new destination to learn, but two states of the same screen to design and test.",
    width: 384,
  },
];

export type OptionId = (typeof optionCards)[number]["id"];

// Letter and order come from the contrast table's scores, so the cards below
// the table cannot disagree with it about which option is A.
export const options: ((typeof optionCards)[number] & { label: string })[] = rankedOptions(
  "profile-workspace",
)
  .map((entry) => {
    const card = optionCards.find((candidate) => candidate.name === entry.name);
    return card ? { ...card, label: entry.label } : null;
  })
  .filter((card): card is (typeof optionCards)[number] & { label: string } => card !== null);
