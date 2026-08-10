import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Root from "./Root";
import { markPublicEntrySkipped } from "./publicEntryState";

const { isAnonymousUserMock } = vi.hoisted(() => ({
  isAnonymousUserMock: vi.fn(),
}));

vi.mock("../auth/authSession", () => ({
  isAnonymousUser: isAnonymousUserMock,
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