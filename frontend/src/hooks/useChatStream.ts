import { useCallback, useEffect, useRef, useState } from "react";
import { streamChat } from "../api";
import { trackEvent } from "../analytics";
import type { ChatMessage, TripInputRequest } from "../types";

export interface AssistantTurnStatus {
  phase: "working" | "loading" | "complete" | "error";
  message: string;
  detail?: string;
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
  /** Where the active trip is going, so the status can name it. */
  destination?: string | null;
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

/** The same work, named as a subject the user can recognise in a list. */
function toolTopic(name: string): string {
  if (/flight/i.test(name)) return "flights";
  if (/hotel/i.test(name)) return "hotels";
  if (/restaurant/i.test(name)) return "food";
  if (/place|review|activit/i.test(name)) return "places";
  if (/route|optimi/i.test(name)) return "routes";
  if (/weather/i.test(name)) return "weather";
  if (/visa/i.test(name)) return "entry rules";
  if (/event/i.test(name)) return "events";
  if (/preference|memory|profile/i.test(name)) return "your preferences";
  if (/update|create|finalize|plan/i.test(name)) return "the itinerary";
  if (/web_search/i.test(name)) return "current information";
  return "";
}

function joinTopics(topics: string[]): string {
  if (topics.length <= 1) return topics[0] ?? "";
  return `${topics.slice(0, -1).join(", ")} and ${topics[topics.length - 1]}`;
}

/** The destination the agent itself just named, read back from its tool call.
 *
 * On a first build there is no trip to read a destination from, and the user's
 * own prompt has already scrolled out of a one-row composer. Guessing at their
 * wording would put a wrong place name in the heading, so this takes the value
 * the agent passed to the planning tool and nothing else.
 */
export function destinationFromToolArgs(name: string, args?: string): string | null {
  if (!args || !/trip|plan|itinerar/i.test(name)) return null;
  const match = /(?:^|,\s*)destination=([^,]+)/i.exec(args);
  const place = match?.[1]?.trim().replace(/[.\u2026]+$/, "").trim();
  if (!place || place.length > 40 || /^(none|null|undefined)$/i.test(place)) return null;
  return place;
}

/** "Building your Goa itinerary" beats "Building your itinerary" when the
 * composer is one row tall and the request has scrolled away. */
export function progressHeading(hasTrip: boolean, place?: string | null): string {
  const named = (place ?? "").trim();
  if (!named) return hasTrip ? "Updating your trip" : "Building your itinerary";
  return hasTrip ? `Updating your ${named} trip` : `Building your ${named} itinerary`;
}

/** Short enough to sit in a list of clauses rather than end a sentence. */
export function waitHint(isNewTrip: boolean, seconds: number): string {
  if (seconds >= 120) return "still working, no need to refresh";
  return isNewTrip ? "full builds take about 2\u20134 minutes" : "a full rebuild takes about 2\u20134 minutes";
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
  destination,
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
  const [coveredTopics, setCoveredTopics] = useState<string[]>([]);
  const [plannedPlace, setPlannedPlace] = useState<string | null>(null);
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
    // The heading stays still so the user is not re-reading a line that keeps
    // changing shape; the detail carries what actually moved. Only work that
    // really happened is listed — inventing plausible-sounding stages would
    // make the status a decoration rather than a report.
    const heading = progressHeading(hasActiveTrip, destination || plannedPlace);
    const detail = [
      progress.label,
      coveredTopics.length ? `covered ${joinTopics(coveredTopics)}` : null,
      elapsedLabel(publishedSeconds),
      waitHint(!hasActiveTrip, publishedSeconds),
    ]
      .filter(Boolean)
      .join(" \u00b7 ");
    if (publishedTurnStatusRef.current === `${heading}|${detail}`) return;
    publishedTurnStatusRef.current = `${heading}|${detail}`;
    onTurnStatus?.({ phase: "working", message: heading, detail });
  }, [
    busy,
    coveredTopics,
    destination,
    hasActiveTrip,
    onTurnStatus,
    plannedPlace,
    progress,
    progressSeconds,
  ]);

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
    setCoveredTopics([]);
    setPlannedPlace(null);
    setProgress({ label: PROGRESS_LABELS.thinking, startedAt: turnStartedAtRef.current });
    const streamController = new AbortController();
    streamControllerRef.current = streamController;
    trackEvent("planning_started", { proposal_only: proposalOnly, retry: retrying });
    setMessages((messages) => [
      ...(retrying ? messages.slice(0, -2) : messages),
      { role: "user", text: outgoing, ts: turnStartedAtRef.current },
      { role: "assistant", text: "" },
    ]);

    const usedTools = new Set<string>();
    const toolTrace: { name: string; args?: string; duration_ms?: number }[] = [];
    const turnSeconds = () => Math.max(1, Math.round((Date.now() - turnStartedAtRef.current) / 1000));
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
            const place = destinationFromToolArgs(name, extras?.args);
            if (place) setPlannedPlace(place);
            setProgress({ label: toolProgressLabel(name), startedAt: turnStartedAtRef.current });
            return;
          }
          for (let index = toolTrace.length - 1; index >= 0; index--) {
            if (toolTrace[index].name === name && toolTrace[index].duration_ms === undefined) {
              toolTrace[index].duration_ms = extras?.duration_ms;
              break;
            }
          }
          const topic = toolTopic(name);
          if (topic) {
            setCoveredTopics((current) =>
              current.includes(topic) ? current : [...current, topic],
            );
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
            message: "Planning complete",
            detail: "Loading your updated itinerary now.",
          });
          setMessages((messages) => {
            const copy = [...messages];
            copy[copy.length - 1] = {
              ...copy[copy.length - 1],
              tools: Array.from(usedTools),
              tool_trace: toolTrace.slice(),
              ts: Date.now(),
              seconds: turnSeconds(),
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
            message: "The Assistant hit an error",
            detail: "Your previous itinerary is still available.",
          });
          setMessages((messages) => {
            const copy = [...messages];
            copy[copy.length - 1] = {
              role: "assistant",
              text: `Warning: ${message}`,
              ts: Date.now(),
              seconds: turnSeconds(),
            };
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
              ts: Date.now(),
              seconds: turnSeconds(),
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
            ts: Date.now(),
            seconds: turnSeconds(),
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