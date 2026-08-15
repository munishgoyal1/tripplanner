import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ProfileSuggestionCard from "./ProfileSuggestionCard";
import type { ProfileSuggestion } from "../api";

const suggestion: ProfileSuggestion = {
  id: "sug_1",
  kind: "note",
  label: "Noticed",
  summary: "Remember that Rhea prefers relaxed mornings?",
  detail: "",
  provenance: "suggested_from_chat",
  source_text: "Rhea likes slow mornings",
  created_at: "2026-08-14T10:00:00Z",
};

function renderCard(remaining = 1) {
  const onResolve = vi.fn();
  render(
    <ProfileSuggestionCard
      suggestion={suggestion}
      remaining={remaining}
      busy={false}
      onResolve={onResolve}
    />,
  );
  return onResolve;
}

describe("ProfileSuggestionCard", () => {
  it("shows the fact as not yet saved", () => {
    renderCard();
    expect(screen.getByText(/not saved yet/i)).toBeTruthy();
    expect(screen.getByText(suggestion.summary)).toBeTruthy();
  });

  it("confirms a suggestion only when the user keeps it", () => {
    const onResolve = renderCard();
    fireEvent.click(screen.getByRole("button", { name: /remember this/i }));
    expect(onResolve).toHaveBeenCalledWith("sug_1", "save");
  });

  it("declines without saving", () => {
    const onResolve = renderCard();
    fireEvent.click(screen.getByRole("button", { name: /not now/i }));
    expect(onResolve).toHaveBeenCalledWith("sug_1", "dismiss");
  });

  it("mentions further noticed facts without stacking cards", () => {
    renderCard(3);
    expect(screen.getByText(/2 more noticed/i)).toBeTruthy();
  });
});
