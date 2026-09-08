interface ItineraryOccurrenceLocation {
  day: number;
  stop: number;
}

export function exactItineraryOccurrence(
  day: number,
  zeroBasedStopIndex: number,
): ItineraryOccurrenceLocation {
  return {
    day,
    stop: zeroBasedStopIndex + 1,
  };
}