import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import WorkspaceDayBar from "./WorkspaceDayBar";

const route = {
  distance_km: 4,
  duration_min: 20,
  mode: "Walk",
  distance_display: "4 km",
  duration_display: "20 min",
};

describe("WorkspaceDayBar", () => {
  it("keeps days and sequence in one compact shared row", () => {
    const onAllDays = vi.fn();
    const onDay = vi.fn();
    const onToggleSequence = vi.fn();
    render(
      <WorkspaceDayBar
        days={[
          { day: 1, label: "Day 1", color: "#bd542f", pin_ids: ["one"], route },
          { day: 2, label: "Day 2", color: "#668064", pin_ids: ["two"], route },
        ]}
        activeDay={2}
        sequenceOpen={false}
        onAllDays={onAllDays}
        onDay={onDay}
        onToggleSequence={onToggleSequence}
      />,
    );

    const row = screen.getByRole("navigation", { name: "Trip days and stop sequence" });
    expect(row).toHaveClass("h-8");
    fireEvent.click(screen.getByRole("button", { name: "All days" }));
    fireEvent.click(screen.getByRole("button", { name: "Day 1" }));
    fireEvent.click(screen.getByRole("button", { name: "Sequence" }));
    expect(onAllDays).toHaveBeenCalled();
    expect(onDay).toHaveBeenCalledWith(1);
    expect(onToggleSequence).toHaveBeenCalled();
  });
});
