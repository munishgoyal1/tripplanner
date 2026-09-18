import { useCallback, useMemo, useRef, useState } from "react";
import type { Itinerary, TripOverview, TripVerification } from "../../../src/types";
import type { ItineraryFilter } from "../../../src/lib/itineraryFilters";
import { itineraryStopMatchesFilters } from "../../../src/lib/itineraryFilters";
import { formatCostDisplay, useDisplayPreferences } from "../../../src/lib/displayPreferences";
import { itinerary as fixtureItinerary, overview as fixtureOverview, verification as gapsVerification } from "./fixture";
import { deriveDay, type DayFacts, type RowFacts } from "./model";

export type ChecksScenario = "gaps" | "contradiction";

export const contradictionVerification: TripVerification = {
  ...gapsVerification,
  verdict: "issues",
  counts: { total: 9, passed: 5, failed: 2, unverified: 2 },
  checks: [
    {
      code: "holiday-closure",
      rule: "Holiday closures",
      statement: "No visit is planned at a place that is closed that day.",
      status: "failed",
      severity: "contradiction",
      findings: ["Day 4: Bagore ki Haveli is closed on Maharishi Valmiki Jayanti (Sat 17 Oct)."],
      gaps: [],
    },
    ...gapsVerification.checks,
  ],
};

export interface FocusTarget {
  day: number;
  index: number;
  name: string;
}

function stats(itinerary: Itinerary) {
  const planned = itinerary.days.flatMap((day) => day.stops.filter((stop) => !["hotel", "airport", "origin"].includes(stop.kind)));
  return { days: itinerary.days.length, stops: planned.length, booked: planned.filter((stop) => stop.booked).length };
}

/**
 * Everything the itinerary pane can do, held once for the whole preview so
 * switching option keeps the same bookings, focus, filters and open states.
 * Planner-side effects (adding a day, rearranging, rechecking) are simulated:
 * the Lab judges the controls, not the agent behind them.
 */
