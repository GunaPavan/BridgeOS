"""Titan v2 embeddings branch in app.agent.embeddings.

Mocked at the boto3.client layer — no AWS calls in CI.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from app.agent.embeddings import (
    DEFAULT_BEDROCK_TITAN,
    TITAN_DIM,
    embed,
    get_active_model,
    get_active_provider,
)


def _titan_payload(dim: int = TITAN_DIM):
    """Realistic shape of Titan Text Embeddings v2 invoke_model response."""
    return json.dumps({"embedding": [0.01] * dim, "inputTextTokenCount": 12})


def test_provider_detected_when_bedrock_region_set(monkeypatch):
    monkeypatch.setenv("BEDROCK_REGION", "us-east-1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert get_active_provider() == "bedrock_titan"
    assert get_active_model() == DEFAULT_BEDROCK_TITAN


def test_bedrock_titan_takes_priority_over_openai(monkeypatch):
    monkeypatch.setenv("BEDROCK_REGION", "us-east-1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert get_active_provider() == "bedrock_titan"


def test_embed_titan_returns_1024_dim_vector(monkeypatch):
    monkeypatch.setenv("BEDROCK_REGION", "us-east-1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    fake_client = MagicMock()
    fake_client.invoke_model.return_value = {
        "body": MagicMock(read=lambda: _titan_payload().encode())
    }
    with patch("boto3.client", return_value=fake_client):
        result = embed("the donor missed last 3 calls")

    assert result.provider == "bedrock_titan"
    assert result.model == DEFAULT_BEDROCK_TITAN
    assert result.dim == TITAN_DIM
    assert len(result.vector) == TITAN_DIM

    # And the request body was correct
    body = json.loads(fake_client.invoke_model.call_args.kwargs["body"])
    assert body["inputText"] == "the donor missed last 3 calls"
    assert body["dimensions"] == TITAN_DIM
    assert body["normalize"] is True


def test_falls_back_to_local_when_bedrock_not_set(monkeypatch):
    monkeypatch.delenv("BEDROCK_REGION", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = embed("hello")
    assert result.provider == "local"
    assert result.dim == 128  # local hashbag default
