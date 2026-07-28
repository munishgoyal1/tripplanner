import type {
  ChatMessage,
  DeselectItemOptions,
  Itinerary,
  MapView,
  SavedTrip,
  SelectItemOptions,
  TripView,
} from '@tripplanner/client';
import {
  createContext,
  type PropsWithChildren,
  useCallback,
  useContext,
  useEffect,
  useReducer,
  useRef,
  useState,
} from 'react';

import {
  getMobileAccount,
  loginWithGoogle,
  logoutMobile,
  tripplannerClient,
  type MobileAccount,
} from '@/lib/tripplanner';
import { LatestRequestGate } from '@/lib/latest-request';

interface TripContextValue {
  view: TripView | null;
  itinerary: Itinerary | null;
  map: MapView | null;
  trips: SavedTrip[];
  messages: ChatMessage[];
  loading: boolean;
  sending: boolean;
  error: string | null;
  canRetryMessage: boolean;
  revision: number;
  account: MobileAccount | null;
  refresh: () => Promise<void>;
  switchTrip: (tripId: string) => Promise<void>;
  startNewTrip: () => Promise<void>;
  sendMessage: (message: string) => Promise<void>;
  retryMessage: () => Promise<void>;
  removePlace: (
    kind: string,
    name: string,
    options?: DeselectItemOptions,
  ) => Promise<void>;
  addPlace: (kind: string, name: string, options?: SelectItemOptions) => Promise<void>;
  setBooked: (day: number, name: string, booked: boolean) => Promise<void>;
  signIn: () => Promise<void>;
  signOut: () => Promise<void>;
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
  const [failedMessage, setFailedMessage] = useState<{
    message: string;
    requestId: string;
    rowCount: number;
  } | null>(null);
  const [revision, bumpRevision] = useReducer((value: number) => value + 1, 0);
  const [account, setAccount] = useState<MobileAccount | null>(null);
  const refreshRequests = useRef(new LatestRequestGate());

  const refresh = useCallback(async () => {
    const request = refreshRequests.current.start();
    setLoading(true);
    setError(null);
    try {
      const results = await Promise.allSettled([
        tripplannerClient.fetchTripView(undefined, request.signal),
        tripplannerClient.fetchItinerary(request.signal),
        tripplannerClient.fetchMapView(request.signal),
        tripplannerClient.fetchSavedTrips(request.signal),
        tripplannerClient.fetchChatHistory(undefined, request.signal),
      ]);
      if (!request.isCurrent()) return;
      const [nextView, nextItinerary, nextMap, nextTrips, history] = results;
      if (nextView.status === 'fulfilled') setView(nextView.value);
      if (nextItinerary.status === 'fulfilled') setItinerary(nextItinerary.value);
      if (nextMap.status === 'fulfilled') setMap(nextMap.value);
      if (nextTrips.status === 'fulfilled') setTrips(nextTrips.value);
      if (history.status === 'fulfilled') setMessages(history.value);
      const failed = results.filter((result) => result.status === 'rejected');
      if (failed.length === results.length) throw failed[0].reason;
      if (failed.length) {
        setError(`${failed.length} section${failed.length === 1 ? '' : 's'} could not refresh.`);
      }
      bumpRevision();
    } catch (caught) {
      if (request.isCurrent()) setError(errorMessage(caught));
    } finally {
      if (request.isCurrent()) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void getMobileAccount().then(setAccount);
    void refresh();
    return () => refreshRequests.current.abort();
  }, [refresh]);

  const signIn = useCallback(async () => {
    setLoading(true);
    setError(null);
    setFailedMessage(null);
    try {
      setAccount(await loginWithGoogle());
      await refresh();
    } catch (caught) {
      setError(errorMessage(caught));
      setLoading(false);
    }
  }, [refresh]);

  const signOut = useCallback(async () => {
    setFailedMessage(null);
    await logoutMobile();
    setAccount(null);
    setView(null);
    setItinerary(null);
    setMap(null);
    setTrips([]);
    setMessages([]);
    await refresh();
  }, [refresh]);

  const switchTrip = useCallback(async (tripId: string) => {
    setLoading(true);
    setError(null);
    setFailedMessage(null);
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
    setFailedMessage(null);
    try {
      await tripplannerClient.startNewTrip();
      await refresh();
    } catch (caught) {
      setError(errorMessage(caught));
      setLoading(false);
    }
  }, [refresh]);

  const runMessage = useCallback(async (
    message: string,
    requestId: string,
    retryRows = 0,
  ) => {
    const trimmed = message.trim();
    if (!trimmed || sending) return;
    setSending(true);
    setError(null);
    setFailedMessage(null);
    setMessages((current) => [
      ...(retryRows ? current.slice(0, -retryRows) : current),
      { role: 'user', text: trimmed },
    ]);
    let streamed = '';
    let hasAssistantDraft = false;
    try {
      await tripplannerClient.streamChat(trimmed, {
        onToken: (token) => {
          streamed += token;
          setMessages((current) => {
            if (!hasAssistantDraft) {
              hasAssistantDraft = true;
              return [...current, { role: 'assistant', text: streamed }];
            }
            return [
              ...current.slice(0, -1),
              { role: 'assistant', text: streamed },
            ];
          });
        },
        onTool: () => undefined,
        onDone: (reply) => {
          if (!streamed && reply) {
            streamed = reply;
            setMessages((current) => [...current, { role: 'assistant', text: reply }]);
          }
        },
        onError: (messageText) => {
          throw new Error(messageText);
        },
      }, { requestId });
      await refresh();
    } catch (caught) {
      setError(errorMessage(caught));
      setFailedMessage({
        message: trimmed,
        requestId,
        rowCount: hasAssistantDraft ? 2 : 1,
      });
    } finally {
      setSending(false);
    }
  }, [refresh, sending]);

  const sendMessage = useCallback(
    (message: string) => runMessage(message, crypto.randomUUID()),
    [runMessage],
  );

  const retryMessage = useCallback(async () => {
    if (!failedMessage) return;
    await runMessage(
      failedMessage.message,
      failedMessage.requestId,
      failedMessage.rowCount,
    );
  }, [failedMessage, runMessage]);

  const removePlace = useCallback(async (
    kind: string,
    name: string,
    options?: DeselectItemOptions,
  ) => {
    setFailedMessage(null);
    try {
      const result = await tripplannerClient.deselectItem(kind, name, options);
      setView(result.view);
      await refresh();
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }, [refresh]);

  const addPlace = useCallback(async (
    kind: string,
    name: string,
    options?: SelectItemOptions,
  ) => {
    setFailedMessage(null);
    try {
      const result = await tripplannerClient.selectItem(kind, name, options);
      setView(result.view);
      await refresh();
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }, [refresh]);

  const setBooked = useCallback(async (day: number, name: string, booked: boolean) => {
    setFailedMessage(null);
    try {
      setItinerary(await tripplannerClient.setStopBooked(day, name, booked));
      await refresh();
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }, [refresh]);

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
      canRetryMessage: failedMessage !== null,
      revision,
      account,
      refresh,
      switchTrip,
      startNewTrip,
      sendMessage,
      retryMessage,
      removePlace,
      addPlace,
      setBooked,
      signIn,
      signOut,
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