import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DecisionCapture } from "./DecisionCapture";

const options = [
  { id: "a", label: "A · Implemented" },
  { id: "b", label: "B · Alternative" },
];

function Harness() {
  const [active, setActive] = useState("a");
  return (
    <DecisionCapture
      labId="multi-city-itinerary"
      labTitle="Transition-day itinerary design"
      options={options}
      activeOption={active}
      onChoose={(option) => setActive(option)}
    />
  );
}

describe("DecisionCapture", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.unstubAllGlobals();
  });

  it("keeps every option browsable after loading an implemented choice", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      "multi-city-itinerary": {
        selection: "a",
        comment: "Implemented in production",
        disposition: "implemented-review",
        implementations: [{
          version: 1,
          selection: "a",
          selectionLabel: "A · Implemented",
          comment: "Implemented in production",
          recordedAt: "2026-08-01T00:00:00.000Z",
        }],
      },
    }), { status: 200 })));

    render(<Harness />);

    expect(await screen.findByText("What was implemented")).not.toBeNull();
    expect(screen.getByText("Saved handoff history")).not.toBeNull();
    expect(screen.getByText("Handoff version 1")).not.toBeNull();
    expect(screen.getAllByText("A · Implemented", { selector: "p" }).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Implemented in production", { selector: "p.whitespace-pre-wrap" }).length).toBeGreaterThan(0);
    expect(screen.getByText("Version 1: A · Implemented - Implemented in production")).not.toBeNull();

    fireEvent.click(screen.getByRole("radio", { name: "B · Alternative" }));

    await waitFor(() => expect((screen.getByRole("radio", { name: "B · Alternative" }) as HTMLInputElement).checked).toBe(true));
    expect(screen.getAllByText("A · Implemented", { selector: "p" }).length).toBeGreaterThan(0);
  });

  it("starts a re-implementation handoff without losing the completed direction", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        "multi-city-itinerary": {
          selection: "a",
          selectionLabel: "A · Implemented",
          comment: "Original implementation",
          disposition: "completed",
          implementation: {
            selection: "a",
            selectionLabel: "A · Implemented",
            comment: "Original implementation",
            recordedAt: "2026-08-01T00:00:00.000Z",
          },
        },
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        selection: "b",
        selectionLabel: "B · Alternative",
        comment: "Apply this revision",
        disposition: "ready",
        handoffs: [
          {
            version: 1,
            selection: "a",
            selectionLabel: "A · Implemented",
            comment: "Original implementation",
            disposition: "completed",
            recordedAt: "2026-08-01T00:00:00.000Z",
          },
          {
            version: 2,
            selection: "b",
            selectionLabel: "B · Alternative",
            comment: "Apply this revision",
            disposition: "ready",
            recordedAt: "2026-08-02T00:00:00.000Z",
          },
        ],
        implementations: [{
          version: 1,
          selection: "a",
          selectionLabel: "A · Implemented",
          comment: "Original implementation",
          recordedAt: "2026-08-02T00:00:00.000Z",
        }],
      }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    render(<Harness />);
    await screen.findByText("What was implemented");

    fireEvent.click(screen.getByRole("radio", { name: "B · Alternative" }));
    await waitFor(() => expect((screen.getByRole("radio", { name: "B · Alternative" }) as HTMLInputElement).checked).toBe(true));
    fireEvent.click(screen.getByRole("radio", { name: "In progress" }));
    fireEvent.change(screen.getByLabelText("Handoff notes"), {
      target: { value: "Apply this revision" },
    });
    const saveButton = screen.getByRole("button", { name: "Save handoff version" });
    fireEvent.click(saveButton);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toMatchObject({
      selection: "b",
      selectionLabel: "B · Alternative",
      comment: "Apply this revision",
      disposition: "ready",
    });
    expect(screen.getAllByText("A · Implemented", { selector: "p" }).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Original implementation", { selector: "p.whitespace-pre-wrap" }).length).toBeGreaterThan(0);
    expect(await screen.findByText("Re-implementation handoff saved")).not.toBeNull();
    expect(screen.getByText("Saved B · Alternative and its exact notes as handoff version 2.")).not.toBeNull();
    expect(screen.getByText("Handoff version 2")).not.toBeNull();
  });

  it("shows exact notes and a final summary for every implementation version", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      "multi-city-itinerary": {
        selection: "b",
        selectionLabel: "B · Alternative",
        comment: "Second exact note",
        disposition: "completed",
        implementations: [
          {
            version: 1,
            selection: "a",
            selectionLabel: "A · Implemented",
            comment: "First exact note\nKeep this line.",
            recordedAt: "2026-08-01T00:00:00.000Z",
          },
          {
            version: 2,
            selection: "b",
            selectionLabel: "B · Alternative",
            comment: "Second exact note",
            recordedAt: "2026-08-02T00:00:00.000Z",
          },
        ],
      },
    }), { status: 200 })));

    render(<Harness />);

    expect(await screen.findByText("Implementation 1")).not.toBeNull();
    expect(screen.getByText("Implementation 2")).not.toBeNull();
    expect(screen.getByText((_, element) => element?.textContent === "First exact note\nKeep this line.", { selector: "p.whitespace-pre-wrap" })).not.toBeNull();
    expect(screen.getAllByText("Second exact note", { selector: "p.whitespace-pre-wrap" }).length).toBeGreaterThan(0);
    expect(screen.getByText("Version 2: B · Alternative - Second exact note | Version 1: A · Implemented - First exact note Keep this line.")).not.toBeNull();
  });

  it("stops waiting and keeps the draft when a save does not respond", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        "multi-city-itinerary": {
          selection: "a",
          selectionLabel: "A · Implemented",
          comment: "Original implementation",
          disposition: "completed",
          implementation: {
            selection: "a",
            selectionLabel: "A · Implemented",
            comment: "Original implementation",
            recordedAt: "2026-08-01T00:00:00.000Z",
          },
        },
      }), { status: 200 }))
      .mockImplementationOnce((_input, init) => new Promise((_resolve, reject) => {
        (init?.signal as AbortSignal).addEventListener("abort", () => {
          reject(new DOMException("Save timed out", "AbortError"));
        });
      }));
    vi.stubGlobal("fetch", fetchMock);

    render(<Harness />);
    await screen.findByText("What was implemented");
    fireEvent.click(screen.getByRole("radio", { name: "B · Alternative" }));

    vi.useFakeTimers();
    fireEvent.click(screen.getByRole("button", { name: "Save handoff version" }));
    expect(screen.getByText("Saving handoff…")).not.toBeNull();
    await act(async () => vi.advanceTimersByTimeAsync(10_000));

    expect(screen.getByText("Save did not complete. The draft is kept in this browser; restart the Labs server, then retry.")).not.toBeNull();
    vi.useRealTimers();
  });

  it("keeps a newer browser draft when the machine record is older", async () => {
    localStorage.setItem("tripplanner-ux-lab-handoff-multi-city-itinerary", JSON.stringify({
      selection: "b",
      comment: "Unsaved offline revision",
      disposition: "parked",
      updatedAt: "2026-08-02T00:00:00.000Z",
    }));
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      "multi-city-itinerary": {
        selection: "a",
        selectionLabel: "A · Implemented",
        comment: "Older machine record",
        disposition: "ready",
        updatedAt: "2026-08-01T00:00:00.000Z",
      },
    }), { status: 200 })));

    render(<Harness />);

    await waitFor(() => expect((screen.getByRole("radio", { name: "B · Alternative" }) as HTMLInputElement).checked).toBe(true));
    expect((screen.getByLabelText("Handoff notes") as HTMLTextAreaElement).value).toBe("Unsaved offline revision");
    expect((screen.getByRole("radio", { name: "Parked" }) as HTMLInputElement).checked).toBe(true);
    expect(screen.getByText("Workspace save pending; browser draft kept")).not.toBeNull();
  });

  it("does not infer implementation evidence from state alone", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      "multi-city-itinerary": {
        selection: "a",
        selectionLabel: "A · Implemented",
        comment: "State-only legacy record",
        disposition: "implemented-review",
        updatedAt: "2026-08-01T00:00:00.000Z",
      },
    }), { status: 200 })));

    render(<Harness />);

    await screen.findByText("Saved handoff history");
    expect(screen.queryByText("What was implemented")).toBeNull();
  });

  it("allows any state without requiring owner-entered implementation evidence", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        "multi-city-itinerary": {
          selection: "a",
          selectionLabel: "A · Implemented",
          comment: "Reviewed choice",
          disposition: "ready",
          updatedAt: "2026-08-01T00:00:00.000Z",
        },
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        selection: "a",
        selectionLabel: "A · Implemented",
        comment: "Reviewed choice",
        disposition: "implemented-review",
        handoffs: [{
          version: 2,
          selection: "a",
          selectionLabel: "A · Implemented",
          comment: "Reviewed choice",
          disposition: "implemented-review",
          recordedAt: "2026-08-02T00:00:00.000Z",
        }],
        implementations: [],
      }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    render(<Harness />);
    await screen.findByText("Saved handoff history");
    fireEvent.click(screen.getByRole("radio", { name: "Implemented - Review" }));
    fireEvent.click(screen.getByRole("button", { name: "Save handoff version" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toMatchObject({
      disposition: "implemented-review",
    });
    expect(await screen.findByText("Handoff version 2")).not.toBeNull();
    expect(screen.queryByText("What was implemented")).toBeNull();
  });
});