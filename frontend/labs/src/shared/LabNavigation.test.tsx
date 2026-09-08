import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LabNavigation } from "./LabNavigation";

describe("LabNavigation", () => {
  it("shows the permanent Lab number in detail-page navigation", () => {
    render(<LabNavigation detail labId="multi-city-itinerary" />);

    expect(screen.getByText("Lab #15")).not.toBeNull();
    expect(screen.getByRole("link", { name: "Back to All Open Labs" })).not.toBeNull();
  });

  it("keeps discarded Labs reachable from catalog navigation", () => {
    render(<LabNavigation current="discarded" />);

    expect(screen.getByRole("link", { name: "Discarded" }).getAttribute("aria-current")).toBe("page");
  });
});