"""Capture each model HTTP attempt, including SDK retries and interrupted streams."""

import json
import time
import uuid
from functools import lru_cache

import httpx

from tripplanner.flight_callbacks import FlightRecorderCallback
from tripplanner.flight_recorder import record


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
        self.parts = []
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
            else body_data(request.content, request.headers.get("content-type", "")),
        )

    def end(self, outcome, error=None):
        if self.finished:
            return
        self.finished = True
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
            else body_data(b"".join(self.parts), self.content_type),
        )


class RecordingStream(httpx.SyncByteStream):
    def __init__(self, stream, capture):
        self.stream, self.capture = stream, capture

    def __iter__(self):
        try:
            for chunk in self.stream:
                if not self.capture.sensitive:
                    self.capture.parts.append(chunk)
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
                    self.capture.parts.append(chunk)
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
        capture = Capture(request, self.sensitive)
        try:
            response = self.inner.handle_request(request)
            capture.status = response.status_code
            capture.headers = dict(response.headers)
            capture.content_type = response.headers.get("content-type", "")
            if response.is_stream_consumed:
                capture.parts.append(response.content)
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
        capture = Capture(request, self.sensitive)
        try:
            response = await self.inner.handle_async_request(request)
            capture.status = response.status_code
            capture.headers = dict(response.headers)
            capture.content_type = response.headers.get("content-type", "")
            if response.is_stream_consumed:
                capture.parts.append(response.content)
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
