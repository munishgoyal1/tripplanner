export interface ActivePlace {
  kind: string;
  name: string;
  day?: number;
  stop?: number;
}

export type WorkspaceFocus =
  | { type: "none" }
  | { type: "place"; place: ActivePlace; token: number }
  | { type: "circuit"; day: number | null; token: number }
  | { type: "route"; day: number; circuitId?: string; token: number };

export type ItineraryJump =
  | { day: number; name?: string; token: number }
  | { summary: true; token: number };

export interface WorkspaceState {
  tripId: string | null;
  tripRevision: number;
  chatRevision: number;
  focus: WorkspaceFocus;
  itineraryJump: ItineraryJump | null;
}

export type WorkspaceAction =
  | { type: "focus"; focus: WorkspaceFocus }
  | { type: "trip-content-changed" }
  | { type: "trip-changed"; tripId?: string | null }
  | { type: "chat-trip-observed"; tripId: string }
  | { type: "jump"; target: ItineraryJump | null }
  | { type: "identity-changed" };

export const initialWorkspaceState: WorkspaceState = {
  tripId: null,
  tripRevision: 0,
  chatRevision: 0,
  focus: { type: "none" },
  itineraryJump: null,
};

export function workspaceReducer(
  state: WorkspaceState,
  action: WorkspaceAction,
): WorkspaceState {
  switch (action.type) {
    case "focus":
      return { ...state, focus: action.focus, itineraryJump: null };
    case "trip-content-changed":
      return { ...state, tripRevision: state.tripRevision + 1 };
    case "trip-changed":
      return {
        ...state,
        tripId: action.tripId || null,
        tripRevision: state.tripRevision + 1,
        chatRevision: state.chatRevision + 1,
        focus: { type: "none" },
        itineraryJump: null,
      };
    case "chat-trip-observed":
      if (state.tripId === action.tripId) return state;
      return {
        ...state,
        tripId: action.tripId,
        chatRevision: state.tripId ? state.chatRevision + 1 : state.chatRevision,
        focus: { type: "none" },
        itineraryJump: null,
      };
    case "jump":
      return { ...state, itineraryJump: action.target };
    case "identity-changed":
      return {
        ...initialWorkspaceState,
        tripRevision: state.tripRevision + 1,
        chatRevision: state.chatRevision + 1,
      };
  }
}