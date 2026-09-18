"""Explicitly configured, single-call structured-output judge transport."""

from __future__ import annotations

import os
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from tripplanner.evals.judge import Judgement


class JudgeProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    provider: Literal["openai", "azure"]
    model: str = Field(min_length=1)
    model_revision: str = Field(min_length=1)
    input_usd_per_million: float = Field(gt=0)
    output_usd_per_million: float = Field(gt=0)
    price_reference: str = Field(min_length=1)
    cumulative_cap_inr: float = Field(gt=0)
    max_completion_tokens: int = Field(default=4096, ge=256, le=16000)
    max_input_bytes: int = Field(default=100000, ge=1000, le=1000000)
    api_key_env: str = "OPENAI_API_KEY"
    endpoint_env: str = "AZURE_OPENAI_ENDPOINT"
    api_version: str = "2024-10-21"

    def identity(self) -> dict:
        result = self.model_dump()
        if self.provider == "azure":
            endpoint = os.environ.get(self.endpoint_env, "")
            parsed = urlparse(endpoint)
            if parsed.scheme != "https" or not parsed.hostname or parsed.query or parsed.username:
                raise ValueError("Azure judge needs an HTTPS endpoint without credentials/query")
            result["endpoint"] = endpoint
        return result


def validate_credentials(profile: JudgeProfile) -> None:
    if not os.environ.get(profile.api_key_env, ""):
        raise ValueError(f"Set the judge credential environment variable {profile.api_key_env}")


def complete(profile: JudgeProfile, messages: list[dict]) -> dict:
    from openai import AzureOpenAI, OpenAI

    validate_credentials(profile)
    key = os.environ[profile.api_key_env]
    kwargs = {"api_key": key, "max_retries": 0, "timeout": 90.0}
    if profile.provider == "azure":
        client = AzureOpenAI(
            **kwargs, azure_endpoint=profile.identity()["endpoint"], api_version=profile.api_version
        )
    else:
        client = OpenAI(**kwargs, base_url="https://api.openai.com/v1")
    with client:
        response = client.chat.completions.create(
            model=profile.model,
            messages=messages,
            max_completion_tokens=profile.max_completion_tokens,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "itinerary_judgement",
                    "strict": True,
                    "schema": Judgement.model_json_schema(),
                },
            },
        )
    choice = response.choices[0]
    return {
        "content": choice.message.content,
        "refusal": choice.message.refusal,
        "finish_reason": choice.finish_reason,
        "model": response.model,
        "request_id": response.id,
        "usage": response.usage.model_dump() if response.usage else None,
    }
