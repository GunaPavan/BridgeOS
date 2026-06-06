# Bridge OS — API

> The live, machine-generated source of truth is the Swagger UI at `http://localhost:8000/docs` when the backend is running.

## Phase 0 — meta

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/health` | Liveness probe. Returns `{"status": "ok", "version": "..."}`. |
| `GET`  | `/` | API root. Returns name, version, docs link. |

## Phase 1 — bridges

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/bridges` | Paginated list of bridges with patient summary + stub health. Query: `skip` (≥0), `limit` (1–200, default 50). |
| `GET`  | `/bridges/{bridge_id}` | Full bridge detail: patient profile + donor cohort. 404 if not found. |

### `BridgeListItem` (response of list)

```json
{
  "id": "uuid",
  "patient_id": "uuid",
  "patient_name": "Aarav Reddy",
  "patient_age": 8,
  "blood_group": "B+",
  "city": "Hyderabad",
  "state": "Telangana",
  "hospital": "Apollo Hospitals",
  "status": "active",
  "active_donor_count": 8,
  "total_donor_count": 10,
  "health": "stable" | "at_risk" | "critical",
  "last_transfusion_date": "2026-05-19",
  "next_transfusion_date": "2026-06-06",
  "days_until_transfusion": 6,
  "created_at": "2026-05-31T..."
}
```

### `BridgeDetail` (response of detail)

Extends `BridgeListItem` with:

```json
{
  "name": "Bridge for Aarav",
  "patient": { /* PatientDetail */ },
  "members": [
    {
      "id": "uuid",
      "role": "primary" | "backup",
      "status": "active" | "paused" | "exited",
      "joined_at": "2025-06-15",
      "notes": null,
      "donor": { /* DonorSummary */ }
    }
  ]
}
```

## Phase 2 — donors

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/donors` | Paginated donor list with filters. Query: `skip` (≥0), `limit` (1–200), `search` (name substring, case-insensitive), `blood_group`, `city`, `is_active` (bool), `kell_negative` (bool), `sort` (name\|last_donation\|response_rate\|total_donations\|age), `order` (asc\|desc). |
| `GET`  | `/donors/{donor_id}` | Full donor profile including all bridge memberships. 404 if not found. |

### `DonorListItem`

```json
{
  "id": "uuid",
  "name": "Priya Sharma",
  "age": 28,
  "blood_group": "B+",
  "rh_negative": false,
  "kell_negative": true,
  "city": "Hyderabad",
  "state": "Telangana",
  "preferred_language": "te",
  "last_donation_date": "2026-05-17",
  "days_since_donation": 14,
  "total_donations": 12,
  "response_rate": 0.42,
  "avg_response_hours": 38.0,
  "is_active": true,
  "is_eligible_to_donate": false,
  "bridge_count": 1
}
```

### `DonorDetail`

Extends `DonorListItem` with `phone`, `lat`, `lng`, `extended_phenotype`, `registered_at`, and:

```json
{
  "memberships": [
    {
      "membership_id": "uuid",
      "bridge_id": "uuid",
      "bridge_name": "Bridge for Aarav",
      "bridge_status": "active",
      "patient_id": "uuid",
      "patient_name": "Aarav Reddy",
      "patient_age": 8,
      "patient_blood_group": "B+",
      "role": "primary",
      "status": "active",
      "joined_at": "2026-01-30"
    }
  ]
}
```

## Phase 3 — patients

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/patients` | Paginated patient roster with filters. Query: `skip`, `limit`, `search` (name substring), `blood_group`, `city`, `active`, `has_bridge`, `bridge_health` (stable\|at_risk\|critical), `sort` (name\|age\|last_transfusion), `order` (asc\|desc). |
| `GET`  | `/patients/{patient_id}` | Full profile + bridge summary + projected next 6 transfusion dates. 404 if not found. |

### `PatientListItem`

