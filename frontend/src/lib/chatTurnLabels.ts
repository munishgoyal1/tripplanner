function startOfDay(value: Date): number {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime();
}

/** Label a turn by when it happened, so a multi-day session reads as a ledger. */
export function turnGroupLabel(ts: number, now: number = Date.now()): string {
  const when = new Date(ts);
  const days = Math.round((startOfDay(new Date(now)) - startOfDay(when)) / 86_400_000);
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return when.toLocaleDateString(undefined, { weekday: "long" });
  return when.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

export function turnDurationLabel(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

export function clockLabel(ts: number): string {
  return new Date(ts).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}
