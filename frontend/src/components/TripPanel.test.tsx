import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { TripView } from "../types";
import TripPanel from "./TripPanel";

// The paged destination guide fetches its own data; stub it so TripPanel tests
// stay focused on the panel's own behavior.
vi.mock("./DestinationGuide", () => ({
  default: ({
    focus,
    city,
    kind,
    query,
    onCities,
  }: {
    focus?: { name?: string } | null;
    city?: string;
    kind?: string;
    query?: string;
    onCities?: (cities: string[]) => void;
  }) => (
    <div
      data-testid="destination-guide"
      data-focus={focus?.name ?? ""}
      data-city={city ?? ""}
      data-kind={kind ?? ""}
      data-query={query ?? ""}
    >
      {onCities && (
        <button type="button" onClick={() => onCities(["Nice", "Paris"])}>
          report cities
        </button>
      )}
    </div>
  ),
}));

const view: TripView = {
  trip_id: "paris-trip",
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
  it("does not duplicate command-bar trip updates in Details", () => {
    render(
      <TripPanel
        view={{ ...view, alerts: ["Itinerary refreshed."] }}
        loading={false}
        navList={[{ kind: "attraction", name: "Eiffel Tower" }]}
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

    expect(screen.queryByText("Trip update")).not.toBeInTheDocument();
    expect(screen.queryByText("Itinerary refreshed.")).not.toBeInTheDocument();
  });

  it("surfaces contextual alternatives through the destination guide when focused", () => {
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

    expect(screen.getByRole("heading", { name: "Eiffel Tower" })).toBeInTheDocument();
    // The browse guide stays mounted (hidden) alongside the focused alternatives
    // guide, so one of the guides carries the focused place's name.
    const guides = screen.getAllByTestId("destination-guide");
    expect(guides.some((guide) => guide.getAttribute("data-focus") === "Eiffel Tower")).toBe(true);
    // The focused card shows only the focused place — alternatives (and their
    // reviews) live in the guide, not inline.
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

  it("offers the same add controls for a focused restaurant", () => {
    const onSelect = vi.fn();
    render(
      <TripPanel
        view={{
          ...view,
          focus: { kind: "restaurant", name: "Le Comptoir" },
          items: [{ ...view.items[0], kind: "restaurant", name: "Le Comptoir", selected: false, occurrences: [] }],
        }}
        loading={false}
        navList={[{ kind: "restaurant", name: "Le Comptoir" }]}
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

    expect(screen.getByRole("combobox", { name: "Choose day to add Le Comptoir" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "+ Add to trip" }));
    expect(onSelect).toHaveBeenCalledWith("restaurant", "Le Comptoir", undefined);
  });

  it("offers remove controls for a restaurant already in the trip", () => {
    render(
      <TripPanel
        view={{
          ...view,
          focus: { kind: "restaurant", name: "Le Comptoir" },
          items: [{
            ...view.items[0],
            kind: "restaurant",
            name: "Le Comptoir",
            selected: true,
            occurrences: [{ day: 2, stop: 1, time: "20:00" }],
          }],
        }}
        loading={false}
        navList={[{ kind: "restaurant", name: "Le Comptoir" }]}
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

    expect(screen.getByRole("button", { name: "Remove Le Comptoir from trip" })).toBeInTheDocument();
  });

  it("keeps the place filters visible while focused and re-scoping returns to browsing", () => {
    const onClearFocus = vi.fn();
    render(
      <TripPanel
        view={view}
        loading={false}
        navList={[{ kind: "attraction", name: "Eiffel Tower" }]}
        focusIndex={0}
        onFocus={vi.fn()}
        onClearFocus={onClearFocus}
        onStep={vi.fn()}
        onSelect={vi.fn()}
        onDeselect={vi.fn()}
        tripVersion={0}
        onSwitched={vi.fn()}
        hideSwitcher
      />,
    );

    expect(screen.getByLabelText("Search all trip places")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "All places" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Food" }));
    expect(onClearFocus).toHaveBeenCalled();
  });

  it("resets the guide scope when the trip changes", () => {
    const props = {
      loading: false,
      navList: [],
      focusIndex: -1,
      onFocus: vi.fn(),
      onClearFocus: vi.fn(),
      onStep: vi.fn(),
      onSelect: vi.fn(),
      onDeselect: vi.fn(),
      tripVersion: 0,
      onSwitched: vi.fn(),
      hideSwitcher: true,
    };
    const paris = { ...view, focus: null };
    const { rerender } = render(<TripPanel view={paris} {...props} />);

    fireEvent.click(screen.getByRole("button", { name: "report cities" }));
    fireEvent.click(screen.getByRole("button", { name: "Nice" }));
    fireEvent.click(screen.getByRole("button", { name: "Hotels" }));
    fireEvent.change(screen.getByLabelText("Search all trip places"), {
      target: { value: "museum" },
    });

    const scoped = screen.getByTestId("destination-guide");
    expect(scoped).toHaveAttribute("data-city", "Nice");
    expect(scoped).toHaveAttribute("data-kind", "hotel");
    expect(scoped).toHaveAttribute("data-query", "museum");

    rerender(
      <TripPanel
        view={{
          ...paris,
          trip_id: "rome-trip",
          title: "Rome",
          destination: "Rome",
          overview: { ...paris.overview!, destination: "Rome" },
        }}
        {...props}
      />,
    );

    const reset = screen.getByTestId("destination-guide");
    expect(reset).toHaveAttribute("data-city", "all");
    expect(reset).toHaveAttribute("data-kind", "highlights");
    expect(reset).toHaveAttribute("data-query", "");
    expect(screen.getByLabelText("Search all trip places")).toHaveValue("");
    expect(screen.queryByRole("button", { name: "Nice" })).not.toBeInTheDocument();
  });
});