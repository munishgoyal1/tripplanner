"""LangGraph trip planner orchestration graph.

Single-agent graph focused on trip planning with tool-calling loop:
  Trip Agent → Tools → Trip Agent → ... → END
"""

from __future__ import annotations

import operator
import time
from dataclasses import dataclass
from functools import lru_cache
from threading import Lock
from typing import Annotated, Any, TypedDict

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage
from langchain_openai import AzureChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from tripplanner import graph_policy
from tripplanner.agents.trip_agent import (
    TRIP_TOOLS,
    build_trip_system_prompt,
    latest_user_has_planning_intent,
    proposal_tools,
    select_tools,
)
from tripplanner.config import get_settings
from tripplanner.observability import app_event
from tripplanner.tools.trip_planner import load_active_trip_dict
from tripplanner.tools_cache import wrap_tools_with_cache
from tripplanner.usage import record_usage
from tripplanner.user_context import get_user_id


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    current_agent: str
    proposal_only: bool


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------
@dataclass
class _RunContext:
    """Prompt shape and start time for one in-flight model call."""

    started_at: float | None = None
    message_count: int = 0
    prompt_chars: int = 0

    def elapsed_ms(self) -> float:
        if self.started_at is None:
            return 0.0
        return (time.monotonic() - self.started_at) * 1000


def _token_counts(response: Any) -> tuple[int, int]:
    """Prompt and completion tokens, from wherever the client reported them.

    Only ``llm_output`` was read before, which this deployment leaves empty, so
    every call recorded zero and the monthly cost cap could never trigger.
    Modern LangChain reports the same numbers on the message instead.
    """
    usage = (getattr(response, "llm_output", None) or {}).get("token_usage") or {}
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    if prompt or completion:
        return prompt, completion

    for batch in getattr(response, "generations", None) or []:
        for generation in batch or []:
            message = getattr(generation, "message", None)
            if message is None:
                continue
            metadata = getattr(message, "usage_metadata", None) or {}
            prompt += int(metadata.get("input_tokens") or 0)
            completion += int(metadata.get("output_tokens") or 0)
            if metadata:
                continue
            fallback = (getattr(message, "response_metadata", None) or {}).get(
                "token_usage"
            ) or {}
            prompt += int(fallback.get("prompt_tokens") or 0)
            completion += int(fallback.get("completion_tokens") or 0)
    return prompt, completion


def _message_chars(message: Any) -> int:
    """Everything the message actually sends, not only its prose.

    Counting ``content`` alone hid the tool calls and their arguments, so the
    logged prompt size grew nine percent while real tokens more than doubled.
    """
    size = len(str(getattr(message, "content", "") or ""))
    extra = getattr(message, "additional_kwargs", None) or {}
    for call in extra.get("tool_calls") or []:
        function = (call or {}).get("function") or {}
        size += len(str(function.get("name") or "")) + len(str(function.get("arguments") or ""))
    return size


