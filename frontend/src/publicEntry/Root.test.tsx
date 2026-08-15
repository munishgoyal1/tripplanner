import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Root from "./Root";
import { markPublicEntrySkipped } from "./publicEntryState";

const { isAnonymousUserMock, fetchSavedTripsMock } = vi.hoisted(() => ({
  isAnonymousUserMock: vi.fn(),
  fetchSavedTripsMock: vi.fn(),
}));

vi.mock("../auth/authSession", () => ({
  isAnonymousUser: isAnonymousUserMock,
}));

vi.mock("../api", () => ({
  fetchSavedTrips: fetchSavedTripsMock,
}));

vi.mock("../components/AccountSettingsController", () => ({
  default: () => null,
}));

vi.mock("../App", () => ({
  default: ({ initialRequest }: { initialRequest?: string | null }) => (
    <div>Workspace request: {initialRequest ?? "none"}</div>
  ),
}));

vi.mock("./PublicEntry", () => ({
  default: ({ onPlan, onSkip }: { onPlan: (request: string) => void; onSkip: () => void }) => (
    <div>
      <h1>Public landing</h1>
      <button type="button" onClick={() => onPlan("Kyoto in April")}>Plan mine</button>
      <button type="button" onClick={onSkip}>Skip to the app</button>
    </div>
  ),
}));

describe("public entry routing", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.history.replaceState({}, "", "/");
    isAnonymousUserMock.mockReturnValue(false);
    fetchSavedTripsMock.mockReset();
    fetchSavedTripsMock.mockResolvedValue([]);
  });

  it("always shows the landing page at /welcome", () => {
    markPublicEntrySkipped();
    window.history.replaceState({}, "", "/welcome");

    render(<Root />);

    expect(screen.getByRole("heading", { name: "Public landing" })).toBeInTheDocument();
  });

  it("opens the root workspace when the landing page is skipped", () => {
    window.history.replaceState({}, "", "/welcome/");
    render(<Root />);

    fireEvent.click(screen.getByRole("button", { name: "Skip to the app" }));

    expect(window.location.pathname).toBe("/");
    expect(screen.getByText("Workspace request: none")).toBeInTheDocument();
  });

  it("returns to the landing page with the browser back button", async () => {
    window.history.replaceState({}, "", "/welcome");
    const historyLength = window.history.length;
    render(<Root />);

    fireEvent.click(screen.getByRole("button", { name: "Skip to the app" }));
    expect(window.history.length).toBe(historyLength + 1);

    window.history.back();

    await waitFor(() => expect(window.location.pathname).toBe("/welcome"));
    expect(screen.getByRole("heading", { name: "Public landing" })).toBeInTheDocument();
  });

  it("carries a landing request into the root workspace", () => {
    window.history.replaceState({}, "", "/welcome");
    render(<Root />);

    fireEvent.click(screen.getByRole("button", { name: "Plan mine" }));

    expect(window.location.pathname).toBe("/");
    expect(screen.getByText("Workspace request: Kyoto in April")).toBeInTheDocument();
  });
});

describe("the /planner route", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.history.replaceState({}, "", "/planner");
    isAnonymousUserMock.mockReturnValue(false);
    fetchSavedTripsMock.mockReset();
    fetchSavedTripsMock.mockResolvedValue([]);
  });

  it("opens the workspace for a signed-in visitor without asking the trip list", () => {
    render(<Root />);

    expect(screen.getByText("Workspace request: none")).toBeInTheDocument();
    expect(fetchSavedTripsMock).not.toHaveBeenCalled();
  });

  it("sends a guest with no trip to the landing page", async () => {
    isAnonymousUserMock.mockReturnValue(true);

    render(<Root />);

    expect(await screen.findByRole("heading", { name: "Public landing" })).toBeInTheDocument();
  });

  it("opens the workspace for a guest who already has a trip", async () => {
    isAnonymousUserMock.mockReturnValue(true);
    fetchSavedTripsMock.mockResolvedValue([{ trip_id: "t1" }]);

    render(<Root />);

    expect(await screen.findByText("Workspace request: none")).toBeInTheDocument();
  });

  it("opens the workspace when the trip lookup fails", async () => {
    isAnonymousUserMock.mockReturnValue(true);
    fetchSavedTripsMock.mockRejectedValue(new Error("offline"));

    render(<Root />);

    expect(await screen.findByText("Workspace request: none")).toBeInTheDocument();
  });

  it("stays on /planner when a guest starts from the landing page", async () => {
    isAnonymousUserMock.mockReturnValue(true);

    render(<Root />);
    fireEvent.click(await screen.findByRole("button", { name: "Plan mine" }));

    expect(window.location.pathname).toBe("/planner");
    expect(screen.getByText("Workspace request: Kyoto in April")).toBeInTheDocument();
  });
});