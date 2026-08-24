import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TripVerificationCard from "./TripVerificationCard";

const { fetchVerificationMock, refreshVerificationMock, repairTripMock } = vi.hoisted(() => ({
  fetchVerificationMock: vi.fn(),
  refreshVerificationMock: vi.fn(),
  repairTripMock: vi.fn(),
}));

vi.mock("../api", () => ({
  fetchVerification: fetchVerificationMock,
  refreshVerification: refreshVerificationMock,
  repairTrip: repairTripMock,
}));

const report = {
  verdict: "clear" as const,
  counts: { total: 1, passed: 1, failed: 0, unverified: 0 },
  checks: [
    {
      code: "I3",
      rule: "Opening hours",
      statement: "Stops fit their opening hours",
      status: "passed" as const,
      severity: "contradiction" as const,
      findings: [],
      gaps: [],
    },
  ],
  days: [],
  unverified_stops: [],
  freshness: null,
};

describe("TripVerificationCard", () => {
  beforeEach(() => {
    fetchVerificationMock.mockReset();
    refreshVerificationMock.mockReset();
    repairTripMock.mockReset();
    fetchVerificationMock.mockResolvedValue(report);
  });

  it("rechecks place facts only after an explicit action and reports changes", async () => {
    const onTripChanged = vi.fn();
    refreshVerificationMock.mockResolvedValue({
      ok: true,
      stale: false,
      message: "Rechecked the itinerary's place facts.",
      checked_at: "2026-08-24T10:00:00+00:00",
      checked: 1,
      total: 2,
      comparison_available: true,
      changes: [{ name: "Louvre Museum", days: [2], changed: ["opening hours"] }],
      failed: [{ name: "Cafe de Flore", days: [3] }],
      closure_watch: {
        status: "checked",
        advisories: [
          {
            name: "Louvre Museum",
            days: [2],
            title: "Louvre renovation notice",
            url: "https://www.louvre.fr/notice",
            snippet: "A gallery is closed for renovation.",
          },
        ],
      },
      verification: {
        ...report,
        freshness: {
          checked_at: "2026-08-24T10:00:00+00:00",
          checked: 1,
          total: 2,
          comparison_available: true,
          changes: [{ name: "Louvre Museum", days: [2], changed: ["opening hours"] }],
          failed: [{ name: "Cafe de Flore", days: [3] }],
          closure_watch: {
            status: "checked",
            advisories: [
              {
                name: "Louvre Museum",
                days: [2],
                title: "Louvre renovation notice",
                url: "https://www.louvre.fr/notice",
                snippet: "A gallery is closed for renovation.",
              },
            ],
          },
        },
      },
    });

    render(<TripVerificationCard onTripChanged={onTripChanged} />);

    expect(await screen.findByText("Everything we can check, checks out")).toBeInTheDocument();
    expect(refreshVerificationMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /Everything we can check/ }));
    fireEvent.click(screen.getByRole("button", { name: "Recheck place facts" }));

    await waitFor(() => expect(refreshVerificationMock).toHaveBeenCalledWith());
    expect(onTripChanged).toHaveBeenCalledOnce();
    expect(screen.getByText("Louvre Museum: opening hours changed.")).toBeInTheDocument();
    expect(screen.getByText("Cafe de Flore — kept the last known facts")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Louvre Museum — Louvre renovation notice" }))
      .toHaveAttribute("href", "https://www.louvre.fr/notice");
  });
});
