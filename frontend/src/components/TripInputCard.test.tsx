import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { TripInputRequest } from "../types";
import TripInputCard, { formatTripInputResponse } from "./TripInputCard";

const request: TripInputRequest = {
  version: 1,
  request_id: "kickoff-1",
  question: "Confirm a few details for Chennai",
  known_context: ["Vegetarian-friendly"],
  fields: [
    { id: "adults", label: "Adults (13+)", kind: "number", value: 1, min: 1, max: 12 },
    { id: "children", label: "Children (0-12)", kind: "number", value: 0, min: 0, max: 8 },
    {
      id: "party_type",
      label: "Trip group",
      kind: "single",
      value: "solo",
      options: [
        { value: "solo", label: "Solo" },
        { value: "family", label: "Family" },
      ],
    },
    { id: "start_date", label: "Start date", kind: "date", value: "2026-11-12" },
    { id: "days", label: "Days", kind: "number", value: 4, min: 2, max: 10 },
    { id: "origin", label: "Travelling from", kind: "text", value: "", placeholder: "Your city" },
  ],
  submit_label: "Use these and continue",
  allow_skip: true,
};

describe("TripInputCard trip facts", () => {
  it("collects a start date, trip length, and an origin city", () => {
    const onSubmit = vi.fn();
    render(<TripInputCard request={request} onSubmit={onSubmit} onSkip={vi.fn()} />);

    const startDate = screen.getByLabelText("Start date");
    const origin = screen.getByLabelText("Travelling from");
    expect(startDate).toHaveValue("2026-11-12");
    expect(origin).toHaveAttribute("placeholder", "Your city");

    fireEvent.change(startDate, { target: { value: "2026-11-20" } });
    fireEvent.change(origin, { target: { value: "Bengaluru" } });
    fireEvent.click(screen.getByRole("button", { name: /Increase Adults/ }));
    fireEvent.click(screen.getByRole("button", { name: /Increase Children/ }));
    fireEvent.click(screen.getByRole("radio", { name: "Family" }));
    fireEvent.click(screen.getByRole("button", { name: /Increase Days/ }));
    fireEvent.click(screen.getByRole("button", { name: /Use these and continue/ }));

    expect(onSubmit).toHaveBeenCalledWith({
      adults: 2,
      children: 1,
      party_type: "family",
      start_date: "2026-11-20",
      days: 5,
      origin: "Bengaluru",
    });
  });

  it("reports an unanswered origin instead of inventing one", () => {
    const answer = formatTripInputResponse(request, {
      adults: 1,
      children: 0,
      party_type: "solo",
      start_date: "2026-11-12",
      days: 4,
      origin: "",
    });

    expect(answer).toContain("Adults (13+): 1");
    expect(answer).toContain("Children (0-12): 0");
    expect(answer).toContain("Trip group: Solo");
    expect(answer).toContain("Start date: 2026-11-12");
    expect(answer).toContain("Travelling from: not specified");
  });

  it("requires a city unless the traveller arranges their own arrival", () => {
    const onSubmit = vi.fn();
    const travelRequest: TripInputRequest = {
      ...request,
      fields: [
        ...request.fields.slice(0, 3),
        {
          id: "travel_scope",
          label: "Journey to the destination",
          kind: "single",
          value: "round_trip",
          options: [
            { value: "round_trip", label: "Plan it from my city" },
            { value: "destination_only", label: "I'll arrange my own way there" },
          ],
        },
        request.fields[5],
      ],
      allow_skip: false,
    };
    render(<TripInputCard request={travelRequest} onSubmit={onSubmit} onSkip={vi.fn()} />);

    expect(screen.getByRole("button", { name: /Use these and continue/ })).toBeDisabled();
    fireEvent.click(screen.getByRole("radio", { name: "I'll arrange my own way there" }));
    expect(screen.queryByLabelText("Travelling from")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Use these and continue/ }));

    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      travel_scope: "destination_only",
      origin: "",
    }));
  });
});
