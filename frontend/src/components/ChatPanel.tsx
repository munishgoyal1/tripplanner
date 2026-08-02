import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check, Copy, Pencil, Send, Square } from "lucide-react";
import {
  streamChat,
  signIn,
  signOut,
  getDisplayName,
  isAnonymousUser,
  fetchAuthConfig,
  fetchChatHistory,
  startNewTrip,
  syncAuth,
  loginWithGoogle,
  logoutGoogle,
  runPrivacyAction,
  fetchGuestDataSummary,
  migrateGuestData,
  getUserId,
  type AuthSession,
} from "../api";
import type { ChatMessage, TripInputRequest } from "../types";
import { trackEvent } from "../analytics";
import AccountSettingsHub from "./AccountSettingsHub";
import SettingsModal from "./SettingsModal";
import TripInputCard, { formatTripInputResponse } from "./TripInputCard";

interface Props {
  onTurnComplete: (tripId?: string) => void;
  /** Bump to reload the persisted transcript (e.g. after switching trips). */
  reloadToken?: number;
  /** Explicit trip id to load chat for (set during saved-trip switching). */
  tripIdHint?: string | null;
  /** Start a fresh planning chat (clears the active trip + general chat). */
  onNewTrip?: () => void;
  /** Called after a successful guest-data import so the App can refresh trip panel. */
  onImported?: () => void;
  /** Desktop owns global New trip/account/settings controls in its command bar. */
  hideGlobalControls?: boolean;
  /** A user-approved command-bar escalation into a real Assistant turn. */
  assistantRequest?: { id: number; message: string; proposalOnly?: boolean } | null;
}

const GREETING: ChatMessage = {
  role: "assistant",
  text: "Where are you traveling from, where would you like to go, and roughly when? I'll build a complete first plan with sensible defaults, and you can change anything here.",
};

const PROGRESS_LABELS = {
  thinking: "Thinking through your request",
  reviewing: "Reviewing the results",
  saving: "Saving your trip updates",
} as const;

function toolProgressLabel(name: string): string {
  if (/flight/i.test(name)) return "Searching live flights";
  if (/hotel/i.test(name)) return "Searching hotels";
  if (/restaurant/i.test(name)) return "Finding restaurants";
  if (/place|review|activit/i.test(name)) return "Checking places and reviews";
  if (/route|optimi/i.test(name)) return "Working out routes";
  if (/weather/i.test(name)) return "Checking the weather";
  if (/visa/i.test(name)) return "Checking entry requirements";
  if (/event/i.test(name)) return "Finding local events";
  if (/preference|memory|profile/i.test(name)) return "Reviewing your preferences";
  if (/update|create|finalize|plan/i.test(name)) return "Updating your itinerary";
  if (/web_search/i.test(name)) return "Researching current information";
  return "Working on your trip";
}

