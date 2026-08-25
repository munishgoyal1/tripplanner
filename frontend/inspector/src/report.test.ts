import { describe, expect, it } from "vitest";
import { openUrl, type TripRecord } from "./report";

describe("openUrl", () => {
  it("opens the exact audit record in the planner workspace", () => {
    const record: TripRecord = {
      id: "tripplanner-sbx-2-auto-validation:spiti_valley_2027-06-01_2027-06-08",
      provenance: "real",
      source: "tripplanner-sbx-2-auto-validation",
      destination: "Spiti Valley",
      days: 7,
      departure_date: "2027-06-01",
      return_date: "2027-06-08",
      user_id: "corpus-spiti-food-friends-7d",
      trip_id: "spiti_valley_2027-06-01_2027-06-08",
      openable: true,
      findings: 26,
    };

    const url = new URL(openUrl(record));

    expect(url.pathname).toBe("/planner");
    expect(url.searchParams.get("inspect")).toBe(record.user_id);
    expect(url.searchParams.get("trip")).toBe(record.trip_id);
    expect(url.searchParams.get("record")).toBe(record.id);
  });
});