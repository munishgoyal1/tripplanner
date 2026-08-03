import { useCallback, useEffect, useRef, useState } from "react";
import { streamChat } from "../api";
import { trackEvent } from "../analytics";
import type { ChatMessage, TripInputRequest } from "../types";

export interface AssistantTurnStatus {
  phase: "working" | "loading" | "complete" | "error";
  message: string;
}

export interface AssistantTurnContext {
  proposalOnly: boolean;
  startedWithoutTrip: boolean;
}

interface FailedRequest {
  message: string;
  proposalOnly: boolean;
  requestId: string;
}

interface UseChatStreamOptions {
  hasActiveTrip: boolean;
  transcriptReady: boolean;
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>;
  onSendStart?: () => void;
  onTurnComplete: (tripId?: string, context?: AssistantTurnContext) => void | Promise<void>;
  onTurnStatus?: (status: AssistantTurnStatus | null) => void;
}

interface SendMessageOptions {
  proposalOnly?: boolean;
  requestId?: string;
  retrying?: boolean;
}

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

export function waitGuidance(isNewTrip: boolean, seconds: number): string {
  if (seconds >= 120) {
    return "Full builds usually take about 2–4 minutes. Still working; no need to refresh.";
  }
  return isNewTrip
    ? "Full itinerary builds usually take about 2–4 minutes."
    : "Updates are usually quicker; a full rebuild can take about 2–4 minutes.";
}

