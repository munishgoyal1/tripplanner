import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { StreamHandlers } from "../api";
import ChatPanel from "./ChatPanel";

const { streamChatMock } = vi.hoisted(() => ({ streamChatMock: vi.fn() }));

vi.mock("../api", () => ({
  streamChat: streamChatMock,
  signIn: vi.fn(),
  signOut: vi.fn(),
  getDisplayName: vi.fn(() => ""),
  isAnonymousUser: vi.fn(() => true),
  fetchAuthConfig: vi.fn().mockResolvedValue({ google: false }),
  fetchChatHistory: vi.fn().mockResolvedValue([]),
  startNewTrip: vi.fn().mockResolvedValue(undefined),
  syncAuth: vi.fn().mockResolvedValue({ authenticated: false }),
  loginWithGoogle: vi.fn(),
  logoutGoogle: vi.fn().mockResolvedValue(undefined),
  runPrivacyAction: vi.fn(),
  fetchGuestDataSummary: vi.fn(),
  migrateGuestData: vi.fn(),
  getUserId: vi.fn(() => "web-test"),
}));

describe("ChatPanel progress", () => {
  beforeEach(() => {
    streamChatMock.mockReset();
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: vi.fn(),
    });
  });

  it("shows immediate and friendly progress while a turn is running", async () => {
    let handlers: StreamHandlers | undefined;
    streamChatMock.mockImplementation((_message: string, nextHandlers: StreamHandlers) => {
      handlers = nextHandlers;
      return new Promise<void>(() => {});
    });
    render(<ChatPanel onTurnComplete={vi.fn()} />);

    const input = screen.getByPlaceholderText(/Plan a 5-day trip/);
    fireEvent.change(input, { target: { value: "Plan a Goa weekend" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(screen.getByText(/Thinking through your request/)).toBeInTheDocument();
    await waitFor(() => expect(handlers).toBeDefined());
    act(() => handlers?.onTool("search_places_with_reviews", "start"));

    expect(screen.getByText(/Checking places and reviews/)).toBeInTheDocument();
    expect(screen.queryByText(/search_places_with_reviews/)).not.toBeInTheDocument();
  });

  it("starts an approved planner review as a proposal-only assistant turn", async () => {
    streamChatMock.mockImplementation((_message: string, handlers: StreamHandlers) => {
      handlers.onDone("I can suggest three options.", "goa-trip");
      return Promise.resolve();
    });
    const prompt = "Review Day 3. Do not change it until I approve an option.";

    render(
      <ChatPanel
        onTurnComplete={vi.fn()}
        assistantRequest={{ id: 1, message: prompt, proposalOnly: true }}
      />,
    );

    await waitFor(() => expect(streamChatMock).toHaveBeenCalledWith(
      prompt,
      expect.any(Object),
      { proposalOnly: true },
    ));
    expect(screen.getByText(prompt)).toBeInTheDocument();
  });
});