```json
{
  "id": "uuid",
  "name": "Aarav Reddy",
  "age": 8,
  "blood_group": "B+",
  "rh_negative": false,
  "kell_negative": true,
  "city": "Hyderabad",
  "state": "Telangana",
  "hospital": "Apollo Hospitals",
  "preferred_language": "te",
  "transfusion_cadence_days": 18,
  "last_transfusion_date": "2026-05-19",
  "next_transfusion_date": "2026-06-06",
  "days_until_transfusion": 6,
  "active": true,
  "has_bridge": true,
  "bridge_health": "stable",
  "active_donor_count": 8
}
```

### `PatientProfile`

Extends `PatientListItem` with `extended_phenotype`, `lat`, `lng`, `registered_at`, and:

```json
{
  "bridge": {
    "bridge_id": "uuid",
    "bridge_name": "Bridge for Aarav",
    "bridge_status": "active",
    "active_donor_count": 8,
    "total_donor_count": 8,
    "health": "stable",
    "created_at": "..."
  },
  "projected_transfusions": [
    "2026-06-06", "2026-06-24", "2026-07-12",
    "2026-07-30", "2026-08-17", "2026-09-04"
  ]
}
```

## Phase 4 — cohort stability (ML)

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/bridges/{bridge_id}/stability` | Per-donor churn predictions (30/60/90 day) with SHAP-explained top factors. 503 if the stability model has not been trained (`python -m scripts.train_stability`). 404 if bridge not found. |

### `BridgeStability` response

```json
{
  "bridge_id": "uuid",
  "bridge_name": "Bridge for Aarav",
  "computed_at": "2026-05-31T01:23:45Z",
  "model_version": "stability_v1",
  "aggregate": {
    "ml_health": "at_risk",
    "avg_churn_90d": 0.28,
    "max_churn_90d": 0.82,
    "at_risk_donor_count": 1,
    "active_donor_count": 8
  },
  "members": [
    {
      "donor_id": "uuid",
      "donor_name": "Priya Sharma",
      "churn_30d": 0.34,
      "churn_60d": 0.61,
      "churn_90d": 0.82,
      "top_factors": [
        {
          "feature": "response_rate",
          "label": "Low response rate (32%)",
          "direction": "increases_churn",
          "impact": 1.42
        },
        {
          "feature": "avg_response_hours",
          "label": "Slow average response (48.0 h)",
          "direction": "increases_churn",
          "impact": 0.93
        },
        {
          "feature": "days_since_donation",
          "label": "Long absence since last donation (120 days)",
          "direction": "increases_churn",
          "impact": 0.61
        }
      ]
    }
  ]
}
```

`aggregate.ml_health` thresholds: `stable` if `avg_churn_90d < 0.25`, `at_risk` if 0.25–0.45, `critical` if ≥ 0.45.

## Phase 5 — rotation schedule (OR-Tools CP-SAT)

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/bridges/{bridge_id}/schedule` | Solve the 12-month rotation. Query: `horizon_days` (30–730, default 365), `time_limit_seconds` (0.5–30, default 5). 404 if bridge missing. 422 if the solver returns `INFEASIBLE`. |
| `POST` | `/bridges/{bridge_id}/schedule/resolve` | Same as GET — re-runs a fresh solve. Reserved for the Phase 6 recruit-then-resolve flow. |

### `BridgeScheduleResponse`

```json
{
  "bridge_id": "uuid",
  "bridge_name": "Bridge for Aarav",
  "horizon_days": 365,
  "transfusion_cadence_days": 18,
  "solved_at": "2026-05-31T01:42:00Z",
  "solve_time_ms": 42,
  "solver_status": "OPTIMAL",
  "objective_value": 12345,
  "message": "",
  "slots": [
    {
      "sequence": 1,
      "transfusion_date": "2026-06-06",
      "donor_id": "uuid",
      "donor_name": "Karan Trivedi",
      "donor_blood_group": "O+"
    }
  ],
  "donor_load": [
    { "donor_id": "uuid", "donor_name": "Karan Trivedi", "assignment_count": 3 }
  ]
}
```

`solver_status` values: `OPTIMAL`, `FEASIBLE`, `INFEASIBLE` (surfaced as 422), `EMPTY` (no transfusions in horizon).

