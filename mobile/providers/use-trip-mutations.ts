import type {
  DeselectItemOptions,
  Itinerary,
  SelectItemOptions,
  SerializedMutationQueue,
  TripView,
} from '@tripplanner/client';
import { useCallback, type Dispatch, type SetStateAction } from 'react';

import { tripplannerClient } from '@/lib/tripplanner';

import { tripErrorMessage } from './trip-provider-utils';

interface TripMutationOptions {
  mutationQueue: SerializedMutationQueue;
  refresh: () => Promise<void>;
  clearFailedMessage: () => void;
  setError: Dispatch<SetStateAction<string | null>>;
  setItinerary: Dispatch<SetStateAction<Itinerary | null>>;
  setView: Dispatch<SetStateAction<TripView | null>>;
}

export function useTripMutations({
  mutationQueue,
  refresh,
  clearFailedMessage,
  setError,
  setItinerary,
  setView,
}: TripMutationOptions) {
  const runMutation = useCallback(<T,>(
    mutation: () => Promise<T>,
    applyResult: (result: T) => void,
  ) => {
    clearFailedMessage();
    return mutationQueue.run(async () => {
      try {
        applyResult(await mutation());
        await refresh();
      } catch (caught) {
        setError(tripErrorMessage(caught));
      }
    });
  }, [clearFailedMessage, mutationQueue, refresh, setError]);

  const removePlace = useCallback((
    kind: string,
    name: string,
    options?: DeselectItemOptions,
  ) => runMutation(
    () => tripplannerClient.deselectItem(kind, name, options),
    (result) => setView(result.view),
  ), [runMutation, setView]);

  const addPlace = useCallback((
    kind: string,
    name: string,
    options?: SelectItemOptions,
  ) => runMutation(
    () => tripplannerClient.selectItem(kind, name, options),
    (result) => setView(result.view),
  ), [runMutation, setView]);

  const setBooked = useCallback((day: number, name: string, booked: boolean) => runMutation(
    () => tripplannerClient.setStopBooked(day, name, booked),
    setItinerary,
  ), [runMutation, setItinerary]);

  return { removePlace, addPlace, setBooked };
}