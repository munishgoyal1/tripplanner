import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
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
  it("keeps every option browsable after loading an implemented choice", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      "multi-city-itinerary": {
        selection: "a",
        comment: "Implemented in production",
        disposition: "implemented-review",
      },
    }), { status: 200 })));

    render(<Harness />);

    expect(await screen.findByText("What was implemented")).not.toBeNull();
    expect(screen.getByText("A · Implemented", { selector: "p" })).not.toBeNull();
    expect(screen.getByText("Implemented in production", { selector: "p.whitespace-pre-wrap" })).not.toBeNull();
    expect(screen.getByText("Version 1: A · Implemented - Implemented in production")).not.toBeNull();

    fireEvent.click(screen.getByRole("radio", { name: "B · Alternative" }));

    await waitFor(() => expect((screen.getByRole("radio", { name: "B · Alternative" }) as HTMLInputElement).checked).toBe(true));
    expect(screen.getByText("A · Implemented", { selector: "p" })).not.toBeNull();
  });

  it("starts a re-implementation handoff without losing the completed direction", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        "multi-city-itinerary": {
          selection: "a",
          selectionLabel: "A · Implemented",
          comment: "Original implementation",
          disposition: "completed",
        },
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        selection: "b",
        selectionLabel: "B · Alternative",
        comment: "Apply this revision",
        disposition: "ready",
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
    fireEvent.change(screen.getByLabelText("Handoff notes"), {
      target: { value: "Apply this revision" },
    });
    const saveButton = screen.getByRole("button", { name: "Save for re-implementation" });
    expect(saveButton.className).toContain("bg-teal-700");
    fireEvent.click(saveButton);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toMatchObject({
      selection: "b",
      selectionLabel: "B · Alternative",
      comment: "Apply this revision",
      disposition: "ready",
    });
    expect(screen.getByText("A · Implemented", { selector: "p" })).not.toBeNull();
    expect(screen.getByText("Original implementation", { selector: "p.whitespace-pre-wrap" })).not.toBeNull();
    expect(await screen.findByText("Re-implementation handoff saved")).not.toBeNull();
    expect(screen.getByText("B · Alternative and its exact notes are ready to implement as Version 2.")).not.toBeNull();
    expect((screen.getByRole("button", { name: "Re-implementation saved" }) as HTMLButtonElement).disabled).toBe(true);
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

    expect(await screen.findByText("Version 1")).not.toBeNull();
    expect(screen.getByText("Version 2")).not.toBeNull();
    expect(screen.getByText((_, element) => element?.textContent === "First exact note\nKeep this line.", { selector: "p.whitespace-pre-wrap" })).not.toBeNull();
    expect(screen.getByText("Second exact note", { selector: "p.whitespace-pre-wrap" })).not.toBeNull();
    expect(screen.getByText("Version 1: A · Implemented - First exact note Keep this line. | Version 2: B · Alternative - Second exact note")).not.toBeNull();
  });

  it("stops waiting and keeps the draft when a save does not respond", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        "multi-city-itinerary": {
          selection: "a",
          selectionLabel: "A · Implemented",
          comment: "Original implementation",
          disposition: "completed",
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
    fireEvent.click(screen.getByRole("button", { name: "Save for re-implementation" }));
    expect(screen.getByText("Saving handoff…")).not.toBeNull();
    await act(async () => vi.advanceTimersByTimeAsync(10_000));

    expect(screen.getByText("Save did not complete. The draft is kept in this browser; restart the Labs server, then retry.")).not.toBeNull();
    vi.useRealTimers();
  });
});