import { describe, expect, it } from "vitest";
import { formatDistance, formatDisplayAmount, formatTemperature } from "./displayPreferences";

describe("display preferences formatting", () => {
  it("formats prices in the selected presentation currency", () => {
    expect(formatDisplayAmount(100, "USD", "INR")).toBe("₹8,300");
    expect(formatDisplayAmount(100, "€", "USD")).toBe("$109");
  });

  it("uses regional distance and temperature conventions", () => {
    expect(formatDistance(10, "United States")).toBe("6.2 mi");
    expect(formatTemperature(20, "United States")).toBe("68°F");
    expect(formatDistance(10, "India")).toBe("10 km");
  });
});
