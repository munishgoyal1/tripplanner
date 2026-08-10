import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDown,
  Check,
  Clock,
  Copy,
  Maximize2,
  MapPin,
  MessageSquare,
  Minimize2,
  Pencil,
  Send,
  Sparkles,
  Square,
  X,
} from "lucide-react";
import {
  getDisplayName,
  isAnonymousUser,
  fetchChatHistory,
  startNewTrip,
  syncAuth,
  fetchGuestDataSummary,
  migrateGuestData,
  getUserId,
  type AuthSession,
} from "../api";
import type { ChatMessage, TurnEffect } from "../types";
import { trackEvent } from "../analytics";
import { saveTurnMeta, withStoredTurnMeta } from "../turnMetadata";
import { openAccountSettings } from "./accountSettings";
import BrandIdentity from "./BrandIdentity";
import TripInputCard, { formatTripInputResponse } from "./TripInputCard";
import {
  elapsedLabel,
  useChatStream,
  waitGuidance,
  type AssistantTurnContext,
  type AssistantTurnStatus,
} from "../hooks/useChatStream";

interface Props {
  onTurnComplete: (tripId?: string, context?: AssistantTurnContext) => void | Promise<void>;
  /** Mirrors live Assistant work into workspace-level status surfaces. */
  onTurnStatus?: (status: AssistantTurnStatus | null) => void;
  /** Bump to reload the persisted transcript (e.g. after switching trips). */
  reloadToken?: number;
  /** Explicit trip id to load chat for (set during saved-trip switching). */
  tripIdHint?: string | null;
  /** Whether an authoritative trip existed when the turn began. */
  hasActiveTrip?: boolean;
  /** Where the active trip is going, so progress can name it. */
  destination?: string | null;
  /** Start a fresh planning chat (clears the active trip + general chat). */
  onNewTrip?: () => void;
  /** Called after a successful guest-data import so the App can refresh trip panel. */
  onImported?: () => void;
  /** Desktop owns global New trip/account/settings controls in its command bar. */
  hideGlobalControls?: boolean;
  /** A user-approved command-bar escalation into a real Assistant turn. */
  assistantRequest?: { id: number; message: string; proposalOnly?: boolean } | null;
  /**
   * Desktop dock shape: a single composer row (`bar`), a reading sheet above
   * that row (`sheet`), or the whole workspace height (`full`). `panel` is the
   * self-contained column used by mobile.
   */
  layout?: "panel" | "bar" | "sheet" | "full";
  /** Switch between the docked shapes from the dock's own controls. */
  onChangeLayout?: (layout: "bar" | "sheet" | "full") => void;
  /** Close the dock entirely. */
  onHide?: () => void;
  /** Stops the last completed turn changed, published by the workspace. */
  turnEffects?: { token: number; effects: TurnEffect[] } | null;
  /** Move Itinerary, Map, and Details to a stop named by a reply. */
  onEffectSelect?: (effect: TurnEffect) => void;
}

export type { AssistantTurnContext, AssistantTurnStatus } from "../hooks/useChatStream";

const GREETING: ChatMessage = {
  role: "assistant",
  text: "Where are you traveling from, where would you like to go, and roughly when? I'll build a complete first plan with sensible defaults, and you can change anything here.",
};

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

