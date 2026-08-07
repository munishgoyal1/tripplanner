import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchChatHistory, type StreamHandlers } from "../api";
import { saveTurnMeta } from "../turnMetadata";
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
    localStorage.clear();
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: vi.fn(),
    });
  });

  async function readyComposer(): Promise<HTMLTextAreaElement> {
    const composer = screen.getByPlaceholderText(/Plan a 5-day trip/);
    await waitFor(() => expect(composer).toBeEnabled());
    return composer as HTMLTextAreaElement;
  }

  it("shows immediate and friendly progress while a turn is running", async () => {
    let handlers: StreamHandlers | undefined;
    const onTurnStatus = vi.fn();
    streamChatMock.mockImplementation((_message: string, nextHandlers: StreamHandlers) => {
      handlers = nextHandlers;
      return new Promise<void>(() => {});
    });
    render(<ChatPanel onTurnComplete={vi.fn()} onTurnStatus={onTurnStatus} />);

    const input = await readyComposer();
    fireEvent.change(input, { target: { value: "Plan a Goa weekend" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(screen.getByText(/Thinking through your request/)).toBeInTheDocument();
    expect(screen.getByText(/Full itinerary builds usually take about 2–4 minutes/)).toBeInTheDocument();
    await waitFor(() => expect(handlers).toBeDefined());
    act(() => handlers?.onTool("search_places_with_reviews", "start"));

    expect(screen.getByText(/Checking places and reviews/)).toBeInTheDocument();
    expect(screen.queryByText(/search_places_with_reviews/)).not.toBeInTheDocument();
    await waitFor(() => expect(onTurnStatus).toHaveBeenLastCalledWith(expect.objectContaining({
      phase: "working",
      message: expect.stringContaining("Checking places and reviews"),
    })));
  });

  it("keeps progress visible while answer text streams", async () => {
    let handlers: StreamHandlers | undefined;
    streamChatMock.mockImplementation((_message: string, nextHandlers: StreamHandlers) => {
      handlers = nextHandlers;
      return new Promise<void>(() => {});
    });
    render(<ChatPanel onTurnComplete={vi.fn()} />);

    const input = await readyComposer();
    fireEvent.change(input, { target: { value: "Update Day 2" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(handlers).toBeDefined());
    act(() => {
      handlers?.onProgress?.("reviewing");
      handlers?.onToken("I found a better route.");
    });

    expect(await screen.findByText("I found a better route.")).toBeInTheDocument();
    expect(screen.getByText(/Reviewing the results/)).toBeInTheDocument();
  });

  it("stops an active response without presenting it as a failed request", async () => {
    const onTurnStatus = vi.fn();
    streamChatMock.mockImplementation(
      (_message: string, handlers: StreamHandlers, options: { signal?: AbortSignal }) => {
        handlers.onToken("Partial itinerary");
        return new Promise<void>((_resolve, reject) => {
          options.signal?.addEventListener("abort", () => {
            reject(new DOMException("Aborted", "AbortError"));
          });
        });
      },
    );
    render(<ChatPanel onTurnComplete={vi.fn()} onTurnStatus={onTurnStatus} />);

    const composer = await readyComposer();
    fireEvent.change(composer, {
      target: { value: "Plan Goa" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(streamChatMock).toHaveBeenCalledOnce());
    await screen.findByText("Partial itinerary");
    fireEvent.click(await screen.findByRole("button", { name: "Stop response" }));

    expect(await screen.findByText(/Response stopped\./)).toHaveTextContent("Partial itinerary");
    expect(screen.queryByRole("button", { name: "Retry request" })).not.toBeInTheDocument();
    expect(composer).toBeEnabled();
    expect(onTurnStatus).toHaveBeenLastCalledWith(null);
  });

  it("copies messages and loads prior user text for editing and resend", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    streamChatMock.mockImplementation((_message: string, handlers: StreamHandlers) => {
      handlers.onToken("A complete plan");
      handlers.onDone("A complete plan", "goa-trip");
      return Promise.resolve();
    });
    render(<ChatPanel onTurnComplete={vi.fn()} />);

    const composer = await readyComposer();
    fireEvent.change(composer, { target: { value: "Plan Goa" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await screen.findByText("A complete plan");
    await waitFor(() => {
      expect(screen.getAllByRole("button", { name: "Copy message" })).toHaveLength(3);
    });
    const copyButtons = screen.getAllByRole("button", { name: "Copy message" });
    fireEvent.click(copyButtons[copyButtons.length - 1]);
    expect(writeText).toHaveBeenCalledWith("A complete plan");

    fireEvent.click(screen.getByRole("button", { name: "Edit message" }));
    expect(composer).toHaveValue("Plan Goa");
    await waitFor(() => expect(composer).toHaveFocus());

    fireEvent.change(composer, { target: { value: "Plan Kerala instead" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(streamChatMock).toHaveBeenCalledTimes(2));
    expect(streamChatMock.mock.calls[1][0]).toBe("Plan Kerala instead");
    expect(streamChatMock.mock.calls[1][2].requestId).not.toBe(
      streamChatMock.mock.calls[0][2].requestId,
    );
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

    await readyComposer();

    await waitFor(() => expect(streamChatMock).toHaveBeenCalledWith(
      prompt,
      expect.any(Object),
      expect.objectContaining({ proposalOnly: true, requestId: expect.any(String) }),
    ));
    expect(screen.getByText(prompt)).toBeInTheDocument();
  });

  it("reuses the operation id when a failed request is retried", async () => {
    streamChatMock
      .mockImplementationOnce((_message: string, handlers: StreamHandlers) => {
        handlers.onError("Please retry.");
        return Promise.resolve();
      })
      .mockImplementationOnce((_message: string, handlers: StreamHandlers) => {
        handlers.onToken("Recovered");
        handlers.onDone("Recovered", "goa-trip");
        return Promise.resolve();
      });
    render(<ChatPanel onTurnComplete={vi.fn()} />);

    fireEvent.change(await readyComposer(), {
      target: { value: "Plan Goa" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByRole("button", { name: "Retry request" });
    fireEvent.click(screen.getByRole("button", { name: "Retry request" }));

    await waitFor(() => expect(streamChatMock).toHaveBeenCalledTimes(2));
    expect(streamChatMock.mock.calls[1][2].requestId).toBe(
      streamChatMock.mock.calls[0][2].requestId,
    );
  });

  it("recovers an interrupted stream with the same operation id", async () => {
    streamChatMock
      .mockRejectedValueOnce(new Error("Connection lost."))
      .mockImplementationOnce((_message: string, handlers: StreamHandlers) => {
        handlers.onToken("Recovered after reconnecting.");
        handlers.onDone("Recovered after reconnecting.", "goa-trip");
        return Promise.resolve();
      });
    render(<ChatPanel onTurnComplete={vi.fn()} />);

    fireEvent.change(await readyComposer(), { target: { value: "Plan Goa" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText("Warning: Connection lost.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry request" }));

    expect(await screen.findByText("Recovered after reconnecting.")).toBeInTheDocument();
    expect(streamChatMock.mock.calls[1][2].requestId).toBe(
      streamChatMock.mock.calls[0][2].requestId,
    );
  });

  it("aborts an active stream and clears workspace status when unmounted", async () => {
    const onTurnStatus = vi.fn();
    let streamSignal: AbortSignal | undefined;
    streamChatMock.mockImplementation(
      (_message: string, _handlers: StreamHandlers, options: { signal?: AbortSignal }) => {
        streamSignal = options.signal;
        return new Promise<void>((_resolve, reject) => {
          options.signal?.addEventListener("abort", () => {
            reject(new DOMException("Aborted", "AbortError"));
          });
        });
      },
    );
    const { unmount } = render(
      <ChatPanel onTurnComplete={vi.fn()} onTurnStatus={onTurnStatus} />,
    );

    fireEvent.change(await readyComposer(), { target: { value: "Plan Goa" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(streamSignal).toBeDefined());

    unmount();

    expect(streamSignal?.aborted).toBe(true);
    expect(onTurnStatus).toHaveBeenLastCalledWith(null);
  });

  it("renders and submits a validated trip input request", async () => {
    streamChatMock
      .mockImplementationOnce((_message: string, handlers: StreamHandlers) => {
        handlers.onInputRequest?.({
          version: 1,
          request_id: "trip-input-1",
          question: "Anything different for this trip?",
          known_context: ["Boutique stays", "Vegetarian-friendly"],
          fields: [
            {
              id: "pace",
              label: "Pace",
              kind: "single",
              value: "balanced",
              options: [
                { value: "easy", label: "Easy" },
                { value: "balanced", label: "Balanced" },
              ],
            },
            { id: "travelers", label: "Travelers", kind: "number", value: 2, min: 1, max: 6 },
          ],
          submit_label: "Build my trip",
          allow_skip: true,
        });
        handlers.onDone("Choose what differs.");
        return Promise.resolve();
      })
      .mockImplementationOnce((_message: string, handlers: StreamHandlers) => {
        handlers.onDone("Building now.");
        return Promise.resolve();
      });
    render(<ChatPanel onTurnComplete={vi.fn()} />);

    fireEvent.change(await readyComposer(), { target: { value: "Plan Paris" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText("Anything different for this trip?")).toBeInTheDocument();
    expect(screen.getByText(/Boutique stays/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "Easy" }));
    fireEvent.click(screen.getByRole("button", { name: "Increase Travelers" }));
    fireEvent.change(screen.getByPlaceholderText(/Plan a 5-day trip/), {
      target: { value: "This draft must not survive the continuation" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Build my trip" }));

    await waitFor(() => expect(streamChatMock).toHaveBeenCalledTimes(2));
    expect(streamChatMock.mock.calls[1][0]).toBe("Use these choices for this trip:\n- Pace: Easy\n- Travelers: 3");
    expect(screen.getByPlaceholderText(/Plan a 5-day trip/)).toHaveValue("");
    expect(screen.queryByText("Anything different for this trip?")).not.toBeInTheDocument();
  });

  it("settles the live counter into a duration badge the answered turn keeps", async () => {
    let handlers: StreamHandlers | undefined;
    streamChatMock.mockImplementation((_message: string, nextHandlers: StreamHandlers) => {
      handlers = nextHandlers;
      return new Promise<void>(() => {});
    });
    render(<ChatPanel onTurnComplete={vi.fn()} />);

    fireEvent.change(await readyComposer(), { target: { value: "Plan Goa" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(handlers).toBeDefined());
    expect(screen.queryByTitle(/This reply took/)).not.toBeInTheDocument();

    act(() => {
      handlers?.onToken("Here is the plan.");
      handlers?.onDone("Here is the plan.");
    });

    const badge = await screen.findByTitle(/This reply took/);
    expect(badge).toHaveTextContent(/^\d+s$/);
  });

  it("leaves the reading position alone and offers a jump to the newest reply", async () => {
    let handlers: StreamHandlers | undefined;
    streamChatMock.mockImplementation((_message: string, nextHandlers: StreamHandlers) => {
      handlers = nextHandlers;
      return new Promise<void>(() => {});
    });
    render(<ChatPanel onTurnComplete={vi.fn()} />);
    const transcript = screen.getByTestId("chat-transcript");
    Object.defineProperty(transcript, "scrollHeight", { configurable: true, value: 2000 });
    Object.defineProperty(transcript, "clientHeight", { configurable: true, value: 500 });
    transcript.scrollTop = 0;
    fireEvent.scroll(transcript);

    fireEvent.change(await readyComposer(), { target: { value: "Plan Goa" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(handlers).toBeDefined());
    act(() => {
      handlers?.onToken("Here is the plan.");
      handlers?.onDone("Here is the plan.");
    });

    const jump = await screen.findByRole("button", { name: /Jump to latest/ });
    const scrolls = vi.mocked(HTMLElement.prototype.scrollIntoView);
    scrolls.mockClear();
    fireEvent.click(jump);

    expect(scrolls).toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByRole("button", { name: /Jump to latest/ })).not.toBeInTheDocument());
  });

  it("lists the stops a reply changed and moves the workspace to one", async () => {
    const onEffectSelect = vi.fn();
    streamChatMock.mockImplementation((_message: string, handlers: StreamHandlers) => {
      handlers.onToken("Rebuilt day 3.");
      handlers.onDone("Rebuilt day 3.");
      return Promise.resolve();
    });
    const { rerender } = render(
      <ChatPanel onTurnComplete={vi.fn()} onEffectSelect={onEffectSelect} turnEffects={null} />,
    );

    fireEvent.change(await readyComposer(), { target: { value: "Rebuild day 3" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("Rebuilt day 3.");

    rerender(
      <ChatPanel
        onTurnComplete={vi.fn()}
        onEffectSelect={onEffectSelect}
        turnEffects={{
          token: 1,
          effects: [
            { kind: "attraction", name: "Louvre", day: 3, stop: 1, change: "moved" },
            { kind: "attraction", name: "Orsay", day: 2, stop: 4, change: "removed" },
          ],
        }}
      />,
    );

    fireEvent.click(await screen.findByRole("button", { name: /Louvre/ }));
    expect(onEffectSelect).toHaveBeenCalledWith(
      expect.objectContaining({ name: "Louvre", day: 3, stop: 1 }),
    );
    expect(screen.queryByRole("button", { name: /Orsay/ })).not.toBeInTheDocument();
    expect(screen.getByText("Orsay")).toBeInTheDocument();
  });

  it("groups a session by when each turn happened", async () => {
    const yesterday = Date.now() - 86_400_000;
    vi.mocked(fetchChatHistory).mockResolvedValueOnce([
      { role: "user", text: "Plan Goa" },
      { role: "assistant", text: "Here is Goa." },
    ]);
    saveTurnMeta("__active__", [
      { role: "user", text: "Plan Goa", ts: yesterday },
      { role: "assistant", text: "Here is Goa.", ts: yesterday, seconds: 12 },
    ]);
    render(<ChatPanel onTurnComplete={vi.fn()} />);

    expect(await screen.findByText("Here is Goa.")).toBeInTheDocument();
    expect(screen.getByRole("separator", { name: "Yesterday" })).toBeInTheDocument();
    expect(screen.getByTitle(/This reply took/)).toHaveTextContent("12s");
  });

  it("stamps each turn with the time it happened", async () => {
    const at = new Date();
    at.setHours(9, 5, 0, 0);
    vi.mocked(fetchChatHistory).mockResolvedValueOnce([
      { role: "user", text: "Plan Goa" },
      { role: "assistant", text: "Here is Goa." },
    ]);
    saveTurnMeta("__active__", [
      { role: "user", text: "Plan Goa", ts: at.getTime() },
      { role: "assistant", text: "Here is Goa.", ts: at.getTime(), seconds: 12 },
    ]);
    render(<ChatPanel onTurnComplete={vi.fn()} />);

    await screen.findByText("Here is Goa.");
    const clock = at.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
    expect(screen.getAllByText(clock)).toHaveLength(2);
    expect(screen.getByText("Assistant")).toBeInTheDocument();
  });

  it("keeps the docked assistant on one row and expands only when asked", async () => {
    const onChangeLayout = vi.fn();
    const onHide = vi.fn();
    const { rerender } = render(
      <ChatPanel onTurnComplete={vi.fn()} layout="bar" onChangeLayout={onChangeLayout} onHide={onHide} />,
    );

    expect(await readyComposer()).toHaveAttribute("rows", "1");
    expect(screen.queryByTestId("chat-transcript")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Conversation/ }));
    expect(onChangeLayout).toHaveBeenCalledWith("sheet");

    rerender(
      <ChatPanel onTurnComplete={vi.fn()} layout="sheet" onChangeLayout={onChangeLayout} onHide={onHide} />,
    );
    expect(screen.getByTestId("chat-transcript")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Maximize/ }));
    expect(onChangeLayout).toHaveBeenCalledWith("full");
    fireEvent.click(screen.getByRole("button", { name: /Minimize/ }));
    expect(onChangeLayout).toHaveBeenCalledWith("bar");
    fireEvent.click(screen.getByRole("button", { name: "Hide Chat" }));
    expect(onHide).toHaveBeenCalled();
  });

  it("opens the docked assistant when the agent asks a question", async () => {
    const onChangeLayout = vi.fn();
    streamChatMock.mockImplementation((_message: string, handlers: StreamHandlers) => {
      handlers.onInputRequest?.({
        version: 1,
        request_id: "trip-input-2",
        question: "Anything different for this trip?",
        known_context: [],
        fields: [{ id: "travelers", label: "Travelers", kind: "number", value: 2, min: 1, max: 6 }],
        submit_label: "Build my trip",
        allow_skip: true,
      });
      handlers.onDone("Choose what differs.");
      return Promise.resolve();
    });
    render(<ChatPanel onTurnComplete={vi.fn()} layout="bar" onChangeLayout={onChangeLayout} />);

    fireEvent.change(await readyComposer(), { target: { value: "Plan Paris" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(onChangeLayout).toHaveBeenCalledWith("sheet"));
  });
});
