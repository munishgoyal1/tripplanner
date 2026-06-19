import { useEffect, useRef, useState } from "react";
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
  type AuthSession,
} from "../api";
import type { ChatMessage } from "../types";
import SettingsModal from "./SettingsModal";

interface Props {
  onTurnComplete: () => void;
  /** Bump to reload the persisted transcript (e.g. after switching trips). */
  reloadToken?: number;
  /** Explicit trip id to load chat for (set during saved-trip switching). */
  tripIdHint?: string | null;
  /** Start a fresh planning chat (clears the active trip + general chat). */
  onNewTrip?: () => void;
}

const GREETING: ChatMessage = {
  role: "assistant",
  text: "Hi! Tell me where and when you'd like to travel and I'll plan it.",
};

export default function ChatPanel({
  onTurnComplete,
  reloadToken = 0,
  tripIdHint = null,
  onNewTrip,
}: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([GREETING]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [activeTool, setActiveTool] = useState<{ name: string; args?: string } | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [showAccount, setShowAccount] = useState(false);
  const [nameInput, setNameInput] = useState(getDisplayName());
  const [googleEnabled, setGoogleEnabled] = useState(false);
  const [auth, setAuth] = useState<AuthSession>({ authenticated: false });
  const [attachments, setAttachments] = useState<string[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const transcriptCacheRef = useRef<Map<string, ChatMessage[]>>(new Map());

  const cacheKey = tripIdHint && tripIdHint.trim() ? tripIdHint.trim() : "__active__";

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
    syncAuth().then(setAuth);
  }, []);

  // Restore the persisted transcript on mount and whenever the active trip
  // changes (switching saved trips bumps `reloadToken`).
  useEffect(() => {
    if (busy) return;
    let cancelled = false;
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
        /* keep whatever's on screen */
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reloadToken, tripIdHint, cacheKey, busy]);

  // Keep a fast in-memory snapshot keyed by trip id for instant switches.
  useEffect(() => {
    transcriptCacheRef.current.set(cacheKey, messages);
  }, [cacheKey, messages]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, activeTool]);

  async function startFresh() {
    if (busy) return;
    try {
      await startNewTrip();
    } catch {
      /* best-effort; still reset the UI */
    }
    setMessages([GREETING]);
    setInput("");
    setAttachments([]);
    onNewTrip?.();
  }

  async function send() {
    const text = input.trim();
    if ((!text && attachments.length === 0) || busy) return;
    if (listening) stopListening();
    const note =
      attachments.length > 0
        ? `\n\n[attached: ${attachments.join(", ")}]`
        : "";
    const outgoing = (text + note).trim();
    setInput("");
    setAttachments([]);
    setBusy(true);
    setMessages((m) => [
      ...m,
      { role: "user", text: outgoing },
      { role: "assistant", text: "" },
    ]);

    const usedTools = new Set<string>();
    const toolTrace: { name: string; args?: string; duration_ms?: number }[] = [];
    await streamChat(outgoing, {
      onToken: (t) =>
        setMessages((m) => {
          const copy = [...m];
          copy[copy.length - 1] = {
            ...copy[copy.length - 1],
            text: copy[copy.length - 1].text + t,
          };
          return copy;
        }),
      onTool: (name, phase, extras) => {
        if (phase === "start") {
          usedTools.add(name);
          toolTrace.push({ name, args: extras?.args });
          setActiveTool({ name, args: extras?.args });
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
      onDone: () => {
        setActiveTool(null);
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
        onTurnComplete();
      },
      onError: (msg) => {
        setActiveTool(null);
        setMessages((m) => {
          const copy = [...m];
          copy[copy.length - 1] = { role: "assistant", text: `⚠️ ${msg}` };
          return copy;
        });
        setBusy(false);
      },
    });
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
          <button
            onClick={startFresh}
            disabled={busy}
            title="Start a new trip plan"
            aria-label="Start a new trip plan"
            className="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium text-slate-700 ring-1 ring-slate-200 transition hover:bg-slate-50 hover:text-ink disabled:opacity-40"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 5v14M5 12h14" />
            </svg>
            <span className="hidden sm:inline">New trip</span>
          </button>
          <div className="relative">
            <button
              onClick={() => setShowAccount((s) => !s)}
              title="Account"
              aria-label="Account"
              className="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm text-slate-700 ring-1 ring-slate-200 transition hover:bg-slate-50 hover:text-ink"
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
            </button>
            {showAccount && (
              <div className="absolute right-0 z-20 mt-1 w-64 rounded-xl border border-slate-200 bg-white p-3 text-sm shadow-lg">
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
                      className="w-full rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100"
                    >
                      Sign out
                    </button>
                  </>
                ) : (
                  <>
                    {googleEnabled && (
                      <button
                        onClick={() => loginWithGoogle()}
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
              </div>
            )}
          </div>
          <button
            onClick={() => setShowSettings(true)}
            title="Travel preferences"
            aria-label="Travel preferences"
            className="rounded-full p-2 text-slate-500 ring-1 ring-slate-200 transition hover:bg-slate-50 hover:text-ink"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </svg>
          </button>
        </div>
      </header>

      <div className="flex-1 space-y-4 overflow-y-auto bg-surface px-5 py-5">
        {messages.map((m, i) => (
          <div
            key={i}
            className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
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
          </div>
        ))}
        {activeTool && (
          <div className="flex items-center gap-2 text-xs text-muted">
            <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-brand" />
            <span>
              running <span className="font-medium text-ink">{activeTool.name}</span>
              {activeTool.args ? (
                <span className="text-muted/80">({activeTool.args})</span>
              ) : null}
              …
            </span>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div className="border-t border-slate-100 bg-white p-4">
        {attachments.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1">
            {attachments.map((name, i) => (
              <span
                key={i}
                className="flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600"
              >
                📎 {name}
                <button
                  onClick={() => setAttachments((a) => a.filter((_, j) => j !== i))}
                  className="text-slate-400 hover:text-ink"
                >
                  ✕
                </button>
              </span>
            ))}
          </div>
        )}
        <div className="flex items-end gap-2">
          <input
            ref={fileRef}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => {
              const names = Array.from(e.target.files ?? []).map((f) => f.name);
              if (names.length) setAttachments((a) => [...a, ...names]);
              e.target.value = "";
            }}
          />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={busy}
            title="Attach a file"
            aria-label="Attach a file"
            className="rounded-full p-2.5 text-slate-500 ring-1 ring-slate-200 transition hover:bg-slate-50 hover:text-ink disabled:opacity-40"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
            </svg>
          </button>
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
            disabled={busy}
          />
          <button
            onClick={send}
            disabled={busy || (!input.trim() && attachments.length === 0)}
            className="btn-primary px-5"
          >
            Send
          </button>
        </div>
      </div>

      {showSettings && <SettingsModal onClose={() => setShowSettings(false)} />}
    </div>
  );
}
