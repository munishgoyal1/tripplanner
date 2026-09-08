import type { TurnEffect } from "../types";

/** Cut at a word boundary so a status line never ends mid-word. */
function clip(text: string, max: number): string {
  const flat = text.replace(/\s+/g, " ").trim();
  if (flat.length <= max) return flat;
  const cut = flat.slice(0, max);
  const space = cut.lastIndexOf(" ");
  const kept = space > max * 0.6 ? cut.slice(0, space) : cut;
  return `${kept.replace(/[\s,;:.\u2026-]+$/, "")}\u2026`;
}

/** The user's own words, because a one-row composer no longer shows them. */
export function requestEcho(request: string, max = 64): string {
  const flat = clip(request ?? "", max);
  return flat ? `\u201c${flat}\u201d` : "";
}

/** The first thing the Assistant actually said, stripped of chat formatting. */
export function answerGist(reply: string, max = 150): string {
  const flat = (reply ?? "")
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/^\s*[-*\u2022]\s+/gm, "")
    .replace(/[*_`#>]/g, "")
    .replace(/\s+/g, " ")
    .trim();
  if (!flat) return "";
  const stop = /[.!?](\s|$)/.exec(flat.slice(0, max + 1));
  return clip(stop ? flat.slice(0, stop.index + 1) : flat, max);
}

function dayLabel(day?: number): string {
  return day && day > 0 ? ` on Day ${day}` : "";
}

/** Say what moved in the user's own vocabulary; fall back to counts in bulk. */
export function changeSummary(effects: TurnEffect[]): string {
  if (!effects.length) return "";
  if (effects.length === 1) {
    const only = effects[0];
    if (only.change === "moved") return `Moved ${only.name} to Day ${only.day}.`;
    if (only.change === "removed") return `Removed ${only.name}.`;
    return `Added ${only.name}${dayLabel(only.day)}.`;
  }
  const counts = { added: 0, moved: 0, removed: 0 };
  for (const effect of effects) counts[effect.change] += 1;
  const parts: string[] = [];
  if (counts.added) parts.push(`added ${counts.added}`);
  if (counts.moved) parts.push(`moved ${counts.moved}`);
  if (counts.removed) parts.push(`removed ${counts.removed}`);
  parts[0] = `${parts[0]} ${parts[0].endsWith(" 1") ? "stop" : "stops"}`;
  const joined =
    parts.length === 1
      ? parts[0]
      : `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
  return `${joined.charAt(0).toUpperCase()}${joined.slice(1)}.`;
}

export interface TurnOutcome {
  destination?: string | null;
  startedWithoutTrip: boolean;
  proposalOnly: boolean;
  effects: TurnEffect[];
  reply: string;
  /** The guard's own account of what the change cost, when there was one. */
  alert?: string;
}

/**
 * Describe the turn that actually happened.
 *
 * A question that changed nothing must not be reported as an update: the bar is
 * the only thing on screen once the composer collapses, so a wrong claim there
 * is the whole story the user gets.
 */
export function completionStatus(outcome: TurnOutcome): { message: string; detail?: string } {
  const place = (outcome.destination ?? "").trim();
  const gist = answerGist(outcome.reply);

  if (outcome.proposalOnly) {
    return {
      message: "Review ready \u2014 nothing changed yet",
      detail: gist || "Your itinerary is untouched until you accept it.",
    };
  }
  if (outcome.startedWithoutTrip) {
    return {
      message: place ? `Your ${place} itinerary is ready` : "Your itinerary is ready",
      detail: gist || "Open Itinerary or Map to look through it.",
    };
  }
  if (outcome.effects.length) {
    return {
      message: place ? `Updated your ${place} trip` : "Updated your trip",
      detail: [changeSummary(outcome.effects), outcome.alert].filter(Boolean).join(" "),
    };
  }
  if (outcome.alert) {
    return { message: outcome.alert, detail: gist || undefined };
  }
  return {
    message: "Answered in chat \u2014 nothing changed",
    detail: gist || "Your itinerary is unchanged.",
  };
}
