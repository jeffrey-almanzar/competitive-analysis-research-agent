# Per-run telemetry: records every Claude and Exa call (for cost/latency numbers and
# eval traces) and mirrors them to Langfuse when it's configured.
#
# The recorder lives in a ContextVar. LangGraph copies the context into the worker
# threads that run parallel nodes, so calls made inside nodes land on the same recorder.

import contextlib
import logging
import os
import threading
import time
import urllib.request
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import lru_cache, wraps
from typing import Any

log = logging.getLogger(__name__)


# --- Run recorder ----------------------------------------------------------


@dataclass
class LLMCall:
    name: str
    model: str  # model that actually served the response
    system: str
    prompt: str
    output: Any
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int
    latency_s: float
    stop_reason: str | None


@dataclass
class ToolCall:
    name: str
    args: dict
    result: Any
    latency_s: float


@dataclass
class RunRecorder:
    started: float = field(default_factory=time.monotonic)
    events: list[LLMCall | ToolCall] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, event: LLMCall | ToolCall) -> None:
        with self._lock:
            self.events.append(event)

    @property
    def llm_calls(self) -> list[LLMCall]:
        return [e for e in self.events if isinstance(e, LLMCall)]

    @property
    def tool_calls(self) -> list[ToolCall]:
        return [e for e in self.events if isinstance(e, ToolCall)]


_recorder: ContextVar[RunRecorder | None] = ContextVar("research_run_recorder", default=None)


def current() -> RunRecorder | None:
    return _recorder.get()


@contextlib.contextmanager
def recording(reuse: bool = False):
    """Start a fresh recorder (or, with reuse=True, keep one that's already active)."""
    existing = _recorder.get()
    if reuse and existing is not None:
        yield existing
        return
    rec = RunRecorder()
    token = _recorder.set(rec)
    try:
        yield rec
    finally:
        _recorder.reset(token)


# --- Langfuse --------------------------------------------------------------


@lru_cache(maxsize=1)
def _langfuse():
    """Return a Langfuse client, or None when tracing is off or the server is unreachable."""
    public, secret = os.getenv("LANGFUSE_PUBLIC_KEY"), os.getenv("LANGFUSE_SECRET_KEY")
    host = os.getenv("LANGFUSE_HOST")
    if not (public and secret and host):
        return None
    try:
        urllib.request.urlopen(f"{host.rstrip('/')}/api/public/health", timeout=2)
    except Exception as exc:
        log.info("Langfuse not reachable at %s (%s); tracing disabled", host, exc)
        return None
    from langfuse import Langfuse

    log.info("Tracing to Langfuse at %s", host)
    # The Anthropic SDK emits its own span per request; llm.structured already records each
    # call as a named generation with usage, so drop the SDK's to avoid double-counting.
    return Langfuse(
        public_key=public,
        secret_key=secret,
        host=host,
        should_export_span=lambda span: not span.name.startswith("anthropic."),
    )


@contextlib.contextmanager
def observe(name: str, as_type: str = "span", **kwargs):
    """Langfuse observation (span/generation/tool/agent); yields None when tracing is off."""
    client = _langfuse()
    if client is None:
        yield None
        return
    with client.start_as_current_observation(name=name, as_type=as_type, **kwargs) as obs:
        yield obs


def flush() -> None:
    client = _langfuse()
    if client is not None:
        client.flush()


def trace_url() -> str | None:
    client = _langfuse()
    if client is None:
        return None
    try:
        url = client.get_trace_url()
    except Exception:
        return None
    # Inside Docker the API host is http://langfuse-web:3000; links are opened from the host.
    host, public = os.getenv("LANGFUSE_HOST", ""), os.getenv("LANGFUSE_PUBLIC_URL", "http://localhost:3000")
    return url.replace(host.rstrip("/"), public.rstrip("/"), 1) if url and host else url


def traced_node(fn):
    """Wrap a LangGraph node in a Langfuse span named after the function."""

    @wraps(fn)
    def wrapper(state):
        with observe(fn.__name__, as_type="chain"):
            return fn(state)

    return wrapper


def tool(name: str):
    """Record an external call (Exa) on the run recorder and as a Langfuse tool span."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            call_args = {"args": list(args), **kwargs}
            start = time.monotonic()
            with observe(name, as_type="tool", input=call_args) as obs:
                result = fn(*args, **kwargs)
                summary = _summarize(result)
                if obs is not None:
                    obs.update(output=summary)
            rec = current()
            if rec is not None:
                rec.add(ToolCall(name, call_args, summary, time.monotonic() - start))
            return result

        return wrapper

    return decorator


def _summarize(result: Any) -> Any:
    """Keep traces readable: page lists become url/title/length rows instead of full text."""
    if isinstance(result, list):
        rows = []
        for item in result:
            url = getattr(item, "url", None)
            if url is None:
                return result
            text = getattr(item, "text", None) or getattr(item, "snippet", "") or ""
            rows.append({"url": url, "title": getattr(item, "title", None),
                         "kind": getattr(item, "kind", None), "chars": len(text)})
        return rows
    return result
