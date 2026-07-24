export interface ActivePlace {
  kind: string;
  name: string;
  day?: number;
  stop?: number;
}

export interface ItineraryJump {
  day: number;
  name?: string;
  token: number;
}

export interface WorkspaceState {
  tripId: string | null;
  tripRevision: number;
  chatRevision: number;
  activePlace: ActivePlace | null;
  itineraryJump: ItineraryJump | null;
}

export type WorkspaceAction =
  | { type: "focus"; place: ActivePlace | null }
  | { type: "trip-content-changed" }
  | { type: "trip-changed"; tripId?: string | null }
  | { type: "chat-trip-observed"; tripId: string }
  | { type: "jump"; target: ItineraryJump | null }
  | { type: "identity-changed" };

export const initialWorkspaceState: WorkspaceState = {
  tripId: null,
  tripRevision: 0,
  chatRevision: 0,
  activePlace: null,
  itineraryJump: null,
};

export function workspaceReducer(
  state: WorkspaceState,
  action: WorkspaceAction,
): WorkspaceState {
  switch (action.type) {
    case "focus":
      return { ...state, activePlace: action.place };
    case "trip-content-changed":
      return { ...state, tripRevision: state.tripRevision + 1 };
    case "trip-changed":
      return {
        ...state,
        tripId: action.tripId || null,
        tripRevision: state.tripRevision + 1,
        chatRevision: state.chatRevision + 1,
        activePlace: null,
        itineraryJump: null,
      };
    case "chat-trip-observed":
      if (state.tripId === action.tripId) return state;
      return {
        ...state,
        tripId: action.tripId,
        chatRevision: state.tripId ? state.chatRevision + 1 : state.chatRevision,
        activePlace: null,
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