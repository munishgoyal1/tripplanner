import { rankedOptions } from "../shared/OptionContrast";

const cards = [
  { id: "journey" as const, name: "Journey canvas", eyebrow: "Fresh direction 01", summary: "Route, day, and place become one spatial canvas.", delta: "A full-width map is the stage; a horizontal journey rail replaces the resident itinerary column, details float beside the selected stop, and the assistant becomes a compact command dock." },
  { id: "storyboard" as const, name: "Trip storyboard", eyebrow: "Fresh direction 02", summary: "The plan reads like a beautifully edited travel story.", delta: "A chapter rail and editorial day stream replace the three equal panes; a supporting map and evidence rail remain visible without interrupting the reading order." },
  { id: "refined" as const, name: "Refined spatial workspace", eyebrow: "Evolve sbx4", summary: "Familiar three-pane planning with a calmer hierarchy.", delta: "The sbx4 itinerary-map-details model stays, while navigation, action grouping, notification density, pane headers, colour, type, and the assistant dock are substantially redesigned." },
  { id: "polish" as const, name: "Precision polish", eyebrow: "Nuance pass", summary: "Keep the layout; sharpen every visible interaction.", delta: "The sbx4 geometry and information order stay fixed. Only iconography, spacing, grouped controls, hover/focus states, professional hide/maximize actions, and surface finish change." },
];

export type OptionId = (typeof cards)[number]["id"];

export const options = rankedOptions("planner-layout-directions")
  .map((ranked) => {
    const card = cards.find((candidate) => candidate.name === ranked.name);
    return card ? { ...card, label: ranked.label, score: ranked.score } : null;
  })
  .filter((card): card is (typeof cards)[number] & { label: string; score: number } => card !== null);
