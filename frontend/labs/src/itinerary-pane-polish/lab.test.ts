import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { publishUnmappedStops } from "../../../src/lib/unmappedStops";
import { allLabs, LAST_ASSIGNED_LAB_NUMBER } from "../shared/labRecords";
import { itinerary, unmappedStops } from "./fixture";
import { deriveDay } from "./model";
import { factMatrix, LAB_ID, options, type OptionId } from "./options";
import { PANES } from "./panes";
import { usePlannerState } from "./state";

// Plain .test.ts so it runs in the node project: server rendering proves the
// parity claims without a jsdom worker, which cannot start in every sandbox.

function renderedText(option: OptionId): string {
  publishUnmappedStops(unmappedStops);
  const Pane = PANES[option];
  function Harness() {
    return createElement(Pane, { state: usePlannerState() });
  }
  return renderToStaticMarkup(createElement(Harness))
    .replace(/<[^>]+>/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&#x27;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/\s+/g, " ");
}

const includesText = (text: string, expected: string) => text.includes(expected.replace(/\s+/g, " "));

describe("itinerary pane polish lab", () => {
  it("allocates permanent Lab number 31 with a catalog entry and Vite entry", () => {
    const lab = allLabs.find((entry) => entry.id === LAB_ID);
    expect(LAST_ASSIGNED_LAB_NUMBER).toBeGreaterThanOrEqual(31);
    expect(lab).toMatchObject({ labNumber: 31, href: "./lab-31-itinerary-pane-polish.html" });
    const vite = readFileSync(resolve(process.cwd(), "labs/vite.config.ts"), "utf8");
    const html = readFileSync(resolve(process.cwd(), "labs/lab-31-itinerary-pane-polish.html"), "utf8");
    expect(vite).toContain('itineraryPanePolish: resolve(__dirname, "lab-31-itinerary-pane-polish.html")');
    expect(html).toContain("./src/itinerary-pane-polish/main.tsx");
  });

  it("orders seven options best first without renaming the letters the owner already used", () => {
    expect(options.map((option) => option.id)).toEqual(["flow", "sections", "crisp", "timeline", "warm", "agenda", "cards"]);
    expect(options.map((option) => option.score)).toEqual([95, 93, 92, 90, 85, 82, 78]);
    expect(options.map((option) => option.label.slice(0, 1))).toEqual(["F", "G", "A", "B", "C", "D", "E"]);
    expect(options.filter((option) => option.chrome !== "today").map((option) => option.id)).toEqual(["flow", "sections", "crisp", "warm"]);
  });

  it("derives production wording for timing labels across circuit, transition and road days", () => {
    const [day1, , day3] = itinerary.days.map((day) => deriveDay(day, [], (value) => value));
    expect(day1.rows[day1.rows.length - 1]).toMatchObject({ name: "Return to ITC Rajputana", timingLabel: "Return", kindLabel: "Hotel return" });
    expect(day1.rows[1].timingLabel).toBe("Land");
    expect(day3.rows[0].timingLabel).toBe("Check out");
    expect(day3.rows[day3.rows.length - 1]?.timingLabel).toBe("Check in");
    expect(day3.rows.find((row) => row.stop.name === "Drive: Chittorgarh to Udaipur")?.timingLabel).toBe("Depart from Chittorgarh");
    expect(day3.transition).toEqual({ from: "ITC Rajputana", to: "Taj Lake Palace" });
    const lunch = itinerary.days[1].stops.findIndex((stop) => stop.name === "Lunch at 1135 AD");
    expect(deriveDay(itinerary.days[1], [], (value) => value).rows[lunch].travel?.conflict).toBe("schedule is 10 min too tight");
  });

  // Facts every option must show without a click, for every day it has open.
  const alwaysVisible = [
    "Jaipur & Udaipur",
    "From Bengaluru",
    "9 of 14 prices from live quotes",
    "Recheck prices",
    "A four-day Rajasthan loop for two",
    "7 of 19 ready",
    "Checked, with gaps we could not confirm",
    "Add a day",
    "Reduce a day",
    "Arrival and the Pink City",
    "Land by breakfast, settle into the hotel",
    "Old-city stops are a short walk apart",
    // Agenda puts value and span in separate table lines, so match the parts.
    "13 hrs 5 min",
    "06:10–19:15",
    "2 hrs 29 min",
    "2 confirmed",
    "3 to book",
    "5 planned",
    "Open route",
    "Hawa Mahal",
    "Must-visit score 92/100",
    "112K reviews",
    "09:00–16:30",
    "1 hr visit",
    "Leave 12:30",
    "Via MI Road; old-city lanes slow down after 11:00",
    "Est. arrive 10:40 · 50 min free before 11:30",
    "The last 2 km is a steep single-lane road",
    "Confirmed",
    "Return to ITC Rajputana",
    "Amber Fort and the palace circuit",
    "Jaipur to Udaipur via Chittorgarh",
    "Lake Pichola and home",
    "Long road day: two drives",
  ];
  const openDayFacts = [
    "Lunch at 1135 AD",
    "schedule is 10 min too tight",
    "Not on map",
    "Must-visit score 95/100",
    "Boat transfer runs from Bansi Ghat only",
    "Depart from Chittorgarh",
    "Check in",
    "Flight: Udaipur (UDR) to Bengaluru (BLR)",
  ];

  it.each(options.map((option) => option.id))("%s keeps every at-rest production fact", (id) => {
    const text = renderedText(id);
    const missing = alwaysVisible.filter((fact) => !includesText(text, fact));
    expect(missing).toEqual([]);
    // F and G shorten the unbooked status to "To book", matching the day header's wording.
    expect(includesText(text, "Needs booking") || includesText(text, "To book")).toBe(true);
    // Clean stop cards folds days that are not in focus; the fact matrix declares that.
    const stopsFold = factMatrix.find((row) => row.fact === "Stops of a day that is not in focus")?.[id] === "tap";
    const missingOpen = openDayFacts.filter((fact) => !includesText(text, fact));
    expect(missingOpen).toEqual(stopsFold ? openDayFacts : []);
  });

  it("places weather and budget at rest exactly where the fact matrix says", () => {
    for (const option of options) {
      const text = renderedText(option.id);
      const weather = factMatrix.find((row) => row.fact.startsWith("Per-day weather"))![option.id];
      const budget = factMatrix.find((row) => row.fact.startsWith("Budget"))![option.id];
      expect(includesText(text, "Light cotton layers"), `${option.id} packing`).toBe(weather === "rest");
      expect(includesText(text, "Confirmed all-in"), `${option.id} budget`).toBe(budget === "rest");
    }
  });
});
