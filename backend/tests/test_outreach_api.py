"""Tests for the /outreach API surface (allocator cycle + wave inspection)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import (
    BloodGroup,
    Bridge,
    BridgeStatus,
    Donor,
    OutreachPing,
    OutreachTier,
    OutreachWave,
    OutreachWaveStatus,
    Patient,
    PingResponse,
    UrgencyTier,
)


def _seed_patient_and_donors(db: Session, *, today: date) -> Patient:
    p = Patient(
        name="Test Patient",
        age=12,
        blood_group=BloodGroup.B_POS,
        rh_negative=False,
        kell_negative=False,
        city="Hyderabad",
        state="Telangana",
        lat=17.39,
        lng=78.46,
        hospital="Apollo",
        transfusion_cadence_days=21,
        last_transfusion_date=today - timedelta(days=20),
        active=True,
    )
    db.add(p)
    db.flush()
    db.add(Bridge(patient_id=p.id, name="Bridge", status=BridgeStatus.ACTIVE))
    for i in range(4):
        db.add(
            Donor(
                name=f"D-{i}",
                age=30,
                blood_group=BloodGroup.O_POS,
                rh_negative=False,
                kell_negative=False,
                phone="+919999999999",
                city="Hyderabad",
                state="Telangana",
                lat=17.40 + 0.01 * i,
                lng=78.46,
                is_active=True,
                response_rate=0.7,
                total_calls=0,
                registered_at=datetime(2025, 1, 1),
            )
        )
    db.commit()
    return p


class TestRunCycleEndpoint:
    def test_dry_run_returns_allocations_without_persisting(
        self, client: TestClient, db_session: Session, monkeypatch
    ) -> None:
        # Pin the system clock so urgency math is deterministic
        from app import system_clock
        anchor = date(2026, 6, 6)
        monkeypatch.setattr(system_clock, "today", lambda *_a, **_k: anchor)
        _seed_patient_and_donors(db_session, today=anchor)

        body = client.post("/outreach/run-cycle?dry_run=true").json()
        assert body["summary"]["dry_run"] is True
        assert body["summary"]["open_slots"] >= 1
        # No waves should hit the DB
        waves = db_session.execute(
            __import__("sqlalchemy").select(OutreachWave)
        ).scalars().all()
        assert len(waves) == 0
        assert len(body["allocations"]) == body["summary"]["open_slots"]

    def test_real_run_creates_wave_rows(
        self, client: TestClient, db_session: Session, monkeypatch
    ) -> None:
        from app import system_clock
        anchor = date(2026, 6, 6)
        monkeypatch.setattr(system_clock, "today", lambda *_a, **_k: anchor)
        _seed_patient_and_donors(db_session, today=anchor)

        body = client.post("/outreach/run-cycle").json()
        assert body["summary"]["waves_created"] >= 1
        waves = db_session.execute(
            __import__("sqlalchemy").select(OutreachWave)
        ).scalars().all()
        assert len(waves) == body["summary"]["waves_created"]
        # Allocation entries surface batches
        first = body["allocations"][0]
        assert first["batch_size"] >= 1
        assert "preferred_language" in first["batch"][0]


class TestListAndGetWaves:
    def test_list_waves_returns_recent(
        self, client: TestClient, db_session: Session, monkeypatch
    ) -> None:
        from app import system_clock
        anchor = date(2026, 6, 6)
        monkeypatch.setattr(system_clock, "today", lambda *_a, **_k: anchor)
        _seed_patient_and_donors(db_session, today=anchor)
        client.post("/outreach/run-cycle")
        body = client.get("/outreach/waves").json()
        assert "items" in body
        assert len(body["items"]) >= 1

    def test_get_wave_returns_pings(
        self, client: TestClient, db_session: Session, monkeypatch
    ) -> None:
        from app import system_clock
        anchor = date(2026, 6, 6)
        monkeypatch.setattr(system_clock, "today", lambda *_a, **_k: anchor)
        _seed_patient_and_donors(db_session, today=anchor)
        client.post("/outreach/run-cycle")
        listed = client.get("/outreach/waves").json()
        wave_id = listed["items"][0]["id"]
        body = client.get(f"/outreach/waves/{wave_id}").json()
        assert body["id"] == wave_id
        assert "pings" in body
        assert all(p["response"] == "pending" for p in body["pings"])

    def test_get_wave_404_for_unknown(self, client: TestClient) -> None:
        resp = client.get(f"/outreach/waves/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestExpireAndSweep:
    def test_expire_sweep_flips_status(
        self, client: TestClient, db_session: Session, monkeypatch
    ) -> None:
        from app import system_clock
        anchor = date(2026, 6, 6)
        monkeypatch.setattr(system_clock, "today", lambda *_a, **_k: anchor)
        p = _seed_patient_and_donors(db_session, today=anchor)
        # Insert a wave that's already expired
        w = OutreachWave(
            patient_id=p.id,
            slot_date=anchor + timedelta(days=1),
            status=OutreachWaveStatus.ACTIVE,
            tier=OutreachTier.TIER_1,
            urgency=UrgencyTier.CRITICAL,
            expires_at=datetime.utcnow() - timedelta(minutes=10),
        )
        db_session.add(w)
        db_session.commit()
        body = client.post("/outreach/expire-and-sweep").json()
        assert body["expired_count"] == 1
        db_session.refresh(w)
        assert w.status == OutreachWaveStatus.EXPIRED
