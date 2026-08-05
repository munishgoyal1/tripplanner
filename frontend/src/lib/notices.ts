import { useSyncExternalStore } from "react";

// One global channel for everything transient the workspace wants to say:
// long-running operations, their outcomes, failures, and decisions the user
// still owes us. The top bar shows the single most important notice so the
// user always looks in the same place instead of hunting for a floating toast.
export type NoticeTone = "progress" | "success" | "error" | "decision";

export interface Notice {
  id: string;
  tone: NoticeTone;
  message: string;
}

// Higher wins when several notices are live at once. Ties go to the newest.
const RANK: Record<NoticeTone, number> = {
  error: 4,
  decision: 3,
  progress: 2,
  success: 1,
};

// Outcomes fade on their own; anything the user must act on stays put.
const AUTO_DISMISS_MS: Partial<Record<NoticeTone, number>> = { success: 4000 };

interface Entry extends Notice {
  seq: number;
}

const entries = new Map<string, Entry>();
const timers = new Map<string, ReturnType<typeof setTimeout>>();
const listeners = new Set<() => void>();
let sequence = 0;
let snapshot: Notice | null = null;

function clearTimer(id: string): void {
  const timer = timers.get(id);
  if (timer) {
    clearTimeout(timer);
    timers.delete(id);
  }
}

function publish(): void {
  let best: Entry | null = null;
  for (const entry of entries.values()) {
    if (!best || RANK[entry.tone] > RANK[best.tone] || (RANK[entry.tone] === RANK[best.tone] && entry.seq > best.seq)) {
      best = entry;
    }
  }
  snapshot = best ? { id: best.id, tone: best.tone, message: best.message } : null;
  for (const listener of listeners) listener();
}

/** Post or replace a notice. Reusing an id keeps one slot for an operation. */
export function notify(notice: Omit<Notice, "id"> & { id?: string }): string {
  const id = notice.id ?? `notice-${++sequence}`;
  clearTimer(id);
  entries.set(id, { id, tone: notice.tone, message: notice.message, seq: ++sequence });
  const ttl = AUTO_DISMISS_MS[notice.tone];
  if (ttl) timers.set(id, setTimeout(() => dismissNotice(id), ttl));
  publish();
  return id;
}

export function dismissNotice(id: string): void {
  clearTimer(id);
  if (entries.delete(id)) publish();
}

export function clearNotices(): void {
  for (const id of timers.keys()) clearTimeout(timers.get(id)!);
  timers.clear();
  entries.clear();
  publish();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** The notice the status bar would currently render. */
export function readNotice(): Notice | null {
  return snapshot;
}

export function useNotice(): Notice | null {
  return useSyncExternalStore(subscribe, readNotice, readNotice);
}
