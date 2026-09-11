import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ExportModal from "./ExportModal";

const { emailTripExportMock } = vi.hoisted(() => ({ emailTripExportMock: vi.fn() }));

vi.mock("../api", () => ({
  downloadTripPdf: vi.fn(),
  emailTripExport: emailTripExportMock,
  tripExportUrl: vi.fn(() => "/api/trip/export"),
}));

describe("ExportModal", () => {
  beforeEach(() => {
    emailTripExportMock.mockReset();
  });

  it("offers Standard and Trip Book with budget and photo checkboxes off", () => {
    render(<ExportModal onClose={vi.fn()} />);

    expect(screen.getByText("Standard")).toBeInTheDocument();
    expect(screen.getByText("Trip Book")).toBeInTheDocument();
    expect(screen.queryByText("Detailed+")).not.toBeInTheDocument();
    expect(screen.queryByText("Trip Card")).not.toBeInTheDocument();
    expect(screen.queryByText("Calendar+")).not.toBeInTheDocument();
    expect(screen.queryByText("Print / Save PDF")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Preview" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download PDF" })).toBeInTheDocument();
    const budgets = screen.getByRole("checkbox", { name: "Show budgets" }) as HTMLInputElement;
    const photos = screen.getByRole("checkbox", { name: "Include 1 photo per stop" }) as HTMLInputElement;
    expect(budgets.checked).toBe(false);
    expect(photos.checked).toBe(false);
  });

  it("reuses the operation id when an uncertain send is retried", async () => {
    emailTripExportMock
      .mockResolvedValueOnce({
        ok: false,
        error: "email_delivery_uncertain",
        message: "Delivery could not be confirmed.",
      })
      .mockResolvedValueOnce({ ok: true, message: "Sent." });
    render(<ExportModal onClose={vi.fn()} />);

    fireEvent.change(screen.getByPlaceholderText("name@example.com"), {
      target: { value: "traveler@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("Delivery could not be confirmed.");
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(emailTripExportMock).toHaveBeenCalledTimes(2));
    expect(emailTripExportMock.mock.calls[1][2]).toBe(
      emailTripExportMock.mock.calls[0][2],
    );
  });
});
