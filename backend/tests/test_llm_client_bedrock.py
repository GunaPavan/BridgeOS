"""Bedrock provider branch in app.agent.llm_client.

All Bedrock calls are stubbed with `unittest.mock.patch` so these tests
require zero AWS credentials and run in ~ms. The contract being tested
is the BRIDGE between our code and boto3 — we don't test boto3 itself.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.agent.llm_client import (
    ChatMessage,
    DEFAULT_BEDROCK_HAIKU,
    DEFAULT_BEDROCK_SONNET,
    chat,
    get_active_provider,
    get_bedrock_model_for_task,
    get_default_model,
)


def _bedrock_payload(text: str = "ok", in_tok: int = 10, out_tok: int = 5):
    """Realistic shape of Claude-on-Bedrock invoke_model response body."""
    return json.dumps(
        {
            "content": [{"type": "text", "text": text}],
            "usage": {"input_tokens": in_tok, "output_tokens": out_tok},
        }
    )


# ------------------------------------------------------------------
# Provider detection
# ------------------------------------------------------------------


def test_provider_detected_when_bedrock_region_set(monkeypatch):
    monkeypatch.setenv("BEDROCK_REGION", "us-east-1")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert get_active_provider() == "bedrock"


def test_bedrock_takes_priority_over_anthropic(monkeypatch):
    """If both BEDROCK_REGION and ANTHROPIC_API_KEY are set, prefer Bedrock —
    it satisfies the hackathon spec's 'unified intelligent AI layer' requirement."""
    monkeypatch.setenv("BEDROCK_REGION", "us-east-1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert get_active_provider() == "bedrock"


def test_get_default_model_returns_sonnet_when_bedrock_active(monkeypatch):
    monkeypatch.setenv("BEDROCK_REGION", "us-east-1")
    monkeypatch.delenv("BEDROCK_SONNET_ID", raising=False)
    assert get_default_model() == DEFAULT_BEDROCK_SONNET


def test_bedrock_model_for_task_routes_intent_to_haiku():
    assert get_bedrock_model_for_task("intent") == DEFAULT_BEDROCK_HAIKU
    assert get_bedrock_model_for_task("chat") == DEFAULT_BEDROCK_SONNET
    # Unknown task falls back to Sonnet (safe default)
    assert get_bedrock_model_for_task("something_else") == DEFAULT_BEDROCK_SONNET


# ------------------------------------------------------------------
# chat() → routes the call through Bedrock
# ------------------------------------------------------------------


def test_chat_task_default_routes_to_sonnet(monkeypatch):
    """A default chat call should hit Sonnet, not Haiku."""
    monkeypatch.setenv("BEDROCK_REGION", "us-east-1")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    fake_client = MagicMock()
    fake_client.invoke_model.return_value = {
        "body": MagicMock(read=lambda: _bedrock_payload("hello from sonnet").encode())
    }

    with patch("boto3.client", return_value=fake_client) as p_boto:
        result = chat(
            "system",
            [ChatMessage(role="user", content="hi")],
            task="chat",
        )

    assert result.provider == "bedrock"
    assert result.model == DEFAULT_BEDROCK_SONNET
    assert result.task == "chat"
    assert result.text == "hello from sonnet"
    assert result.tokens_in == 10
    assert result.tokens_out == 5
    p_boto.assert_called_once_with("bedrock-runtime", region_name="us-east-1")
    # And the model id passed in the invoke_model call IS Sonnet
    call_kwargs = fake_client.invoke_model.call_args.kwargs
    assert call_kwargs["modelId"] == DEFAULT_BEDROCK_SONNET


def test_chat_task_intent_routes_to_haiku(monkeypatch):
    """Intent classification uses Haiku — cheaper + faster."""
    monkeypatch.setenv("BEDROCK_REGION", "us-east-1")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    fake_client = MagicMock()
    fake_client.invoke_model.return_value = {
        "body": MagicMock(read=lambda: _bedrock_payload("intent_label").encode())
    }

    with patch("boto3.client", return_value=fake_client):
        result = chat(
            "system",
            [ChatMessage(role="user", content="classify this")],
            task="intent",
        )

    assert result.model == DEFAULT_BEDROCK_HAIKU
    assert result.task == "intent"
    assert fake_client.invoke_model.call_args.kwargs["modelId"] == DEFAULT_BEDROCK_HAIKU


def test_chat_passes_temperature_and_max_tokens_to_bedrock(monkeypatch):
    monkeypatch.setenv("BEDROCK_REGION", "us-east-1")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    fake_client = MagicMock()
    fake_client.invoke_model.return_value = {
        "body": MagicMock(read=lambda: _bedrock_payload().encode())
    }

    with patch("boto3.client", return_value=fake_client):
        chat(
            "you are helpful",
            [ChatMessage(role="user", content="hi")],
            max_tokens=512,
            temperature=0.7,
        )

    body = json.loads(fake_client.invoke_model.call_args.kwargs["body"])
    assert body["max_tokens"] == 512
    assert body["temperature"] == 0.7
    assert body["system"] == "you are helpful"
    assert body["messages"] == [{"role": "user", "content": "hi"}]


# ------------------------------------------------------------------
# Backwards compatibility — when BEDROCK_REGION is unset, fall through
# ------------------------------------------------------------------


def test_falls_back_to_anthropic_when_bedrock_not_set(monkeypatch):
    monkeypatch.delenv("BEDROCK_REGION", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert get_active_provider() == "anthropic"


def test_falls_back_to_mock_when_nothing_set(monkeypatch):
    monkeypatch.delenv("BEDROCK_REGION", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert get_active_provider() == "mock"
