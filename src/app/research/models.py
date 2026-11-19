# The Claude models a research run can use. Single source of truth for the API,
# the worker, MCP, the CLI, the eval and the web UI (served at GET /models).

from dataclasses import dataclass

# Measured: Opus 5.5 eval baseline, median $0.94 per 6-competitor report (2026-11-19).
OPUS_COST_PER_COMPETITOR = 0.157


@dataclass(frozen=True)
class ModelOption:
    id: str
    label: str
    capability: str
    input_per_mtok: float  # $ per million input tokens (prompts up to 100K tokens)
    output_per_mtok: float
    est_cost_per_competitor: float  # $ per competitor researched
    cost_measured: bool  # True if the estimate comes from a real run, not price scaling
    server_fallback: bool  # accepts the server-side refusal fallback parameter


def _scaled(output_per_mtok: float) -> float:
    """Estimate per-competitor cost by scaling the measured Opus figure by price.
    All three models price input:output at 1:5, so one ratio scales the whole bill."""
    return round(OPUS_COST_PER_COMPETITOR * output_per_mtok / 20.0, 4)


MODELS: list[ModelOption] = [
    ModelOption(
        id="claude-haiku-5-5",
        label="Claude Haiku 5.5",
        capability="Fastest and cheapest. Good for a quick first scan of a market; "
        "may pick weaker competitors and write shallower gap analysis.",
        input_per_mtok=0.10,
        output_per_mtok=0.50,
        est_cost_per_competitor=_scaled(0.50),
        cost_measured=False,
        server_fallback=False,  # Haiku 5.5 has no server-side fallback; sending one 400s
    ),
    ModelOption(
        id="claude-sonnet-5-5",
        label="Claude Sonnet 5.5",
        capability="Balanced quality and speed. Solid competitor selection and "
        "extraction for everyday research.",
        input_per_mtok=2.00,
        output_per_mtok=10.00,
        est_cost_per_competitor=_scaled(10.00),
        cost_measured=False,
        server_fallback=True,
    ),
    ModelOption(
        id="claude-opus-5-5",
        label="Claude Opus 5.5",
        capability="Most capable. Best judgment on which companies really compete "
        "and on where the market gaps are.",
        input_per_mtok=4.00,
        output_per_mtok=20.00,
        est_cost_per_competitor=OPUS_COST_PER_COMPETITOR,
        cost_measured=True,
        server_fallback=True,
    ),
]

MODEL_IDS: tuple[str, ...] = tuple(m.id for m in MODELS)
BY_ID: dict[str, ModelOption] = {m.id: m for m in MODELS}

# Cheapest model is the default everywhere a model isn't chosen explicitly.
DEFAULT_MODEL: str = min(MODELS, key=lambda m: m.est_cost_per_competitor).id


def get(model_id: str) -> ModelOption:
    try:
        return BY_ID[model_id]
    except KeyError:
        raise ValueError(f"Unknown model {model_id!r}; choose one of {', '.join(MODEL_IDS)}") from None
