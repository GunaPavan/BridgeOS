# Bridge OS

**The operating system for Blood Bridges.**

AI-driven coordination infrastructure to scale Blood Warriors' Blood Bridge model for recurring thalassemia transfusion care across India.

Built by **AlgoWarriors** — Gunaputra Nagendra Pavan Yedida and Aakash Jangeeti — for the **AI for Good Hackathon 2026** (Blend360, with Blood Warriors Foundation and HackCulture as impact partners).

---

## 🧪 Running this yourself

> **Heads up:** The live deployment (`bridge-os.click` + `api.bridge-os.click`) ran on AWS credits provided by Blend360 for the AI for Good 2.0 hackathon. Those credentials have been revoked now that judging is closed, so the public URLs are no longer reachable. The complete codebase, real Blood Warriors dataset, trained ML models, and infrastructure manifests are all in this repo — you can clone it and run the system locally without an AWS account, or drop in your own AWS account to redeploy.

**Local quick-start (no AWS, no Cognito, no Twilio account needed):**

```bash
git clone https://github.com/GunaPavan/BridgeOS.git
cd BridgeOS

# --- Backend (FastAPI + SQLite, ML models load from backend/models/) ---
cd backend
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e .
python -m scripts.seed               # ingests Dataset.csv into local SQLite
python -m uvicorn app.main:app --port 8000

# --- Frontend (Next.js) — in a second terminal ---
cd frontend
npm install
npm run dev                          # http://localhost:3000
```

Visit `http://localhost:3000/dashboard` — the local shell opens directly with no sign-in (production used Cognito; self-host skips that for easy browsing). Every page works against the seeded SQLite DB; Bedrock LLM calls cleanly fall back to a keyword classifier when AWS credentials aren't configured, so the Care Agent + outreach engine still demo end-to-end.