export function elapsedLabel(seconds: number): string {
  if (seconds < 60) return `${seconds}s elapsed`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s elapsed`;
}

export function useChatStream({
  hasActiveTrip,
  transcriptReady,
  setMessages,
  onSendStart,
  onTurnComplete,
  onTurnStatus,
}: UseChatStreamOptions) {
  const [busy, setBusy] = useState(false);
  const [tripInputRequest, setTripInputRequest] = useState<TripInputRequest | null>(null);
  const [failedRequest, setFailedRequest] = useState<FailedRequest | null>(null);
  const [activeTool, setActiveTool] = useState<{ name: string; args?: string } | null>(null);
  const [progress, setProgress] = useState<{ label: string; startedAt: number } | null>(null);
  const [progressSeconds, setProgressSeconds] = useState(0);
  const streamControllerRef = useRef<AbortController | null>(null);
  const turnStartedAtRef = useRef(0);
  const publishedTurnStatusRef = useRef("");

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

  useEffect(() => {
    if (!busy || !progress) return;
    const publishedSeconds = Math.floor(progressSeconds / 10) * 10;
    const message = `${progress.label}. ${elapsedLabel(publishedSeconds)}. ${waitGuidance(!hasActiveTrip, publishedSeconds)}`;
    if (publishedTurnStatusRef.current === message) return;
    publishedTurnStatusRef.current = message;
    onTurnStatus?.({ phase: "working", message });
  }, [busy, hasActiveTrip, onTurnStatus, progress, progressSeconds]);

  useEffect(() => () => {
    streamControllerRef.current?.abort();
  }, []);

  useEffect(() => () => onTurnStatus?.(null), [onTurnStatus]);

  async function sendMessage(outgoing: string, options: SendMessageOptions = {}): Promise<void> {
    const proposalOnly = options.proposalOnly ?? false;
    const requestId = options.requestId ?? crypto.randomUUID();
    const retrying = options.retrying ?? false;
    if (!outgoing.trim() || busy || !transcriptReady) return;

    onSendStart?.();
    setFailedRequest(null);
    setTripInputRequest(null);
    setBusy(true);
    turnStartedAtRef.current = Date.now();
    publishedTurnStatusRef.current = "";
    setProgress({ label: PROGRESS_LABELS.thinking, startedAt: turnStartedAtRef.current });
    const streamController = new AbortController();
    streamControllerRef.current = streamController;
    trackEvent("planning_started", { proposal_only: proposalOnly, retry: retrying });
    setMessages((messages) => [
      ...(retrying ? messages.slice(0, -2) : messages),
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
      setMessages((messages) => {
        const copy = [...messages];
        copy[copy.length - 1] = {
          ...copy[copy.length - 1],
          text: copy[copy.length - 1].text + text,
        };
        return copy;
      });
    };
    const discardPendingTokens = () => {
      pendingTokens = "";
      if (tokenFrame != null) window.cancelAnimationFrame(tokenFrame);
      tokenFrame = null;
    };
    let handledError = false;

    try {
      await streamChat(outgoing, {
        onToken: (text) => {
          pendingTokens += text;
          if (tokenFrame == null) tokenFrame = window.requestAnimationFrame(flushTokens);
        },
        onProgress: (stage) => {
          setProgress({ label: PROGRESS_LABELS[stage], startedAt: turnStartedAtRef.current });
        },
        onInputRequest: setTripInputRequest,
        onTool: (name, phase, extras) => {
          if (phase === "start") {
            usedTools.add(name);
            toolTrace.push({ name, args: extras?.args });
            setActiveTool({ name, args: extras?.args });
            setProgress({ label: toolProgressLabel(name), startedAt: turnStartedAtRef.current });
            return;
          }
          for (let index = toolTrace.length - 1; index >= 0; index--) {
            if (toolTrace[index].name === name && toolTrace[index].duration_ms === undefined) {
              toolTrace[index].duration_ms = extras?.duration_ms;
              break;
            }
          }
          setActiveTool(null);
        },
        onDone: (_reply, tripId) => {
          if (tokenFrame != null) window.cancelAnimationFrame(tokenFrame);
          flushTokens();
          setActiveTool(null);
          setProgress(null);
          onTurnStatus?.({
            phase: "loading",
            message: "The planning work is complete. Loading your updated itinerary now.",
          });
          setMessages((messages) => {
            const copy = [...messages];
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
          void onTurnComplete(tripId, {
            proposalOnly,
            startedWithoutTrip: !hasActiveTrip,
          });
        },
        onError: (message) => {
          if (streamController.signal.aborted) return;
          handledError = true;
          discardPendingTokens();
          setActiveTool(null);
          setProgress(null);
          onTurnStatus?.({
            phase: "error",
            message: "The Assistant hit an error. Your previous itinerary is still available.",
          });
          setMessages((messages) => {
            const copy = [...messages];
            copy[copy.length - 1] = { role: "assistant", text: `Warning: ${message}` };
            return copy;
          });
          setFailedRequest({ message: outgoing, proposalOnly, requestId });
          trackEvent("planning_failed", { proposal_only: proposalOnly });
        },
      }, { proposalOnly, requestId, signal: streamController.signal });
    } catch (error) {
      if (streamController.signal.aborted) {
        discardPendingTokens();
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
        discardPendingTokens();
        setActiveTool(null);
        setProgress(null);
        onTurnStatus?.({
          phase: "error",
          message: "The Assistant could not finish that update. Your previous itinerary is still available.",
        });
        setMessages((messages) => {
          const copy = [...messages];
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

  function stopResponse(): void {
    streamControllerRef.current?.abort();
    setActiveTool(null);
    setProgress(null);
    onTurnStatus?.(null);
  }

  const clearTurnArtifacts = useCallback((): void => {
    setFailedRequest(null);
    setTripInputRequest(null);
  }, []);

  function retryFailedRequest(): void {
    if (!failedRequest) return;
    void sendMessage(failedRequest.message, {
      proposalOnly: failedRequest.proposalOnly,
      requestId: failedRequest.requestId,
      retrying: true,
    });
  }

  return {
    activeTool,
    busy,
    clearTurnArtifacts,
    failedRequest,
    progress,
    progressSeconds,
    retryFailedRequest,
    sendMessage,
    stopResponse,
    tripInputRequest,
  };
}