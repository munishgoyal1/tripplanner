"""ASGI capture that preserves streaming and records disconnects without consuming bodies."""

import time
import uuid

from tripplanner.flight_http import body_data
from tripplanner.flight_recorder import IDENTITY, SPAN, TRACE, record


class FlightRecorderMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path", "").removeprefix("/api")
        # Auth/document bodies contain credentials or identity documents. Static resources
        # are not trip evidence. Their ordinary HTTP status telemetry remains available.
        if not path.startswith(("/chat", "/trip", "/preferences", "/places", "/maps")):
            return await self.app(scope, receive, send)
        sensitive = "document" in path or "share" in path
        token = TRACE.set(uuid.uuid4().hex)
        identity_token = IDENTITY.set({})
        span_token = SPAN.set("")
        started = time.monotonic()
        request_parts, response_parts = [], []
        headers = dict(scope.get("headers", []))
        content_type = ""
        status = None
        complete = False
        disconnected = False
        error = None
        record("api.start", method=scope["method"], path=path)

        async def read():
            nonlocal disconnected
            message = await receive()
            if message["type"] == "http.request" and not sensitive:
                request_parts.append(message.get("body", b""))
            elif message["type"] == "http.disconnect":
                disconnected = True
            return message

        async def write(message):
            nonlocal status, content_type, complete
            if message["type"] == "http.response.start":
                status = message["status"]
                content_type = dict(message.get("headers", [])).get(b"content-type", b"").decode()
            elif message["type"] == "http.response.body":
                if not sensitive and any(
                    t in content_type for t in ("json", "text", "event-stream")
                ):
                    response_parts.append(message.get("body", b""))
                complete = not message.get("more_body", False)
            await send(message)

        try:
            await self.app(scope, read, write)
        except BaseException as exc:
            error = type(exc).__name__
            raise
        finally:
            record(
                "api.end",
                method=scope["method"],
                path=path,
                status=status,
                duration_ms=(time.monotonic() - started) * 1000,
                complete=complete,
                disconnected=disconnected,
                error=error,
                request="<sensitive>"
                if sensitive or status in {401, 403}
                else body_data(b"".join(request_parts), headers.get(b"content-type", b"").decode()),
                response="<sensitive>"
                if sensitive
                else body_data(b"".join(response_parts), content_type),
            )
            TRACE.reset(token)
            SPAN.reset(span_token)
            IDENTITY.reset(identity_token)
