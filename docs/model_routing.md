# Bedrock Multi-Model Routing

Bridge OS speaks to AWS Bedrock through a single client and routes each call
to the cheapest model that can do the job well. This document explains the
routing rules, expected cost envelope, and fallback behaviour.

## Provider precedence

The `app/agent/llm_client.py` resolver picks a provider in this order:

| Order | Trigger env var | Provider | Why this rank |
|-------|-----------------|----------|---------------|
| 1 | `BEDROCK_REGION` | AWS Bedrock (multi-model) | Spec-mandated "unified intelligent AI layer" |
| 2 | `ANTHROPIC_API_KEY` | Anthropic direct (Claude Haiku) | Portable fallback for local dev |
| 3 | _(none)_ | Rule-based mock | Demos work without any API key |

Embeddings (`app/agent/embeddings.py`) follow the same precedence:
Bedrock Titan v2 → OpenAI → 128-d local hashbag.

## Task → model decisions (Bedrock only)

| Task | Inference profile id | Latency | Cost / 1K tokens (in / out) |
|------|---------------------|--------:|-----------------------------|
| `chat` (default) | `us.anthropic.claude-sonnet-4-5-20250929-v1:0` | 2–8 s | $0.003 / $0.015 |
| `intent` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | 0.5–2 s | $0.001 / $0.005 |
| `embed` (cohort memory) | `amazon.titan-embed-text-v2:0` | 0.1–0.3 s | $0.00002 in only |

> **Why the `us.` prefix?** Claude 4.x models on Bedrock are gated behind
> cross-region inference profiles, not raw foundation-model IDs. Calling the
> bare `anthropic.claude-sonnet-4-5-…` ID returns
> `ValidationException: Invocation of model ID … isn't supported with
> on-demand throughput`. The `us.` prefix routes through the US system-defined
> inference profile that the account already has access to. The older 3.x
> family (`claude-3-5-sonnet-20241022-v2:0`, etc.) is marked end-of-life by
> Anthropic and returns `ResourceNotFoundException` on Bedrock.

### Sample 5-minute coordinator session cost

- 1× caregiver chat → Sonnet, ~500 tokens out: **$0.0075**
- 3× intent classifications → Haiku, ~50 tokens each: **$0.00019**
- 2× memory writes → Titan, 200 tokens each: **$0.000008**

**≈ $0.008 per session**. At 100 sessions/day → $0.80/day → $24/month.

## Why this routing wins

- **Cost**: Haiku is **12× cheaper input + 12× cheaper output** than Sonnet.
  Routing intent classification to Haiku and reserving Sonnet for chat keeps
  costs under the hackathon's $40 cap even at heavy demo load.
- **Latency**: Haiku replies in ~0.5 s vs Sonnet's 1–3 s — better UX for
  classification-style calls (e.g. WhatsApp intent in the webhook).
- **Quality**: Sonnet's reasoning is materially better for caregiver
  conversations, multilingual nuance, and cohort-level explanations.

## Cross-provider memory (embeddings)

Cohort memory rows store `embedding_provider` and `embedding_dim` per row.
When you switch from the local 128-d fallback to Titan's 1024-d output,
old rows simply become invisible to retrieval (dim mismatch returns empty).
This is **graceful degradation** — no broken queries, no crashes. To migrate
historical memories to Titan, run:

```bash
python -m scripts.reembed_memories
```

This is an opt-in operation; it costs roughly $0.00002 per memory row.

## Failure modes + fallback

| Failure | Behaviour |
|---------|-----------|
| `AccessDeniedException` (model not enabled in account) | Logged warning, raises 500. **Fix**: enable the model in Bedrock console > Model access. |
| Network timeout > 30 s | boto3 default timeout fires; error propagates as 500. |
| Bedrock rate limit | boto3 retries with backoff. After exhaustion, error propagates. |
| `BEDROCK_REGION` unset | Falls through to Anthropic direct → mock chain. |

## Required IAM permissions

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["bedrock:InvokeModel"],
    "Resource": [
      "arn:aws:bedrock:us-east-1:*:inference-profile/us.anthropic.claude-sonnet-4-5-20250929-v1:0",
      "arn:aws:bedrock:us-east-1:*:inference-profile/us.anthropic.claude-haiku-4-5-20251001-v1:0",
      "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-sonnet-4-5-20250929-v1:0",
      "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
      "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0"
    ]
  }]
}
```

Credentials come from the default boto3 chain — env vars, `~/.aws/credentials`,
or an instance profile when deployed on App Runner / EC2.

## Operational knobs

| Env var | Default | Purpose |
|---------|---------|---------|
| `BEDROCK_REGION` | _unset_ | Activates Bedrock routing |
| `BEDROCK_SONNET_ID` | `us.anthropic.claude-sonnet-4-5-20250929-v1:0` | Override chat model (inference-profile id) |
| `BEDROCK_HAIKU_ID` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | Override intent model (inference-profile id) |
| `BEDROCK_TITAN_ID` | `amazon.titan-embed-text-v2:0` | Override embedding model |

## See also

- `app/agent/llm_client.py` — provider detection + `_call_bedrock`
- `app/agent/embeddings.py` — Titan branch + cross-dim graceful degradation
- `tests/test_llm_client_bedrock.py` — routing contract tests
- `tests/test_embeddings_titan.py` — Titan branch tests