def _cached_tokens(response: Any) -> int:
    """Prompt tokens the provider served from its cache, when it says so.

    Caching is the cheapest saving available on a prompt this size, and the only
    way to know whether it is working is to count what it returns.
    """
    for batch in getattr(response, "generations", None) or []:
        for generation in batch or []:
            message = getattr(generation, "message", None)
            details = (getattr(message, "usage_metadata", None) or {}).get(
                "input_token_details"
            ) or {}
            if details.get("cache_read") is not None:
                return int(details.get("cache_read") or 0)
    usage = (getattr(response, "llm_output", None) or {}).get("token_usage") or {}
    return int((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)


class _UsageCallback(BaseCallbackHandler):
    """Record per-user LLM token usage after every chat completion.

    Reads the token counts from wherever the client put them, then feeds them to
    :mod:`tripplanner.usage`, which handles the monthly cost bucket and
    persistence.

    One instance is attached to the shared model client, so per-call state is
    keyed by LangChain's ``run_id`` rather than held on the handler. Otherwise
    two concurrent turns would overwrite each other's start time and prompt size.
    """

    def __init__(self, model: str) -> None:
        self._model = model
        self._lock = Lock()
        self._runs: dict[Any, _RunContext] = {}

    def _take(self, run_id: Any) -> _RunContext:
        with self._lock:
            return self._runs.pop(run_id, _RunContext())

    def on_chat_model_start(
        self,
        _serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        run_id: Any = None,
        **_: Any,
    ) -> None:
        batch = messages[0] if messages else []
        context = _RunContext(
            started_at=time.monotonic(),
            message_count=len(batch),
            prompt_chars=sum(_message_chars(message) for message in batch),
        )
        with self._lock:
            self._runs[run_id] = context

    def on_llm_end(self, response: Any, run_id: Any = None, **_: Any) -> None:  # noqa: D401
        try:
            context = self._take(run_id)
            duration_ms = context.elapsed_ms()
            from tripplanner.ops_metrics import record_model_call

            record_model_call(self._model, "ok", duration_ms)
            prompt, completion = _token_counts(response)
            app_event(
                "llm_call",
                status="ok",
                model=self._model,
                ms=round(duration_ms, 2) if context.started_at is not None else None,
                message_count=context.message_count,
                prompt_chars=context.prompt_chars,
                prompt_tokens=prompt,
                completion_tokens=completion,
                cached_tokens=_cached_tokens(response),
            )
            if prompt == 0 and completion == 0:
                return
            record_usage(
                get_user_id() or "local",
                model=self._model,
                prompt_tokens=prompt,
                completion_tokens=completion,
            )
        except Exception:
            # Accounting must never break a turn.
            pass

    def on_llm_error(self, error: BaseException, run_id: Any = None, **_: Any) -> None:
        try:
            context = self._take(run_id)
            duration_ms = context.elapsed_ms()
            from tripplanner.ops_metrics import record_model_call

            record_model_call(self._model, "error", duration_ms)
            app_event(
                "llm_call",
                status="error",
                model=self._model,
                ms=round(duration_ms, 2) if context.started_at is not None else None,
                message_count=context.message_count,
                prompt_chars=context.prompt_chars,
                error=type(error).__name__,
            )
        except Exception:
            pass


@lru_cache(maxsize=4)
def _build_llm(
    endpoint: str, api_key: str, deployment: str, api_version: str
) -> AzureChatOpenAI:
    return AzureChatOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        azure_deployment=deployment,
        api_version=api_version,
        temperature=0.3,
        max_retries=5,
        # Stream tokens so astream_events emits on_chat_model_stream chunks —
        # this is what lets the web UIs render the reply as it's typed instead
        # of waiting for the whole turn (which felt "stuck").
        streaming=True,
        # Without this a streamed turn reports no tokens at all, so everything
        # the web UI does would go unpriced.
        stream_usage=True,
        callbacks=[_UsageCallback(deployment)],
    )


def _get_llm() -> AzureChatOpenAI:
    """Return the shared model client.

    A planning turn makes one model call per tool phase. Building a client per
    call also built a fresh HTTP client, so every round paid a new TLS handshake
    to Azure OpenAI before the first token. The client carries no per-call
    state; usage accounting is keyed by run id instead.
    """
    s = get_settings()
    return _build_llm(
        s.azure_openai_endpoint,
        s.azure_openai_api_key,
        s.azure_openai_deployment,
        s.azure_openai_api_version,
    )


def reset_llm_cache_for_tests() -> None:
    _build_llm.cache_clear()


_MAX_MODEL_TOOL_RESULT_CHARS = 1_500
_MAX_MODEL_TOOL_RESULTS_TOTAL_CHARS = 12_000
_TOOL_RESULT_TRUNCATION = (
    "\n...[truncated for synthesis; full result remains in graph state]"
)


def _messages_for_model(messages: list[BaseMessage]) -> list[BaseMessage]:
    tool_results = [
        message
        for message in messages
        if isinstance(message, ToolMessage) and isinstance(message.content, str)
    ]
    if not tool_results:
        return messages
    result_limit = min(
        _MAX_MODEL_TOOL_RESULT_CHARS,
        _MAX_MODEL_TOOL_RESULTS_TOTAL_CHARS // len(tool_results),
    )
    content_limit = max(0, result_limit - len(_TOOL_RESULT_TRUNCATION))
    return [
        message.model_copy(
            update={
                "content": (
                    message.content[:content_limit] + _TOOL_RESULT_TRUNCATION
                )[:result_limit]
            }
        )
        if isinstance(message, ToolMessage)
        and isinstance(message.content, str)
        and len(message.content) > result_limit
        else message
        for message in messages
    ]