export function usePlannerState() {
  const { currency, region } = useDisplayPreferences();
  const [itinerary, setItinerary] = useState<Itinerary>(fixtureItinerary);
  const [filters, setFilters] = useState<ItineraryFilter[]>([]);
  const [focus, setFocus] = useState<FocusTarget | null>(null);
  const [circuitDay, setCircuitDay] = useState<number | null>(null);
  const [allDays, setAllDays] = useState(false);
  const [removing, setRemoving] = useState<string | null>(null);
  const [lastAction, setLastAction] = useState("Click a stop, a day header, a booking status or a filter — every control is live.");
  const [rechecking, setRechecking] = useState(false);
  const [recheckOutcome, setRecheckOutcome] = useState("");
  const [scenario, setScenario] = useState<ChecksScenario>("gaps");
  const [checksExpanded, setChecksExpanded] = useState(false);
  const [repairing, setRepairing] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [checksOutcome, setChecksOutcome] = useState<string[]>([]);
  const [repaired, setRepaired] = useState(false);
  const bookingRef = useRef(itinerary);
  bookingRef.current = itinerary;

  const formatCost = useCallback((value: string) => formatCostDisplay(value, currency), [currency]);
  const days: DayFacts[] = useMemo(
    () => itinerary.days
      .filter((day) => filters.length === 0 || day.stops.some((stop, index) => itineraryStopMatchesFilters(stop, filters, day.stops, index)))
      .map((day) => deriveDay(day, filters, formatCost)),
    [itinerary, filters, formatCost],
  );

  const setBooked = useCallback((dayNumber: number, name: string, next: boolean): Itinerary => {
    const updated: Itinerary = {
      ...bookingRef.current,
      days: bookingRef.current.days.map((day) => day.day === dayNumber
        ? { ...day, stops: day.stops.map((stop) => stop.name === name ? { ...stop, booked: next } : stop) }
        : day),
    };
    const refreshed = { ...updated, stats: stats(updated) };
    bookingRef.current = refreshed;
    setItinerary(refreshed);
    setLastAction(`${name} marked ${next ? "confirmed" : "as needing booking"}.`);
    return refreshed;
  }, []);

  const verification = scenario === "contradiction" && !repaired ? contradictionVerification : gapsVerification;

  const focusAt = (day: number, index: number, name: string, message: string) => {
    setFocus({ day, index, name });
    setCircuitDay(null);
    setAllDays(false);
    setLastAction(message);
  };
  const removeAt = async (dayNumber: number, index: number, name: string) => {
    setRemoving(`${dayNumber}-${index}`);
    await new Promise((resolve) => window.setTimeout(resolve, 650));
    setItinerary((current) => {
      const updated = {
        ...current,
        days: current.days.map((day) => day.day === dayNumber ? { ...day, stops: day.stops.filter((_, position) => position !== index - 1) } : day),
      };
      const refreshed = { ...updated, stats: stats(updated) };
      bookingRef.current = refreshed;
      return refreshed;
    });
    setFocus((current) => current && current.day === dayNumber && current.index === index ? null : current);
    setRemoving(null);
    setLastAction(`${name} removed from Day ${dayNumber}.`);
  };

  return {
    focusAt,
    removeAt,
    itinerary,
    overview: fixtureOverview as TripOverview,
    verification,
    days,
    stats: stats(itinerary),
    currency,
    region,
    filters,
    toggleFilter: (filter: ItineraryFilter) => {
      setFilters((current) => current.includes(filter) ? current.filter((entry) => entry !== filter) : [...current, filter]);
      setLastAction(`Filter toggled: ${filter}. Map and itinerary show the same subset.`);
    },
    focus,
    isFocused: (day: number, row: RowFacts) => !!focus && focus.day === day && focus.index === row.index && !row.circuitReturn,
    focusStop: (day: number, row: RowFacts) => {
      if (!row.focusable) return;
      focusAt(day, row.index, row.stop.name, `${row.stop.name} focused: photos and reviews load in Details, pin highlighted on the map.`);
    },
    showOnMap: (day: number, row: RowFacts) => {
      focusAt(day, row.index, row.stop.name, row.routeFocusable ? `Map shows the complete route for ${row.stop.name}.` : `Map jumps to ${row.stop.name}.`);
    },
    circuitDay,
    allDays,
    showDay: (day: number) => {
      setCircuitDay(day);
      setAllDays(false);
      setLastAction(`Map shows the complete Day ${day} circuit.`);
    },
    showAllDays: () => {
      setAllDays(true);
      setCircuitDay(null);
      setLastAction("Map shows every itinerary day.");
    },
    openRoute: (day: number) => setLastAction(`Day ${day} route opens in Google Maps (new tab, suppressed in the Lab).`),
    toggleBooked: (day: number, row: RowFacts) => setBooked(day, row.stop.name, !row.stop.booked),
    setBooked,
    removing,
    removeStop: (dayNumber: number, row: RowFacts) => removeAt(dayNumber, row.index, row.stop.name),
    isRemoving: (dayNumber: number, row: RowFacts) => removing === `${dayNumber}-${row.index}`,
    adjustDays: (direction: "add" | "reduce", replan: boolean) => {
      setLastAction(`Planner asked to ${direction === "add" ? "add" : "remove"} a day · ${replan ? "replan the whole itinerary" : "keep existing days stable"}.`);
    },
    rechecking,
    recheckOutcome,
    runRecheck: async () => {
      setRechecking(true);
      setRecheckOutcome("");
      await new Promise((resolve) => window.setTimeout(resolve, 900));
      setRechecking(false);
      setRecheckOutcome("Rechecked 2; 1 price changed.");
      setLastAction("Prices rechecked against the providers.");
    },
    scenario,
    setScenario: (next: ChecksScenario) => {
      setScenario(next);
      setRepaired(false);
      setChecksOutcome([]);
    },
    checksExpanded,
    toggleChecks: () => setChecksExpanded((open) => !open),
    repairing,
    refreshing,
    checksOutcome,
    runRepair: async () => {
      setRepairing(true);
      await new Promise((resolve) => window.setTimeout(resolve, 900));
      setRepairing(false);
      setRepaired(true);
      setChecksOutcome(["Moved Bagore ki Haveli to Day 3 at 18:45."]);
      setLastAction("Planner rearranged the stops you had not chosen.");
    },
    runRefresh: async () => {
      setRefreshing(true);
      await new Promise((resolve) => window.setTimeout(resolve, 900));
      setRefreshing(false);
      setChecksOutcome(["Rechecked 14 places. Nothing changed."]);
      setLastAction("Place facts rechecked.");
    },
    note: setLastAction,
    lastAction,
  };
}

export type PlannerState = ReturnType<typeof usePlannerState>;
