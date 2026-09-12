"""Capture each model HTTP attempt, including SDK retries and interrupted streams."""

import hashlib
import json
import time
import uuid
from functools import lru_cache

import httpx

from tripplanner.flight_callbacks import FlightRecorderCallback
from tripplanner.flight_recorder import capture_provider_bodies, enabled, record


class BodyCapture:
    """Count all bytes while retaining at most 64 KiB for failure diagnostics."""

    limit = 64 * 1024

    def __init__(self, retain=True):
        self.data = bytearray()
        self.size = 0
        self.digest = hashlib.sha256()
        self.retain = retain and enabled()

    def append(self, chunk):
        self.size += len(chunk)
        self.digest.update(chunk)
        if self.retain:
            self.data.extend(chunk[:max(0, self.limit - len(self.data))])

    def summary(self):
        return {"bytes": self.size, "sha256": self.digest.hexdigest(),
                "truncated": self.size > len(self.data)}

    def body(self, content_type, include):
        if not include or not self.retain:
            return {"omitted": "metadata only", **self.summary()}
        if self.size > len(self.data):
            return {"excerpt": bytes(self.data).decode("utf-8", errors="replace"),
                    **self.summary()}
        return body_data(bytes(self.data), content_type)


def body_data(body, content_type=""):
    if "json" in content_type:
        try:
            return json.loads(body)
        except (ValueError, UnicodeDecodeError):
            pass
    if "text" in content_type or "event-stream" in content_type:
        return body.decode("utf-8", errors="replace")
    return body


class Capture:
    def __init__(self, request, sensitive):
        self.id = uuid.uuid4().hex
        self.start = time.monotonic()
        self.sensitive = sensitive
        self.parts = BodyCapture(not sensitive)
        self.request_body = BodyCapture(not sensitive)
        self.request_body.append(request.content)
        self.request_type = request.headers.get("content-type", "")
        self.done = False
        self.tail = b""
        self.finished = False
        self.status = None
        self.headers = {}
        self.content_type = ""
        record(
            "http.attempt",
            attempt_id=self.id,
            method=request.method,
            url=str(request.url),
            headers=dict(request.headers),
            retry_count=request.headers.get("x-stainless-retry-count"),
            body="<sensitive>"
            if sensitive
            else self.request_body.body(self.request_type, capture_provider_bodies()),
        )

    def append(self, chunk):
        self.parts.append(chunk)
        boundary = self.tail + chunk
        self.done = self.done or b"data: [DONE]" in boundary
        self.tail = boundary[-32:]

    def end(self, outcome, error=None):
        if self.finished:
            return
        self.finished = True
        if outcome == "interrupted" and self.done:
            outcome = "complete"
        failed = outcome != "complete" or (self.status is not None and self.status >= 400)
        include = failed or capture_provider_bodies()
        record(
            "http.result",
            attempt_id=self.id,
            status=self.status,
            headers=self.headers,
            outcome=outcome,
            duration_ms=(time.monotonic() - self.start) * 1000,
            error=str(error) if error else None,
            body="<sensitive>"
            if self.sensitive
            else self.parts.body(self.content_type, include),
            request_body="<sensitive>" if self.sensitive else self.request_body.body(
                self.request_type, failed and not capture_provider_bodies()
            ),
        )


class RecordingStream(httpx.SyncByteStream):
    def __init__(self, stream, capture):
        self.stream, self.capture = stream, capture

    def __iter__(self):
        try:
            for chunk in self.stream:
                if not self.capture.sensitive:
                    self.capture.append(chunk)
                yield chunk
            self.capture.end("complete")
        except BaseException as exc:
            self.capture.end("error", exc)
            raise

    def close(self):
        try:
            self.stream.close()
        finally:
            self.capture.end("interrupted")


class AsyncRecordingStream(httpx.AsyncByteStream):
    def __init__(self, stream, capture):
        self.stream, self.capture = stream, capture

    async def __aiter__(self):
        try:
            async for chunk in self.stream:
                if not self.capture.sensitive:
                    self.capture.append(chunk)
                yield chunk
            self.capture.end("complete")
        except BaseException as exc:
            self.capture.end("error", exc)
            raise

    async def aclose(self):
        try:
            await self.stream.aclose()
        finally:
            self.capture.end("interrupted")


class RecordingTransport(httpx.BaseTransport):
    def __init__(self, inner=None, *, sensitive=False):
        self.inner = inner or httpx.HTTPTransport()
        self.sensitive = sensitive

    def handle_request(self, request):
        if not enabled():
            return self.inner.handle_request(request)
        capture = Capture(request, self.sensitive)
        try:
            response = self.inner.handle_request(request)
            capture.status = response.status_code
            capture.headers = dict(response.headers)
            capture.content_type = response.headers.get("content-type", "")
            if response.is_stream_consumed:
                capture.append(response.content)
                capture.end("complete")
            else:
                response.stream = RecordingStream(response.stream, capture)
            return response
        except BaseException as exc:
            capture.end("error", exc)
            raise

    def close(self):
        self.inner.close()


class AsyncRecordingTransport(httpx.AsyncBaseTransport):
    def __init__(self, inner=None, *, sensitive=False):
        self.inner = inner or httpx.AsyncHTTPTransport()
        self.sensitive = sensitive

    async def handle_async_request(self, request):
        if not enabled():
            return await self.inner.handle_async_request(request)
        capture = Capture(request, self.sensitive)
        try:
            response = await self.inner.handle_async_request(request)
            capture.status = response.status_code
            capture.headers = dict(response.headers)
            capture.content_type = response.headers.get("content-type", "")
            if response.is_stream_consumed:
                capture.append(response.content)
                capture.end("complete")
            else:
                response.stream = AsyncRecordingStream(response.stream, capture)
            return response
        except BaseException as exc:
            capture.end("error", exc)
            raise

    async def aclose(self):
        await self.inner.aclose()


@lru_cache(maxsize=2)
def model_recording_options(*, sensitive=False):
    return {
        "callbacks": [FlightRecorderCallback(sensitive=sensitive)],
        "http_client": httpx.Client(transport=RecordingTransport(sensitive=sensitive), timeout=600),
        "http_async_client": httpx.AsyncClient(
            transport=AsyncRecordingTransport(sensitive=sensitive), timeout=600
        ),
    }
