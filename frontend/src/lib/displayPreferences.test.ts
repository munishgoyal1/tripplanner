import { describe, expect, it } from "vitest";
import { formatCostDisplay, formatDistance, formatDisplayAmount, formatTemperature } from "./displayPreferences";

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
  });

  it("converts preformatted itinerary cost hints without showing the source", () => {
    expect(formatCostDisplay("€1,100", "INR")).toBe("₹99,239");
    expect(formatCostDisplay("€8-25 tickets (est.)", "INR")).toBe("₹722-₹2,255 tickets (est.)");
    expect(formatCostDisplay("Mid-range", "INR")).toBe("Mid-range");
  });
});
