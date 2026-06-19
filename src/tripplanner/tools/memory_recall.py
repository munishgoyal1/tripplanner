"""Semantic-ish recall over the user's persistent memory.

The trip agent has accumulated `learned_notes`, `past_trip_mentions`,
`past_trips`, `interests`, `dislikes`, `family_members`, and an `about_me`
free-text blob via the continuous-learning tools. None of that is useful
unless the agent can FIND the bits relevant to the current question.

Rather than pulling Azure OpenAI embeddings (extra cost + deployment + cold
start), this tool uses a small BM25-lite scorer over tokens. Quality is
"good enough" for ~hundreds of notes per user. If/when the corpus grows past
that or fuzzy paraphrase recall is needed we can swap in embeddings behind
the same tool interface — the agent doesn't care how scoring works.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

from langchain_core.tools import tool

from tripplanner.tools.user_preferences import load_preferences

# Tiny English stopword list — keeping it short on purpose: removing every
# word in nltk's list throws away too many signals for short notes.
_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "of", "to", "in", "on", "at",
    "for", "with", "is", "are", "was", "were", "be", "been", "being", "i",
    "we", "you", "they", "he", "she", "it", "my", "our", "your", "their",
    "this", "that", "these", "those", "from", "as", "by", "do", "does",
    "did", "have", "has", "had", "will", "would", "should", "could", "than",
    "then", "so", "not", "no", "yes",
}

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9'-]+")


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "") if t.lower() not in _STOPWORDS]


def _collect_items(prefs: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten the prefs blob into recall-ready items.

    Each item: {kind, text, payload} where text is the searchable surface and
    payload is the original structure echoed back to the agent.
    """
    items: list[dict[str, Any]] = []

    for n in prefs.get("learned_notes", []) or []:
        if isinstance(n, dict) and n.get("note"):
            items.append({"kind": "learned_note", "text": n["note"], "payload": n})

    for m in prefs.get("past_trip_mentions", []) or []:
        if not isinstance(m, dict):
            continue
        bits = [m.get("destination", ""), m.get("when", ""), m.get("with_whom", ""),
                m.get("sentiment", ""), m.get("notes", "")]
        text = " ".join(b for b in bits if b)
        if text.strip():
            items.append({"kind": "past_trip_mention", "text": text, "payload": m})

    for t in prefs.get("past_trips", []) or []:
        if not isinstance(t, dict):
            continue
        bits = [t.get("destination", ""), str(t.get("dates", "")),
                str(t.get("rating", "")), t.get("notes", "")]
        text = " ".join(b for b in bits if b)
        if text.strip():
            items.append({"kind": "past_trip", "text": text, "payload": t})

    for fam in prefs.get("family_members", []) or []:
        if not isinstance(fam, dict):
            continue
        bits = [fam.get("relationship", ""), fam.get("name", ""),
                str(fam.get("age", "")), fam.get("dietary", ""),
                fam.get("mobility", ""),
                " ".join(fam.get("interests", []) or []),
                fam.get("notes", "")]
        text = " ".join(b for b in bits if b)
        if text.strip():
            items.append({"kind": "family_member", "text": text, "payload": fam})

    for tag in prefs.get("interests", []) or []:
        if isinstance(tag, str) and tag.strip():
            items.append({"kind": "interest", "text": tag, "payload": tag})
    for tag in prefs.get("dislikes", []) or []:
        if isinstance(tag, str) and tag.strip():
            items.append({"kind": "dislike", "text": tag, "payload": tag})

    about = prefs.get("about_me", "") or ""
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", about):
        s = sentence.strip()
        if len(s) >= 8:
            items.append({"kind": "about_me", "text": s, "payload": s})

    return items


def _score_bm25(query_tokens: list[str], items: list[dict[str, Any]]) -> list[tuple[float, dict[str, Any]]]:
    """Light BM25 (k1=1.5, b=0.75) over the flattened item corpus.

    Doc count is tiny per user so we compute IDF directly each call.
    """
    if not items or not query_tokens:
        return []
    docs = [_tokenize(it["text"]) for it in items]
    n = len(docs)
    avgdl = sum(len(d) for d in docs) / n if n else 0.0

    # df per query token
    df: dict[str, int] = {}
    for tok in set(query_tokens):
        df[tok] = sum(1 for d in docs if tok in d)

    k1, b = 1.5, 0.75
    scored: list[tuple[float, dict[str, Any]]] = []
    for it, doc in zip(items, docs):
        if not doc:
            continue
        dl = len(doc)
        score = 0.0
        for tok in query_tokens:
            f = doc.count(tok)
            if not f:
                continue
            idf = math.log(1 + (n - df[tok] + 0.5) / (df[tok] + 0.5))
            denom = f + k1 * (1 - b + b * (dl / avgdl)) if avgdl else f + k1
            score += idf * (f * (k1 + 1)) / denom
        if score > 0:
            scored.append((score, it))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


@tool
def recall_relevant_memory(query: str, top_k: int = 3) -> str:
    """Recall items from the user's memory most relevant to a query.

    Searches across learned notes, past trip mentions, agent-planned past
    trips, family members, interests, dislikes, and the user's About-me text.
    Uses BM25-lite token scoring (no API call, no cost). Returns the top-K
    matches as JSON, each with `kind`, `text`, `score`, and `payload`.

    Use BEFORE asking the user a question that might already be answered in
    memory (e.g. "Mumbai again — did the family like the last one?"). If
    nothing scores high, returns an empty results list.

    Args:
        query: Free-text question or topic ("kid-friendly hotel preferences",
               "previous Goa trip", "father's mobility needs").
        top_k: Max items to return. 1-10. Default 3.
    """
    if not query.strip():
        return "query is required."

    top_k = max(1, min(int(top_k or 3), 10))
    prefs = load_preferences()
    items = _collect_items(prefs)
    query_tokens = _tokenize(query)
    scored = _score_bm25(query_tokens, items)[:top_k]

    return json.dumps(
        {
            "query": query,
            "results": [
                {"kind": it["kind"], "text": it["text"], "score": round(s, 3), "payload": it["payload"]}
                for s, it in scored
            ],
        },
        indent=2,
    )

