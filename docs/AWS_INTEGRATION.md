# AWS Real Integrations

Bridge OS uses four AWS services for the production runtime:

| Service | Module | Role |
|---|---|---|
| SES | `app.integrations.ses_client` | Email channel (caregiver digests, emergency fallback) |
| SQS | `app.integrations.sqs_client` | Outbound dispatch queue (decouples allocator from Twilio) |
| SNS | `app.integrations.sns_client` | Event fan-out (donor reply, wave expired, etc.) |
| EventBridge Scheduler | `infra/eventbridge.yaml` | Cron source (replaces APScheduler in production) |

Every service is built on top of the unified bootstrap layer in
`app/integrations/aws.py` — that's the single source of truth for region,
boto3 clients, auth probing, and resource naming.

---

## Auth chain

`aws_available()` returns True if **any** of these resolves:

1. `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` env vars
2. `AWS_PROFILE` / `AWS_DEFAULT_PROFILE` env var pointing to a profile in `~/.aws/credentials`
3. `~/.aws/credentials` file populated (the default after `aws configure`)
4. `AWS_CONTAINER_CREDENTIALS_RELATIVE_URI` (ECS/Fargate task role)

Set `BRIDGE_OS_DISABLE_AWS=1` to force mock mode regardless of the above.

## Region

Resolved with this precedence:

```
AWS_REGION  →  AWS_DEFAULT_REGION  →  BEDROCK_REGION  →  us-east-1
```

## Mock fallback

If `aws_available()` returns False, every client (`ses_client`, `sqs_client`,
`sns_client`) returns mock IDs (`MOCK-...`) and writes the same audit rows
as a live call. This lets:

- Developers run the whole stack with zero AWS config
- CI tests stay deterministic
- The demo continue working even if AWS hits a regional outage

## Resource naming + tagging

Every resource we create gets:

- Name prefix `team019-bridge-os-*` (override with `BRIDGE_OS_AWS_PREFIX`)
- Tags: `Project=bridge-os`, `Team=019`, `Owner=Gunaputra`, `ManagedBy=app.integrations.aws`

Cleanup is a single command:

```bash
bash scripts/aws_cleanup.sh
```

## Cost guard

The whole stack runs on free tier:

| Service | Free tier (monthly) | Our 48h usage | Cost |
|---|---|---|---|
| SES | 62,000 emails | ~200 | $0 |
| SQS | 1M requests | ~5,000 | $0 |
| SNS | 1M publishes | ~2,000 | $0 |
| EventBridge | 14M invocations | ~10,000 | $0 |

If you want a hard cap, set an AWS Budget at $30 via the Console.

## Per-service setup

See:
- [`SES.md`](./SES.md) — verify-identity sandbox flow
- [`SQS.md`](./SQS.md) — dispatch queue + DLQ topology
- [`SNS.md`](./SNS.md) — topic catalogue + subscriber map
- [`EVENTBRIDGE.md`](./EVENTBRIDGE.md) — post-deploy cron setup