# ---------------------------------------------------------------------------
# Trip agent node
# ---------------------------------------------------------------------------
def _tool_was_called(messages: list[BaseMessage], tool_name: str) -> bool:
    for message in messages:
        for tool_call in getattr(message, "tool_calls", None) or []:
            name = (
                tool_call.get("name")
                if isinstance(tool_call, dict)
                else getattr(tool_call, "name", None)
            )
            if name == tool_name:
                return True
    return False


_COMPLETION_RESEARCH_TOOLS = graph_policy.COMPLETION_RESEARCH_TOOLS
_MAX_POST_RESEARCH_UPDATES = graph_policy.MAX_POST_RESEARCH_UPDATES
_MAX_INITIAL_ITINERARY_UPDATES = graph_policy.MAX_INITIAL_ITINERARY_UPDATES
_MAX_TOOL_PHASES_PER_TURN = graph_policy.MAX_TOOL_PHASES_PER_TURN


def _current_turn_tool_phases(messages: list[BaseMessage]) -> int:
    return graph_policy.current_turn_tool_phases(messages)


def _active_trip_for_policy() -> dict[str, Any]:
    try:
        return load_active_trip_dict() or {}
    except Exception:
        return {}


def _trip_update_requirement(messages: list[BaseMessage]) -> str | None:
    return graph_policy.trip_update_requirement(
        messages,
        _active_trip_for_policy(),
        has_planning_intent=latest_user_has_planning_intent(messages),
    )


def _trip_hotel_search_requirement(messages: list[BaseMessage]) -> str | None:
    return graph_policy.trip_hotel_search_requirement(
        messages,
        _active_trip_for_policy(),
        has_planning_intent=latest_user_has_planning_intent(messages),
    )


def _trip_hotel_fallback_requirement(messages: list[BaseMessage]) -> str | None:
    return graph_policy.trip_hotel_fallback_requirement(messages)


def _latest_user_starts_new_trip(messages: list[BaseMessage]) -> bool:
    return graph_policy.latest_user_starts_new_trip(messages)


def _pending_trip_kickoff_answer(messages: list[BaseMessage]) -> bool:
    return graph_policy.pending_trip_kickoff_answer(messages)


def _trip_kickoff_tool_choice(messages: list[BaseMessage]) -> str | None:
    """Choose the required preference-aware step before creating a new trip."""
    return graph_policy.trip_kickoff_tool_choice(
        messages,
        _active_trip_for_policy(),
        has_planning_intent=latest_user_has_planning_intent(messages),
    )


def _trip_creation_tool_choice(messages: list[BaseMessage]) -> str | None:
    """Require a fresh plan for an explicit switch away from the active destination."""
    return graph_policy.trip_creation_tool_choice(messages, _active_trip_for_policy())


