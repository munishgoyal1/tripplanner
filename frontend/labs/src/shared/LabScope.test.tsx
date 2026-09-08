import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LabScope } from "./LabScope";
import { LAB_SELECTION_SAVED_EVENT } from "./useLabSelections";

afterEach(() => vi.unstubAllGlobals());

describe("LabScope", () => {
  it("shows authoritative status in the top area and updates after a save", async () => {
    localStorage.setItem("tripplanner_lab_change_markers", "hidden");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      "multi-city-itinerary": {
        disposition: "ready",
        stateChangedAt: "2026-08-02T10:18:59.727Z",
      },
    }), { status: 200 })));

    render(<LabScope labId="multi-city-itinerary" />);

    expect(await screen.findByText("In progress")).not.toBeNull();
    expect(screen.getByText("Since 2 Aug 2026")).not.toBeNull();

    window.dispatchEvent(new CustomEvent(LAB_SELECTION_SAVED_EVENT, {
      detail: {
        labId: "multi-city-itinerary",
        selection: {
          disposition: "implemented-review",
          stateChangedAt: "2026-08-03T00:00:00.000Z",
        },
      },
    }));

    expect(await screen.findByText("Implemented - To be reviewed")).not.toBeNull();
    expect(screen.getByText("Since 3 Aug 2026")).not.toBeNull();
  });

  it("does not infer a lifecycle state when machine status is unavailable", async () => {
    localStorage.setItem("tripplanner_lab_change_markers", "hidden");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));

    render(<LabScope labId="multi-city-itinerary" />);

    expect(await screen.findByText("Status unavailable")).not.toBeNull();
    expect(screen.queryByText("Implemented - To be reviewed")).toBeNull();
  });

  it("keeps a saved status when an older initial request finishes afterward", async () => {
    localStorage.setItem("tripplanner_lab_change_markers", "hidden");
    let resolveFetch!: (response: Response) => void;
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise<Response>((resolve) => {
      resolveFetch = resolve;
    })));

    render(<LabScope labId="multi-city-itinerary" />);
    window.dispatchEvent(new CustomEvent(LAB_SELECTION_SAVED_EVENT, {
      detail: {
        labId: "multi-city-itinerary",
        selection: {
          disposition: "completed",
          stateChangedAt: "2026-08-04T00:00:00.000Z",
        },
      },
    }));

    expect(await screen.findByText("Completed")).not.toBeNull();
    resolveFetch(new Response(JSON.stringify({
      "multi-city-itinerary": {
        disposition: "ready",
        stateChangedAt: "2026-08-02T10:18:59.727Z",
      },
    }), { status: 200 }));

    expect(await screen.findByText("Since 4 Aug 2026")).not.toBeNull();
    expect(screen.queryByText("In progress")).toBeNull();
  });
});
