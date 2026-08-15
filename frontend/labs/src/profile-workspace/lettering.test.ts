import { describe, expect, it } from "vitest";

import { rankedOptions } from "../shared/OptionContrast";
import { options } from "./options";

/** Labs whose own option cards letter themselves from the contrast scores. */
const LABS_WITH_OPTION_CARDS = ["profile-workspace"];

describe("option lettering", () => {
  it("gives the best-scored option the letter A", () => {
    for (const labId of LABS_WITH_OPTION_CARDS) {
      const ranked = rankedOptions(labId);
      expect(ranked.length).toBeGreaterThan(0);
      expect(ranked[0].label.startsWith("A · ")).toBe(true);
      expect(ranked[0].score).toBe(Math.max(...ranked.map((option) => option.score)));
    }
  });

  it("hands out consecutive letters in descending score order", () => {
    for (const labId of LABS_WITH_OPTION_CARDS) {
      const ranked = rankedOptions(labId);
      ranked.forEach((option, index) => {
        expect(option.label).toBe(`${String.fromCharCode(65 + index)} · ${option.name}`);
        if (index > 0) {
          expect(ranked[index - 1].score).toBeGreaterThanOrEqual(option.score);
        }
      });
    }
  });

  it("letters the profile workspace cards the same way the contrast table does", () => {
    // The table and the cards used to letter independently, so the top-ranked
    // "Full profile page" read as A above and B below on the same screen.
    const ranked = rankedOptions("profile-workspace");

    expect(options.map((option) => option.label)).toEqual(ranked.map((option) => option.label));
    expect(options[0].label.startsWith("A · ")).toBe(true);
    expect(options[0].name).toBe("Full profile page");
  });
});
