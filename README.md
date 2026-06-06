# Bridge OS

**The operating system for Blood Bridges.**

Software infrastructure to scale Blood Warriors' Blood Bridge model for recurring thalassemia transfusion care across India.

Built by **AlgoWarriors** — Gunaputra Nagendra Pavan Yedida and Aakash Jangeeti — for the **AI for Good Hackathon 2026** (Blend360, with Blood Warriors Foundation and HackCulture as impact partners).

---

## What this is

Every blood donor app in India is built for *one moment* — a stranger needs blood, find another stranger fast. Thalassemia is the opposite: a child needs compatible blood every 18 days for life. That is not a search problem. It is a *recurring care infrastructure* problem.

Blood Warriors invented the operational solution — **Blood Bridge**: a fixed cohort of 8–10 voluntary donors permanently assigned to each patient, rotating every 18 days. Bridge OS is the software layer that makes this model scale from 58 patients in Hyderabad to thousands nationally.

## Five AI systems, one product

| # | System | Stack | Lives at |
|---|--------|-------|----------|
| 1 | **Cohort Stability Predictor** | XGBoost (3 horizons) + SHAP TreeExplainer | `/bridges/{id}` Stability panel |
| 2 | **Rotation Scheduler** | Google OR-Tools CP-SAT | `/bridges/{id}` Schedule tab |
| 3 | **Live Cohort Simulator** | Stateless re-execution of 1 + 2 + recommender | `/simulator` |
| 4 | **Multilingual Care Agent + WhatsApp** | AWS Bedrock (Sonnet + Haiku + Titan v2) · Anthropic Claude fallback · mock + Twilio (or mock) | `/agent`, `/whatsapp` |
| 5 | **Alert Allocator** — global donor outreach engine with five tiers (auto WhatsApp · manual phone queue · final broadcast · external · emergency) | Per-cycle CP-SAT-style assignment, P_accept math, urgency keyed off `gap/cadence`, NULL-safe cooldowns, geo reach-window for emergencies | `/recommendations`, `/manual-calls`, `/analytics`, EMERGENCY button on `/patients/{id}` |

Each one is hot-pluggable — set an env var to flip from mock to live, no code change.

## What's in the box

- **16 multi-page routes**: `/`, `/how-it-works`, `/about`, `/dashboard`, `/bridges`, `/donors`, `/patients`, `/recommendations`, `/manual-calls`, `/simulator`, `/analytics`, `/integrations`, `/whatsapp`, `/agent`, `/settings` (plus `/bridges/[id]`, `/donors/[id]`, `/patients/[id]` detail routes)
- **50+ backend endpoints** across 11 routers
- **12 ORM entities**: Patient, Donor, Bridge, BridgeMembership, WhatsAppMessage, AgentMessage, CohortMemory, OutreachWave, OutreachPing, ManualCallQueue, EmergencyEvent, OutreachCooldown
- **395 backend pytest tests** · **180+ frontend Vitest tests** · live Playwright E2E — every one green
- **Stability AUC ≥ 0.75** on every horizon (30/60/90 day churn) with XGBoost + SHAP
- **Cohort RAG memory** with hot-pluggable embeddings (Bedrock Titan v2 / OpenAI / local hash fallback)
- **React Flow cohort graph** + grid view toggle on `/simulator`
- **Auto language detection** across 8 Indian scripts in the Care Agent

---

## Repository structure

```
bridge-os/
├── backend/                     # FastAPI + SQLAlchemy + ML services
│   ├── app/
│   │   ├── api/                 # 10 API routers
│   │   ├── models/              # SQLAlchemy entities
│   │   ├── schemas/             # Pydantic schemas
│   │   ├── ml/                  # XGBoost stability + OR-Tools scheduler
│   │   ├── simulator/           # Stateless what-if engine
│   │   ├── recommender/         # Composite candidate scorer
│   │   ├── agent/               # LLM care agent (AWS Bedrock / Anthropic / mock)
│   │   ├── integrations/        # Twilio + eRaktKosh + ICMR mocks
│   │   └── synthetic/           # Synthetic data generator
│   ├── tests/                   # 170 pytest tests
│   ├── scripts/                 # seed.py + train_stability.py
│   └── data/models/             # Saved XGBoost JSON + SHAP report
├── frontend/                    # Next.js 14 App Router
│   ├── app/                     # Routes (marketing + (app) layout group)
│   ├── components/
│   │   ├── ui/                  # Reusable primitives
│   │   └── marketing/           # Marketing nav + footer
│   ├── lib/                     # API client, utils
│   ├── tests/                   # 99 Vitest tests
│   └── e2e/                     # 59 live Playwright tests
├── docs/                        # ARCHITECTURE · DATA_MODEL · API · DEMO_SCRIPT
├── infra/                       # (reserved for production deploy config)
└── docker-compose.yml           # Postgres 16 + pgvector for production parity
```

