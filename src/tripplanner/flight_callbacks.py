"""Model and tool evidence without per-token storage writes."""

import threading
import time

from langchain_core.callbacks import BaseCallbackHandler

from tripplanner.flight_recorder import SPAN, TRACE, record


class FlightRecorderCallback(BaseCallbackHandler):
    run_inline = True

    def __init__(self, *, sensitive=False):
        self.sensitive = sensitive
        self._runs = {}
        self._traces = {}
        self._lock = threading.Lock()

    def _start(self, kind, run_id, parent_run_id, **payload):
        SPAN.set(str(run_id))
        with self._lock:
            if str(run_id) in self._runs:
                return
            self._runs[str(run_id)] = time.monotonic()
        record(
            kind + ".start",
            span_id=str(run_id),
            parent_span_id=str(parent_run_id or ""),
            payload={"omitted": "sensitive document processing"} if self.sensitive else payload,
        )

    def _end(self, kind, run_id, parent_run_id, **payload):
        with self._lock:
            start = self._runs.pop(str(run_id), None)
        if start is None:
            return
        record(
            kind,
            span_id=str(run_id),
            parent_span_id=str(parent_run_id or ""),
            duration_ms=(time.monotonic() - start) * 1000 if start else None,
            payload={"omitted": "sensitive document processing"} if self.sensitive else payload,
        )
        SPAN.set(str(parent_run_id or ""))

    def on_chat_model_start(self, serialized, messages, *, run_id, parent_run_id=None, **kwargs):
        self._start(
            "llm",
            run_id,
            parent_run_id,
            message_count=sum(len(batch) for batch in messages),
            model=(kwargs.get("invocation_params") or {}).get("model"),
        )

    def on_llm_start(self, serialized, prompts, *, run_id, parent_run_id=None, **kwargs):
        self._start("llm", run_id, parent_run_id, prompt_count=len(prompts))

    def on_llm_end(self, response, *, run_id, parent_run_id=None, **kwargs):
        self._end("llm.end", run_id, parent_run_id)

    def on_llm_error(self, error, *, run_id, parent_run_id=None, **kwargs):
        self._end(
            "llm.error", run_id, parent_run_id, error=str(error), error_type=type(error).__name__
        )

    def on_tool_start(self, serialized, input_str, *, run_id, parent_run_id=None, **kwargs):
        self._start(
            "tool", run_id, parent_run_id, tool=(serialized or {}).get("name")
        )

    def on_tool_end(self, output, *, run_id, parent_run_id=None, **kwargs):
        text = str(getattr(output, "content", output))
        rejected = text.lstrip().lower().startswith("error:")
        self._end("tool.end", run_id, parent_run_id, rejected=rejected,
                  error=text[:1024] if rejected else None)

    def on_tool_error(self, error, *, run_id, parent_run_id=None, **kwargs):
        self._end(
            "tool.error", run_id, parent_run_id, error=str(error), error_type=type(error).__name__
        )

    def on_retry(self, retry_state, *, run_id, parent_run_id=None, **kwargs):
        record(
            "retry",
            span_id=str(run_id),
            parent_span_id=str(parent_run_id or ""),
            attempt=retry_state.attempt_number,
            outcome=str(retry_state.outcome),
        )


class ToolRecorderCallback(FlightRecorderCallback):
    ignore_llm = True

    def on_chat_model_start(self, *args, **kwargs):
        pass

    def on_llm_start(self, *args, **kwargs):
        pass

    def on_llm_end(self, *args, **kwargs):
        pass

    def on_llm_error(self, *args, **kwargs):
        pass

    def on_tool_start(self, serialized, input_str, *, run_id, parent_run_id=None, **kwargs):
        # The cached wrapper invokes the original tool. Keep only the outer pair.
        with self._lock:
            nested = str(parent_run_id) in self._runs and str(parent_run_id) not in self._traces
        if not nested:
            super().on_tool_start(serialized, input_str, run_id=run_id,
                                  parent_run_id=parent_run_id, **kwargs)

    def on_chain_start(self, serialized, inputs, *, run_id, parent_run_id=None, **kwargs):
        if parent_run_id is None:
            self._traces[str(run_id)] = TRACE.get()
            TRACE.set(TRACE.get() or str(run_id))
            self._start("graph", run_id, parent_run_id)

    def on_chain_end(self, outputs, *, run_id, parent_run_id=None, **kwargs):
        if parent_run_id is None:
            self._end("graph.end", run_id, parent_run_id)
            TRACE.set(self._traces.pop(str(run_id), ""))

    def on_chain_error(self, error, *, run_id, parent_run_id=None, **kwargs):
        if parent_run_id is None:
            self._end(
                "graph.error",
                run_id,
                parent_run_id,
                error=str(error),
                error_type=type(error).__name__,
            )
            TRACE.set(self._traces.pop(str(run_id), ""))