export default function ChatPanel({
  onTurnComplete,
  reloadToken = 0,
  tripIdHint = null,
  onNewTrip,
  onImported,
  hideGlobalControls = false,
  assistantRequest = null,
}: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([GREETING]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [tripInputRequest, setTripInputRequest] = useState<TripInputRequest | null>(null);
  const [failedRequest, setFailedRequest] = useState<{
    message: string;
    proposalOnly: boolean;
    requestId: string;
  } | null>(null);
  const [activeTool, setActiveTool] = useState<{ name: string; args?: string } | null>(null);
  const [progress, setProgress] = useState<{ label: string; startedAt: number } | null>(null);
  const [progressSeconds, setProgressSeconds] = useState(0);
  const [showSettings, setShowSettings] = useState(false);
  const [showAccount, setShowAccount] = useState(false);
  const [nameInput, setNameInput] = useState(getDisplayName());
  const [googleEnabled, setGoogleEnabled] = useState(false);
  const [auth, setAuth] = useState<AuthSession>({ authenticated: false });
  const [privacyBusy, setPrivacyBusy] = useState(false);
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
  const accountRef = useRef<HTMLDivElement>(null);
  const transcriptCacheRef = useRef<Map<string, ChatMessage[]>>(new Map());
  const loadedTranscriptRequestRef = useRef<string | null>(null);
  // Set to true immediately after a Google sign-in where the previous identity
  // was a guest web-* id. The transcript effect reads this and skips loading
  // the (now-irrelevant) guest chat, keeping the screen at GREETING + banner.
  const freshSignInRef = useRef(false);
  const handledAssistantRequestRef = useRef(0);
  const sendRequestedMessageRef = useRef<(message: string, proposalOnly?: boolean) => void>(() => {});
  const streamControllerRef = useRef<AbortController | null>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const copyTimerRef = useRef<number | null>(null);
  const [copiedMessage, setCopiedMessage] = useState<number | null>(null);

  useEffect(() => {
    if (!assistantRequest || busy || !transcriptReady || handledAssistantRequestRef.current === assistantRequest.id) return;
    handledAssistantRequestRef.current = assistantRequest.id;
    sendRequestedMessageRef.current(assistantRequest.message, assistantRequest.proposalOnly);
  }, [assistantRequest, busy, transcriptReady]);

  useEffect(() => {
    if (!progress) {
      setProgressSeconds(0);
      return;
    }
    const update = () => setProgressSeconds(Math.floor((Date.now() - progress.startedAt) / 1000));
    update();
    const timer = window.setInterval(update, 1000);
    return () => window.clearInterval(timer);
  }, [progress]);

  useEffect(() => () => {
    streamControllerRef.current?.abort();
    if (copyTimerRef.current != null) window.clearTimeout(copyTimerRef.current);
  }, []);

  useEffect(() => {
    const openAccount = () => setShowAccount(true);
    const openSettings = () => setShowSettings(true);
    window.addEventListener("tripplanner:open-account", openAccount);
    window.addEventListener("tripplanner:open-settings", openSettings);
    return () => {
      window.removeEventListener("tripplanner:open-account", openAccount);
      window.removeEventListener("tripplanner:open-settings", openSettings);
    };
  }, []);

  useEffect(() => {
    if (!showAccount) return;
    const dismissOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setShowAccount(false);
    };
    window.addEventListener("keydown", dismissOnEscape);
    return () => window.removeEventListener("keydown", dismissOnEscape);
  }, [showAccount]);

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
    fetchAuthConfig().then((c) => setGoogleEnabled(c.google));
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
        const next = rows.length ? rows.map((r) => ({ role: r.role, text: r.text })) : [GREETING];
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
    setFailedRequest(null);
    setTripInputRequest(null);
  }, [cacheKey, reloadToken, tripIdHint]);

  // Keep a fast in-memory snapshot keyed by trip id for instant switches.
  useEffect(() => {
    transcriptCacheRef.current.set(cacheKey, messages);
  }, [cacheKey, messages]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, activeTool]);

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
    setFailedRequest(null);
    setTripInputRequest(null);
    onNewTrip?.();
    trackEvent("new_trip_started", { surface: "assistant" });
  }

  async function sendMessage(
    outgoing: string,
    proposalOnly = false,
    requestId: string = crypto.randomUUID(),
    retrying = false,
  ) {
    if (!outgoing.trim() || busy || !transcriptReady) return;
    if (listening) stopListening();
    setInput("");
    setFailedRequest(null);
    setTripInputRequest(null);
    setBusy(true);
    setProgress({ label: PROGRESS_LABELS.thinking, startedAt: Date.now() });
    const streamController = new AbortController();
    streamControllerRef.current = streamController;
    trackEvent("planning_started", { proposal_only: proposalOnly, retry: retrying });
    setMessages((m) => [
      ...(retrying ? m.slice(0, -2) : m),
      { role: "user", text: outgoing },
      { role: "assistant", text: "" },
    ]);

    const usedTools = new Set<string>();
    const toolTrace: { name: string; args?: string; duration_ms?: number }[] = [];
    let pendingTokens = "";
    let tokenFrame: number | null = null;
    const flushTokens = () => {
      tokenFrame = null;
      if (!pendingTokens) return;
      const text = pendingTokens;
      pendingTokens = "";
      setMessages((m) => {
        const copy = [...m];
        copy[copy.length - 1] = {
          ...copy[copy.length - 1],
          text: copy[copy.length - 1].text + text,
        };
        return copy;
      });
    };
    let handledError = false;
    try {
      await streamChat(outgoing, {
        onToken: (text) => {
          setProgress(null);
          pendingTokens += text;
          if (tokenFrame == null) tokenFrame = window.requestAnimationFrame(flushTokens);
        },
      onProgress: (stage) => {
        setProgress({ label: PROGRESS_LABELS[stage], startedAt: Date.now() });
      },
      onInputRequest: (request) => {
        setTripInputRequest(request);
      },
      onTool: (name, phase, extras) => {
        if (phase === "start") {
          usedTools.add(name);
          toolTrace.push({ name, args: extras?.args });
          setActiveTool({ name, args: extras?.args });
          setProgress({ label: toolProgressLabel(name), startedAt: Date.now() });
        } else {
          // Attach the duration to the most recent matching start entry that
          // doesn't already have one.
          for (let i = toolTrace.length - 1; i >= 0; i--) {
            if (toolTrace[i].name === name && toolTrace[i].duration_ms === undefined) {
              toolTrace[i].duration_ms = extras?.duration_ms;
              break;
            }
          }
          setActiveTool(null);
        }
      },
      onDone: (_reply, tripId) => {
        if (tokenFrame != null) window.cancelAnimationFrame(tokenFrame);
        flushTokens();
        setActiveTool(null);
        setProgress(null);
        setMessages((m) => {
          const copy = [...m];
          copy[copy.length - 1] = {
            ...copy[copy.length - 1],
            tools: Array.from(usedTools),
            tool_trace: toolTrace.slice(),
          };
          return copy;
        });
        setBusy(false);
        setFailedRequest(null);
        trackEvent("planning_completed", { proposal_only: proposalOnly });
        onTurnComplete(tripId);
      },
        onError: (msg) => {
          if (streamController.signal.aborted) return;
          handledError = true;
          pendingTokens = "";
          if (tokenFrame != null) window.cancelAnimationFrame(tokenFrame);
          tokenFrame = null;
          setActiveTool(null);
          setProgress(null);
          setMessages((m) => {
            const copy = [...m];
            copy[copy.length - 1] = { role: "assistant", text: `Warning: ${msg}` };
            return copy;
          });
          setFailedRequest({ message: outgoing, proposalOnly, requestId });
          trackEvent("planning_failed", { proposal_only: proposalOnly });
        },
      }, { proposalOnly, requestId, signal: streamController.signal });
    } catch (error) {
      if (streamController.signal.aborted) {
        pendingTokens = "";
        if (tokenFrame != null) window.cancelAnimationFrame(tokenFrame);
        tokenFrame = null;
        setMessages((current) => {
          const next = [...current];
          const draft = next[next.length - 1];
          if (draft?.role === "assistant") {
            const partial = draft.text.trimEnd();
            next[next.length - 1] = {
              ...draft,
              text: partial ? `${partial}\n\nResponse stopped.` : "Response stopped.",
            };
          }
          return next;
        });
      } else if (!handledError) {
        pendingTokens = "";
        if (tokenFrame != null) window.cancelAnimationFrame(tokenFrame);
        tokenFrame = null;
        setActiveTool(null);
        setProgress(null);
        setMessages((m) => {
          const copy = [...m];
          copy[copy.length - 1] = {
            role: "assistant",
            text: `Warning: ${error instanceof Error ? error.message : "The chat request failed."}`,
          };
          return copy;
        });
        setFailedRequest({ message: outgoing, proposalOnly, requestId });
        trackEvent("planning_failed", { proposal_only: proposalOnly });
      }
    } finally {
      if (streamControllerRef.current === streamController) {
        streamControllerRef.current = null;
      }
      setActiveTool(null);
      setProgress(null);
      if (tokenFrame != null) window.cancelAnimationFrame(tokenFrame);
      flushTokens();
      setBusy(false);
    }
  }

  sendRequestedMessageRef.current = (message, proposalOnly) => {
    void sendMessage(message, proposalOnly);
  };

  function send() {
    void sendMessage(input.trim());
  }

  function stopResponse() {
    streamControllerRef.current?.abort();
    setActiveTool(null);
    setProgress(null);
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

  async function handleDeleteTripHistory() {
    const ok = window.confirm(
      "Delete all saved trips and related chat history for this account? This cannot be undone."
    );
    if (!ok) return;
    setPrivacyBusy(true);
    try {
      const res = await runPrivacyAction("delete_trip_history");
      if (!res.ok) {
        window.alert(res.message || "Could not delete trip history.");
        return;
      }
      await startFresh();
      window.alert("Trip history deleted.");
      setShowAccount(false);
    } finally {
      setPrivacyBusy(false);
    }
  }

  async function handleClearAllData() {
    const typed = window.prompt('Type DELETE to clear all your app data for this account.');
    if ((typed || "").trim().toUpperCase() !== "DELETE") return;
    setPrivacyBusy(true);
    try {
      const res = await runPrivacyAction("clear_all_data", typed || "");
      if (!res.ok) {
        window.alert(res.message || "Could not clear data.");
        return;
      }
      await startFresh();
      window.alert("All app data cleared for this account.");
      setShowAccount(false);
    } finally {
      setPrivacyBusy(false);
    }
  }

  async function handleDeleteAccountData() {
    const typed = window.prompt(
      'Type DELETE to delete this app account data. This clears all app data and signs you out.'
    );
    if ((typed || "").trim().toUpperCase() !== "DELETE") return;
    setPrivacyBusy(true);
    try {
      const res = await runPrivacyAction("delete_account", typed || "");
      if (!res.ok) {
        window.alert(res.message || "Could not delete account data.");
        return;
      }
      if (auth.authenticated) {
        await logoutGoogle();
      } else {
        signOut();
      }
      window.alert("Account data deleted.");
      window.location.reload();
    } finally {
      setPrivacyBusy(false);
    }
  }

  return (
    <div className="flex h-full flex-col bg-white">
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-100 bg-white/85 px-5 py-3 backdrop-blur">
        <div className="flex items-center gap-3">
          <span className="grid h-9 w-9 place-items-center rounded-2xl bg-gradient-to-br from-brand to-brand-700 text-base text-white shadow-sm">
            ✈
          </span>
          <div>
            <h1 className="display text-lg font-semibold leading-tight text-ink">
              Trip Planner
            </h1>
            <p className="text-xs text-muted">Your AI travel concierge</p>
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
              onClick={() => setShowAccount(true)}
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
            {false && showAccount && createPortal(
              <div ref={accountRef} className="fixed right-3 top-14 z-[100] w-64 rounded-xl border border-slate-200 bg-white p-3 text-sm shadow-lg">
                {auth.authenticated ? (
                  <>
                    <div className="mb-2 flex items-center gap-2">
                      {auth.picture && (
                        <img
                          src={auth.picture}
                          alt=""
                          className="h-8 w-8 rounded-full"
                          referrerPolicy="no-referrer"
                        />
                      )}
                      <div className="min-w-0">
                        <p className="truncate font-medium text-ink">
                          {auth.display_name || "Signed in"}
                        </p>
                        {auth.email && (
                          <p className="truncate text-xs text-slate-500">{auth.email}</p>
                        )}
                      </div>
                    </div>
                    <button
                      onClick={async () => {
                        await logoutGoogle();
                        window.location.reload();
                      }}
                      disabled={privacyBusy}
                      className="w-full rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100"
                    >
                      Sign out
                    </button>
                  </>
                ) : (
                  <>
                    {googleEnabled && (
                      <button
                        onClick={() => {
                          trackEvent("login", { method: "google_start" });
                          loginWithGoogle();
                        }}
                        className="mb-3 flex w-full items-center justify-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                      >
                        <svg width="16" height="16" viewBox="0 0 24 24">
                          <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1z" />
                          <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23z" />
                          <path fill="#FBBC05" d="M5.84 14.1a6.6 6.6 0 0 1 0-4.2V7.06H2.18a11 11 0 0 0 0 9.88l3.66-2.84z" />
                          <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1A11 11 0 0 0 2.18 7.06l3.66 2.84C6.71 7.31 9.14 5.38 12 5.38z" />
                        </svg>
                        Sign in with Google
                      </button>
                    )}
                    <p className="mb-2 text-xs text-slate-500">
                      {googleEnabled ? "Or sign in with a name. " : ""}Your
                      preferences and trips follow this identity across devices.
                      (Use “local” to share state with the CLI.)
                    </p>
                <input
                  className="w-full rounded-lg border border-slate-200 px-2 py-1.5 text-sm focus:border-brand focus:outline-none"
                  placeholder="Your name"
                  value={nameInput}
                  onChange={(e) => setNameInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && nameInput.trim()) {
                      trackEvent("login", { method: "name" });
                      signIn(nameInput);
                      setShowAccount(false);
                      window.location.reload();
                    }
                  }}
                />
                <div className="mt-2 flex justify-between gap-2">
                  {!isAnonymousUser() && (
                    <button
                      onClick={() => {
                        signOut();
                        window.location.reload();
                      }}
                      className="rounded-lg px-3 py-1.5 text-xs text-slate-500 hover:bg-slate-100"
                    >
                      Sign out
                    </button>
                  )}
                  <button
                    onClick={() => {
                      if (!nameInput.trim()) return;
                      trackEvent("login", { method: "name" });
                      signIn(nameInput);
                      setShowAccount(false);
                      window.location.reload();
                    }}
                    disabled={!nameInput.trim()}
                    className="ml-auto rounded-lg bg-brand px-3 py-1.5 text-xs font-medium text-white disabled:opacity-40"
                  >
                    Sign in
                  </button>
                </div>
                  </>
                )}

                <div className="my-3 h-px bg-slate-200" />

                <button
                  onClick={() => {
                    window.dispatchEvent(new Event("tripplanner:analytics-settings"));
                    setShowAccount(false);
                  }}
                  className="mb-2 w-full rounded-lg border border-slate-200 px-3 py-1.5 text-left text-xs text-slate-600 hover:bg-slate-100"
                >
                  Analytics preferences
                </button>

                <button
                  onClick={() => {
                    setShowSettings(true);
                    setShowAccount(false);
                  }}
                  disabled={privacyBusy}
                  className="mb-2 w-full rounded-lg border border-slate-200 px-3 py-1.5 text-left text-xs text-slate-600 hover:bg-slate-100"
                >
                  Edit preferences
                </button>

                <button
                  onClick={handleDeleteTripHistory}
                  disabled={privacyBusy}
                  className="mb-2 w-full rounded-lg border border-amber-200 bg-amber-50 px-3 py-1.5 text-left text-xs text-amber-800 hover:bg-amber-100 disabled:opacity-50"
                >
                  Delete trip history
                </button>

                <button
                  onClick={handleClearAllData}
                  disabled={privacyBusy}
                  className="mb-2 w-full rounded-lg border border-rose-200 bg-rose-50 px-3 py-1.5 text-left text-xs text-rose-800 hover:bg-rose-100 disabled:opacity-50"
                >
                  Clear all my data
                </button>

                <button
                  onClick={handleDeleteAccountData}
                  disabled={privacyBusy}
                  className="w-full rounded-lg border border-rose-300 bg-rose-100 px-3 py-1.5 text-left text-xs font-medium text-rose-900 hover:bg-rose-200 disabled:opacity-50"
                >
                  Delete account
                </button>

                <p className="mt-2 text-[10px] text-slate-500">
                  Privacy controls follow a GDPR-style model: access/edit, delete trip history,
                  erase all app data, and account data deletion.
                </p>
              </div>,
              document.body,
            )}
          </div>
          {false && !hideGlobalControls && <button
            onClick={() => setShowSettings(true)}
            title="Travel preferences"
            aria-label="Travel preferences"
            className="rounded-full p-2 text-slate-500 ring-1 ring-slate-200 transition hover:bg-slate-50 hover:text-ink"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </svg>
          </button>}
        </div>
      </header>

      <div className="flex-1 space-y-4 overflow-y-auto bg-surface px-5 py-5">
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
        {messages.map((m, i) => (
          <div
            key={i}
            className={`group flex flex-col ${m.role === "user" ? "items-end" : "items-start"}`}
          >
            <div
              className={`max-w-[82%] whitespace-pre-wrap rounded-3xl px-4 py-2.5 text-sm leading-relaxed shadow-card ring-1 ${
                m.role === "user"
                  ? "bg-gradient-to-br from-brand to-brand-600 text-white ring-brand/30"
                  : "bg-white text-ink ring-slate-100"
              }`}
            >
              {m.text || (busy && i === messages.length - 1 ? "…" : "")}
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
        ))}
        {busy && progress && (
          <div className="flex items-center gap-2 text-xs text-muted">
            <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-brand" />
            <span>
              <span className="font-medium text-ink">{progress.label}</span>
              {progressSeconds >= 2 ? ` · ${progressSeconds}s` : ""}…
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

      <div className="border-t border-slate-100 bg-white p-4">
        {failedRequest && (
          <button
            onClick={() => void sendMessage(
              failedRequest.message,
              failedRequest.proposalOnly,
              failedRequest.requestId,
              true,
            )}
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
            rows={2}
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

      {showSettings && createPortal(
        <SettingsModal onClose={() => setShowSettings(false)} />,
        document.body,
      )}
      {showAccount && createPortal(
        <AccountSettingsHub
          auth={auth}
          googleEnabled={googleEnabled}
          localIdentityActive={!isAnonymousUser()}
          nameInput={nameInput}
          privacyBusy={privacyBusy}
          onNameInputChange={setNameInput}
          onClose={() => setShowAccount(false)}
          onGoogleSignIn={() => {
            trackEvent("login", { method: "google_start" });
            loginWithGoogle();
          }}
          onLocalSignIn={() => {
            if (!nameInput.trim()) return;
            trackEvent("login", { method: "name" });
            signIn(nameInput);
            setShowAccount(false);
            window.location.reload();
          }}
          onSignOut={async () => {
            if (auth.authenticated) await logoutGoogle();
            else signOut();
            window.location.reload();
          }}
          onOpenTravelProfile={() => {
            setShowAccount(false);
            setShowSettings(true);
          }}
          onOpenAnalytics={() => {
            setShowAccount(false);
            window.dispatchEvent(new Event("tripplanner:analytics-settings"));
          }}
          onDeleteTripHistory={() => void handleDeleteTripHistory()}
          onClearAllData={() => void handleClearAllData()}
          onDeleteAccount={() => void handleDeleteAccountData()}
        />,
        document.body,
      )}
    </div>
  );
}
