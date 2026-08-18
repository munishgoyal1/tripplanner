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
    fireEvent.click(screen.getByRole("button", { name: /Increase Days/ }));
    fireEvent.click(screen.getByRole("button", { name: /Use these and continue/ }));

    expect(onSubmit).toHaveBeenCalledWith({
      start_date: "2026-11-20",
      days: 5,
      origin: "Bengaluru",
    });
  });

  it("reports an unanswered origin instead of inventing one", () => {
    const answer = formatTripInputResponse(request, {
      start_date: "2026-11-12",
      days: 4,
      origin: "",
    });

    expect(answer).toContain("Start date: 2026-11-12");
    expect(answer).toContain("Travelling from: not specified");
  });
});
