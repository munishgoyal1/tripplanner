import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TravelDocumentsVault from "./TravelDocumentsVault";
import * as api from "../api";

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof api>("../api");
  return {
    ...actual,
    fetchTravelDocuments: vi.fn(),
    fetchDocumentReadiness: vi.fn(),
    deleteTravelDocument: vi.fn(),
    clearTravelDocuments: vi.fn(),
    extractTravelDocument: vi.fn(),
    saveTravelDocument: vi.fn(),
  };
});

const mocked = api as unknown as {
  fetchTravelDocuments: ReturnType<typeof vi.fn>;
  fetchDocumentReadiness: ReturnType<typeof vi.fn>;
  deleteTravelDocument: ReturnType<typeof vi.fn>;
  clearTravelDocuments: ReturnType<typeof vi.fn>;
  extractTravelDocument: ReturnType<typeof vi.fn>;
  saveTravelDocument: ReturnType<typeof vi.fn>;
};

function passport(overrides: Partial<api.TravelDocument> = {}): api.TravelDocument {
  return {
    id: "doc-1",
    scope: "traveler",
    type: "passport",
    status: "ready",
    traveller_key: "self",
    traveller_name: "Munish",
    trip_id: null,
    fields: { holder_name: "Munish", issuing_country: "India", number_last4: "8842", expiry: "2031-04-02" },
    provenance: {
      source_kind: "image",
      confidence: 0.98,
      confirmed_by_user: true,
      captured_at: "2026-02-01T10:00:00+00:00",
    },
    created_at: "2026-02-01T10:00:00+00:00",
    updated_at: "2026-02-01T10:00:00+00:00",
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mocked.fetchTravelDocuments.mockResolvedValue({ documents: [], type_labels: {} });
  mocked.fetchDocumentReadiness.mockResolvedValue({ checks: [], blockers: 0, warnings: 0, badge: "" });
});

describe("TravelDocumentsVault", () => {
  it("states plainly that the document itself is never kept", async () => {
    render(<TravelDocumentsVault />);
    expect(
      await screen.findByText(/We keep the details we read, never the document/i),
    ).toBeTruthy();
  });

  it("shows a traveller with no passport as needing something on file", async () => {
    mocked.fetchDocumentReadiness.mockResolvedValue({
      travellers: [{ key: "self", name: "Munish", relationship: "you" }],
      checks: [],
      blockers: 0,
      warnings: 0,
      badge: "",
    });
    render(<TravelDocumentsVault />);
    expect(await screen.findByText("Nothing on file")).toBeTruthy();
  });

  it("reveals only the stored fields, marking the number as a last four", async () => {
    mocked.fetchTravelDocuments.mockResolvedValue({ documents: [passport()], type_labels: {} });
    render(<TravelDocumentsVault />);
    fireEvent.click(await screen.findByRole("button", { name: "View" }));
    expect(screen.getByText("8842")).toBeTruthy();
    expect(screen.getByText("last 4")).toBeTruthy();
    expect(screen.getByText(/read once and discarded/i)).toBeTruthy();
  });

  it("keeps trip gaps visible next to the documents they refer to", async () => {
    mocked.fetchDocumentReadiness.mockResolvedValue({
      travellers: [{ key: "self", name: "Munish", relationship: "you" }],
      checks: [
        {
          id: "passport-margin-self",
          severity: "blocker",
          traveller_key: "self",
          traveller_name: "Munish",
          title: "Munish's passport is too close to expiry",
          detail: "It expires 38 days after you return.",
          rule: "expiry >= return + 6 months",
          origin: "computed",
          action: "Check the destination's exact rule.",
        },
      ],
      blockers: 1,
      warnings: 0,
      badge: "1 document to fix",
    });
    render(<TravelDocumentsVault />);
    expect(await screen.findByText("This trip needs attention")).toBeTruthy();
    expect(screen.getByText("expiry >= return + 6 months")).toBeTruthy();
    expect(screen.getByText("Computed here")).toBeTruthy();
  });

  it("asks for confirmation before deleting every detail", async () => {
    mocked.fetchTravelDocuments.mockResolvedValue({ documents: [passport()], type_labels: {} });
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<TravelDocumentsVault />);
    fireEvent.click(await screen.findByRole("button", { name: "Delete every document detail" }));
    await waitFor(() => expect(confirm).toHaveBeenCalled());
    expect(mocked.clearTravelDocuments).not.toHaveBeenCalled();
    confirm.mockRestore();
  });

  it("saves only the reviewed fields after an extraction", async () => {
    mocked.extractTravelDocument.mockResolvedValue({
      type: "passport",
      source_kind: "text",
      fields: [
        { key: "holder_name", label: "Name", value: "Munish", masked: false, confidence: 0.99 },
        { key: "number_last4", label: "Document number", value: "8842", masked: true, confidence: 0.93 },
      ],
    });
    mocked.saveTravelDocument.mockResolvedValue(passport());
    render(<TravelDocumentsVault />);

    fireEvent.click(await screen.findByRole("button", { name: /Add a document/i }));
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "Passport of Munish, number X8842" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Read the pasted text" }));

    expect(await screen.findByText("Check what we read")).toBeTruthy();
    expect(screen.getByText(/The file is deleted when you save/i)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Save details" }));
    await waitFor(() => expect(mocked.saveTravelDocument).toHaveBeenCalled());
    const saved = mocked.saveTravelDocument.mock.calls[0][0];
    expect(saved.fields).toEqual({ holder_name: "Munish", number_last4: "8842" });
    expect(saved.provenance.confirmed_by_user).toBe(true);
  });
});
