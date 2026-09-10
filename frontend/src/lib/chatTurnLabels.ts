function startOfDay(value: Date): number {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime();
}

/** Epoch ms, epoch seconds, or an ISO string — always as a local Date. */
export function clockDate(ts: number | string): Date {
  if (typeof ts === "string") {
    const parsed = Date.parse(ts);
    if (!Number.isNaN(parsed)) return new Date(parsed);
    const numeric = Number(ts);
    if (!Number.isNaN(numeric)) return clockDate(numeric);
    return new Date(Number.NaN);
  }
  const ms = ts > 0 && ts < 1_000_000_000_000 ? ts * 1000 : ts;
  return new Date(ms);
}

/** Label a turn by when it happened, so a multi-day session reads as a ledger. */
export function turnGroupLabel(ts: number, now: number = Date.now()): string {
  const when = clockDate(ts);
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

export function clockLabel(ts: number | string): string {
  return clockDate(ts).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}
