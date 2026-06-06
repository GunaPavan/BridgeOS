"""Tests for POST /outreach/commit-allocations — the coordinator-curated
materialisation endpoint."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    BloodGroup,
    Bridge,
    BridgeStatus,
    Donor,
    OutreachPing,
    OutreachWave,
    Patient,
)


def _seed_patient(db: Session, *, bg: BloodGroup = BloodGroup.B_POS) -> Patient:
    p = Patient(
        name="Commit Test Patient",
        age=10,
        blood_group=bg,
        rh_negative=False,
        kell_negative=False,
        city="Hyderabad",
        state="Telangana",
        lat=17.39,
        lng=78.46,
        hospital="Apollo",
        transfusion_cadence_days=21,
        last_transfusion_date=date.today() - timedelta(days=20),
        active=True,
    )
    db.add(p)
    db.flush()
    db.add(Bridge(patient_id=p.id, name="Bridge", status=BridgeStatus.ACTIVE))
    db.commit()
    return p


def _seed_donor(
    db: Session,
    *,
    bg: BloodGroup = BloodGroup.O_POS,
    name: str = "Test Donor",
    is_active: bool = True,
    last_donation_days_ago: int | None = None,
) -> Donor:
    d = Donor(
        name=name,
        age=28,
        blood_group=bg,
        rh_negative=False,
        kell_negative=False,
        phone="+919999000000",
        city="Hyderabad",
        state="Telangana",
        lat=17.40,
        lng=78.46,
        is_active=is_active,
        response_rate=0.7,
        last_donation_date=(
            date.today() - timedelta(days=last_donation_days_ago)
            if last_donation_days_ago is not None
            else None
        ),
        registered_at=datetime(2025, 1, 1),
    )
    db.add(d)
    db.commit()
    return d


class TestCommitAllocations:
    def test_creates_one_wave_per_selection(
        self, client: TestClient, db_session: Session
    ) -> None:
        p = _seed_patient(db_session)
        d1 = _seed_donor(db_session, name="d1")
        d2 = _seed_donor(db_session, name="d2")
        slot_date = (date.today() + timedelta(days=1)).isoformat()

        resp = client.post(
            "/outreach/commit-allocations",
            json={
                "selections": [
                    {
                        "patient_id": str(p.id),
                        "slot_date": slot_date,
                        "donor_ids": [str(d1.id), str(d2.id)],
                    }
                ]
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["created_count"] == 1
        assert len(body["created_wave_ids"]) == 1

        # Wave persisted with 2 pings
        wave = db_session.execute(select(OutreachWave)).scalar_one()
        assert wave.triggered_by == "coordinator_manual"
        assert len(wave.pings) == 2

    def test_per_selection_independent_failures(
        self, client: TestClient, db_session: Session
    ) -> None:
        good_patient = _seed_patient(db_session)
        good_donor = _seed_donor(db_session, name="good")
        bad_patient_id = uuid.uuid4()
        slot_date = (date.today() + timedelta(days=1)).isoformat()

        resp = client.post(
            "/outreach/commit-allocations",
            json={
                "selections": [
                    {
                        "patient_id": str(good_patient.id),
                        "slot_date": slot_date,
                        "donor_ids": [str(good_donor.id)],
                    },
                    {
                        "patient_id": str(bad_patient_id),
                        "slot_date": slot_date,
                        "donor_ids": [str(good_donor.id)],
                    },
                ]
            },
        )
        body = resp.json()
        # One created, one skipped — selection failures don't poison the batch
        assert body["created_count"] == 1
        diag = body["diagnostics"]
        assert any(d.get("skipped_reason") == "patient_not_found" for d in diag)

    def test_drops_donors_who_fail_validation_but_keeps_eligible_ones(
        self, client: TestClient, db_session: Session
    ) -> None:
        p = _seed_patient(db_session, bg=BloodGroup.B_POS)
        good = _seed_donor(db_session, bg=BloodGroup.O_POS, name="good")
        bad_bg = _seed_donor(db_session, bg=BloodGroup.A_POS, name="bad_bg")
        recent = _seed_donor(
            db_session,
            bg=BloodGroup.O_POS,
            name="recent",
            last_donation_days_ago=45,  # within 90d clinical deferral
        )
        slot_date = (date.today() + timedelta(days=1)).isoformat()

        resp = client.post(
            "/outreach/commit-allocations",
            json={
                "selections": [
                    {
                        "patient_id": str(p.id),
                        "slot_date": slot_date,
                        "donor_ids": [str(good.id), str(bad_bg.id), str(recent.id)],
                    }
                ]
            },
        )
        body = resp.json()
        assert body["created_count"] == 1
        wave_id = body["created_wave_ids"][0]
        # Only `good` should be in the wave's pings
        wave = db_session.get(OutreachWave, uuid.UUID(wave_id))
        assert len(wave.pings) == 1
        assert wave.pings[0].donor_id == good.id
        # Diagnostics record the dropped donors with reasons
        dropped = body["diagnostics"][0]["dropped"]
        assert any("blood_group_incompatible" in d for d in dropped)
        assert any("within_90d_deferral" in d for d in dropped)

    def test_zero_eligible_donors_skips_creating_a_wave(
        self, client: TestClient, db_session: Session
    ) -> None:
        p = _seed_patient(db_session)
        bad = _seed_donor(db_session, bg=BloodGroup.A_POS, name="incompatible")
        slot_date = (date.today() + timedelta(days=1)).isoformat()

        resp = client.post(
            "/outreach/commit-allocations",
            json={
                "selections": [
                    {
                        "patient_id": str(p.id),
                        "slot_date": slot_date,
                        "donor_ids": [str(bad.id)],
                    }
                ]
            },
        )
        body = resp.json()
        assert body["created_count"] == 0
        assert body["diagnostics"][0]["skipped_reason"] == "no_eligible_donors_after_validation"

    def test_empty_selections_returns_422(self, client: TestClient) -> None:
        resp = client.post("/outreach/commit-allocations", json={"selections": []})
        assert resp.status_code == 422  # min_length=1

    def test_donor_list_must_be_non_empty(
        self, client: TestClient, db_session: Session
    ) -> None:
        p = _seed_patient(db_session)
        slot_date = (date.today() + timedelta(days=1)).isoformat()
        resp = client.post(
            "/outreach/commit-allocations",
            json={
                "selections": [
                    {
                        "patient_id": str(p.id),
                        "slot_date": slot_date,
                        "donor_ids": [],
                    }
                ]
            },
        )
        assert resp.status_code == 422  # min_length=1 on donor_ids