## Phase 6 — recommendations + recruit

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/recommendations` | Cross-bridge inbox of recruitment recommendations. Query: `only_weak` (default `true`), `top_k_per_bridge` (1–20, default 5), `at_risk_threshold` (0–1, default 0.5). 503 if stability model not loaded. |
| `GET`  | `/bridges/{id}/recommendations` | Per-bridge: weak donors + ranked replacement candidates. Same `top_k` + `at_risk_threshold` params. 404 if bridge missing. |
| `POST` | `/bridges/{id}/recruit` | Add a candidate donor. Body: `{candidate_donor_id, replace_donor_id?, notes?}`. 422 if blood-group incompatible. 409 if candidate is already an active member. 404 if either bridge or candidate not found. |

Composite candidate score: 30% distance + 30% response rate + 40% predicted 90d churn (lower is better). Kell-match adds a +0.10 bonus on top.

## Phase 7 — analytics

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/analytics` | System-wide aggregate stats: totals, donor pool breakdown, side-by-side stub vs ML cohort-health distributions, patients-by-city, stability model training metrics + live inference timing across all bridges. |

`stability_model` is `null` if the model isn't trained yet; in that case `ml_health` falls back to `stub_health`.

## Phase 8 — integrations

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/integrations` | Status hub for all external systems. Returns `mocked`, `connected`, `not_configured`, or `error` per integration with description + sample_count + last_sync + docs_url + phase. |
| `GET`  | `/integrations/eraktkosh/inventory` | Mock eRaktKosh blood-bank inventory. Query: `city`, `blood_group`. Deterministic per (bank × date). |
| `GET`  | `/integrations/icmr-rdri/lookup` | Mock ICMR Rare Donor Registry lookup. Query: `blood_group`, `kell_negative`, `city`. |

Mock data lives in `app.integrations.eraktkosh` and `app.integrations.icmr_rdri`. Swap the `fetch_inventory` / `lookup_donors` functions for real HTTP clients without changing the schemas.

## Phase 9 — simulator

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/simulator/bridges/{id}/scenario` | Stateless what-if. Body: `{ejected_donor_ids: [uuid…]}`. Runs stability + scheduler + recommender over baseline AND post-action cohorts in one call. Returns both states + a `delta` block. **No DB writes.** 503 if model not loaded, 404 if bridge missing. |

Used by the `/simulator` page to power the click-to-eject demo: each toggle instantly recomputes everything in ~50–100 ms.

## Phase 10 — WhatsApp (Twilio)

Real two-way WhatsApp messaging — coordinators can text donors from the dashboard, donors reply on their phones, and every message is stored. Twilio is hot-pluggable: with creds set the page sends real WhatsApps; without them it works in mock mode (`MOCK…` SIDs) so the demo runs offline.

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/whatsapp/status` | Twilio configuration probe. Returns `{is_live, from_number, sandbox_join_instructions}`. `is_live=true` only when both `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN` are set. |
| `GET`  | `/whatsapp/templates` | List of predefined outbound message templates (`slot_reminder`, `recruit_invite`, `thank_you`, `swap_request`) — each with a body template and a `requires_bridge` flag. |
| `GET`  | `/whatsapp/conversations` | One row per donor with at least one message — includes the last message and a count. Sorted most-recent first. |
| `GET`  | `/whatsapp/conversations/{donor_id}` | Full message thread for a donor in chronological order. 404 if donor missing. |
| `GET`  | `/whatsapp/messages` | Flat list of recent messages across all donors. Query: `limit` (1–200, default 50). |
| `POST` | `/whatsapp/send` | Send a message to a donor. Body: `{donor_id, body?, template_key?, bridge_id?}`. Exactly one of `body`/`template_key` is required; templates that reference patient context require `bridge_id`. Returns the persisted message + `is_live_twilio` flag. 404 if donor or bridge missing. |
| `POST` | `/whatsapp/webhook` | Twilio inbound webhook. Form-encoded (`From`, `To`, `Body`, `MessageSid`). Stores the message against the donor matched by phone (or `null` if unknown) and returns a TwiML `<Response><Message>` ACK. |

To go live with the Twilio WhatsApp Sandbox:

1. Sign up at <https://www.twilio.com/console> (free trial)
2. Activate the WhatsApp Sandbox (Settings → Programmable Messaging)
3. Set env vars: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, optional `TWILIO_WHATSAPP_FROM`
4. Point the sandbox webhook at `https://<your-tunnel>/whatsapp/webhook`
5. Donors send `join <sandbox-keyword>` to the sandbox number to opt in

