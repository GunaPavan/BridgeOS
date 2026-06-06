# Bridge OS — Autonomous Mode Demo Script

A ~5 minute walkthrough that proves the system is **actually automated** — not "we have features and someone clicks them," but a runtime that ticks the allocator, sends follow-ups, classifies replies, and applies cooldowns without anyone touching a button.

The arc maps directly onto the problem statement's "Automate outreach, follow-ups, and escalations" pillar.

---

## Set-up (60 seconds, before pitching)

- **Backend** running at `http://localhost:8000` (`uvicorn app.main:app`) — scheduler auto-starts with FastAPI lifespan
- **Frontend** running at `http://localhost:3000` (`npm run dev`)
- **Browser tabs**:
  1. `/dashboard` (overview)
  2. `/system/scheduler` (the automation engine itself)
  3. `/outreach/[some-wave-id]` (a real wave with pings — to show the follow-up timeline)
  4. `/analytics` (for the Reply Intelligence panel at the close)
- **Optional**: `BEDROCK_REGION=us-east-1` + AWS creds — gives you a live Bedrock classify in Beat 4. If unset, the keyword fallback runs and the demo still works.
- **Optional**: `TWILIO_ACCOUNT_SID` + `TWILIO_AUTH_TOKEN` + `TWILIO_WHATSAPP_FROM` — produces real WhatsApp buzzes on judge phones. If unset, mock SIDs are used; the audit trail is still real.

### Pre-load

Visit `/system/scheduler`. Confirm:
- **Status** = running, 5 jobs enabled, 0 failures (24h)
- All five jobs visible: `auto_run_cycle`, `auto_expire_and_escalate`, `auto_pending_nudge`, `auto_pre_donation_reminder`, `auto_post_donation_thank_you`

---

## The script

### Beat 1 — The autonomous claim (45s) → `/system/scheduler`

> "Before I show you the system at work, I want to prove it's actually autonomous — not that we have a button labelled 'Run cycle' that a coordinator has to click. **This page IS the runtime.** Five background jobs tick on cron schedules — the allocator every 5 minutes, the expiry sweep every minute, donor follow-ups on their own cadences. Nothing here was triggered by me. The page is just showing you the audit log."

Point at the **Recent runs** table. Every row is a real, untouched execution.

> "But cron in production is invisible to a judge. So we have a 'demo mode' that compresses every cadence — the allocator goes from every 5 minutes to every 30 seconds — so you can watch the loop tick in real time."

**Click `Enter demo mode`.** A red banner slides in at the top.

> "Watch the right edge of your screen — that's the live tick widget. It's counting down to the next allocator run."

Switch to `/dashboard`. Point at the **SchedulerTick** chip — countdown going.

---

### Beat 2 — The autonomous loop in 60 seconds (90s) → `/dashboard` + `/outreach`

Wait ~30 seconds. The tick hits zero.

> "There — the allocator just ran. Let me show you what happened."

Go to `/outreach`. The waves list has 1-3 new rows with `triggered_by=auto_cycle`.

> "Each row is a wave. Each wave has pings — one per donor we asked. Click into one."

Open a wave detail. Each ping row has the **follow-up timeline** under it:

```
Sent · Nudged · Reminded · Thanked
```

> "These four stages are the lifecycle of every WhatsApp ping. **Sent** is automatic — happened the moment the allocator picked the donor. **Nudged** fires if they don't reply within 4 hours. **Reminded** fires the day before their slot. **Thanked** fires the day after the donation. All driven by the same scheduler — no operator anywhere."

Click **`Nudge now`** on a pending ping (demo override that ignores the 4h gate).

> "Manual override for demo speed — would have fired automatically at the 4h mark. Watch the timeline update."

Timeline now shows: `Sent · Nudged ×1`.

---

### Beat 3 — Tier escalation (45s) → `/system/scheduler/runs`

Go back to `/system/scheduler` and scroll to recent runs. Point at `auto_expire_and_escalate`.

