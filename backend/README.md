# Bridge OS — Backend

FastAPI service with SQLAlchemy, XGBoost, and OR-Tools.

## Setup (Windows)

```powershell
# From bridge-os/backend
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

## Run

```powershell
# Ensure Postgres is up (from project root: docker compose up -d)
copy ..\.env.example .env
uvicorn app.main:app --reload
# API docs: http://localhost:8000/docs
```

## Test

```powershell
pytest
```

## Structure

```
backend/
├── pyproject.toml
├── app/
│   ├── main.py             # FastAPI app factory + routes mount
│   ├── config.py           # Pydantic settings
│   ├── db.py               # SQLAlchemy session
│   ├── api/                # API route modules
│   ├── models/             # SQLAlchemy entities
│   ├── schemas/            # Pydantic request/response schemas
│   ├── ml/                 # Stability + scheduler
│   ├── integrations/       # Twilio, eRaktKosh mock, ICMR mock
│   └── synthetic/          # Data generator
├── alembic/                # Migrations
├── scripts/                # Seeding, training
└── tests/
```