**Want the full deployed experience?** Drop your own AWS account ID into `infra/task-definition.json` (it's parameterised with `${AWS_ACCOUNT_ID}`), populate the Secrets Manager entries referenced by `valueFrom`, and the GitHub Actions OIDC pipeline (`.github/workflows/deploy-backend.yml`) will build the Docker image and roll the ECS service on every push to `main`. The CloudWatch dashboard JSON and 2 Lambda subscribers under `infra/lambda/` import cleanly into any account.

---

## The problem

Every blood donor app in India is built for *one moment* — a stranger needs blood, find another stranger fast.

Thalassemia is the opposite: a child needs compatible blood **every 18 days for life**. That is not a search problem. It is a recurring care infrastructure problem.

Blood Warriors invented the operational solution — **Blood Bridge**: a fixed cohort of 8–10 voluntary donors permanently assigned to each patient, rotating every 18 days. Bridge OS is the AI + automation layer that makes this model scale from a few dozen patients in Hyderabad to thousands nationally.

---

## What's deployed

| Surface | Detail |
|---|---|
| **84 patients** in RDS Postgres (real Blood Warriors data) |
| **6,862 donors** with response-rate, donation history, geography |
| **79 active Blood Bridges** with ML-scored cohort health |
| **625 bridge memberships** rotating across the cohort |
| **Four channels live**: Voice (Twilio), WhatsApp (Twilio), SMS (AWS SNS), Email (AWS SES) |
| **Bedrock LLM** composes every outreach + every inbound reply, in 8 Indian languages |
| **EventBridge Scheduler** runs 7 background jobs (allocator, escalation, follow-ups) without a human |
| **One-click demo** on `/system/scheduler` fires all four channels in parallel against the demo target |

---

## 🚀 Five differentiators

| # | System | Stack | Lives at |
|---|---|---|---|
| 1 | **Cohort Stability Predictor** | XGBoost (3 horizons: 30/60/90-day churn) + SHAP TreeExplainer | `/bridges/{id}` Stability panel |
| 2 | **Rotation Scheduler** | Google OR-Tools CP-SAT — assigns every transfusion in 12 months to one donor under deferral + cadence + load balancing in ~50 ms | `/bridges/{id}` Schedule tab |
| 3 | **Live Cohort Simulator** | Stateless re-execution of stability + scheduler + recommender on a what-if cohort | `/simulator` (drag-drop graph) |
| 4 | **Multilingual AI Care Agent** | AWS Bedrock (Claude Sonnet 4.5 + Haiku 4.5 + Titan v2) · 8 Indian languages · pgvector cohort memory · hardened against prompt injection | `/agent` |
| 5 | **Alert Allocator** | Per-cycle CP-SAT-style assignment over urgency-tiered waves · multi-channel outbound · auto-escalation to coordinator phone · emergency geo-broadcast | `/recommendations`, `/analytics`, `EMERGENCY` button on `/patients/{id}` |

Each system is hot-pluggable — flip an env var to switch between mock and live; no code change.

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         Coordinators                              │
│        Next.js dashboard (Amplify) — Cognito JWT auth             │
└──────────────────────────────┬───────────────────────────────────┘
                               │ HTTPS
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  FastAPI backend on AWS Fargate (api.bridge-os.click via ALB)     │
│  ┌──────────────┬──────────────────────┬───────────────────────┐ │
│  │  REST API    │  EventBridge cron    │  In-process SES       │ │
│  │  (50+ ep)    │  jobs (every 5-15m)  │  inbound poller       │ │
│  └──────────────┴──────────────────────┴───────────────────────┘ │
└──────┬───────────────┬───────────────┬───────────────┬───────────┘
       │               │               │               │
       ▼               ▼               ▼               ▼
┌──────────┐  ┌──────────────┐  ┌──────────┐  ┌──────────────┐
│ RDS PG16 │  │ Bedrock      │  │ SNS+SQS  │  │ Twilio       │
│ + pgvec  │  │ Sonnet+Haiku │  │ +SES+S3  │  │ Voice + WA   │
└──────────┘  │ + Titan v2   │  └──────────┘  └──────────────┘
              └──────────────┘
                ▲     │
        Bedrock │     │ EventBridge → 2 Lambda subscribers
   classifies   │     ▼  + CloudWatch dashboards + Secrets Manager
   intent       └─────────────────────────────────────────────────
```

---

## ☁️ AWS services used (16)

| Service | What it does | Why this one |
|---|---|---|
| **Amazon Bedrock** | Hosts Claude Sonnet 4.5 (outreach + Care Agent), Haiku 4.5 (intent classifier), Titan v2 (1024-dim embeddings). | Native AWS, no separate API key, no data egress, billed in one account. |
| **AWS Polly** (via Twilio Say) | TTS for the voice call (`Polly.Kajal-Neural`, Indian English). | Best en-IN Neural voice that reads "B positive" and "Tuesday ninth" correctly. |
| **Amazon SES** | Sends outreach emails (verified `bridge-os.click` domain) AND receives donor replies (raw `.eml` dropped to S3 by a receipt rule). | IAM-only auth, native S3 inbound, free up to 1k inbound/month. |
| **Amazon SNS** | Topic fan-out for `caregiver-reply-*` and `donor-status-*` events, AND outbound direct-SMS to donors via `BLDWAR` sender ID. | One bus, many subscribers (Lambda, in-process, SQS); free SMS path for India. |
| **Amazon SQS** | Dispatch queue for outbound messages + DLQ for poison messages. | At-least-once delivery + retry safety: a failed Twilio send is replayed, never lost. |
| **Amazon Cognito** | User pool, JWT auth, hosted UI, RBAC groups (`admins`, `donors`, `patients`), PostConfirmation Lambda trigger. | Free tier, plugs into FastAPI as a JWT validator, supports per-role portals. |
| **Amazon RDS** (Postgres 16 + pgvector) | Primary DB + 1024-dim vector store for the Care Agent's cohort memory. | One DB for relational + vector — no separate Pinecone / Weaviate to provision. |
| **Amazon S3** | Stores raw inbound `.eml` files dropped by the SES receipt rule. | Durable cheap storage; SES integrates natively. |
| **Amazon EventBridge Scheduler** | Managed cron firing the allocator cycle, expiry sweep, call escalation, SES inbound poller, etc. | Replaced APScheduler so we don't need an always-on worker for cron. |
| **AWS Secrets Manager** | Holds Twilio credentials, DB URL, SES from-address. ECS pulls at boot. | Secrets stay out of git + task def env; rotation possible without redeploy. |
| **Amazon ECS Fargate** | Runs the FastAPI container; an ALB fronts it at `api.bridge-os.click`. | Serverless containers, no node management, only pay for vCPU-seconds used. |
| **Amazon ECR** | Private Docker registry for `team019-bridge-os-backend`. | Required by Fargate; OIDC-authed push from GitHub Actions — no IAM key. |
| **AWS Amplify Hosting** | Builds + serves the Next.js frontend at `main.d3fwu2lhbcn0pw.amplifyapp.com`. | Zero-config Next.js builds, branch-tied previews, free SSL + edge caching. |
| **Amazon CloudWatch** | Dashboard + alarms on SQS depth, SES bounce rate, RDS CPU. | Free metrics + alarms in Free Tier; same console as everything else. |
| **AWS Lambda** | 2 subscribers on the `caregiver-reply-*` topics handling side effects. | Serverless side effects — no extra container, scales to zero. |
| **Amazon Route 53** | DNS + MX records for `bridge-os.click` (MX points at SES inbound). | Required so SES can receive mail at our domain. |

---

## 🤖 ML models / classical algorithms (7)

| Model | Predicts / decides | Why this one |
|---|---|---|
| **XGBoost — Cohort Stability Predictor** | Probability a Blood Bridge collapses in 30 / 60 / 90 days. | Best on small tabular medical data; SHAP TreeExplainer gives clinician trust. |
| **Multi-class Churn Classifier** (bake-off winner of 6: XGB, RF, LR, GBM, CatBoost, LGBM) | Donor will churn vs. stay vs. lapse. | Bakeoff picks the model objectively per metric (AUC + calibration). |
| **Survival (time-to-event) model** (bake-off winner of 5: Cox PH, RSF, Weibull AFT, DeepSurv, GBSA) | Days until a donor likely stops responding. | Survival > classification when "when" matters; risk score informs urgency. |
| **SHAP TreeExplainer** | Per-feature explanations on the stability + churn outputs. | Shows judges WHY the model said "at risk" instead of a black box. |
| **OR-Tools CP-SAT — Rotation Scheduler** | Assigns donors to slots respecting cooldowns, blood-type compat, geo. | Hard constraints that ML can't enforce — CP-SAT is the SOTA free solver. |
| **Bedrock Claude Sonnet 4.5** | Composes the 4-channel outreach copy + powers the Care Agent. | Strongest reasoning + multilingual (8 Indian languages) in one call. |
| **Bedrock Claude Haiku 4.5** | Classifies inbound replies (YES / NO / MAYBE / question / abuse / opt-out). | 12× cheaper + 5× faster than Sonnet; identical accuracy on short labelled intents. |
| **Bedrock Titan Embed v2** | 1024-dim embeddings for pgvector cohort memory. | Native AWS embedding model, no API key, cheap, good semantic match. |

---

## 🛠️ Tech stack

| Layer | Pick | Why |
|---|---|---|
| Backend framework | **FastAPI** + Pydantic v2 | Async, auto OpenAPI docs, strict schemas — judges can browse `/docs`. |
| DB | **SQLAlchemy 2.0** + Alembic + psycopg3 | Mature ORM, real migrations, async-ready driver. |
| Vector search | **pgvector** inside RDS | No second DB; cosine similarity in SQL alongside relational rows. |
| ML libs | xgboost · scikit-learn · shap · ortools | Tabular ML + explainability + constraint solver in 4 libs. |
| Cron | APScheduler locally → **EventBridge Scheduler** in prod | Same job code, no infrastructure when scaling out. |
| Frontend | **Next.js 14 App Router** + React 18 + TypeScript | Modern, SSR + client mix, server actions ready. |
| Data fetching | **TanStack Query** | Caching, polling, optimistic updates — judges see the live engine ticking. |
| UI | Tailwind + Framer Motion + lucide-react | Fast styling, smooth animations, consistent icons. |
| Graph UI | **reactflow** | Cohort simulator's drag-drop graph (Differentiator #3). |
| Auth | **amazon-cognito-identity-js** | Direct Cognito flows (signup + Hosted UI). |
| Telephony | **Twilio SDK** | Voice + WhatsApp + webhook signatures from one vendor. |
| Containerisation | Docker + buildx | Single image goes through ECR → ECS Fargate. |
| CI/CD | GitHub Actions OIDC → ECR/ECS · Amplify CI → frontend | No long-lived AWS keys; auto-deploys on `push main`. |
| Tests | pytest + factory-boy (backend) · Playwright + Vitest (frontend) | Unit + integration + E2E coverage on both halves. |

---

## 📁 Repository layout

```
bridge-os/
├── README.md                          # this file
├── .github/workflows/                 # GitHub Actions OIDC → ECR/ECS
├── amplify.yml                        # Amplify build config (frontend)
│
├── backend/                           # FastAPI + SQLAlchemy + ML services
│   ├── Dockerfile                     # multi-stage build → ECS Fargate
│   ├── app/
│   │   ├── api/                       # 15 routers — donors, patients, bridges,
│   │   │                              # whatsapp, agent, admin_demo, admin_system,
│   │   │                              # analytics, scheduler, emails, …
│   │   ├── models/                    # SQLAlchemy entities
│   │   ├── schemas/                   # Pydantic schemas
│   │   ├── ml/                        # XGBoost stability + churn + survival + OR-Tools
│   │   ├── agent/                     # Bedrock chat client + cohort memory + language detect
│   │   ├── services/                  # demo_outreach, reply_classifier, caregiver_auto_reply, …
│   │   ├── integrations/              # twilio_client, sns_sms_client, ses_client, aws, …
│   │   ├── outreach/                  # CP-SAT allocator, dispatch queue, inbound email poller
│   │   ├── events/                    # SNS publishers + subscribers (in-process + Lambda)
│   │   └── scheduler/                 # EventBridge-compatible cron jobs
│   ├── scripts/                       # seed.py, ingest_real_dataset.py, train_*
│   ├── data/Dataset.csv               # Blood Warriors real data (7034 rows)
│   ├── models/                        # Pre-trained joblibs (churn + survival)
│   └── tests/                         # pytest + factory-boy
│
└── frontend/                          # Next.js 14 App Router
    ├── app/
    │   ├── (app)/                     # 🔒 Auth-gated dashboard routes
    │   │   ├── layout.tsx             # session check → redirect to /login?next=…
    │   │   ├── dashboard, bridges, donors, patients, analytics,
    │   │   ├── simulator, agent, whatsapp, recommendations,
    │   │   ├── system/scheduler       # ← Automation engine + demo button
    │   │   ├── settings, integrations, donor, patient
    │   │   └── outreach, emails, [id] detail routes
    │   ├── login, signup              # Cognito direct
    │   ├── how-it-works, about
    │   └── page.tsx                   # Landing (with reviewer credentials card)
    ├── components/
    │   ├── ui/                        # 80+ presentational components
    │   └── marketing/                 # Hero, footer, nav
    └── lib/
        ├── api.ts                     # Typed FastAPI client (~2k lines)
        ├── cognito.ts                 # Sign-in / sign-up / token helpers
        └── utils.ts
```

---

## 🛟 Local development

```bash
# ----- Backend (FastAPI, SQLite by default) -----
cd backend
python -m venv .venv
.venv\Scripts\activate                  # Windows
# source .venv/bin/activate              # macOS / Linux
pip install -e ".[dev]"
python -m scripts.seed --source data/Dataset.csv  # populate from Blood Warriors data
pytest                                  # ~400 tests should pass
uvicorn app.main:app --reload           # http://localhost:8000

# ----- Frontend (Next.js 14) -----
cd ../frontend
npm install
cp .env.local.example .env.local        # then edit NEXT_PUBLIC_* values
npm run dev                             # http://localhost:3000
npx playwright test --workers=1         # 59 E2E (needs backend running)
```

Open <http://localhost:3000>, sign in with the reviewer credentials at the top, and you're in.

---

## 🌍 Going live (optional)

Every external system is hot-pluggable via env vars. Without any of these set, everything runs in mock mode for the demo.

```bash
# Care Agent — AWS Bedrock multi-model (preferred for production)
# Routes chat -> Sonnet, intent -> Haiku, embeddings -> Titan v2.
export BEDROCK_REGION=us-east-1

# Anthropic direct fallback (used if BEDROCK_REGION is unset)
export ANTHROPIC_API_KEY=sk-ant-...

# WhatsApp + Voice via Twilio
export TWILIO_ACCOUNT_SID=AC_...
export TWILIO_AUTH_TOKEN=...
export TWILIO_WHATSAPP_FROM=whatsapp:+14155238886    # default = sandbox
export TWILIO_VOICE_FROM=+1XXXXXXXXXX

# AWS SES (email) + SNS (SMS) + Cognito + Bedrock
# all picked up via the default boto3 chain (~/.aws/credentials).

# Postgres + pgvector instead of local SQLite
docker compose up -d
export DATABASE_URL=postgresql+psycopg://bridge:bridge@localhost:5432/bridge_os
```

---

## 📚 Documentation

- [Architecture](docs/ARCHITECTURE.md) — every phase, every module, every test count
- [Data model](docs/DATA_MODEL.md) — entities, relationships, enums
- [API](docs/API.md) — every endpoint with method + path + purpose
- [Events](docs/EVENTS.md) — SNS topic catalogue + subscriber side effects
- [Demo script](docs/DEMO_SCRIPT.md) — the 4-minute walkthrough + Q&A canned answers

---

## 👥 Credits

- **Team AlgoWarriors** — Gunaputra Nagendra Pavan Yedida, Aakash Jangeeti
- **Hackathon** — AI for Good 2026 · Blend360 · impact partners: Blood Warriors Foundation + HackCulture
- **Inspiration** — [Blood Warriors Foundation](https://bloodwarriors.in) and the Blood Bridge model
