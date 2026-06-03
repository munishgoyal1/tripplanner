import { useEffect, useRef, useState } from "react";
import { streamChat } from "../api";
import type { ChatMessage } from "../types";

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
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, activeTool]);

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setBusy(true);
    setMessages((m) => [...m, { role: "user", text }, { role: "assistant", text: "" }]);

    const usedTools = new Set<string>();
    await streamChat(text, {
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
      <header className="border-b bg-white px-5 py-3">
        <h1 className="text-lg font-semibold text-ink">Trip Planner</h1>
        <p className="text-xs text-slate-500">Powered by your AI travel agent</p>
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
        <div className="flex items-end gap-2">
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
            disabled={busy || !input.trim()}
            className="rounded-xl bg-brand px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
