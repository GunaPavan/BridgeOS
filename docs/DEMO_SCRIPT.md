# Bridge OS — Demo Script

A 4-minute walkthrough designed around one patient (**Aarav Reddy, 8, B+ Kell-negative**) and one destabilising donor (**Priya Sharma**, response rate 32%, last donation 120 days ago).

The narrative is locked in synthetic data: searching "Priya Sharma" always returns the same donor, who is always on Aarav's bridge, who is always the at-risk donor in the analytics + recommendations + simulator pages.

---

## The set-up (10 seconds, before pitching)

- **Backend running** at `http://localhost:8000` (`uvicorn app.main:app`)
- **Frontend running** at `http://localhost:3000` (`npm run dev`)
- **Browser windows**: one tab on `/`, one on `/whatsapp` (so the inbound webhook moment is instant)
- Optional: `ANTHROPIC_API_KEY` set so the Care Agent demo uses real Claude

---

## The script

### Beat 1 — Hook (30s) → `/`

> "Every blood donor app in India is built for the same moment — a stranger needs blood, find another stranger fast. Thalassemia is the *opposite*. A child needs a transfusion **every 18 days, for life**. Blood Warriors solved the operational problem — they assemble cohorts of 8–10 donors per patient who recur-donate for years. We built Bridge OS to scale that model from 58 patients in Hyderabad to thousands nationally."

- Show the gradient hero on `/`
- Point at the impact strip: **~100K patients · every 18d · 8–10 donors · 1 patient · for years**
- Click **Open the dashboard**

### Beat 2 — The cohort, the destabiliser (45s) → `/bridges` → Aarav's bridge

> "Every Blood Bridge is a first-class object. Health score, 12-month timeline, every donor visible."

