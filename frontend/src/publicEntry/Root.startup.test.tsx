import { act, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import Root from "./Root";

const pending = vi.hoisted(() => {
  let resolve!: () => void;
  const ready = new Promise<void>((done) => { resolve = done; });
  return { ready, resolve };
});

vi.mock("../components/AccountSettingsController", () => ({ default: () => null }));
vi.mock("../App", async () => {
  await pending.ready;
  return { default: () => <main>Loaded planner</main> };
});
vi.mock("./PublicEntry", () => { throw new Error("Planner must not load the landing route"); });
vi.mock("../ops/OpsDashboard", () => { throw new Error("Planner must not load operations"); });

it("shows a visible status while planner code is delayed, then opens the planner", async () => {
  window.history.replaceState({}, "", "/planner");
  render(<Root />);
  expect(screen.getByRole("status")).toHaveTextContent("Opening your planner");
  await act(async () => { pending.resolve(); });
  expect(await screen.findByText("Loaded planner")).toBeInTheDocument();
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});
