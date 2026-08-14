import { describe, expect, it } from "vitest";

describe("profile preference contract", () => {
  it("keeps the user-facing pace choices mapped to stable planner values", () => {
    const paceValues = ["balanced", "see_it_all", "relaxed"];

    expect(paceValues).toEqual(["balanced", "see_it_all", "relaxed"]);
    expect(paceValues).not.toContain("See it all");
  });
});
