import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchOpsEvals, type EvalsReport } from "../api";
import EvalsDashboard from "./EvalsDashboard";

vi.mock("../api", () => ({ fetchOpsEvals: vi.fn() }));

const report: EvalsReport = {
  version: 1,
  generated_at: "2026-09-23T12:00:00Z",
  judge: {
    rubric: { version: "itinerary-v1", dimensions: [{ key: "meal_quality", criterion: "Are meals concrete?" }] },
    judge_model: "operator-model",
    method: "operator session",
    dimension_means: { meal_quality: 1 },
    trips: [{
      slug: "goa-relaxed",
      destination: "Goa",
      days: 4,
      request: "Plan a relaxed 4 day trip to Goa",
      status: "complete",
      overall_score: 1,
      assessments: [{ dimension: "meal_quality", status: "scored", score: 1, rationale: "Every meal is TBD.", evidence: [{ path: "/plan/x", quote: "Lunch (TBD)" }] }],
    }],
  },
  audit: {
    corpus: { size: 10, sources: ["generated finals (10)"] },
    observations: [],
    rules: [{ code: "I9", title: "Continuity", statement: "Every move is explained.", severity: "gate", hits: 4, trips: 2 }],
    top_groups: [{ rule: "I9", symptom: "Day N jumps", count: 4, example: "Day 3", accepted: false }],
  },
  findings: [{ id: "BL-1", title: "Checkout after departure", severity: "high", area: "Scheduling", evidence: "Tokyo day 4", impact: "Wrong order", fix: "Sort anchors", source: "judge", status: "fixed", resolution: "Stays move before the departure on save." }],
  efficiencies: [{ id: "EE-1", title: "One place classifier", value: "high", effort: "S", evidence: "two classifiers", plan: "merge" }],
};

describe("EvalsDashboard", () => {
  beforeEach(() => vi.mocked(fetchOpsEvals).mockReset());

  it("renders findings first and the judge matrix with evidence on demand", async () => {
    vi.mocked(fetchOpsEvals).mockResolvedValue(report);
    render(<EvalsDashboard />);

    expect(await screen.findByText("Checkout after departure")).toBeInTheDocument();
    expect(screen.getByText("Stays move before the departure on save.")).toBeInTheDocument();
    expect(screen.getByText("0 critical or high open · 1 fixed")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /LLM judge/ }));
    fireEvent.click(screen.getByText("Goa"));
    expect(screen.getByText("Every meal is TBD.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /Deterministic audit/ }));
    expect(screen.getByText("Day N jumps")).toBeInTheDocument();
  });

  it("hides the console from anyone but the owner", async () => {
    vi.mocked(fetchOpsEvals).mockRejectedValueOnce(Object.assign(new Error("Evaluation report unavailable (404)."), { status: 404 }));
    render(<EvalsDashboard />);
    await waitFor(() => expect(screen.getByText("404")).toBeInTheDocument());
  });
});
