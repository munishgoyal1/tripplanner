import { useEffect, useRef, useState } from "react";
import {
  streamChat,
  signIn,
  signOut,
  getDisplayName,
  isAnonymousUser,
  fetchAuthConfig,
  syncAuth,
  loginWithGoogle,
  logoutGoogle,
  type AuthSession,
} from "../api";
import type { ChatMessage } from "../types";
import SettingsModal from "./SettingsModal";

interface Props {
  onTurnComplete: () => void;
}

export default function ChatPanel({ onTurnComplete }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      text: "Hi! Tell me where and when you'd like to travel and I'll plan it.",
    },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [activeTool, setActiveTool] = useState<string | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [showAccount, setShowAccount] = useState(false);
  const [nameInput, setNameInput] = useState(getDisplayName());
  const [googleEnabled, setGoogleEnabled] = useState(false);
  const [auth, setAuth] = useState<AuthSession>({ authenticated: false });
  const [attachments, setAttachments] = useState<string[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  // On load, learn whether Google OAuth is available and pick up any existing
  // session (the cookie mirrors its identity into localStorage via syncAuth).
  useEffect(() => {
    fetchAuthConfig().then((c) => setGoogleEnabled(c.google));
    syncAuth().then(setAuth);
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, activeTool]);

  async function send() {
    const text = input.trim();
    if ((!text && attachments.length === 0) || busy) return;
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
      onTool: (name, phase) => {
        if (phase === "start") {
          usedTools.add(name);
          setActiveTool(name);
        } else {
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
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b bg-white px-5 py-3">
        <div>
          <h1 className="text-lg font-semibold text-ink">Trip Planner</h1>
          <p className="text-xs text-slate-500">Powered by your AI travel agent</p>
        </div>
        <div className="flex items-center gap-1">
          <div className="relative">
            <button
              onClick={() => setShowAccount((s) => !s)}
              title="Account"
              aria-label="Account"
              className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-sm text-slate-600 hover:bg-slate-100 hover:text-ink"
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
            className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 hover:text-ink"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </svg>
          </button>
        </div>
      </header>

      <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
        {messages.map((m, i) => (
          <div
            key={i}
            className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[80%] whitespace-pre-wrap rounded-2xl px-4 py-2 text-sm shadow-sm ${
                m.role === "user"
                  ? "bg-brand text-white"
                  : "bg-white text-ink"
              }`}
            >
              {m.text || (busy && i === messages.length - 1 ? "…" : "")}
              {m.tools && m.tools.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {m.tools.map((t) => (
                    <span
                      key={t}
                      className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-500"
                    >
                      {t}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        {activeTool && (
          <div className="text-xs italic text-slate-400">running {activeTool}…</div>
        )}
        <div ref={endRef} />
      </div>

      <div className="border-t bg-white p-3">
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
            className="rounded-xl p-2 text-slate-500 hover:bg-slate-100 hover:text-ink disabled:opacity-40"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
            </svg>
          </button>
          <textarea
            className="flex-1 resize-none rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-brand focus:outline-none"
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
            className="rounded-xl bg-brand px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
          >
            Send
          </button>
        </div>
      </div>

      {showSettings && <SettingsModal onClose={() => setShowSettings(false)} />}
    </div>
  );
}
