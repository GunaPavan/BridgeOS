# Bridge OS — SNS event bus (Phase E4)

The event bus decouples the inbound WhatsApp webhook from the side effects it
triggers. Instead of doing five things synchronously inside one HTTP request,
the webhook publishes a single SNS event and the in-process `EventDispatcher`
fans it out to subscribers.

This document is the topic catalogue + subscriber map + replay model.

---

## Topology

```
┌─ /whatsapp/webhook ─┐                ┌─ in-process subscribers ──────────┐
│                     │                │                                   │
│   classify_reply ──┼─► SNS topic ──► │  caregiver_notify                 │
│                     │   (e.g. donor- │  cooldown_handler                 │
│                     │    reply-out-  │  ema_feedback                     │
│                     │    of-town)    │  sibling_cancel                   │
└─────────────────────┘                │  allocator_refire                 │
                                       └───────────────────────────────────┘
```

Each subscriber gets its own DB session, its own exception isolation, and runs
in the `EventDispatcher` daemon thread (1 Hz tick). When we deploy and add
Lambda subscribers to the same SNS topics, this in-process dispatcher stays
on as a redundant audit path.

---

## Topic catalogue

All seven topics. Topic-name prefix is `team019-bridge-os-` (overridable via
the `BRIDGE_OS_AWS_PREFIX` env var) — the names below are the short keys
referenced in code.

| Topic | Published when | Default in-process subscribers |
|---|---|---|
| `donor-reply-accept` | Webhook receives an explicit YES | `ema_feedback_audit`, `caregiver_notify` |
| `donor-reply-decline` | Webhook receives an explicit NO | `ema_feedback_audit` |
| `donor-reply-out-of-town` | Classifier labels OUT_OF_TOWN with confidence ≥ threshold | `cooldown_out_of_town_audit` |
| `donor-reply-medical-defer` | Classifier labels MEDICAL_DEFER | `cooldown_medical_audit` |
| `donor-reply-opt-out` | Classifier labels STOP | `cooldown_opt_out_audit` |
| `wave-expired` | An outreach wave passes its expiry without acceptance | `allocator_refire_audit` |
| `wave-accepted` | A wave is fully covered (donor accepted, slot booked) | `sibling_cancel_audit` |

The dispatcher reads the in-process publish history (`sns_client.recent_events`)
once a second, dedupes by message id, and invokes each registered subscriber.

---

## Adding a subscriber

Register against the topic enum. Subscribers must be idempotent — SNS does
**not** guarantee exactly-once delivery and the in-process dispatcher is
intentionally simple about dedup (it drops anything it has already seen
within the current process lifetime).

```python
# app/events/subscribers/my_subscriber.py
from app.events.dispatcher import register_subscriber
from app.events.topics import TopicName


@register_subscriber(TopicName.DONOR_REPLY_OUT_OF_TOWN, name="my_audit")
def my_audit(body: dict, session_factory) -> None:
    """Body shape comes from app/events/publishers.py — type-stable."""
    donor_id = body["donor_id"]
    with session_factory() as session:
        # ... your idempotent side effect ...
        session.commit()
```

Then import the module from `app/events/subscribers/__init__.py` so the
decorator fires on app boot.

---

## Publishers

Always go through the typed helpers in `app/events/publishers.py` rather than
calling `sns_client.publish` directly. The helpers carry the canonical body
shape per topic so subscribers can rely on key names being stable.

```python
from app.events import publish_donor_reply_out_of_town

publish_donor_reply_out_of_town(donor_id=donor.id)
```

If `BRIDGE_OS_DISABLE_AWS=1` or boto3 isn't configured, publishes are routed
to the in-memory mock — the dispatcher still receives them, so dev / tests
exercise the same code paths as production.

---

## Operating

| What | Where |
|---|---|
| Live feed of recent events | `GET /system/events/recent?limit=20[&topic=donor-reply-accept]` |
| Topic catalogue + subscribers | `GET /system/events/topics` |
| Dispatcher worker stats | `GET /system/events/status` |
| Replay a single event (audit / re-run side effects) | `POST /system/events/republish/{message_id}` |
| UI | `/system/scheduler` page → "Event bus" section |

Topic ARNs are auto-provisioned on first publish in live mode and tagged
`Project=bridge-os, Team=019, Owner=Gunaputra, Type=events`. Cleanup is
`aws sns list-topics | grep team019-bridge-os- | xargs -n1 aws sns delete-topic`.

---

## Why not just call the side effects inline?

Three reasons that matter for the demo and the production roadmap:

1. **Webhook latency.** Before E4 the Twilio webhook did 5 things
   synchronously and held the HTTP request open the whole time. Now it
   publishes once (~5 ms in mock, ~30 ms in live) and returns the TwiML
   acknowledgement. The donor sees the reply faster and Twilio doesn't
   retry on slow webhooks.
2. **Failure isolation.** If one side effect fails (e.g. the EMA
   calculation throws on a corrupt donor record) the other four still run.
   In the synchronous design, one exception killed all five.
3. **Future-proofing for Lambda fan-out.** After deployment we add Lambda
   subscribers to the same topics so the side effects can run cross-process.
   No code in the publishers or the existing subscribers changes — only
   the wiring in Terraform.

---

## Mock vs live

| Mode | When | Behaviour |
|---|---|---|
| Mock | `BRIDGE_OS_DISABLE_AWS=1` or boto3 not installed | `publish` appends to an in-memory deque per topic; dispatcher reads from the same deque. No network calls. |
| Live | AWS credentials reachable | `publish` calls real `sns:Publish`; also appends to the in-memory deque so the UI feed and the in-process dispatcher continue to work. |

Even in live mode the dispatcher serves as a backup subscriber — the UX
guarantee is "the side effect runs at least once, even if the Lambda
subscription is mis-wired."
