import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TripFeedbackControl from "./TripFeedbackControl";

const { submitTripFeedbackMock } = vi.hoisted(() => ({
  submitTripFeedbackMock: vi.fn(),
}));

vi.mock("../api", () => ({
  submitTripFeedback: submitTripFeedbackMock,
}));

describe("TripFeedbackControl", () => {
  beforeEach(() => {
    submitTripFeedbackMock.mockReset();
  });

  it("treats one thumb tap as a complete submission and remains available", async () => {
    submitTripFeedbackMock.mockResolvedValue({ count: 1, feedback_id: "fb_current", last_sentiment: "up" });
    render(<TripFeedbackControl initial={{ count: 0 }} />);

    fireEvent.click(screen.getByRole("button", { name: "This trip works" }));

    await waitFor(() => expect(submitTripFeedbackMock).toHaveBeenCalledWith({
      sentiment: "up",
      client: "web",
    }));
    expect(await screen.findByText("Sent")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "This trip misses" })).toBeEnabled();
  });

  it("submits optional stars and comment as a later append", async () => {
    submitTripFeedbackMock
      .mockResolvedValueOnce({ count: 1, feedback_id: "fb_current", last_sentiment: "up" })
      .mockResolvedValueOnce({ count: 1, feedback_id: "fb_current", last_rating: 4 });
    render(<TripFeedbackControl initial={{ count: 0 }} />);

    fireEvent.click(screen.getByRole("button", { name: "This trip works" }));
    await waitFor(() => expect(submitTripFeedbackMock).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "4 stars" }));
    fireEvent.change(screen.getByPlaceholderText("Optional: what would you change?"), {
      target: { value: "Day 3 is too long." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add feedback" }));

    await waitFor(() => expect(submitTripFeedbackMock).toHaveBeenCalledWith({
      feedback_id: "fb_current",
      rating: 4,
      comment: "Day 3 is too long.",
      client: "web",
    }));
    expect(screen.getByText("Sent")).toBeInTheDocument();
  });
});