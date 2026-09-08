import type { SerializedMutationQueue } from '@tripplanner/client';
import { useCallback, type Dispatch, type SetStateAction } from 'react';

import { tripplannerClient } from '@/lib/tripplanner';

import { tripErrorMessage } from './trip-provider-utils';

interface SavedTripLifecycleOptions {
  mutationQueue: SerializedMutationQueue;
  refresh: () => Promise<void>;
  clearFailedMessage: () => void;
  setError: Dispatch<SetStateAction<string | null>>;
  setLoading: Dispatch<SetStateAction<boolean>>;
}

export function useSavedTripLifecycle({
  mutationQueue,
  refresh,
  clearFailedMessage,
  setError,
  setLoading,
}: SavedTripLifecycleOptions) {
  const switchTrip = useCallback((tripId: string) => {
    setLoading(true);
    setError(null);
    clearFailedMessage();
    return mutationQueue.run(async () => {
      setLoading(true);
      setError(null);
      try {
        await tripplannerClient.switchTrip(tripId);
        await refresh();
      } catch (caught) {
        setError(tripErrorMessage(caught));
        setLoading(false);
      }
    });
  }, [clearFailedMessage, mutationQueue, refresh, setError, setLoading]);

  const startNewTrip = useCallback(() => {
    setLoading(true);
    clearFailedMessage();
    return mutationQueue.run(async () => {
      setLoading(true);
      try {
        await tripplannerClient.startNewTrip();
        await refresh();
      } catch (caught) {
        setError(tripErrorMessage(caught));
        setLoading(false);
      }
    });
  }, [clearFailedMessage, mutationQueue, refresh, setError, setLoading]);

  return { switchTrip, startNewTrip };
}