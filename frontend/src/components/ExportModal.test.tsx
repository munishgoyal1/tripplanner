import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ExportModal from "./ExportModal";

const { emailTripExportMock } = vi.hoisted(() => ({ emailTripExportMock: vi.fn() }));

vi.mock("../api", () => ({
  downloadTripPdf: vi.fn(),
  emailTripExport: emailTripExportMock,
  tripExportUrl: vi.fn(() => "/api/trip/export"),
}));

describe("ExportModal email delivery", () => {
  beforeEach(() => {
    emailTripExportMock.mockReset();
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