---

## Quick start

```bash
# ----- Backend (FastAPI, SQLite by default) -----
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS / Linux
pip install -e ".[dev]"
python -m scripts.seed             # Seed synthetic data
python -m scripts.train_stability  # Train XGBoost models
pytest                             # 170 tests should pass
uvicorn app.main:app --reload      # http://localhost:8000

# ----- Frontend (Next.js 14) -----
cd frontend
npm install
npm test                           # Vitest, 99 tests
npm run dev                        # http://localhost:3000
npx playwright test --workers=1    # 59 E2E (needs backend running)
```

Open <http://localhost:3000> and you're in.

---

## Going live (optional)

Every external system is hot-pluggable via env vars. Without any of these set, everything runs in mock mode for the demo.

```bash
# Care Agent — AWS Bedrock multi-model (preferred for production)
# Routes chat -> Sonnet, intent -> Haiku, embeddings -> Titan v2.
# See docs/model_routing.md for cost + IAM details.
export BEDROCK_REGION=us-east-1
# Optional model overrides:
# export BEDROCK_SONNET_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
# export BEDROCK_HAIKU_ID=anthropic.claude-3-haiku-20240307-v1:0
# export BEDROCK_TITAN_ID=amazon.titan-embed-text-v2:0

# Fallback: Anthropic direct (used if BEDROCK_REGION is unset)
export ANTHROPIC_API_KEY=sk-ant-...
export ANTHROPIC_MODEL=claude-haiku-4-5         # optional

# WhatsApp via Twilio
export TWILIO_ACCOUNT_SID=AC_...
export TWILIO_AUTH_TOKEN=...
export TWILIO_WHATSAPP_FROM=whatsapp:+14155238886  # default = sandbox number

# Postgres + pgvector instead of local SQLite
docker compose up -d
export DATABASE_URL=postgresql+psycopg://bridge:bridge@localhost:5432/bridge_os
```

---

## Tech stack

| Layer | Choice |
|---|---|
| Backend | FastAPI · SQLAlchemy 2 · Pydantic · Postgres 16 + pgvector (or SQLite) |
| ML | XGBoost (3 churn horizons) · SHAP TreeExplainer · Google OR-Tools (CP-SAT) |
| LLM | AWS Bedrock multi-model (Claude Sonnet + Haiku + Titan v2) · Anthropic Claude direct fallback · rule-based mock |
| Comms | Twilio WhatsApp (real or mocked) |
| Mocks | eRaktKosh blood-bank inventory · ICMR Rare Donor Registry |
| Frontend | Next.js 14 (App Router) · TypeScript · Tailwind · TanStack Query · Framer Motion · Lucide |
| Testing | pytest · Vitest + React Testing Library · Playwright (live E2E) |

---

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — every phase, every module, every test count
- [Data model](docs/DATA_MODEL.md) — entities, relationships, enums
- [API](docs/API.md) — every endpoint with method + path + purpose
- [Demo script](docs/DEMO_SCRIPT.md) — the 4-minute walkthrough + Q&A canned answers

---

## Credits

- **Team AlgoWarriors** — Gunaputra Nagendra Pavan Yedida, Aakash Jangeeti
- **Hackathon** — AI for Good 2026 · Blend360 · impact partners: Blood Warriors Foundation + HackCulture
- **Inspiration** — [Blood Warriors Foundation](https://bloodwarriors.in) and the Blood Bridge model