## Care Agent (multilingual LLM)

Natural-language assistant. Coordinators ask in any of 8 Indian languages; the agent assembles per-entity context ("cohort memory") and either calls a real LLM or falls back to a rule-based mock that demos every flow.

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/agent/status` | Returns `{is_live, provider, model, supported_languages, multi_model, chat_model?, intent_model?, embedding_model?}`. Provider order: `bedrock` (BEDROCK_REGION) > `anthropic` (ANTHROPIC_API_KEY) > `mock`. When Bedrock is active, `multi_model: true` and the three per-task model ids are populated. |
| `POST` | `/agent/chat` | Body: `{query, session_id?, donor_id?, bridge_id?, patient_id?, language?}`. Returns the persisted user + assistant messages, the `sources` cited, plus `provider`/`model`/`is_live`/`task`. Pass the same `session_id` on subsequent turns to resume history. |
| `GET`  | `/agent/sessions?limit=N` | One row per session: id, first/last message time, count, last user query, language. |
| `GET`  | `/agent/sessions/{session_id}` | Full chronological history. 404 if session unknown. |

The supplied `donor_id` / `bridge_id` / `patient_id` triggers `app.agent.context.build_*_context()` which assembles a structured plain-text summary (profile + memberships + recent messages + cohort) the LLM reads as ground truth on every turn.

Supported languages: `en`, `hi`, `te`, `ta`, `mr`, `bn`, `kn`, `gu`.

To go live with AWS Bedrock (preferred — multi-model routing for chat / intent / embeddings):

```bash
export BEDROCK_REGION=us-east-1
# Optional model overrides — see docs/model_routing.md
# export BEDROCK_SONNET_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
# export BEDROCK_HAIKU_ID=anthropic.claude-3-haiku-20240307-v1:0
# export BEDROCK_TITAN_ID=amazon.titan-embed-text-v2:0
```

Or Anthropic direct (portable fallback):

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export ANTHROPIC_MODEL=claude-haiku-4-5   # optional
```

### Cohort memory (RAG)

The agent also retrieves prior episodic memories before answering, and persists every Q&A as a new memory for the next turn.

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/agent/memories?entity_id=<uuid>&limit=N` | Inspect stored memories, optionally filtered by entity. |

Chat responses include:

- `retrieved_memories`: list of top-K relevant memories (id, kind, summary, cosine score)
- `sources`: now includes one row per retrieved memory tagged `memory:<kind>` so the UI can cite them

Auto-detection: when the chat query contains Indic script (Devanagari / Bengali / Gujarati / Tamil / Telugu / Kannada), the response's `detected_language` field is set and the answer is delivered in that language regardless of the requested `language`.

Embeddings are hot-pluggable just like the LLM:

```bash
# AWS Bedrock — Amazon Titan Text v2 (1024-d, preferred for production)
export BEDROCK_REGION=us-east-1
# export BEDROCK_TITAN_ID=amazon.titan-embed-text-v2:0   # optional override

