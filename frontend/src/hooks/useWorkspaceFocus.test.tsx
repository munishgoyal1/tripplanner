import { act, renderHook } from "@testing-library/react";
import { useReducer } from "react";
import { describe, expect, it } from "vitest";
import { initialWorkspaceState, workspaceReducer } from "../workspaceState";
import { useWorkspaceFocus } from "./useWorkspaceFocus";

function useFocusHarness() {
  const [workspace, dispatch] = useReducer(workspaceReducer, initialWorkspaceState);
  return {
    workspace,
    controller: useWorkspaceFocus(workspace.focus, dispatch),
  };
}

describe("useWorkspaceFocus", () => {
  it("keeps place, circuit, route, and all-days focus mutually exclusive", () => {
    const { result } = renderHook(useFocusHarness);

    act(() => result.current.controller.setPlace({
      kind: "hotel",
      name: "Goa Marriott",
      day: 2,
      stop: 1,
    }));
    expect(result.current.workspace.focus).toMatchObject({
      type: "place",
      place: { name: "Goa Marriott", day: 2, stop: 1 },
    });

    act(() => result.current.controller.setCircuit(3));
    expect(result.current.workspace.focus).toMatchObject({ type: "circuit", day: 3 });
    expect(result.current.controller.place).toBeNull();

    act(() => result.current.controller.setRoute(1));
    expect(result.current.workspace.focus).toMatchObject({ type: "route", day: 1 });
    expect(result.current.controller.circuitToken).toBe(0);

    act(() => result.current.controller.setCircuit(null));
    expect(result.current.workspace.focus).toMatchObject({ type: "circuit", day: null });
    expect(result.current.controller.routeToken).toBe(0);

    act(() => result.current.controller.clear());
    expect(result.current.workspace.focus).toEqual({ type: "none" });
  });

  it("issues a fresh token when the same focus action is repeated", () => {
    const { result } = renderHook(useFocusHarness);

    act(() => result.current.controller.setPlace({ kind: "attraction", name: "Louvre Museum" }));
    const firstPlaceToken = result.current.controller.placeToken;
    act(() => result.current.controller.setPlace({ kind: "attraction", name: "Louvre Museum" }));
    expect(result.current.controller.placeToken).toBeGreaterThan(firstPlaceToken);

    act(() => result.current.controller.setRoute(1));
    const firstRouteToken = result.current.controller.routeToken;
    act(() => result.current.controller.setRoute(1));
    expect(result.current.controller.routeToken).toBeGreaterThan(firstRouteToken);
  });
});