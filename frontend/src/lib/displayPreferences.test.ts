import { describe, expect, it } from "vitest";
import {
  displayLocale,
  formatCostDisplay,
  formatDistance,
  formatDisplayAmount,
  formatTemperature,
  normalizeDisplayLanguage,
  normalizeDisplayRegion,
  supportedDisplayLanguages,
  supportedDisplayRegions,
} from "./displayPreferences";

describe("display preferences formatting", () => {
  it("formats prices in the selected presentation currency", () => {
    expect(formatDisplayAmount(100, "USD", "INR")).toBe("₹8,300");
    expect(formatDisplayAmount(100, "€", "USD")).toBe("$109");
    expect(formatDisplayAmount(100, "USD", "CNY")).toBe("CN¥720");
  });

  it("uses regional distance and temperature conventions", () => {
    expect(formatDistance(10, "United States")).toBe("6.2 mi");
    expect(formatTemperature(20, "United States")).toBe("68°F");
    expect(formatDistance(10, "India")).toBe("10 km");
    expect(formatDistance(10, "US")).toBe("6.2 mi");
    expect(formatTemperature(20, "IN")).toBe("20°C");
  });

  it("offers fixed country and language choices instead of free text", () => {
    const regions = supportedDisplayRegions();
    const languages = supportedDisplayLanguages();

    expect(regions.length).toBeGreaterThan(200);
    expect(regions).toContainEqual({ code: "IN", label: "India" });
    expect(regions).toContainEqual({ code: "US", label: "United States" });
    expect(regions.every((region) => /^[A-Z]{2}$/.test(region.code))).toBe(true);
    expect(languages.map((language) => language.code)).toContain("en");
    expect(languages.map((language) => language.code)).toContain("fr");
  });

  it("migrates previously typed countries and rejects unknown values", () => {
    expect(normalizeDisplayRegion("India")).toBe("IN");
    expect(normalizeDisplayRegion("USA")).toBe("US");
    expect(normalizeDisplayRegion("uk")).toBe("GB");
    expect(normalizeDisplayRegion("Atlantis")).toBe("");
    expect(normalizeDisplayLanguage("fr-FR")).toBe("fr");
    expect(normalizeDisplayLanguage("klingon")).toBe("en");
  });

  it("builds the presentation locale from country and language together", () => {
    expect(displayLocale({ region: "IN", language: "en", currency: "USD" })).toBe("en-IN");
    expect(displayLocale({ region: "FR", language: "fr", currency: "USD" })).toBe("fr-FR");
    expect(displayLocale({ region: "", language: "en", currency: "USD" })).toBe("en");
  });

  it("converts preformatted itinerary cost hints without showing the source", () => {
    expect(formatCostDisplay("€1,100", "INR")).toBe("₹99,239");
    expect(formatCostDisplay("€8-25 tickets (est.)", "INR")).toBe("₹722-₹2,255 tickets (est.)");
    expect(formatCostDisplay("Mid-range", "INR")).toBe("Mid-range");
  });
});
