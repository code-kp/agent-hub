from __future__ import annotations

LITELLM_PREFIX = "litellm:"
_KNOWN_PROVIDER_PREFIXES = (
    "anthropic/",
    "azure/",
    "bedrock/",
    "cerebras/",
    "cohere/",
    "deepseek/",
    "gemini/",
    "google/",
    "groq/",
    "mistral/",
    "ollama/",
    "openai/",
    "openrouter/",
    "perplexity/",
    "vertex_ai/",
    "xai/",
)


def lite_llm_model(model_name: str) -> str:
    normalized = normalize_lite_llm_reference(model_name)
    return "{prefix}{model}".format(prefix=LITELLM_PREFIX, model=normalized)


def is_lite_llm_model(model_name: str | None) -> bool:
    normalized = str(model_name or "").strip().lower()
    return normalized.startswith(LITELLM_PREFIX)


def strip_lite_llm_prefix(model_name: str) -> str:
    normalized = str(model_name or "").strip()
    if is_lite_llm_model(normalized):
        return normalized[len(LITELLM_PREFIX) :].strip()
    return normalized


def normalize_lite_llm_reference(model_name: str) -> str:
    normalized = strip_lite_llm_prefix(model_name)
    if not normalized:
        raise ValueError("LiteLLM model name cannot be blank.")

    lowered = normalized.lower()
    if lowered.startswith(_KNOWN_PROVIDER_PREFIXES):
        return normalized

    if lowered.startswith("gemini"):
        return "gemini/{model}".format(model=normalized)

    raise ValueError(
        "LiteLLM models must use an explicit provider/model reference such as "
        "`openai/gpt-4o-mini`, `anthropic/claude-3-7-sonnet`, or "
        "`gemini/gemini-2.0-flash`."
    )


def normalize_model_reference(
    model_name: str | None,
    *,
    model_backend: str | None = None,
) -> str:
    normalized = str(model_name or "").strip()
    if not normalized:
        return ""
    if is_lite_llm_model(normalized):
        return normalized
    if str(model_backend or "").strip().lower() == "litellm":
        return lite_llm_model(normalized)
    return normalized
