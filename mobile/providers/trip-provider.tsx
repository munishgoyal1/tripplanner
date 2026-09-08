import type {
  ChatMessage,
  DeselectItemOptions,
  Itinerary,
  MapView,
  SavedTrip,
  SelectItemOptions,
  TripView,
} from '@tripplanner/client';
import { LatestRequestGate, SerializedMutationQueue } from '@tripplanner/client';
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

import { tripErrorMessage } from './trip-provider-utils';
import { useSavedTripLifecycle } from './use-saved-trip-lifecycle';
import { useTripMutations } from './use-trip-mutations';

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
  const [mutationQueue] = useState(() => new SerializedMutationQueue());
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
      if (request.isCurrent()) setError(tripErrorMessage(caught));
    } finally {
      if (request.isCurrent()) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void getMobileAccount().then(setAccount);
    void refresh();
    return () => refreshRequests.current.abort();
  }, [refresh]);

  const signIn = useCallback(() => {
    setLoading(true);
    setError(null);
    setFailedMessage(null);
    return mutationQueue.run(async () => {
      setLoading(true);
      setError(null);
      try {
        setAccount(await loginWithGoogle());
        await refresh();
      } catch (caught) {
        setError(tripErrorMessage(caught));
        setLoading(false);
      }
    });
  }, [mutationQueue, refresh]);

  const signOut = useCallback(() => {
    setFailedMessage(null);
    return mutationQueue.run(async () => {
      await logoutMobile();
      setAccount(null);
      setView(null);
      setItinerary(null);
      setMap(null);
      setTrips([]);
      setMessages([]);
      await refresh();
    });
  }, [mutationQueue, refresh]);

  const clearFailedMessage = useCallback(() => setFailedMessage(null), []);
  const { switchTrip, startNewTrip } = useSavedTripLifecycle({
    mutationQueue,
    refresh,
    clearFailedMessage,
    setError,
    setLoading,
  });

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
      setError(tripErrorMessage(caught));
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

  const { removePlace, addPlace, setBooked } = useTripMutations({
    mutationQueue,
    refresh,
    clearFailedMessage,
    setError,
    setItinerary,
    setView,
  });

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