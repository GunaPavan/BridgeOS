"""Hot-pluggable embeddings + cosine similarity.

Resolution order matches the agent's LLM client philosophy:
    1. BEDROCK_REGION  -> Amazon Titan Text v2 (1024d)
    2. OPENAI_API_KEY  -> OpenAI text-embedding-3-small
    3. (none)          -> deterministic local hash-bag fallback (lexical similarity, 128d)

The local fallback is good enough for short hackathon-scale memory: it gives
real cosine signal on token overlap and runs with zero deps.

Cross-provider memory: cohort_memory rows store `embedding_dim` per row, so
mixing providers is safe — retrieval just filters to vectors that match the
querying provider's dim. Use `scripts/reembed_memories.py` to migrate.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from dataclasses import dataclass
from typing import Literal


EmbedProvider = Literal["bedrock_titan", "openai", "local"]
DEFAULT_DIM = 128
TITAN_DIM = 1024
DEFAULT_BEDROCK_TITAN = "amazon.titan-embed-text-v2:0"


@dataclass(frozen=True)
class EmbedResult:
    vector: list[float]
    provider: EmbedProvider
    model: str
    dim: int


def _env(name: str) -> str | None:
    val = os.environ.get(name)
    return val if val else None


def get_active_provider() -> EmbedProvider:
    if _env("BEDROCK_REGION"):
        return "bedrock_titan"
    if _env("OPENAI_API_KEY"):
        return "openai"
    return "local"


def get_active_model() -> str:
    p = get_active_provider()
    if p == "bedrock_titan":
        return _env("BEDROCK_TITAN_ID") or DEFAULT_BEDROCK_TITAN
    if p == "openai":
        return _env("OPENAI_EMBEDDING_MODEL") or "text-embedding-3-small"
    return f"bridge-os-localhash-d{DEFAULT_DIM}"


# ----- local hash-bag fallback -----


_TOKEN_RE = re.compile(r"\w+", flags=re.UNICODE)


def _stable_hash(s: str) -> int:
    """Deterministic across processes (Python's `hash()` is not)."""
    return int(hashlib.sha256(s.encode("utf-8")).hexdigest()[:12], 16)


def _embed_local(text: str, dim: int = DEFAULT_DIM) -> list[float]:
    """Hash bag-of-words to a `dim`-d vector, L2-normalized."""
    tokens = [t.lower() for t in _TOKEN_RE.findall(text or "")]
    if not tokens:
        return [0.0] * dim
    vec = [0.0] * dim
    for t in tokens:
        # Three hashes per token = more cross-token signal without inflating dim
        for salt in (b"a", b"b", b"c"):
            h = _stable_hash(salt.decode() + t) % dim
            vec[h] += 1.0
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return vec
    return [x / norm for x in vec]


# ----- live provider paths -----


def _embed_openai(text: str) -> list[float]:
    from openai import OpenAI  # type: ignore[import-not-found]

    client = OpenAI(api_key=_env("OPENAI_API_KEY"))
    model = get_active_model()
    resp = client.embeddings.create(input=text, model=model)
    return list(resp.data[0].embedding)


def _embed_bedrock_titan(text: str) -> list[float]:
    """Amazon Titan Text Embeddings v2 on Bedrock. 1024-dim, L2-normalized."""
    import json

    import boto3  # type: ignore[import-not-found]

    region = _env("BEDROCK_REGION") or "us-east-1"
    model_id = _env("BEDROCK_TITAN_ID") or DEFAULT_BEDROCK_TITAN
    client = boto3.client("bedrock-runtime", region_name=region)
    body = {"inputText": text, "dimensions": TITAN_DIM, "normalize": True}
    response = client.invoke_model(modelId=model_id, body=json.dumps(body))
    payload = json.loads(response["body"].read())
    return list(payload["embedding"])


def embed(text: str) -> EmbedResult:
    """Single entry point used by `agent.memory`."""
    provider = get_active_provider()
    model = get_active_model()
    if provider == "bedrock_titan":
        vec = _embed_bedrock_titan(text)
    elif provider == "openai":
        vec = _embed_openai(text)
    else:
        vec = _embed_local(text)
    return EmbedResult(vector=vec, provider=provider, model=model, dim=len(vec))


# ----- similarity -----


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity in [-1, 1]. Returns 0 if either vector is zero."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0 or nb == 0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))
