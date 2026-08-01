import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AnalyticsConsent from "./AnalyticsConsent";

describe("AnalyticsConsent", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      enabled: false,
      measurement_id: "",
    }), { status: 200, headers: { "Content-Type": "application/json" } })));
  });

  it("opens preferences and saves consent when analytics is not configured", async () => {
    render(<AnalyticsConsent />);
    await waitFor(() => expect(fetch).toHaveBeenCalled());

    expect(screen.queryByRole("complementary", { name: "Analytics preferences" })).not.toBeInTheDocument();
    act(() => window.dispatchEvent(new Event("tripplanner:analytics-settings")));

    expect(screen.getByRole("complementary", { name: "Analytics preferences" })).toBeInTheDocument();
    expect(screen.getByText(/not configured in this environment/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Allow analytics" }));

    expect(localStorage.getItem("tripplanner_analytics_consent")).toBe("granted");
    expect(screen.queryByRole("complementary", { name: "Analytics preferences" })).not.toBeInTheDocument();
  });
});