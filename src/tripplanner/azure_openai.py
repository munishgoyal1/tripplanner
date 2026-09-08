from __future__ import annotations

from typing import Any

from tripplanner.config import get_settings


class AzureOpenAIDisabledError(RuntimeError):
    pass


def require_azure_openai_enabled(settings: Any | None = None) -> Any:
    resolved = settings or get_settings()
    if not resolved.enable_azure_openai:
        raise AzureOpenAIDisabledError(
            "Azure OpenAI is intentionally disabled by ENABLE_AZURE_OPENAI."
        )
    return resolved
