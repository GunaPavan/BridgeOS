"""Hot-pluggable LLM client.

Provider resolution order:
    1. BEDROCK_REGION                    -> AWS Bedrock (multi-model: Sonnet + Haiku)
    2. ANTHROPIC_API_KEY                 -> Claude direct (claude-haiku by default)
    3. (none)                            -> mock

Bedrock is preferred because it satisfies the hackathon's "unified intelligent
AI layer" spec requirement AND lets us route tasks to different models within
one provider (Sonnet for chat, Haiku for fast intent classification).

The mock is NOT a placeholder — `app.agent.engine` calls it explicitly when
no key is set and it produces responses good enough to demo every flow.

This module ONLY does the network call; intent detection + tool routing +
response shaping live in `app.agent.engine`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal


Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(frozen=True)
class LLMResponse:
    text: str
    provider: str  # "bedrock", "anthropic", or "mock"
    model: str
    tokens_in: int | None = None
    tokens_out: int | None = None
    task: str | None = None  # Which routing task triggered the model ("chat", "intent", etc.)


# Default Bedrock model IDs.
# Updated 2026-06: the 3.x family was retired on Bedrock ("end of life") so
# the older IDs return ResourceNotFoundException. The 4.x family ships as
# cross-region inference profiles only; the raw foundation-model id returns
# "Invocation of model ID ... isn't supported with on-demand throughput".
# The `us.` prefix below is the US cross-region inference profile that works
# for an account in us-east-1. Override via BEDROCK_SONNET_ID / BEDROCK_HAIKU_ID.
DEFAULT_BEDROCK_SONNET = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
DEFAULT_BEDROCK_HAIKU = "us.anthropic.claude-haiku-4-5-20251001-v1:0"


# ----- provider detection -----


def _env(name: str) -> str | None:
    val = os.environ.get(name)
    return val if val else None


def is_live() -> bool:
    """True if any live LLM provider is configured."""
    return get_active_provider() != "mock"


def get_active_provider() -> Literal["bedrock", "anthropic", "mock"]:
    if _env("BEDROCK_REGION"):
        return "bedrock"
    if _env("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "mock"


def get_default_model() -> str:
    """The model that would be used right now given env vars (chat task)."""
    provider = get_active_provider()
    if provider == "bedrock":
        return _env("BEDROCK_SONNET_ID") or DEFAULT_BEDROCK_SONNET
    if provider == "anthropic":
        return _env("ANTHROPIC_MODEL") or "claude-haiku-4-5"
    return "bridge-os-mock-v1"


def get_bedrock_model_for_task(task: str) -> str:
    """Return the Bedrock model id chosen for a given task type.

    Routing:
        "intent"      -> Haiku (fast classification, cheap)
        "chat"        -> Sonnet (deep reasoning, default for user-facing)
        anything else -> Sonnet (safe default)
    """
    if task == "intent":
        return _env("BEDROCK_HAIKU_ID") or DEFAULT_BEDROCK_HAIKU
    return _env("BEDROCK_SONNET_ID") or DEFAULT_BEDROCK_SONNET


# ----- entry point -----


def chat(
    system_prompt: str,
    messages: list[ChatMessage],
    *,
    max_tokens: int = 1024,
    temperature: float = 0.3,
    task: str = "chat",
    mock_handler=None,  # callable(system, messages) -> str, used in mock mode
) -> LLMResponse:
    """Run a chat completion. Returns text + provider metadata.

    `task` (Bedrock only): determines which Bedrock model handles the call.
        "chat"   -> Sonnet (deep reasoning, user-facing)
        "intent" -> Haiku (fast classification)
        Defaults to "chat" — other providers ignore this hint.

    `mock_handler` is required in mock mode — `engine.py` passes its rule-based
    responder. We keep that out of this module so the LLM layer is pure.
    """
    provider = get_active_provider()
    if provider == "bedrock":
        return _call_bedrock(system_prompt, messages, max_tokens, temperature, task)
    if provider == "anthropic":
        resp = _call_anthropic(system_prompt, messages, max_tokens, temperature)
        return LLMResponse(
            text=resp.text, provider=resp.provider, model=resp.model,
            tokens_in=resp.tokens_in, tokens_out=resp.tokens_out, task=task,
        )
    if mock_handler is None:
        raise RuntimeError("Mock mode but no mock_handler provided")
    text = mock_handler(system_prompt, messages)
    return LLMResponse(
        text=text,
        provider="mock",
        model="bridge-os-mock-v1",
        task=task,
    )


def _call_bedrock(
    system_prompt: str,
    messages: list[ChatMessage],
    max_tokens: int,
    temperature: float,
    task: str,
) -> LLMResponse:
    """Invoke a Claude model on AWS Bedrock via boto3.

    Uses the Messages API format (anthropic_version=bedrock-2023-05-31).
    Picks Sonnet or Haiku based on `task`. AWS credentials are resolved by
    the default boto3 chain (env vars, ~/.aws/credentials, instance profile).
    """
    import json

    import boto3  # type: ignore[import-not-found]

    region = _env("BEDROCK_REGION") or "us-east-1"
    model_id = get_bedrock_model_for_task(task)

    client = boto3.client("bedrock-runtime", region_name=region)
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system_prompt,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
    }
    response = client.invoke_model(modelId=model_id, body=json.dumps(body))
    payload = json.loads(response["body"].read())

    text_parts = []
    for block in payload.get("content", []):
        if block.get("type") == "text":
            text_parts.append(block.get("text", ""))

    usage = payload.get("usage", {})
    return LLMResponse(
        text="".join(text_parts).strip(),
        provider="bedrock",
        model=model_id,
        tokens_in=usage.get("input_tokens"),
        tokens_out=usage.get("output_tokens"),
        task=task,
    )


def _call_anthropic(
    system_prompt: str,
    messages: list[ChatMessage],
    max_tokens: int,
    temperature: float,
) -> LLMResponse:
    from anthropic import Anthropic  # type: ignore[import-not-found]

    api_key = _env("ANTHROPIC_API_KEY")
    assert api_key, "ANTHROPIC_API_KEY required"
    model = get_default_model()
    client = Anthropic(api_key=api_key)

    api_messages = [{"role": m.role, "content": m.content} for m in messages]
    response = client.messages.create(
        model=model,
        system=system_prompt,
        messages=api_messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    # Extract text from response
    text_parts = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            text_parts.append(getattr(block, "text", ""))
    return LLMResponse(
        text="".join(text_parts).strip(),
        provider="anthropic",
        model=model,
        tokens_in=getattr(response.usage, "input_tokens", None),
        tokens_out=getattr(response.usage, "output_tokens", None),
    )


