# Claude calls that return validated Pydantic objects via structured outputs.

import os
from functools import lru_cache
from typing import TypeVar

import anthropic
from pydantic import BaseModel

MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _client() -> anthropic.Anthropic:
    # Reads ANTHROPIC_API_KEY (or another configured credential) from the environment.
    return anthropic.Anthropic()


def structured(system: str, prompt: str, schema: type[T], effort: str = "medium") -> T:
    """Ask Claude for a response matching `schema` and return the parsed object."""
    response = _client().beta.messages.parse(
        model=MODEL,
        max_tokens=16_000,
        system=system,
        messages=[{"role": "user", "content": prompt}],
        output_format=schema,
        output_config={"effort": effort},
        # If the model declines on a safety classifier, the API retries on a fallback model.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if response.stop_reason == "refusal":
        category = response.stop_details.category if response.stop_details else None
        raise LLMError(f"Claude declined the request (category: {category}).")
    if response.stop_reason == "max_tokens":
        raise LLMError("Claude's response hit max_tokens before finishing.")
    if response.parsed_output is None:
        raise LLMError(f"No structured output returned (stop_reason={response.stop_reason}).")
    return response.parsed_output
