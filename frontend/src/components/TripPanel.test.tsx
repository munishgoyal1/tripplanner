import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { TripView } from "../types";
import TripPanel from "./TripPanel";

const view: TripView = {
  has_trip: true,
  title: "Paris",
  destination: "Paris",
  focus: { kind: "attraction", name: "Eiffel Tower" },
  is_fallback: false,
  empty_message: "",
  alerts: [],
  overview: {
    destination: "Paris",
    origin: "Delhi",
    departure_date: "2026-09-12",
    return_date: "2026-09-16",
    travelers: 2,
    status: "draft",
    notes: "",
    counts: { flights: 0, hotels: 1, activities: 1, days: 3 },
    total_cost: null,
    total_cost_display: "",
  },
  items: [{
    kind: "attraction",
    name: "Eiffel Tower",
    selected: true,
    rating: 4.7,
    review_count: 100,
    address: "Champ de Mars",
    summary: "",
    website: "",
    photos: [],
    reviews: [],
    occurrences: [
      { day: 1, stop: 2, time: "10:00" },
      { day: 3, stop: 1, time: "18:00" },
    ],
  }],
};

describe("TripPanel place removal", () => {
  it("removes a single-occurrence place from the prominent In trip control", async () => {
    const onDeselect = vi.fn().mockResolvedValue(true);
    render(
      <TripPanel
        view={{
          ...view,
          items: [{ ...view.items[0], photos: ["photo.jpg"], occurrences: [] }],
        }}
        loading={false}
        navList={[{ kind: "attraction", name: "Eiffel Tower" }]}
        focusIndex={0}
        onFocus={vi.fn()}
        onClearFocus={vi.fn()}
        onStep={vi.fn()}
        onSelect={vi.fn()}
        onDeselect={onDeselect}
        tripVersion={0}
        onSwitched={vi.fn()}
        hideSwitcher
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Remove Eiffel Tower from trip" }));

    await waitFor(() => expect(onDeselect).toHaveBeenCalledWith(
      "attraction",
      "Eiffel Tower",
      { all_occurrences: true },
    ));
  });

  it("prioritizes the focused occurrence and offers remove everywhere", async () => {
    const onDeselect = vi.fn().mockResolvedValue(true);
    render(
      <TripPanel
        view={view}
        loading={false}
        navList={[{ kind: "attraction", name: "Eiffel Tower" }]}
        focusIndex={0}
        onFocus={vi.fn()}
        onClearFocus={vi.fn()}
        onStep={vi.fn()}
        onSelect={vi.fn()}
        onDeselect={onDeselect}
        focusContext={{ day: 3, stop: 1 }}
        tripVersion={0}
        onSwitched={vi.fn()}
        hideSwitcher
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /In trip/ }));
    expect(screen.getByRole("menuitem", { name: /Remove this occurrence.*Day 3/ })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Remove everywhere" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("menuitem", { name: /Remove this occurrence.*Day 3/ }));
    await waitFor(() => expect(onDeselect).toHaveBeenCalledWith(
      "attraction",
      "Eiffel Tower",
      { day: 3, stop: 1, all_occurrences: false },
    ));
  });
});