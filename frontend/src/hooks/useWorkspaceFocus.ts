import { useCallback, useRef, type Dispatch } from "react";
import type { ActivePlace, WorkspaceAction, WorkspaceFocus } from "../workspaceState";

export function useWorkspaceFocus(
  focus: WorkspaceFocus,
  dispatch: Dispatch<WorkspaceAction>,
) {
  const tokenRef = useRef(focus.type === "none" ? 0 : focus.token);
  const nextToken = useCallback(() => {
    tokenRef.current += 1;
    return tokenRef.current;
  }, []);

  const setPlace = useCallback((place: ActivePlace) => {
    dispatch({ type: "focus", focus: { type: "place", place, token: nextToken() } });
  }, [dispatch, nextToken]);

  const setCircuit = useCallback((day: number | null) => {
    dispatch({ type: "focus", focus: { type: "circuit", day, token: nextToken() } });
  }, [dispatch, nextToken]);

  const setRoute = useCallback((day: number, circuitId?: string) => {
    dispatch({ type: "focus", focus: { type: "route", day, circuitId, token: nextToken() } });
  }, [dispatch, nextToken]);

  const clear = useCallback(() => {
    dispatch({ type: "focus", focus: { type: "none" } });
  }, [dispatch]);

  return {
    place: focus.type === "place" ? focus.place : null,
    placeToken: focus.type === "place" ? focus.token : 0,
    circuitDay: focus.type === "circuit" ? focus.day : null,
    circuitToken: focus.type === "circuit" ? focus.token : 0,
    routeDay: focus.type === "route" ? focus.day : null,
    routeCircuitId: focus.type === "route" ? focus.circuitId : null,
    routeToken: focus.type === "route" ? focus.token : 0,
    setPlace,
    setCircuit,
    setRoute,
    clear,
  };
}