function clockLabel(ts: number): string {
  return new Date(ts).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

export default function ChatPanel({
  onTurnComplete,
  onTurnStatus,
  reloadToken = 0,
  tripIdHint = null,
  hasActiveTrip = false,
  destination = null,
  onNewTrip,
  onImported,
  hideGlobalControls = false,
  assistantRequest = null,
  layout = "panel",
  onChangeLayout,
  onHide,
  turnEffects = null,
  onEffectSelect,
}: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([GREETING]);
  const [input, setInput] = useState("");
  const [auth, setAuth] = useState<AuthSession>({ authenticated: false });
  // Guest-import banner: set when sign-in just occurred and the old guest account had data.
  const [guestBanner, setGuestBanner] = useState<{
    guestId: string;
    tripCount: number;
    hasPreferences: boolean;
  } | null>(null);
  const [guestMigrating, setGuestMigrating] = useState(false);
    // Becomes true once syncAuth resolves so the transcript effect doesn't
    // race against it and load old guest messages before we know the auth state.
    const [authChecked, setAuthChecked] = useState(false);
  const [transcriptReady, setTranscriptReady] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const topRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  // Reading position belongs to the reader: only follow the stream when the
  // reader is already at the bottom, and advertise new content otherwise.
  const atBottomRef = useRef(true);
  const [hasNewBelow, setHasNewBelow] = useState(false);
  const appliedEffectsTokenRef = useRef(0);
  const transcriptCacheRef = useRef<Map<string, ChatMessage[]>>(new Map());
  const loadedTranscriptRequestRef = useRef<string | null>(null);
  // Set to true immediately after a Google sign-in where the previous identity
  // was a guest web-* id. The transcript effect reads this and skips loading
  // the (now-irrelevant) guest chat, keeping the screen at GREETING + banner.
  const freshSignInRef = useRef(false);
  const handledAssistantRequestRef = useRef(0);
  const sendRequestedMessageRef = useRef<(message: string, proposalOnly?: boolean) => void>(() => {});
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const copyTimerRef = useRef<number | null>(null);
  const onSendStartRef = useRef<() => void>(() => setInput(""));
  const [copiedMessage, setCopiedMessage] = useState<number | null>(null);
  const {
    activeTool,
    busy,
    clearTurnArtifacts,
    failedRequest,
    progress,
    progressSeconds,
    receipts,
    retryFailedRequest,
    sendMessage,
    stopResponse,
    tripInputRequest,
  } = useChatStream({
    hasActiveTrip,
    destination,
    transcriptReady,
    setMessages,
    onSendStart: () => onSendStartRef.current(),
    onTurnComplete,
    onTurnStatus,
  });

  useEffect(() => {
    if (!assistantRequest || busy || !transcriptReady || handledAssistantRequestRef.current === assistantRequest.id) return;
    handledAssistantRequestRef.current = assistantRequest.id;
    sendRequestedMessageRef.current(assistantRequest.message, assistantRequest.proposalOnly);
  }, [assistantRequest, busy, transcriptReady]);

  useEffect(() => () => {
    if (copyTimerRef.current != null) window.clearTimeout(copyTimerRef.current);
  }, []);

  const cacheKey = tripIdHint && tripIdHint.trim() ? tripIdHint.trim() : "__active__";
  const transcriptRequestKey = JSON.stringify([cacheKey, reloadToken, tripIdHint]);

  // --- mic dictation (Web Speech API, Chrome/Edge/Safari) -------------------
  // Feature-detected at runtime; no SpeechRecognition types in lib.dom yet,
  // so we keep this loosely typed and guard everywhere.
  const recognitionRef = useRef<any>(null);
  const inputRef = useRef(input);
  inputRef.current = input;
  const SpeechRec =
    typeof window !== "undefined"
      ? (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
      : null;
  const micSupported = Boolean(SpeechRec);
  const [listening, setListening] = useState(false);

  const stopListening = () => {
    try {
      recognitionRef.current?.stop?.();
    } catch {
      // already stopped
    }
    setListening(false);
  };

  onSendStartRef.current = () => {
    if (listening) stopListening();
    setInput("");
  };

  const toggleListening = () => {
    if (!micSupported) return;
    if (listening) {
      stopListening();
      return;
    }
    try {
      const r = new SpeechRec();
      r.continuous = true;
      r.interimResults = true;
      r.lang = navigator.language || "en-US";
      // Snapshot what's already typed so we append rather than replace.
      const base = inputRef.current ? inputRef.current.trimEnd() + " " : "";
      let finalText = "";
      r.onresult = (ev: any) => {
        let interim = "";
        for (let i = ev.resultIndex; i < ev.results.length; i++) {
          const chunk = ev.results[i][0].transcript;
          if (ev.results[i].isFinal) finalText += chunk;
          else interim += chunk;
        }
        setInput((base + finalText + interim).replace(/\s+/g, " ").trimStart());
      };
      r.onerror = () => setListening(false);
      r.onend = () => setListening(false);
      recognitionRef.current = r;
      r.start();
      setListening(true);
    } catch {
      setListening(false);
    }
  };

  // If the user starts a turn while we're still listening, stop the mic so
  // it doesn't keep appending speech after the send.
  useEffect(() => {
    if (busy && listening) stopListening();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [busy]);

  // On load, learn whether Google OAuth is available and pick up any existing
  // session (the cookie mirrors its identity into localStorage via syncAuth).
  useEffect(() => {
    syncAuth().then((session) => {
      setAuth(session);
      // If we just obtained an authenticated session and the previous id was a
      // guest web-* identity, check whether that guest had any data worth importing.
      const prevGuestId = session.prev_guest_id;
      if (session.authenticated && session.user_id && prevGuestId) {
        // Mark a fresh sign-in so the transcript effect skips loading old guest
        // messages — the user should see a clean slate + the import banner.
        freshSignInRef.current = true;
        setMessages([GREETING]);
        transcriptCacheRef.current.clear();
        fetchGuestDataSummary(prevGuestId).then((summary) => {
          if (summary.has_data) {
            setGuestBanner({
              guestId: prevGuestId,
              tripCount: summary.trip_count,
              hasPreferences: Boolean(summary.has_preferences),
            });
          }
        });
      }
      if (session.authenticated && session.user_id && session.prev_user_id !== session.user_id) {
        window.dispatchEvent(new Event("tripplanner:identity-changed"));
      }
      // Always set authChecked LAST so the transcript effect only fires after
      // freshSignInRef is already in the correct state.
      setAuthChecked(true);
    });
  }, []);

  // Restore the persisted transcript on mount and whenever the active trip
  // changes (switching saved trips bumps `reloadToken`).
  // Gate on authChecked: don't run until syncAuth has resolved so that
  // freshSignInRef is already set and we never flash old guest messages.
  useEffect(() => {
    if (!authChecked) return;
    if (busy) return;
    if (loadedTranscriptRequestRef.current === transcriptRequestKey) return;
    loadedTranscriptRequestRef.current = transcriptRequestKey;
    // Skip transcript reload on a fresh sign-in from guest mode — the user
    // should see a clean GREETING + the import banner, not old guest messages.
    if (freshSignInRef.current) {
      freshSignInRef.current = false;
      setTranscriptReady(true);
      return;
    }
    let cancelled = false;
    setTranscriptReady(false);
    const cached = transcriptCacheRef.current.get(cacheKey);
    if (cached) {
      setMessages(cached);
    } else {
      setMessages([GREETING]);
    }
    fetchChatHistory(tripIdHint || undefined)
      .then((rows) => {
        if (cancelled) return;
        const next = rows.length ? withStoredTurnMeta(cacheKey, rows) : [GREETING];
        transcriptCacheRef.current.set(cacheKey, next);
        setMessages(next);
      })
      .catch(() => {
        if (loadedTranscriptRequestRef.current === transcriptRequestKey) {
          loadedTranscriptRequestRef.current = null;
        }
        /* keep whatever's on screen */
      })
      .finally(() => {
        if (!cancelled) setTranscriptReady(true);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authChecked, reloadToken, tripIdHint, cacheKey, busy, transcriptRequestKey]);

  useEffect(() => {
    clearTurnArtifacts();
  }, [cacheKey, clearTurnArtifacts, reloadToken, tripIdHint]);

  // Keep a fast in-memory snapshot keyed by trip id for instant switches.
  useEffect(() => {
    transcriptCacheRef.current.set(cacheKey, messages);
  }, [cacheKey, messages]);

  useEffect(() => {
    if (atBottomRef.current) {
      endRef.current?.scrollIntoView({ behavior: "smooth" });
      return;
    }
    setHasNewBelow(true);
  }, [messages, activeTool]);

  // Retain each turn's timing and stop links across a reload; the persisted
  // transcript itself is role + text only.
  useEffect(() => {
    if (!transcriptReady) return;
    saveTurnMeta(cacheKey, messages);
  }, [cacheKey, messages, transcriptReady]);

  useEffect(() => {
    if (!turnEffects || !turnEffects.effects.length) return;
    if (appliedEffectsTokenRef.current === turnEffects.token) return;
    appliedEffectsTokenRef.current = turnEffects.token;
    setMessages((current) => {
      const index = current.map((m) => m.role).lastIndexOf("assistant");
      if (index < 0) return current;
      const next = [...current];
      next[index] = { ...next[index], effects: turnEffects.effects };
      return next;
    });
  }, [turnEffects]);

  const handleTranscriptScroll = () => {
    const node = scrollRef.current;
    if (!node) return;
    const atBottom = node.scrollHeight - node.scrollTop - node.clientHeight < 48;
    atBottomRef.current = atBottom;
    if (atBottom) setHasNewBelow(false);
  };

  const jumpToLatest = () => {
    atBottomRef.current = true;
    setHasNewBelow(false);
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  const renderedTurns = useMemo(() => {
    let currentGroup: string | null = null;
    return messages.map((message, index) => {
      const label = message.ts ? turnGroupLabel(message.ts) : null;
      const group = label && label !== currentGroup ? label : null;
      if (label) currentGroup = label;
      return { message, index, group };
    });
  }, [messages]);

  // When the import banner appears, scroll to the top so it's immediately visible.
  useEffect(() => {
    if (guestBanner) {
      topRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [guestBanner]);

  async function startFresh() {
    if (busy) return;
    try {
      await startNewTrip();
    } catch (error) {
      setMessages((messages) => [
        ...messages,
        {
          role: "assistant",
          text: error instanceof Error ? error.message : "Could not start a new trip. Please try again.",
        },
      ]);
      return;
    }
    setMessages([GREETING]);
    setInput("");
    clearTurnArtifacts();
    onNewTrip?.();
    trackEvent("new_trip_started", { surface: "assistant" });
  }

  sendRequestedMessageRef.current = (message, proposalOnly) => {
    void sendMessage(message, { proposalOnly });
  };

  function send() {
    const outgoing = input.trim();
    if (!outgoing || busy || !transcriptReady) return;
    void sendMessage(outgoing);
  }

  async function copyMessage(text: string, index: number) {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedMessage(index);
      if (copyTimerRef.current != null) window.clearTimeout(copyTimerRef.current);
      copyTimerRef.current = window.setTimeout(() => setCopiedMessage(null), 1600);
    } catch {
      setCopiedMessage(null);
    }
  }

  function editAndResend(text: string) {
    setInput(text);
    window.requestAnimationFrame(() => {
      composerRef.current?.focus();
      composerRef.current?.setSelectionRange(text.length, text.length);
    });
  }

  // A question from the agent lives in the transcript, so a collapsed dock has
  // to open far enough to answer it.
  useEffect(() => {
    if (tripInputRequest && layout === "bar") onChangeLayout?.("sheet");
  }, [tripInputRequest, layout, onChangeLayout]);

  const docked = layout !== "panel";
  const wideTurns = layout === "full";
  const lastReply = useMemo(
    () => [...messages].reverse().find((m) => m.role === "assistant" && m.text) ?? null,
    [messages],
  );

  const brandHeader = (
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-100 bg-white/85 px-5 py-3 backdrop-blur">
        <div className="flex items-center gap-3">
          <div>
            <BrandIdentity />
            <p className="ml-[46px] mt-0.5 text-xs text-muted">Your AI travel concierge</p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          {!hideGlobalControls && <button
            onClick={startFresh}
            disabled={busy || !transcriptReady}
            title="Start a new trip plan"
            aria-label="Start a new trip plan"
            className="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium text-slate-700 ring-1 ring-slate-200 transition hover:bg-slate-50 hover:text-ink disabled:opacity-40"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 5v14M5 12h14" />
            </svg>
            <span className="hidden sm:inline">New trip</span>
          </button>}
          <div>
            {!hideGlobalControls && <button
              onClick={() => openAccountSettings()}
              title="Account settings"
              aria-label="Account settings"
              className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-semibold text-slate-600 transition hover:bg-slate-50"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                <circle cx="12" cy="7" r="4" />
              </svg>
              <span className="max-w-[8rem] truncate">
                {auth.authenticated
                  ? auth.display_name || "Account"
                  : isAnonymousUser()
                  ? "Sign in"
                  : getDisplayName() || "Account"}
              </span>
            </button>}
          </div>
        </div>
      </header>
  );

  const transcriptBlock = (
      <div className="relative min-h-0 flex-1">
      <div
        ref={scrollRef}
        data-testid="chat-transcript"
        onScroll={handleTranscriptScroll}
        className="h-full space-y-4 overflow-y-auto bg-surface px-5 py-5"
      >
        {/* Guest-import banner: shown once after OAuth sign-in when guest had data */}
        {guestBanner && (
          <div ref={topRef} className="flex items-start gap-3 rounded-2xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm shadow-card">
            <span className="mt-0.5 text-sky-600">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
            </span>
            <div className="flex-1">
              <p className="font-medium text-sky-900">
                {guestBanner.tripCount > 0
                  ? `You have ${guestBanner.tripCount} trip${guestBanner.tripCount !== 1 ? "s" : ""} from your guest session.`
                  : "You have travel preferences from your guest session."}
              </p>
              <p className="mt-0.5 text-xs text-sky-700">
                Import {guestBanner.tripCount > 0 && guestBanner.hasPreferences ? "them" : "this data"} into your account so it is available across devices.
              </p>
              <div className="mt-2 flex gap-2">
                <button
                  disabled={guestMigrating}
                  onClick={async () => {
                    setGuestMigrating(true);
                    const authId = getUserId();
                    const result = await migrateGuestData(authId, guestBanner.guestId);
                    if (!result.ok) {
                      setGuestMigrating(false);
                      return;
                    }
                    setGuestBanner(null);
                    setGuestMigrating(false);
                    // Clear in-memory cache so the next transcript load
                    // fetches the freshly migrated chat from the server.
                    transcriptCacheRef.current.clear();
                    // Notify App to refresh the trip panel and trip switcher.
                    onImported?.();
                    // Load the migrated chat transcript in-place.
                    fetchChatHistory(tripIdHint || undefined).then((rows) => {
                      const next = rows.length
                        ? rows.map((r) => ({ role: r.role, text: r.text }))
                        : [GREETING];
                      setMessages(next);
                    });
                  }}
                  className="rounded-full bg-sky-600 px-3 py-1 text-xs font-medium text-white hover:bg-sky-700 disabled:opacity-50"
                >
                  {guestMigrating ? "Importing…" : "Import my trips"}
                </button>
                <button
                  disabled={guestMigrating}
                  onClick={() => {
                    setGuestBanner(null);
                    // Load the authenticated user's own chat (empty is fine — start fresh).
                    transcriptCacheRef.current.clear();
                    fetchChatHistory(tripIdHint || undefined).then((rows) => {
                      const next = rows.length
                        ? rows.map((r) => ({ role: r.role, text: r.text }))
                        : [GREETING];
                      setMessages(next);
                    });
                  }}
                  className="rounded-full px-3 py-1 text-xs text-sky-700 hover:bg-sky-100"
                >
                  No thanks
                </button>
              </div>
            </div>
          </div>
        )}
        {renderedTurns.map(({ message: m, index: i, group }) => (
          <Fragment key={i}>
          {group && (
            <div className="flex items-center gap-3 pt-1" role="separator" aria-label={group}>
              <span className="h-px flex-1 bg-slate-200" />
              <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">{group}</span>
              <span className="h-px flex-1 bg-slate-200" />
            </div>
          )}
          <div
            className={`group flex flex-col ${m.role === "user" ? "items-end" : "items-start"}`}
          >
            {m.role === "user" && m.ts !== undefined && (
              <div className="mb-1 px-1 text-[10px] text-slate-400">{clockLabel(m.ts)}</div>
            )}
            <div
              className={`${wideTurns ? "max-w-[min(56rem,94%)]" : "max-w-[88%]"} rounded-lg px-3.5 py-2.5 text-sm leading-relaxed shadow-card ring-1 ${
                m.role === "user"
                  ? "rounded-br-sm bg-gradient-to-br from-brand to-brand-600 text-white ring-brand/30"
                  : "bg-white text-ink ring-slate-200"
              }`}
            >
              {m.role === "assistant" && (
                <div className="mb-1.5 flex items-center gap-1.5">
                  <Sparkles size={11} className="shrink-0 text-brand" aria-hidden />
                  <span className="text-[10px] font-bold uppercase tracking-wide text-slate-400">
                    Assistant
                  </span>
                  {m.ts !== undefined && (
                    <span className="text-[10px] text-slate-400">{clockLabel(m.ts)}</span>
                  )}
                  {m.seconds !== undefined && (
                    <span
                      title={`This reply took ${turnDurationLabel(m.seconds)}`}
                      className="ml-auto inline-flex items-center gap-1 rounded-sm bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500"
                    >
                      <Clock size={10} aria-hidden /> {turnDurationLabel(m.seconds)}
                    </span>
                  )}
                </div>
              )}
              <div className="whitespace-pre-wrap">
              {m.text || (busy && i === messages.length - 1 ? "…" : "")}
              </div>
              {m.tools && m.tools.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {m.tools.map((t) => {
                    const trace = m.tool_trace?.find((x) => x.name === t);
                    const tip = trace?.args
                      ? trace.duration_ms !== undefined
                        ? `${trace.args} · ${trace.duration_ms}ms`
                        : trace.args
                      : trace?.duration_ms !== undefined
                        ? `${trace.duration_ms}ms`
                        : undefined;
                    return (
                      <span
                        key={t}
                        title={tip}
                        className={`rounded-full px-2 py-0.5 text-[10px] ${
                          m.role === "user"
                            ? "bg-white/20 text-white/90"
                            : "bg-slate-100 text-slate-500"
                        }`}
                      >
                        {t}
                        {trace?.duration_ms !== undefined && (
                          <span className="ml-1 text-slate-400">
                            {trace.duration_ms}ms
                          </span>
                        )}
                      </span>
                    );
                  })}
                </div>
              )}
            </div>
            {m.role === "assistant" && Boolean(m.effects?.length) && (
              <div className="mt-1.5 flex flex-wrap items-center gap-1.5 px-1">
                {m.effects?.map((effect, effectIndex) =>
                  effect.change === "removed" ? (
                    <span
                      key={`${effect.name}-${effectIndex}`}
                      title={`${effect.name} was removed from the plan`}
                      className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-400 line-through"
                    >
                      <MapPin size={10} aria-hidden />
                      {effect.name}
                    </span>
                  ) : (
                    <button
                      key={`${effect.name}-${effectIndex}`}
                      type="button"
                      onClick={() => onEffectSelect?.(effect)}
                      title={`Go to ${effect.name}${effect.day ? ` on day ${effect.day}` : ""}`}
                      className="inline-flex items-center gap-1 rounded-full bg-brand/10 px-2 py-0.5 text-[10px] font-semibold text-brand transition hover:bg-brand/20"
                    >
                      <MapPin size={10} aria-hidden />
                      {effect.name}
                      {effect.day ? <span className="text-brand/70">D{effect.day}</span> : null}
                    </button>
                  ),
                )}
              </div>
            )}
            {m.text && !(busy && i === messages.length - 1) && (
              <div className="mt-1 flex min-h-7 items-center gap-0.5 px-1 text-slate-400 opacity-60 transition group-focus-within:opacity-100 group-hover:opacity-100">
                <button
                  type="button"
                  onClick={() => void copyMessage(m.text, i)}
                  title={copiedMessage === i ? "Copied" : "Copy message"}
                  aria-label={copiedMessage === i ? "Message copied" : "Copy message"}
                  className="rounded-md p-1.5 hover:bg-white hover:text-ink focus:opacity-100 focus:outline-none focus:ring-2 focus:ring-brand/20"
                >
                  {copiedMessage === i ? <Check size={15} /> : <Copy size={15} />}
                </button>
                {m.role === "user" && (
                  <button
                    type="button"
                    onClick={() => editAndResend(m.text)}
                    disabled={busy}
                    title="Edit in the composer and send as a new instruction"
                    aria-label="Edit message"
                    className="rounded-md p-1.5 hover:bg-white hover:text-ink focus:opacity-100 focus:outline-none focus:ring-2 focus:ring-brand/20 disabled:opacity-30"
                  >
                    <Pencil size={15} />
                  </button>
                )}
              </div>
            )}
          </div>
          </Fragment>
        ))}
        {busy && progress && (
          <div className="flex items-start gap-2 rounded-md border border-brand/15 bg-brand/[0.04] px-3 py-2.5 text-xs text-muted" role="status" aria-live="polite">
            <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-brand" />
            <span className="min-w-0">
              <span className="block font-medium text-ink">{progress.label}…</span>
              <span className="mt-0.5 block leading-relaxed">
                {elapsedLabel(progressSeconds)} · {waitGuidance(!hasActiveTrip, progressSeconds)}
              </span>
              {receipts.length > 0 && (
                <span className="mt-2 block space-y-1 border-t border-brand/10 pt-2">
                  {receipts.map((receipt) => (
                    <span key={receipt.seq} className="block text-[11px] leading-snug text-muted">
                      <span className="tabular-nums text-muted/70">{receipt.at}</span>{" "}
                      <span className="text-ink">{receipt.text}</span>
                      {receipt.detail && <span> · {receipt.detail}</span>}
                      {receipt.source && <span className="text-muted/70"> · {receipt.source}</span>}
                    </span>
                  ))}
                </span>
              )}
            </span>
          </div>
        )}
        {tripInputRequest && (
          <TripInputCard
            key={tripInputRequest.request_id}
            request={tripInputRequest}
            disabled={busy}
            onSubmit={(values) => void sendMessage(formatTripInputResponse(tripInputRequest, values))}
            onSkip={() => void sendMessage("Use the prefilled defaults and continue.")}
          />
        )}
        <div ref={endRef} />
      </div>
      {hasNewBelow && (
        <button
          type="button"
          onClick={jumpToLatest}
          className="absolute bottom-3 left-1/2 z-20 inline-flex -translate-x-1/2 items-center gap-1.5 rounded-full bg-ink px-3 py-1.5 text-xs font-semibold text-white shadow-pop"
        >
          <ArrowDown size={13} aria-hidden /> Jump to latest
        </button>
      )}
      </div>
  );

  const composerBlock = (
      <div className={docked ? "min-w-0 flex-1" : "border-t border-slate-100 bg-white p-4"}>
        {failedRequest && (
          <button
            onClick={retryFailedRequest}
            disabled={busy}
            className="mb-2 text-xs font-medium text-brand hover:underline disabled:opacity-40"
          >
            Retry request
          </button>
        )}
        <div className="flex items-end gap-2">
          {micSupported && (
            <button
              onClick={toggleListening}
              disabled={busy}
              title={listening ? "Stop dictation" : "Start voice dictation"}
              aria-label={listening ? "Stop dictation" : "Start voice dictation"}
              aria-pressed={listening}
              className={`rounded-full p-2.5 ring-1 transition disabled:opacity-40 ${
                listening
                  ? "bg-brand text-white ring-brand shadow-pop animate-pulse"
                  : "text-slate-500 ring-slate-200 hover:bg-slate-50 hover:text-ink"
              }`}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="9" y="3" width="6" height="12" rx="3" />
                <path d="M5 11a7 7 0 0 0 14 0" />
                <line x1="12" y1="18" x2="12" y2="22" />
                <line x1="9" y1="22" x2="15" y2="22" />
              </svg>
            </button>
          )}
          <textarea
            ref={composerRef}
            className="flex-1 resize-none rounded-2xl border border-slate-200 bg-white px-4 py-2.5 text-sm shadow-sm transition placeholder:text-slate-400 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
            rows={docked ? 1 : 2}
            placeholder="e.g. Plan a 5-day trip to Goa in December for 2 people"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            disabled={busy || !transcriptReady}
          />
          <button
            onClick={busy ? stopResponse : send}
            disabled={!busy && (!transcriptReady || !input.trim())}
            title={busy ? "Stop response" : "Send message"}
            aria-label={busy ? "Stop response" : "Send"}
            className={busy
              ? "grid h-11 w-11 shrink-0 place-items-center rounded-full bg-ink text-white transition hover:bg-slate-700"
              : "btn-primary grid h-11 w-11 shrink-0 place-items-center rounded-full p-0"
            }
          >
            {busy ? <Square size={15} fill="currentColor" /> : <Send size={18} />}
          </button>
        </div>
      </div>
  );

  if (!docked) {
    return (
      <div className="flex h-full flex-col bg-white">
        {brandHeader}
        {transcriptBlock}
        {composerBlock}
      </div>
    );
  }

  const dockButton = "inline-flex shrink-0 items-center gap-1.5 rounded-sm px-2 py-1.5 text-[11px] font-semibold text-slate-600 transition hover:bg-slate-100 hover:text-ink";
  const dockControls = (
    <>
      {layout === "bar" ? (
        <button type="button" onClick={() => onChangeLayout?.("sheet")} className={dockButton}>
          <MessageSquare size={12} aria-hidden /> Conversation
        </button>
      ) : (
        <button
          type="button"
          onClick={() => onChangeLayout?.("bar")}
          title="Minimize the conversation back to the bottom row"
          className={dockButton}
        >
          <Minimize2 size={12} aria-hidden /> Minimize
        </button>
      )}
      <button
        type="button"
        onClick={() => onChangeLayout?.(layout === "full" ? "sheet" : "full")}
        title={layout === "full" ? "Restore the conversation sheet" : "Maximize the conversation"}
        className={dockButton}
      >
        {layout === "full" ? <Minimize2 size={12} aria-hidden /> : <Maximize2 size={12} aria-hidden />}
        {layout === "full" ? "Restore" : "Maximize"}
      </button>
      {onHide && (
        <button type="button" onClick={onHide} title="Hide chat" aria-label="Hide Chat" className={dockButton}>
          <X size={12} aria-hidden />
        </button>
      )}
    </>
  );

  return (
    <div className="relative bg-white">
      {layout !== "bar" && (
        <div
          className={`absolute inset-x-0 bottom-full z-30 flex flex-col border-t border-slate-200 bg-white shadow-pop ${
            layout === "full" ? "h-[calc(100dvh-7.5rem)]" : "h-[58vh]"
          }`}
        >
          <div className="flex shrink-0 items-center gap-2 border-b border-slate-200 px-3 py-2">
            <MessageSquare size={13} className="text-brand" aria-hidden />
            <p className="text-[12px] font-semibold text-ink">Chat</p>
            <div className="ml-auto flex items-center gap-1">{dockControls}</div>
          </div>
          {transcriptBlock}
        </div>
      )}
      <div className="flex items-center gap-2 px-3 py-2">
        <div className="flex shrink-0 items-center gap-1">{layout === "bar" ? dockControls : null}</div>
        {layout === "bar" && (
          <p className="hidden min-w-0 flex-1 truncate text-[11px] text-slate-500 lg:block">
            {busy && progress ? (
              <>
                <span className="font-semibold text-ink">{progress.label}…</span>{" "}
                {elapsedLabel(progressSeconds)}
              </>
            ) : lastReply ? (
              <>
                <span className="font-semibold text-slate-600">Last reply</span> · {lastReply.text}
              </>
            ) : null}
          </p>
        )}
        {composerBlock}
      </div>
    </div>
  );
}
