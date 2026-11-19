# Claude calls that return validated Pydantic objects via structured outputs.
# Every call is recorded (model, usage, latency) for cost tracking, evals and tracing.

import contextlib
import os
import time
from contextvars import ContextVar
from functools import lru_cache
from typing import TypeVar

import anthropic
from pydantic import BaseModel

from app.research import models, telemetry

# Default when a run doesn't choose a model: CLAUDE_MODEL if set, else the cheapest option.
MODEL = os.getenv("CLAUDE_MODEL", models.DEFAULT_MODEL)
models.get(MODEL)  # fail fast on a typo in CLAUDE_MODEL

# The model for the current research run. LangGraph copies context into its worker
# threads, so every Claude call inside a run uses the run's model.
_run_model: ContextVar[str | None] = ContextVar("research_run_model", default=None)


def current_model() -> str:
    return _run_model.get() or MODEL


@contextlib.contextmanager
def use_model(model: str | None):
    """Run the enclosed Claude calls on `model` (validated); None keeps the default."""
    if model is None:
        yield current_model()
        return
    models.get(model)
    token = _run_model.set(model)
    try:
        yield model
    finally:
        _run_model.reset(token)


T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _client() -> anthropic.Anthropic:
    # Reads ANTHROPIC_API_KEY (or another configured credential) from the environment.
    return anthropic.Anthropic()


def structured(
    system: str,
    prompt: str,
    schema: type[T],
    effort: str = "medium",
    model: str | None = None,
    name: str | None = None,
) -> T:
    """Ask Claude for a response matching `schema` and return the parsed object."""
    model = model or current_model()
    name = name or schema.__name__
    # On a safety-classifier decline, retry on a fallback model where the model supports it.
    # Haiku 5.5 has no server-side fallback, and sending the parameter would fail.
    fallback = (
        {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
        if models.BY_ID.get(model) is None or models.BY_ID[model].server_fallback
        else {}
    )
    start = time.monotonic()
    with telemetry.observe(
        name,
        as_type="generation",
        model=model,
        input=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        model_parameters={"effort": effort, "max_tokens": 16_000},
    ) as gen:
        response = _client().beta.messages.parse(
            model=model,
            max_tokens=16_000,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_format=schema,
            output_config={"effort": effort},
            **fallback,
        )
        usage = response.usage
        usage_details = {
            "input": usage.input_tokens,
            "output": usage.output_tokens,
            "cache_read_input_tokens": usage.cache_read_input_tokens or 0,
            "cache_creation_input_tokens": usage.cache_creation_input_tokens or 0,
        }
        output = response.parsed_output.model_dump() if response.parsed_output is not None else None
        if gen is not None:
            gen.update(
                model=response.model,
                output=output,
                usage_details=usage_details,
                metadata={"stop_reason": response.stop_reason, "request_id": response._request_id},
            )

    rec = telemetry.current()
    if rec is not None:
        rec.add(
            telemetry.LLMCall(
                name=name,
                model=response.model,
                system=system,
                prompt=prompt,
                output=output,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_input_tokens=usage.cache_read_input_tokens or 0,
                cache_creation_input_tokens=usage.cache_creation_input_tokens or 0,
                latency_s=time.monotonic() - start,
                stop_reason=response.stop_reason,
            )
        )

    if response.stop_reason == "refusal":
        category = response.stop_details.category if response.stop_details else None
        raise LLMError(f"Claude declined the request (category: {category}).")
    if response.stop_reason == "max_tokens":
        raise LLMError("Claude's response hit max_tokens before finishing.")
    if response.parsed_output is None:
        raise LLMError(f"No structured output returned (stop_reason={response.stop_reason}).")
    return response.parsed_output