- On `/bridges`, find **Bridge for Aarav** (the first card with **B+** group)
- Click in
- Show the **8 donors in the cohort**
- Scroll to the **Stability panel** (Differentiator #1)

> "We trained XGBoost on synthetic donor behaviour to predict 30/60/90-day churn. Every prediction comes with SHAP factors — no black box. Priya Sharma is at the top because her response rate is 32% and she hasn't donated in 120 days. The model surfaces *why*, not just *what*."

- Highlight Priya at the top of the stability ranking
- Point at her SHAP factors

### Beat 3 — The rotation, the constraint solver (30s) → Schedule tab on the bridge

> "The next 12 months of transfusions are solved by Google's OR-Tools CP-SAT solver — hard constraints on the 90-day deferral rule and 18-day cadence, soft minimisation on distance and response rate. About 50 milliseconds."

- Show the **Schedule timeline** (Differentiator #2)
- Mention OPTIMAL / OR-Tools provenance
- Point at any one donor's slot count

### Beat 4 — The "wow" moment (60s) → `/simulator`

> "Now the moment everyone asks about — *what happens if Priya drops?* Watch."

- Navigate to `/simulator` (Aarav is pre-selected)
- Show baseline avg churn (~35%), 1 at-risk donor
- **Click Priya's tile** to eject her
- Wait 1 second for the panels to re-compute

> "Avg churn dropped from 35% to 28%. The 'at risk' counter went to zero. The scheduler flipped to INFEASIBLE — the rotation breaks without her — but the recommender instantly surfaced the top 3 candidates ranked by composite score: distance + response rate + predicted churn + Kell-match bonus."

- Point at the **Suggested Replacements** column
- Mention this is a **stateless what-if** — no database writes, fully replayable (Differentiator #3)

### Beat 5 — Real WhatsApp + multilingual agent (60s) → `/whatsapp` then `/agent`

> "When the coordinator confirms a swap, they reach the donor on WhatsApp — the channel donors already use."

- On `/whatsapp`, click **New** → search **Priya Sharma** → pick her
- Pick template **slot_reminder** → click **Send**
- The bubble lands instantly with patient name + bridge auto-filled (Differentiator #4)
- If `TWILIO_*` set: mention "this just sent a real WhatsApp via Twilio"

> "And when the coordinator wants to think out loud, we have a multilingual agent."

- Navigate to `/agent`
- Click the **Donor** context chip → search **Priya Sharma** → pick her
- Switch language to **Hindi (हिन्दी)** in the picker
- Ask: **"Why is this donor at risk?"**
- Show the answer cites her 32% response rate, 2 donations, last 120 days ago

> "Eight Indian languages. The agent assembles fresh per-entity context every turn — profile, recent WhatsApps, bridge memberships — and answers grounded in the live database. Anthropic Claude when configured, deterministic fallback when not, so the demo never breaks."

### Beat 6 — Trust + scale (30s) → `/analytics` → `/integrations` → `/settings`

> "Last 30 seconds — let me show you it's not slideware."

- Open `/analytics` — show the ML cohort health distribution next to the stub for trust calibration
- Open `/integrations` — show eRaktKosh and ICMR RDRI sample data
- Open `/settings` — show **170 backend tests · 99 frontend tests · 59 live E2E** under "About this build"

> "Every model runs against live synthetic data. Every integration has a real API surface that swaps from mock to live by setting an env var. Zero login required, every page clickable."

### Beat 7 — Closing (15s)

> "Built by AlgoWarriors — Gunaputra Nagendra Pavan Yedida and Aakash Jangeeti — for the AI for Good Hackathon 2026. The product augments what Blood Warriors already runs brilliantly. The patient at the top of our demo is named Aarav. The destabilising donor is named Priya. We optimise for *their* calendar — not the dashboard's."

---

## Backup demo paths (if anything breaks live)

- **Backend down?** Mock mode handles every Care Agent and WhatsApp path. The simulator + stability + scheduler still require backend; if backend is down, jump straight to `/about` and walk the architecture diagram on `/how-it-works`.
- **Frontend errored?** The 19 fullPage screenshots in `frontend/playwright-report/` cover every page as the E2E suite captures them on every run.

## Screenshot manifest (auto-captured by E2E)

Each was captured by the live Playwright suite during this build:

| File | Page |
|---|---|
| `landing-page.png` | `/` |
| `how-it-works.png` | `/how-it-works` |
| `about-page.png` | `/about` |
| `bridges-list.png` | `/bridges` |
| `aarav-bridge-detail.png` | `/bridges/{aarav-id}` |
| `aarav-stability.png` | Stability panel on Aarav's bridge |
| `aarav-schedule.png` | Schedule timeline on Aarav's bridge |
| `donors-list.png` | `/donors` |
| `priya-donor-detail.png` | `/donors/{priya-id}` |
| `patients-list.png` | `/patients` |
| `aarav-patient-profile.png` | `/patients/{aarav-id}` |
| `recommendations-inbox.png` | `/recommendations` |
| `simulator-baseline.png` | `/simulator` before ejection |
| `simulator-after-eject.png` | `/simulator` after ejecting Priya |
| `analytics-dashboard.png` | `/analytics` |
| `integrations-page.png` | `/integrations` |
| `whatsapp-page.png` | `/whatsapp` |
| `agent-page.png` | `/agent` |
| `settings-page.png` | `/settings` |

## Five quick questions judges might ask + canned answers

**Q: Did you train on real patient data?**
A: No — synthetic data with a known generative process. We can quote AUC honestly (0.62 / 0.68 / 0.70 across 30/60/90-day horizons) because Priya's high-risk signals are real signals; the labels are derivable.

**Q: Is the LLM agent grounded?**
A: Yes — every turn assembles a fresh context block (profile + recent WhatsApps + bridge memberships) and passes it as ground truth. The system prompt instructs Claude to never invent names or numbers. Mock mode uses rule-based intent detection on the *question only* — context never hijacks intent.

**Q: How does the scheduler handle infeasibility?**
A: INFEASIBLE is itself a signal. The simulator demonstrates this — eject Priya, the rotation breaks, and the same UI surfaces the top 3 candidates to make it feasible again.

**Q: Privacy?**
A: No login on the demo (synthetic data only). For production, donor phone numbers and patient IDs would sit behind JWT + OTP (we have prior production experience with that pattern from another project). The agent's cohort memory stays in Postgres + pgvector — never sent to LLMs without explicit per-turn assembly.

**Q: What's the deployment story?**
A: FastAPI + Postgres backend deploys to any container host (App Runner, Render, Fly, Railway). Frontend deploys to Vercel. Both layers are stateless apart from Postgres; everything is hot-pluggable via env vars (AWS Bedrock vs Anthropic direct, Twilio creds, eRaktKosh URLs).


---

## Alert Allocator demo (Phase 15)

3-minute walkthrough you can paste into the demo script:

1. **Open `/recommendations`** — show critical bridges flagged by the churn model. Point out: "These are bridges the ML thinks will collapse."
2. **Open `/manual-calls`** in a second tab — empty Kanban. Say: "This is where the phone team works. Empty for now."
3. **Back to /recommendations** → hit "Run allocator cycle" (POST /outreach/run-cycle). Show the JSON response: 22 critical bridges, ~25 pings planned, 0 shortfall.
4. **Open one wave** in `/outreach/waves/{id}` — show the slot_ref token in each ping body.
5. **Dispatch the wave** (`POST /outreach/waves/{id}/dispatch`). 8 Twilio messages fly out. Or, in mock mode, the message rows appear in `/whatsapp`.
6. **Simulate a YES reply** via the webhook (`POST /whatsapp/webhook` with body `YES (ref abc12345)`). Watch the wave flip to ACCEPTED; sibling pings silently cancel; the donor is promoted to ACTIVE in their bridge membership.
7. **Now expire the rest** (`POST /outreach/expire-and-sweep?auto_escalate=true`) — every PENDING-and-unaccepted wave gets the next-tier wave auto-spawned. Refresh `/manual-calls` — donors from the expired Tier 2 waves appear in the Kanban.
8. **The big finale**: open any patient detail page → hit the red **EMERGENCY OUTREACH** button. Fill coordinator name + 2-hour deadline + reason. Hit confirm. Result: "23 reachable donors of 6,949 active in pool" — geo-filtered by 25 km/h reach window. Wave spawned at EMERGENCY tier. `eRaktKosh_banks` + `icmr_rare_donors` returned in the response — show that the phone team can work hospital-bank acquisition in parallel.
9. **Close with `/analytics`** — the Alert Allocator panel shows pings-per-acceptance, avg time-to-accept by urgency, donor-fatigue distribution.

The story line: "Our ML doesn't just predict — it changes who gets called, in what order, on what channel, with what cadence."
