import { useRef, useState, type Dispatch, type SetStateAction } from "react";
import { SerializedMutationQueue, type WorkspaceAction } from "@tripplanner/client";
import {
  deselectItem,
  getUserId,
  resetTrip,
  selectItem,
  startNewTrip,
  type DeselectItemOptions,
  type SelectItemOptions,
} from "../api";
import { trackEvent } from "../analytics";
import type { AssistantTurnStatus } from "../components/ChatPanel";
import { dismissNotice, notify } from "../lib/notices";
import type { PlannerReview, TripView, TripWorkspaceView } from "../types";

export interface NavRef {
  kind: string;
  name: string;
  day?: number;
  stop?: number;
}

interface MutableRef<T> {
  current: T;
}

interface WorkspaceTripMutationOptions {
  workspaceEpoch: MutableRef<number>;
  refreshGeneration: MutableRef<number>;
  refreshController: MutableRef<AbortController | null>;
  refresh: (focus?: NavRef | null) => Promise<TripView | null | undefined>;
  applyView: (view: TripView, focus: NavRef | null) => void;
  dispatchWorkspace: Dispatch<WorkspaceAction>;
  setPlaceFocus: (place: NavRef) => void;
  setView: Dispatch<SetStateAction<TripView | null>>;
  setPanelSeed: Dispatch<SetStateAction<TripWorkspaceView | null>>;
  setLoading: Dispatch<SetStateAction<boolean>>;
  setPlannerReview: Dispatch<SetStateAction<PlannerReview | null>>;
  setAssistantTurnStatus: Dispatch<SetStateAction<AssistantTurnStatus | null>>;
  setNavList: Dispatch<SetStateAction<NavRef[]>>;
  setInspectorOpen: Dispatch<SetStateAction<boolean>>;
  setChatOpen: Dispatch<SetStateAction<boolean>>;
}

function focusKind(kind: string): string {
  if (["hotel", "airport", "station", "bus_station"].includes(kind)) return kind;
  return "attraction";
}

function errorStatus(error: unknown): number | undefined {
  return typeof error === "object" && error !== null && "status" in error
    ? (error as { status?: number }).status
    : undefined;
}

function retryDelay(error: unknown): number {
  if (typeof error !== "object" || error === null || !("retryAfterMs" in error)) return 2000;
  return (error as { retryAfterMs?: number | null }).retryAfterMs ?? 2000;
}

