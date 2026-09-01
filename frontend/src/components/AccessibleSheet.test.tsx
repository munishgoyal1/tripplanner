import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import AccessibleSheet from "./AccessibleSheet";

function SheetHarness() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>Open details</button>
      <AccessibleSheet
        open={open}
        label="Trip details"
        closeLabel="Close trip details"
        onClose={() => setOpen(false)}
      >
        <button type="button">Last action</button>
      </AccessibleSheet>
    </>
  );
}

describe("AccessibleSheet", () => {
  it("exposes dialog semantics only while open and restores its opener", () => {
    render(<SheetHarness />);
    const opener = screen.getByRole("button", { name: "Open details" });

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    opener.focus();
    fireEvent.click(opener);

    expect(screen.getByRole("dialog", { name: "Trip details" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close trip details" })).toHaveFocus();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it("keeps forward and backward keyboard focus inside the sheet", () => {
    render(<SheetHarness />);
    fireEvent.click(screen.getByRole("button", { name: "Open details" }));
    const close = screen.getByRole("button", { name: "Close trip details" });
    const last = screen.getByRole("button", { name: "Last action" });

    last.focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(close).toHaveFocus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(last).toHaveFocus();
  });

  it("closes from the modal backdrop", () => {
    const onClose = vi.fn();
    render(
      <AccessibleSheet
        open
        label="Trip details"
        closeLabel="Close trip details"
        onClose={onClose}
      >
        Details
      </AccessibleSheet>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Close Trip details" }));
    expect(onClose).toHaveBeenCalledOnce();
  });
});