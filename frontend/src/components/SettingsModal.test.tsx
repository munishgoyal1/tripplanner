import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Preferences } from "../api";
import SettingsModal from "./SettingsModal";

const preferences: Preferences = {
  display_name: "Munish Goyal",
  home_city: "Bengaluru",
  home_country: "India",
  display_region: "IN",
  display_language: "en",
  display_currency: "USD",
  trip_style: "balanced",
  budget_level: "moderate",
  flight_class: "economy",
  prefer_direct_flights: true,
  hotel_star_rating_min: 3,
  dietary: ["local favourites"],
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
}));

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return { ...actual, ...mocks, regenerateProfileSummary: vi.fn() };
});

describe("SettingsModal preference shelf", () => {
  beforeEach(() => {
    mocks.savePreferences.mockClear();
  });

  it("shows visible choices and saves the selected internal preference value", async () => {
    render(<SettingsModal section="travel" embedded onClose={vi.fn()} />);

    expect(await screen.findByRole("heading", { name: "A better trip starts here" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Trip rhythm" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Planning style" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Where you stay" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Food and flavour" })).toBeInTheDocument();
    expect(screen.getByText("trip_pace: balanced")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "+ See it all" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(mocks.savePreferences).toHaveBeenCalledWith({ trip_style: "packed" }));
  });

  it("keeps an unrelated food tag selected when adding another (union)", async () => {
    render(<SettingsModal section="travel" embedded onClose={vi.fn()} />);

    await screen.findByRole("heading", { name: "Food and flavour" });
    fireEvent.click(screen.getByRole("button", { name: "+ Vegetarian" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(mocks.savePreferences).toHaveBeenCalledWith({ dietary: ["local favourites", "vegetarian"] }),
    );
  });

  it("replaces a mutually exclusive diet tag instead of combining it (intersection)", async () => {
    render(<SettingsModal section="travel" embedded onClose={vi.fn()} />);

    await screen.findByRole("heading", { name: "Food and flavour" });
    fireEvent.click(screen.getByRole("button", { name: "+ Vegetarian" }));
    fireEvent.click(screen.getByRole("button", { name: "+ Vegan" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(mocks.savePreferences).toHaveBeenCalledWith({ dietary: ["local favourites", "vegan"] }),
    );
  });
});