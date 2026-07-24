import type {
  ChatMessage,
  DeselectItemOptions,
  Itinerary,
  MapView,
  SavedTrip,
  TripView,
} from '@tripplanner/client';
import {
  createContext,
  type PropsWithChildren,
  useCallback,
  useContext,
  useEffect,
  useReducer,
  useState,
} from 'react';

import { tripplannerClient } from '@/lib/tripplanner';

interface TripContextValue {
  view: TripView | null;
  itinerary: Itinerary | null;
  map: MapView | null;
  trips: SavedTrip[];
  messages: ChatMessage[];
  loading: boolean;
  sending: boolean;
  error: string | null;
  revision: number;
  refresh: () => Promise<void>;
  switchTrip: (tripId: string) => Promise<void>;
  startNewTrip: () => Promise<void>;
  sendMessage: (message: string) => Promise<void>;
  removePlace: (
    kind: string,
    name: string,
    options?: DeselectItemOptions,
  ) => Promise<void>;
  addPlace: (kind: string, name: string) => Promise<void>;
  setBooked: (day: number, name: string, booked: boolean) => Promise<void>;
}

const TripContext = createContext<TripContextValue | null>(null);

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong.';
}

export function TripProvider({ children }: PropsWithChildren) {
  const [view, setView] = useState<TripView | null>(null);
  const [itinerary, setItinerary] = useState<Itinerary | null>(null);
  const [map, setMap] = useState<MapView | null>(null);
  const [trips, setTrips] = useState<SavedTrip[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [revision, bumpRevision] = useReducer((value: number) => value + 1, 0);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextView, nextItinerary, nextMap, nextTrips, history] = await Promise.all([
        tripplannerClient.fetchTripView(),
        tripplannerClient.fetchItinerary(),
        tripplannerClient.fetchMapView(),
        tripplannerClient.fetchSavedTrips(),
        tripplannerClient.fetchChatHistory(),
      ]);
      setView(nextView);
      setItinerary(nextItinerary);
      setMap(nextMap);
      setTrips(nextTrips);
      setMessages(history);
      bumpRevision();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const switchTrip = useCallback(async (tripId: string) => {
    setLoading(true);
    setError(null);
    try {
      await tripplannerClient.switchTrip(tripId);
      await refresh();
    } catch (caught) {
      setError(errorMessage(caught));
      setLoading(false);
    }
  }, [refresh]);

  const startNewTrip = useCallback(async () => {
    setLoading(true);
    try {
      await tripplannerClient.startNewTrip();
      await refresh();
    } catch (caught) {
      setError(errorMessage(caught));
      setLoading(false);
    }
  }, [refresh]);

  const sendMessage = useCallback(async (message: string) => {
    const trimmed = message.trim();
    if (!trimmed || sending) return;
    setSending(true);
    setError(null);
    setMessages((current) => [...current, { role: 'user', text: trimmed }]);
    let streamed = '';
    try {
      await tripplannerClient.streamChat(trimmed, {
        onToken: (token) => {
          streamed += token;
          setMessages((current) => {
            const withoutDraft = current.filter((item) => item.role !== 'assistant' || item.text !== streamed.slice(0, -token.length));
            return [...withoutDraft, { role: 'assistant', text: streamed }];
          });
        },
        onTool: () => undefined,
        onDone: () => undefined,
        onError: (messageText) => {
          throw new Error(messageText);
        },
      });
      await refresh();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setSending(false);
    }
  }, [refresh, sending]);

  const removePlace = useCallback(async (
    kind: string,
    name: string,
    options?: DeselectItemOptions,
  ) => {
    try {
      const result = await tripplannerClient.deselectItem(kind, name, options);
      setView(result.view);
      await refresh();
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }, [refresh]);

  const addPlace = useCallback(async (kind: string, name: string) => {
    try {
      const result = await tripplannerClient.selectItem(kind, name);
      setView(result.view);
      await refresh();
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }, [refresh]);

  const setBooked = useCallback(async (day: number, name: string, booked: boolean) => {
    try {
      setItinerary(await tripplannerClient.setStopBooked(day, name, booked));
      bumpRevision();
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }, []);

  return (
    <TripContext.Provider value={{
      view,
      itinerary,
      map,
      trips,
      messages,
      loading,
      sending,
      error,
      revision,
      refresh,
      switchTrip,
      startNewTrip,
      sendMessage,
      removePlace,
      addPlace,
      setBooked,
    }}>
      {children}
    </TripContext.Provider>
  );
}

export function useTrip(): TripContextValue {
  const value = useContext(TripContext);
  if (!value) throw new Error('useTrip must be used inside TripProvider.');
  return value;
}