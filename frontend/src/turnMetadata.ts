// The persisted transcript is role+text only, so a reload would otherwise drop
// the duration, timestamp, and stop links a turn carries. Keep that display
// metadata beside it, keyed by trip, instead of widening the agent's history
// contract.
import type { ChatMessage, TurnEffect } from "./types";

interface TurnMeta {
  ts?: number;
  seconds?: number;
  effects?: TurnEffect[];
}

type Store = Record<string, Record<string, TurnMeta>>;

const STORAGE_KEY = "tripplanner_turn_meta_v1";
const MAX_TRIPS = 12;
// The bucket a conversation uses before it has a trip of its own.
const GENERAL_KEY = "__active__";

function fingerprint(text: string): string {
  let hash = 0;
  for (let index = 0; index < text.length; index++) {
    hash = (hash * 31 + text.charCodeAt(index)) | 0;
  }
  return `${text.length}.${hash.toString(36)}`;
}

// Position cannot be part of the key: the live transcript carries a greeting the
// server never stores, so every turn would shift by one on reload. Identity is
// the turn itself, with a counter to separate genuinely repeated turns.
function signatures(messages: ChatMessage[]): string[] {
  const seen = new Map<string, number>();
  return messages.map((message) => {
    const base = `${message.role}:${fingerprint(message.text)}`;
    const occurrence = seen.get(base) ?? 0;
    seen.set(base, occurrence + 1);
    return `${base}:${occurrence}`;
  });
}

function readStore(): Store {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Store) : {};
  } catch {
    return {};
  }
}

function writeStore(store: Store): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
  } catch {
    /* private mode or quota — timing simply falls back to session-only */
  }
}

/** Re-attach stored timing and effects to a transcript loaded from the server. */
export function withStoredTurnMeta(tripKey: string, messages: ChatMessage[]): ChatMessage[] {
  const store = readStore();
  // A trip created mid-conversation inherits the turns it was planned from, so
  // the pre-trip bucket answers until that trip has saved a bucket of its own.
  const stored = store[tripKey] ?? store[GENERAL_KEY];
  if (!stored) return messages;
  const keys = signatures(messages);
  return messages.map((message, index) => {
    const meta = stored[keys[index]];
    if (!meta) return message;
    return {
      ...message,
      ts: message.ts ?? meta.ts,
      seconds: message.seconds ?? meta.seconds,
      effects: message.effects ?? meta.effects,
    };
  });
}

/** Persist the display metadata of every turn that carries any. */
export function saveTurnMeta(tripKey: string, messages: ChatMessage[]): void {
  // A transcript that failed to load shows only the greeting; treating that as
  // "this trip has no timing" would erase the history it could not read.
  if (!messages.some((message) => message.role === "user")) return;
  const entries: Record<string, TurnMeta> = {};
  const keys = signatures(messages);
  messages.forEach((message, index) => {
    if (message.ts === undefined && message.seconds === undefined && !message.effects?.length) return;
    entries[keys[index]] = {
      ts: message.ts,
      seconds: message.seconds,
      effects: message.effects,
    };
  });
  const store = readStore();
  if (!Object.keys(entries).length) {
    if (!store[tripKey]) return;
    delete store[tripKey];
    writeStore(store);
    return;
  }
  store[tripKey] = entries;
  const tripKeys = Object.keys(store);
  for (const stale of tripKeys.slice(0, Math.max(0, tripKeys.length - MAX_TRIPS))) {
    if (stale !== tripKey) delete store[stale];
  }
  writeStore(store);
}
