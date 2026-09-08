import { describe, expect, it } from "vitest";

describe("family details capture contract", () => {
  it("keeps shared, individual, passive, and trip-only capture concepts distinct", () => {
    const options = ["roster", "questions", "defaults", "chat", "matrix"];
    const provenance = ["explicitly_saved", "suggested_from_chat", "trip_only", "not_now"];

    expect(options).toHaveLength(5);
    expect(new Set(options).size).toBe(5);
    expect(provenance).toContain("suggested_from_chat");
    expect(provenance).toContain("trip_only");
  });
});
