"""Retry an incomplete model response without replaying graph tools."""

from __future__ import annotations

import random
import time

import httpx

from tripplanner.observability import app_event
from tripplanner.ops_metrics import record_model_recovery


def invoke_model(model, messages):
    started = time.monotonic()
    for attempt in range(2):
        try:
            response = model.invoke(messages)
        except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ReadTimeout) as exc:
            if attempt:
                record_model_recovery("exhausted")
                app_event(
                    "model_recovery",
                    status="error",
                    outcome="exhausted",
                    error=type(exc).__name__,
                    ms=(time.monotonic() - started) * 1000,
                )
                raise
            app_event("model_recovery", status="retrying", stage="retry", error=type(exc).__name__)
            time.sleep(random.uniform(0.25, 0.5))
        except Exception:
            if attempt:
                record_model_recovery("exhausted")
                app_event("model_recovery", status="error", outcome="exhausted")
            raise
        else:
            if attempt:
                record_model_recovery("recovered")
                app_event(
                    "model_recovery",
                    status="ok",
                    outcome="recovered",
                    ms=(time.monotonic() - started) * 1000,
                )
            return response