# Or OpenAI direct
export OPENAI_API_KEY=sk-...
export OPENAI_EMBEDDING_MODEL=text-embedding-3-small   # optional
```

Without either set, the agent uses a deterministic local hash-bag fallback (128-d, lexical similarity, zero deps). The `embedding` column is stored as JSON in SQLite and is one column-type swap from native pgvector in Postgres.


---

## Alert Allocator — global donor outreach engine

The Alert Allocator is the fifth AI system in Bridge OS. It decides **who to ping, on what channel, when, and how many** — under contention (many patients sharing the same donor pool) and under deadline pressure (variable per-patient transfusion cadences).

Five escalation tiers running through one engine:

| Tier | Channel | Template | Donors in scope |
|---|---|---|---|
| **Tier 1** | WhatsApp | `urgent_slot_alert` | Top-K minimal-batch (P_accept ≥ tier target) |
| **Tier 2** | WhatsApp | `urgent_slot_alert` | + next-best 4–6 fresh donors |
| **Tier 2.5** | **Phone** | Manual call script | Auto-promoted to `/manual-calls` Kanban |
| **Tier 3** | WhatsApp | `final_ask_soft` | Full pool incl. `inactive_limited_despite_calls` cohort |
| **Tier 4** | External | — | eRaktKosh inventory + ICMR RDRI lookup + coordinator alert |
| **EMERGENCY** | WhatsApp + phone | `urgent_slot_alert` (override quiet hours) | Every donor within reach window |

### Math

- **P_accept** for batch B: `1 - Π(1 - r_i)` where `r_i = donor.response_rate × (1 - churn_90d)`
- **Urgency tier**: keyed off `gap / cadence` (fraction of cycle remaining). Critical = gap ≤ 1d OR overdue; High = gap ≤ 3d AND ratio ≤ 0.15; Medium = gap ≤ 7d AND ratio ≤ 0.35.
- **Per-tier targets**: Critical 0.95 (max 8), High 0.85 (max 6), Medium 0.70 (max 4).
- **Composite score**: distance ⬇ + response rate ⬆ + (1 − churn) ⬆ + Kell match + survival bonus − fairness rotation penalty − bridge stickiness penalty.

### Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/outreach/run-cycle?dry_run=true` | Run one cycle of the global allocator. `dry_run` returns the proposed allocations without persisting. |
| `GET`  | `/outreach/waves` | List recent waves (filter `?status=active|accepted|expired`). |
| `GET`  | `/outreach/waves/{id}` | Wave detail with full ping list. |
| `POST` | `/outreach/waves/{id}/dispatch?override_quiet_hours=true` | Send the wave's PENDING pings via Twilio. `override_quiet_hours` only honoured in EMERGENCY tier. |
| `POST` | `/outreach/waves/{id}/promote-to-manual` | Hand the wave's unresponsive donors to the Tier 2.5 phone team. |
| `POST` | `/outreach/waves/{id}/force-include?donor_id=...` | Coordinator override — add a donor to an ACTIVE wave. |
| `POST` | `/outreach/waves/{id}/force-exclude?donor_id=...` | Coordinator override — cancel a PENDING ping. |
| `POST` | `/outreach/expire-and-sweep?auto_escalate=true` | Expire stale waves AND auto-create the next-tier wave per slot. |
| `POST` | `/outreach/confirm?donor_id=...&slot_ref=...` | Manual ACCEPTED close. |
| `POST` | `/outreach/decline?donor_id=...&slot_ref=...` | Manual DECLINED close. |
| `POST` | `/outreach/cancel-acceptance?donor_id=...` | Reverse a prior acceptance (donor can't make it anymore). |
| `POST` | `/outreach/emergency` | Coordinator-triggered emergency outreach. Body: `{patient_id, coordinator_name, transfusion_deadline_at, justification}`. Returns reachable donor count + spawned wave id + parallel eRaktKosh/ICMR results. |
| `GET`  | `/outreach/emergency/{event_id}` | Inspect an emergency event. |
| `GET`  | `/outreach/manual-calls?state=queued|in_progress|resolved` | Kanban-ready cards ordered by likely conversion. |
| `POST` | `/outreach/manual-calls/{id}/assign?caller=...` | Caller picks up a queued card. |
| `POST` | `/outreach/manual-calls/{id}/attempt?notes=...&callback_at=...` | Log a phone-call attempt without resolving. |
| `POST` | `/outreach/manual-calls/{id}/resolve?outcome=accepted|declined|no_answer|wrong_number|moved|other` | Final outcome. ACCEPTED + DECLINED feed back into the same close handlers the WhatsApp webhook uses. |
| `GET`  | `/outreach/analytics?lookback_days=30` | Operational metrics — pings-per-acceptance, avg minutes-to-accept by urgency, donor-fatigue distribution, manual-queue state, recent emergencies. |

### Webhook acceptance

Every `urgent_slot_alert` carries a `(ref XXXXXXXX)` token (first 8 hex of the OutreachPing id). The `/whatsapp/webhook` handler parses the ref from inbound bodies; `Intent.ACCEPT` calls `confirm_outreach_acceptance` (closes wave, cancels siblings, 90-day cooldown, promotes donor to ACTIVE membership, fires caregiver `transfusion_confirmed_caregiver` template), `Intent.DECLINE` calls `record_outreach_decline` (30-day per-patient cooldown). Refs route AROUND the existing G1 PENDING-recruit flow — outreach replies stay on the outreach close handlers.

### Cooldowns

| Reason | Window | Scope |
|---|---|---|
| `RECENT_DONATION` | 90 days | Global (every patient) — clinical |
| `DECLINED` | 30 days | Per-(donor, patient) |
| `NO_REPLY` | 7 days | Global |
| `OPT_OUT_TEMPORARY` | coordinator-set | Global |

Emergency tier waives social cooldowns. **It never waives the 90-day clinical deferral.**

---

## Phase E — AWS integrations

See [ARCHITECTURE.md](ARCHITECTURE.md#phase-e--aws-real-integrations-e1e4)
for the Mermaid diagram + service inventory; this section is the endpoint
reference.

### E2 — SES email channel

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/emails` | Paginated list (filters: `recipient`, `status`, `template_key`) |
| `GET` | `/emails/{id}` | Single email row |
| `GET` | `/emails/distribution?window=30d` | Counts grouped by template + status |
| `POST` | `/emails/test` | Operator sends a test email to a verified SES identity |

Templates: `caregiver_daily_digest`, `caregiver_emergency_alert`,
`coordinator_failure_alert`, plus `__email_fallback` variants that mirror
WhatsApp body text when Twilio is in mock mode.

Scheduler job `auto_caregiver_email_digest` runs daily at 08:00 IST
(`30 2 * * *` UTC).

### E3 — SQS dispatch queue

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/system/dispatch-queue/status` | Depths + DispatchWorker stats |
| `GET` | `/system/dispatch-queue/messages?limit=10` | Peek at primary queue (debug) |
| `GET` | `/system/dispatch-queue/dlq?limit=10` | Peek at DLQ |
| `POST` | `/system/dispatch-queue/replay-dlq` | Re-enqueue everything in the DLQ |
| `DELETE` | `/system/dispatch-queue/messages/{id}` | Drop a poison message (checks primary + DLQ) |

Env var `BRIDGE_OS_DISPATCH_INLINE=1` reverts to the legacy synchronous
Twilio path (used by re-ingest scripts and a handful of tests).

### E4 — SNS event bus

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/system/events/topics` | Topic catalogue + in-process subscribers |
| `GET` | `/system/events/recent?limit=50&topic=donor-reply-accept` | Recent published events |
| `GET` | `/system/events/status` | EventDispatcher worker stats |
| `POST` | `/system/events/republish/{id}` | Replay a single event by MessageId |

Seven topics: `donor-reply-accept`, `donor-reply-decline`,
`donor-reply-out-of-town`, `donor-reply-medical-defer`,
`donor-reply-opt-out`, `wave-expired`, `wave-accepted`. Full subscriber
mapping in [EVENTS.md](EVENTS.md).

### Shared

All E-phase endpoints respect the `BRIDGE_OS_DISABLE_AWS=1` env var (forces
mock mode) and the `BRIDGE_OS_AWS_PREFIX` env var (overrides the
`team019-bridge-os-` resource prefix). The unified `/system/health/full`
endpoint reports `ses`, `sqs`, and `sns` stanzas alongside the existing
`bedrock` + `twilio` stanzas.
