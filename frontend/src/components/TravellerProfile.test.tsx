import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Preferences } from "../api";
import TravellerProfile from "./TravellerProfile";

const preferences: Preferences = {
  display_name: "Munish Goyal",
  home_city: "Bengaluru",
  home_country: "India",
  trip_style: "balanced",
  budget_level: "moderate",
  flight_class: "economy",
  prefer_direct_flights: true,
  hotel_star_rating_min: 3,
  dietary: [],
  interests: [],
  dislikes: [],
  about_me: "",
  profile_summary: "",
  planning_mode: "interactive",
};

const mocks = vi.hoisted(() => ({
  fetchPreferences: vi.fn(() => Promise.resolve(preferences)),
  savePreferences: vi.fn(() => Promise.resolve({ ok: true, about_me_extracted: [] })),
  fetchProfileSuggestions: vi.fn(() => Promise.resolve([])),
  resolveProfileSuggestion: vi.fn(() => Promise.resolve([])),
}));

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return { ...actual, ...mocks };
});

describe("TravellerProfile", () => {
  beforeEach(() => {
    mocks.savePreferences.mockClear();
  });

  it("requires confirmation before remembering a family detail from chat", async () => {
    render(<TravellerProfile />);

    expect(await screen.findByRole("region", { name: "Suggested family detail" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Remember/ }));

    await waitFor(() => expect(screen.getByText(/Remembered for future trips/)).toBeInTheDocument());
    expect(mocks.savePreferences).toHaveBeenCalledWith({ about_me: "Rhea prefers relaxed mornings." });
  });

  it("keeps a dismissed suggestion out of the durable profile", async () => {
    render(<TravellerProfile />);

    expect(await screen.findByRole("region", { name: "Suggested family detail" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Not now" }));

    expect(screen.getByText(/Nothing saved/)).toBeInTheDocument();
    expect(mocks.savePreferences).not.toHaveBeenCalled();
  });
});