def trip_agent(state: AgentState) -> AgentState:
    """The trip planner agent — invokes LLM with tools bound."""
    # parallel_tool_calls=True asks the model to emit independent calls in a
    # single turn so ToolNode can execute them concurrently — cuts the
    # round-trip cost in half when we need flights AND hotels AND weather etc.
    # select_tools() binds only the relevant subset (heavy search tools are
    # added only once planning is active) to trim per-turn prompt tokens.
    proposal_only = bool(state.get("proposal_only"))
    decision = graph_policy.resolve_completion_policy(
        messages=state["messages"],
        active_trip=_active_trip_for_policy(),
        proposal_only=proposal_only,
        has_planning_intent=latest_user_has_planning_intent(state["messages"]),
    )
    if decision.budget_exhausted:
        gaps = list(decision.completion_gaps)
        app_event(
            "agent_model_round",
            tool_phase=decision.tool_phases,
            forced_reason=decision.forced_reason,
            completion_gap_count=len(gaps),
            message_count=len(state["messages"]),
        )
        instructions = [
            build_trip_system_prompt(),
            SystemMessage(content=(
                "The bounded planning-tool budget is exhausted. Do not call another tool. "
                "Give a concise best-effort summary of the plan already persisted. "
                + (
                    "State these unresolved details honestly without discarding the usable "
                    "itinerary: " + " ".join(gaps)
                    if gaps
                    else "Confirm that the best available itinerary has been saved."
                )
            )),
        ]
        response = _get_llm().invoke(
            instructions + _messages_for_model(state["messages"])
        )
        return {"messages": [response], "current_agent": "trip"}

    app_event(
        "agent_model_round",
        tool_phase=decision.tool_phases,
        forced_tool=decision.forced_tool,
        forced_reason=decision.forced_reason,
        message_count=len(state["messages"]),
    )
    tools = select_tools(state["messages"], proposal_only=proposal_only)
    if decision.forced_tool:
        tools = [tool for tool in tools if tool.name == decision.forced_tool]
    llm = _get_llm().bind_tools(
        tools,
        parallel_tool_calls=True,
        **({"tool_choice": decision.forced_tool} if decision.forced_tool else {}),
    )
    instructions = [build_trip_system_prompt()]
    if decision.forced_reason == "new_trip_creation":
        instructions.append(SystemMessage(content=(
            "The user explicitly requested a different whole-trip destination. "
            "Call create_trip_plan now so the existing active trip is not overwritten."
        )))
    elif decision.forced_reason == "hotel_provider_fallback":
        instructions.append(SystemMessage(content=(
            (decision.requirement or "")
            + " Call search_places_with_reviews before writing any final response."
        )))
    elif decision.forced_reason == "persist_or_repair_plan":
        instructions.append(SystemMessage(content=(
            (decision.requirement or "")
            + " Call update_trip_plan before writing any final response."
        )))
    elif decision.forced_reason == "missing_concrete_hotel":
        instructions.append(SystemMessage(content=(
            (decision.requirement or "")
            + " Call search_hotels before writing any final response."
        )))
    elif decision.kickoff_tool == "request_trip_input":
        instructions.append(SystemMessage(content=(
            "Start this new trip with one compact preference review. Call "
            "request_trip_input now. Enumerate the relevant saved preferences and "
            "past-trip signals already applied in known_context_json, and prefill "
            "useful trip-specific choices. Do not call create_trip_plan yet."
        )))
    elif decision.kickoff_tool == "recommend_trip_duration":
        instructions.append(SystemMessage(content=(
            "Call recommend_trip_duration now. Preserve any explicit user duration. "
            "Otherwise estimate a fitting duration from destination scope, saved pace, "
            "and a concise set of likely preference-matched anchor experiences."
        )))
    if proposal_only:
        instructions.append(SystemMessage(content=(
            "PROPOSAL-ONLY REVIEW: analyze the itinerary and offer concise numbered options. "
            "Do not create, update, finalize, book, resume, or otherwise mutate trip or user data. "
            "Ask the user to approve an option before any later mutation turn."
        )))
    response = llm.invoke(instructions + _messages_for_model(state["messages"]))
    return {"messages": [response], "current_agent": "trip"}


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------
# Wrap the tools with read-through caching for deterministic lookups (flights,
# place reviews, weather, etc.); stateful tools (write/finalize) pass through
# untouched. This is what stops the agent from re-billing Amadeus/Google on
# every turn for the same query.
_CACHED_TOOLS = wrap_tools_with_cache(list(TRIP_TOOLS))
tool_node = ToolNode(_CACHED_TOOLS)
proposal_tool_node = ToolNode(proposal_tools(_CACHED_TOOLS))


def _should_continue(state: AgentState) -> str:
    """Route: if last message has tool calls → tools, else → end."""
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "proposal_tools" if state.get("proposal_only") else "tools"
    return "end"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------
def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("trip_agent", trip_agent)
    graph.add_node("tools", tool_node)
    graph.add_node("proposal_tools", proposal_tool_node)

    graph.set_entry_point("trip_agent")

    # Agent → tools or end
    graph.add_conditional_edges(
        "trip_agent",
        _should_continue,
        {"tools": "tools", "proposal_tools": "proposal_tools", "end": END},
    )

    # Tools → back to agent (for multi-step tool calling)
    graph.add_edge("tools", "trip_agent")
    graph.add_edge("proposal_tools", "trip_agent")

    return graph.compile()


# Singleton compiled graph
app_graph = build_graph()