> "Every minute, this job sweeps waves whose deadlines passed without acceptance. When it finds one, it doesn't drop into a manual queue — it auto-creates the next-tier wave. Tier 1 → Tier 2 → Tier 3. The full pool gradually opens up. Soft messaging gradually escalates. **Nobody touches anything.**"

If a recent expire-and-escalate run has `escalations: [{...}]` in its payload, expand it.

---

### Beat 4 — Smart reply classification (90s) → `/whatsapp/webhook` simulation + `/analytics`

This is the closing differentiator — the "interpret donor responses to guide next steps" bullet.

In a terminal:
```bash
DONOR_ID=$(curl -s http://localhost:8000/donors?limit=1 | jq -r '.items[0].id')
PHONE=$(curl -s http://localhost:8000/donors/$DONOR_ID | jq -r '.phone')
curl -s -X POST http://localhost:8000/whatsapp/webhook \
  --data-urlencode "From=whatsapp:$PHONE" \
  --data-urlencode "Body=I am out of town this week, sorry"
```

The TwiML response prints:
```xml
<Response><Message>Thanks for letting us know — we won't reach out for the next week. Safe travels!</Message></Response>
```

> "I just simulated a donor replying 'I am out of town this week.' Not YES, not NO — a free-text message. **Watch what the system did**: classified the intent as `out_of_town` with 80% confidence, applied a 7-day cross-patient cooldown, and sent a polite acknowledgement. All in one request."

Switch to `/analytics` and scroll to **Reply Intelligence**.

> "The classifier writes every inbound to an audit log. Here's the intent distribution over the last 30 days, the confidence histogram, the top reschedule reasons. **This is the feedback loop** — operators can correct wrong classifications, which becomes our training set for fine-tuning later."

---

### Beat 5 — Wrap (30s) → back to `/system/scheduler`

Click `Exit demo mode`. Red banner disappears. Cadences restore.

> "Three things you saw without me ever clicking 'send':
> - 1: **Outreach automated** — the allocator picks donors and dispatches.
> - 2: **Follow-ups automated** — pre-donation reminders, post-donation thank-yous, pending-ping nudges.
> - 3: **Replies interpreted** — free-text inbound becomes a structured side-effect.
>
> Every one of those maps directly to the problem statement's `Automate outreach, follow-ups, and escalations` pillar. The system runs Blood Warriors' operational loop with **minimal manual effort** — exactly what they asked for."

---

## Fallback paths if something breaks

| Symptom | Recovery |
|---|---|
| Scheduler status shows "stopped" | `BRIDGE_OS_DISABLE_SCHEDULER` is set — unset and restart uvicorn |
| Allocator runs but `items_processed=0` | No critical slots in the cohort. Re-ingest with `--target $(date +%Y-%m-%d)` to refresh the urgency distribution |
| Bedrock 403 | Switch to keyword fallback by unsetting `BEDROCK_REGION`; the classifier still picks up out_of_town / medical_defer / reschedule from regex |
| Twilio "MOCK" SIDs in WhatsApp panel | That's expected when `TWILIO_ACCOUNT_SID` isn't set — point out the audit row is still real |

---

## Demo mode cadence reference

| Job | Default | Demo |
|---|---|---|
| `auto_run_cycle` | `*/5 * * * *` (5 min) | `*/30 * * * * *` (30 s) |
| `auto_expire_and_escalate` | `* * * * *` (1 min) | `*/15 * * * * *` (15 s) |
| `auto_pending_nudge` | `*/30 * * * *` (30 min) | `*/45 * * * * *` (45 s) |
| `auto_pre_donation_reminder` | `0 9 * * *` (daily 09:00) | `0 * * * * *` (every minute, sec 0) |
| `auto_post_donation_thank_you` | `0 */6 * * *` (every 6 h) | `*/45 * * * * *` (45 s) |

A `cron_override` per job (via `PATCH /system/scheduler/jobs/{name}`) outranks both the default and the demo cron — useful if you want to keep one specific job slow during the demo while everything else races.
