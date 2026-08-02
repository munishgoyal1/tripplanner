import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AnalyticsConsent, { AnalyticsPreferences } from "./AnalyticsConsent";

describe("AnalyticsConsent", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      enabled: false,
      measurement_id: "",
    }), { status: 200, headers: { "Content-Type": "application/json" } })));
  });

  it("initializes silently and saves consent within an inline preference view", async () => {
    const onBack = vi.fn();
    render(<><AnalyticsConsent /><AnalyticsPreferences onBack={onBack} /></>);
    await waitFor(() => expect(fetch).toHaveBeenCalled());

    expect(screen.getByRole("region", { name: "Analytics preferences" })).toBeInTheDocument();
    expect(screen.getByText(/not configured in this environment/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Allow analytics" }));

    expect(localStorage.getItem("tripplanner_analytics_consent")).toBe("granted");
    expect(screen.getByText("Current choice: Allowed")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Back to settings" }));
    expect(onBack).toHaveBeenCalledOnce();
  });

  it("shows the bottom prompt only for first-run consent when analytics is configured", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      enabled: true,
      measurement_id: "G-TEST",
    }), { status: 200, headers: { "Content-Type": "application/json" } })));

    render(<AnalyticsConsent />);

    expect(await screen.findByRole("complementary", { name: "Analytics consent" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "No thanks" }));
    expect(localStorage.getItem("tripplanner_analytics_consent")).toBe("denied");
    expect(screen.queryByRole("complementary", { name: "Analytics consent" })).not.toBeInTheDocument();
  });
});