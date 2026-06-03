import { useEffect, useRef, useState } from "react";
import { streamChat } from "../api";
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
  const [attachments, setAttachments] = useState<string[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

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
