import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Root from "./Root";

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
  });

  it("always shows the landing page at the public root", async () => {
    render(<Root />);

    expect(await screen.findByRole("heading", { name: "Public landing" })).toBeInTheDocument();
  });

  it("redirects the legacy welcome route to the public root", async () => {
    window.history.replaceState({}, "", "/welcome/");

    render(<Root />);

    expect(window.location.pathname).toBe("/");
    expect(await screen.findByRole("heading", { name: "Public landing" })).toBeInTheDocument();
  });

  it("opens the planner workspace when the landing page is skipped", async () => {
    render(<Root />);

    fireEvent.click(await screen.findByRole("button", { name: "Skip to the app" }));

    expect(window.location.pathname).toBe("/planner");
    expect(await screen.findByText("Workspace request: none")).toBeInTheDocument();
  });

  it("returns to the landing page with the browser back button", async () => {
    const historyLength = window.history.length;
    render(<Root />);

    fireEvent.click(await screen.findByRole("button", { name: "Skip to the app" }));
    expect(window.history.length).toBe(historyLength + 1);

    window.history.back();

    await waitFor(() => expect(window.location.pathname).toBe("/"));
    expect(await screen.findByRole("heading", { name: "Public landing" })).toBeInTheDocument();
  });

  it("carries a landing request into the planner workspace", async () => {
    render(<Root />);

    fireEvent.click(await screen.findByRole("button", { name: "Plan mine" }));

    expect(window.location.pathname).toBe("/planner");
    expect(await screen.findByText("Workspace request: Kyoto in April")).toBeInTheDocument();
  });
});

describe("the /planner route", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.history.replaceState({}, "", "/planner");
  });

  it("opens the workspace directly", async () => {
    render(<Root />);

    expect(await screen.findByText("Workspace request: none")).toBeInTheDocument();
  });
});