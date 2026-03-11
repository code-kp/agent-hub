from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import warnings

import core.contracts.models as contracts_models


@dataclass(frozen=True)
class ResolvedModel:
    reference: str
    display_name: str
    backend: str
    adk_model: Any


def resolve_model(model_name: str) -> ResolvedModel:
    normalized = str(model_name or "").strip()
    if not normalized:
        raise ValueError("Model name cannot be blank.")

    if contracts_models.is_lite_llm_model(normalized):
        return _resolve_lite_llm_model(normalized)

    return ResolvedModel(
        reference=normalized,
        display_name=normalized,
        backend="native",
        adk_model=normalized,
    )


def _resolve_lite_llm_model(model_name: str) -> ResolvedModel:
    provider_model = contracts_models.normalize_lite_llm_reference(model_name)

    try:
        from google.adk.models.lite_llm import LiteLlm
    except ImportError as exc:  # pragma: no cover - exercised in unit tests via patch
        raise RuntimeError(
            "LiteLLM models require the optional ADK extensions dependency. "
            "Run `uv sync --all-groups --all-extras` after adding `litellm`."
        ) from exc

    return ResolvedModel(
        reference=contracts_models.lite_llm_model(provider_model),
        display_name=contracts_models.lite_llm_model(provider_model),
        backend="litellm",
        adk_model=_build_litellm_adapter(LiteLlm, provider_model),
    )


def describe_model_error(exc: Exception, *, model_reference: str) -> str:
    raw_error = " ".join(str(exc or "").split()).strip()
    reference = str(model_reference or "").strip()
    lowered = raw_error.lower()

    if "default credentials were not found" in lowered or "failed to load vertex credentials" in lowered:
        if reference.startswith("litellm:"):
            return (
                "The configured LiteLLM model could not authenticate. "
                "If you want Google AI Studio, use `litellm:gemini/<model>` with "
                "`GOOGLE_API_KEY` or `GEMINI_API_KEY`. If you want Vertex AI, "
                "configure Application Default Credentials and the required Vertex settings."
            )
        return (
            "The configured model could not authenticate with the provider. "
            "Check the provider credentials and model routing configuration."
        )

    if "api key" in lowered and ("missing" in lowered or "not configured" in lowered or "not found" in lowered):
        return (
            "The configured model provider is missing its API key. "
            "Set the provider-specific credentials before running the agent."
        )

    if "litellm models must use an explicit provider/model reference" in lowered:
        return raw_error or (
            "LiteLLM models must use an explicit provider/model reference."
        )

    if reference.startswith("litellm:"):
        return (
            "The configured LiteLLM model request failed. "
            "Check the provider/model reference and provider credentials."
        )

    return raw_error or "The model request failed."


def should_retry_model_error(exc: Exception) -> bool:
    raw_error = " ".join(str(exc or "").split()).strip().lower()
    if not raw_error:
        return False

    retry_markers = (
        '"code": 500',
        "'code': 500",
        " 500 internal",
        "status': 'internal'",
        'status": "internal"',
        "internal error encountered",
        "service unavailable",
        "temporarily unavailable",
        "upstream connect error",
    )
    return any(marker in raw_error for marker in retry_markers)


def _build_litellm_adapter(litellm_cls: Any, provider_model: str) -> Any:
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"\[GEMINI_VIA_LITELLM\].*",
            category=UserWarning,
        )
        return litellm_cls(model=provider_model)
