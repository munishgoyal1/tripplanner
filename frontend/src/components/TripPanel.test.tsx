import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
  available_days: [1, 2, 3],
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
  it("keeps alternatives compact when one place is focused", () => {
    render(
      <TripPanel
        view={{
          ...view,
          items: [
            view.items[0],
            {
              ...view.items[0],
              name: "Louvre Museum",
              reviews: [{ rating: 5, text: "Alternative review", author: "A traveler" }],
            },
          ],
        }}
        loading={false}
        navList={[
          { kind: "attraction", name: "Eiffel Tower" },
          { kind: "attraction", name: "Louvre Museum" },
        ]}
        focusIndex={0}
        onFocus={vi.fn()}
        onClearFocus={vi.fn()}
        onStep={vi.fn()}
        onSelect={vi.fn()}
        onDeselect={vi.fn()}
        tripVersion={0}
        onSwitched={vi.fn()}
        hideSwitcher
      />,
    );

    expect(screen.getByText("More places")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Louvre Museum" })).toBeInTheDocument();
    expect(screen.queryByText("Alternative review")).not.toBeInTheDocument();
  });

  it("removes a single-occurrence place from the shared action control", async () => {
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

  it("moves a normal place to another day using its exact occurrence", async () => {
    const onSelect = vi.fn().mockResolvedValue(true);
    render(
      <TripPanel
        view={{
          ...view,
          items: [{
            ...view.items[0],
            occurrences: [{ day: 1, stop: 2, time: "10:00" }],
          }],
        }}
        loading={false}
        navList={[{ kind: "attraction", name: "Eiffel Tower" }]}
        focusIndex={0}
        onFocus={vi.fn()}
        onClearFocus={vi.fn()}
        onStep={vi.fn()}
        onSelect={onSelect}
        onDeselect={vi.fn()}
        tripVersion={0}
        onSwitched={vi.fn()}
        hideSwitcher
      />,
    );

    fireEvent.change(screen.getByRole("combobox", { name: "Change Eiffel Tower day" }), {
      target: { value: "2" },
    });

    await waitFor(() => expect(onSelect).toHaveBeenCalledWith(
      "attraction",
      "Eiffel Tower",
      { day: 2, source_day: 1, source_stop: 2 },
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
    const dayThreeSelect = screen.getByRole("combobox", {
      name: "Change Eiffel Tower visit on Day 3",
    });
    expect(within(dayThreeSelect).queryByRole("option", { name: "Day 1" })).not.toBeInTheDocument();
    expect(within(dayThreeSelect).getByRole("option", { name: "Day 2" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove Eiffel Tower from Day 3" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove everywhere" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Remove Eiffel Tower from Day 3" }));
    await waitFor(() => expect(onDeselect).toHaveBeenCalledWith(
      "attraction",
      "Eiffel Tower",
      { day: 3, stop: 1, all_occurrences: false },
    ));
  });
});