export function useWorkspaceTripMutations({
  workspaceEpoch,
  refreshGeneration,
  refreshController,
  refresh,
  applyView,
  dispatchWorkspace,
  setPlaceFocus,
  setView,
  setPanelSeed,
  setLoading,
  setPlannerReview,
  setAssistantTurnStatus,
  setNavList,
  setInspectorOpen,
  setChatOpen,
}: WorkspaceTripMutationOptions) {
  const [mutationQueue] = useState(() => new SerializedMutationQueue());
  const pendingDeselects = useRef(new Set<string>());

  const handleNewTrip = async () => {
    setAssistantTurnStatus(null);
    setPanelSeed(null);
    dispatchWorkspace({ type: "trip-changed" });
    await refresh(null);
  };

  const handleStartNewTrip = async () => {
    const epoch = workspaceEpoch.current;
    const userId = getUserId();
    await mutationQueue.run(async () => {
      if (epoch !== workspaceEpoch.current || userId !== getUserId()) return;
      try {
        dismissNotice("action-error");
        for (let attempt = 0; ; attempt += 1) {
          try {
            await startNewTrip();
            break;
          } catch (error) {
            if (errorStatus(error) !== 409 || attempt === 89) throw error;
            notify({
              id: "action-error",
              tone: "progress",
              message: "Waiting for the Assistant to finish before starting a new trip...",
            });
            await new Promise((resolve) => setTimeout(resolve, retryDelay(error)));
          }
        }
        if (epoch !== workspaceEpoch.current || userId !== getUserId()) return;
        await handleNewTrip();
        setInspectorOpen(true);
        setChatOpen(true);
        trackEvent("new_trip_started", { surface: "desktop" });
      } catch (error) {
        notify({
          id: "action-error",
          tone: "error",
          message: error instanceof Error ? error.message : "Could not start a new trip.",
        });
      }
    });
  };

  const handleResetTrip = async () => {
    if (
      !window.confirm(
        "Reset this trip? The itinerary and everything you've picked will be cleared. " +
          "The destination, dates and travellers stay, so you can rebuild from the same brief.",
      )
    ) return;
    const epoch = workspaceEpoch.current;
    const userId = getUserId();
    await mutationQueue.run(async () => {
      if (epoch !== workspaceEpoch.current || userId !== getUserId()) return;
      try {
        dismissNotice("action-error");
        const workspace = await resetTrip();
        if (epoch !== workspaceEpoch.current || userId !== getUserId()) return;
        ++refreshGeneration.current;
        refreshController.current?.abort();
        setLoading(false);
        setAssistantTurnStatus(null);
        setPanelSeed(workspace);
        dispatchWorkspace({ type: "trip-changed" });
        if (workspace) applyView(workspace.view, null);
        else await refresh(null);
        notify({
          id: "trip-reset",
          tone: "success",
          message: "Trip reset",
          detail: "The plan is empty. Your destination, dates and travellers are unchanged.",
        });
        trackEvent("trip_reset", { surface: "desktop" });
      } catch (error) {
        notify({
          id: "action-error",
          tone: "error",
          message: "Could not reset the trip",
          detail: error instanceof Error ? error.message : undefined,
        });
      }
    });
  };

  const selectWhenAvailable = async (
    kind: string,
    name: string,
    options?: SelectItemOptions,
    isCurrent: () => boolean = () => true,
  ) => {
    for (let attempt = 0; attempt < 90; attempt += 1) {
      if (!isCurrent()) return null;
      try {
        return await selectItem(kind, name, options);
      } catch (error) {
        if (errorStatus(error) !== 409 || attempt === 89) throw error;
        notify({
          id: "action-error",
          tone: "progress",
          message: "Waiting for the Assistant to finish before adding this place...",
        });
        await new Promise((resolve) => setTimeout(resolve, retryDelay(error)));
      }
    }
    throw new Error("Could not add the place.");
  };

  const handleSelect = async (kind: string, name: string, options?: SelectItemOptions) => {
    const epoch = workspaceEpoch.current;
    const userId = getUserId();
    return mutationQueue.run(async () => {
      if (epoch !== workspaceEpoch.current || userId !== getUserId()) return false;
      try {
        setAssistantTurnStatus(null);
        dismissNotice("action-error");
        const next = await selectWhenAvailable(
          kind,
          name,
          options,
          () => epoch === workspaceEpoch.current && userId === getUserId(),
        );
        if (!next || epoch !== workspaceEpoch.current || userId !== getUserId()) return false;
        const nextKind = focusKind(kind);
        setPlaceFocus({ kind: nextKind, name });
        ++refreshGeneration.current;
        refreshController.current?.abort();
        setLoading(false);
        setView({ ...next.view, alerts: next.alerts });
        setPlannerReview(next.planner_review ?? null);
        setNavList(next.view.items.map((item) => ({ kind: item.kind, name: item.name })));
        const placement = next.placement || next.placements?.[0] || null;
        if (placement?.day && placement?.name) {
          dispatchWorkspace({
            type: "jump",
            target: { day: placement.day, name: placement.name, token: Date.now() },
          });
        }
        dispatchWorkspace({ type: "trip-content-changed" });
        trackEvent("place_added", { exact_day: Boolean(options?.day) });
        return true;
      } catch (error) {
        notify({
          id: "action-error",
          tone: "error",
          message: error instanceof Error ? error.message : "Could not add the place.",
        });
        return false;
      }
    });
  };

  const handleDeselect = async (
    kind: string,
    name: string,
    options: DeselectItemOptions = { all_occurrences: true },
  ) => {
    const epoch = workspaceEpoch.current;
    const userId = getUserId();
    const mutationKey = [
      focusKind(kind),
      name.trim().toLowerCase(),
      options.all_occurrences === false ? options.day ?? "day" : "all",
      options.stop ?? "stop",
    ].join(":");
    if (pendingDeselects.current.has(mutationKey)) return false;
    pendingDeselects.current.add(mutationKey);
    try {
      return await mutationQueue.run(async () => {
        if (epoch !== workspaceEpoch.current || userId !== getUserId()) return false;
        try {
          setAssistantTurnStatus(null);
          dismissNotice("action-error");
          const next = await deselectItem(kind, name, options);
          if (epoch !== workspaceEpoch.current || userId !== getUserId()) return false;
          const retainedFocus = {
            kind: focusKind(kind),
            name,
            day: options.all_occurrences === false ? options.day : undefined,
            stop: options.all_occurrences === false ? options.stop : undefined,
          };
          setPlaceFocus(retainedFocus);
          ++refreshGeneration.current;
          refreshController.current?.abort();
          setLoading(false);
          setView({ ...next.view, focus: retainedFocus, alerts: next.alerts });
          setPlannerReview(next.planner_review ?? null);
          setNavList(next.view.items.map((item) => ({ kind: item.kind, name: item.name })));
          dispatchWorkspace({ type: "trip-content-changed" });
          trackEvent("place_removed", {
            scope: options.all_occurrences === false ? "occurrence" : "all",
          });
          return true;
        } catch (error) {
          notify({
            id: "action-error",
            tone: "error",
            message: error instanceof Error ? error.message : "Could not remove the place.",
          });
          return false;
        }
      });
    } finally {
      pendingDeselects.current.delete(mutationKey);
    }
  };

  const handleStopRemove = async (kind: string, name: string, day: number, stop: number) => {
    await handleDeselect(kind, name, { day, stop, all_occurrences: false });
  };

  return {
    handleNewTrip,
    handleStartNewTrip,
    handleResetTrip,
    handleSelect,
    handleDeselect,
    handleStopRemove,
  };
}
