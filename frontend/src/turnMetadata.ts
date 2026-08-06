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

function fingerprint(text: string): string {
  let hash = 0;
  for (let index = 0; index < text.length; index++) {
    hash = (hash * 31 + text.charCodeAt(index)) | 0;
  }
  return `${text.length}.${hash.toString(36)}`;
}

function signature(message: ChatMessage, index: number): string {
  return `${index}:${message.role}:${fingerprint(message.text)}`;
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
  const stored = readStore()[tripKey];
  if (!stored) return messages;
  return messages.map((message, index) => {
    const meta = stored[signature(message, index)];
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
  const entries: Record<string, TurnMeta> = {};
  messages.forEach((message, index) => {
    if (message.ts === undefined && message.seconds === undefined && !message.effects?.length) return;
    entries[signature(message, index)] = {
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
  const keys = Object.keys(store);
  for (const stale of keys.slice(0, Math.max(0, keys.length - MAX_TRIPS))) {
    if (stale !== tripKey) delete store[stale];
  }
  writeStore(store);
}
