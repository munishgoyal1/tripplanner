import { useSyncExternalStore } from "react";

// One global channel for everything transient the workspace wants to say:
// long-running operations, their outcomes, failures, and decisions the user
// still owes us. The top bar shows the single most important notice so the
// user always looks in the same place instead of hunting for a floating toast.
export type NoticeTone = "progress" | "success" | "error" | "decision";

export interface Notice {
  id: string;
  tone: NoticeTone;
  /** One short line: what happened. */
  message: string;
  /** Everything after the headline: why, what it cost, what to do next. */
  detail?: string;
}

// Higher wins when several notices are live at once. Ties go to the newest.
const RANK: Record<NoticeTone, number> = {
  error: 4,
  decision: 3,
  progress: 2,
  success: 1,
};

// Nothing expires on a timer. A notice that vanishes while the user is still
// reading it is worse than one that lingers, and the next notice replaces this
// one anyway. Outcomes stay until something newer has something to say.

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
  snapshot = best
    ? { id: best.id, tone: best.tone, message: best.message, detail: best.detail }
    : null;
  for (const listener of listeners) listener();
}

/** Post or replace a notice. Reusing an id keeps one slot for an operation. */
export function notify(notice: Omit<Notice, "id"> & { id?: string }): string {
  const id = notice.id ?? `notice-${++sequence}`;
  clearTimer(id);
  entries.set(id, {
    id,
    tone: notice.tone,
    message: notice.message,
    detail: notice.detail,
    seq: ++sequence,
  });
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
