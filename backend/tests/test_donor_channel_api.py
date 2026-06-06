"""E6 — /donors/{id}/channel + /patients/{id}/caregiver-channel CRUD tests."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import (
    BloodGroup,
    CaregiverRelation,
    ContactChannel,
    Donor,
    Language,
    Patient,
)


def _make_donor(db: Session) -> Donor:
    d = Donor(
        name="Vikram K", age=28, phone="+919900000088",
        blood_group=BloodGroup.B_POS, city="Hyderabad", state="Telangana",
        lat=17.39, lng=78.46, preferred_language=Language.ENGLISH,
        is_active=True,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def _make_patient(db: Session, *, with_email: bool = True) -> Patient:
    p = Patient(
        name="Riya", age=8, blood_group=BloodGroup.B_POS,
        rh_negative=False, kell_negative=False,
        city="Hyderabad", state="Telangana", lat=17.39, lng=78.46,
        hospital="Apollo", transfusion_cadence_days=21,
        last_transfusion_date=date(2026, 5, 1), active=True,
        caregiver_name="Anita", caregiver_phone="+919900000099",
        caregiver_email="anita@example.com" if with_email else None,
        caregiver_relation=CaregiverRelation.MOTHER,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def test_get_donor_channel_returns_default_whatsapp(client: TestClient, db_session: Session):
    """Donor default is WHATSAPP (post-E6.1 pivot) because it's the only
    channel where replies feed back into the automation loop."""
    d = _make_donor(db_session)
    r = client.get(f"/donors/{d.id}/channel")
    assert r.status_code == 200
    body = r.json()
    assert body["preferred_channel"] == "whatsapp"
    assert body["name"] == "Vikram K"


def test_patch_donor_channel_to_sms_is_allowed_as_opt_in(
    client: TestClient, db_session: Session
):
    """Operators CAN opt a donor into SMS as a one-way alert channel —
    just not the default. The body gets a 'call coordinator' tail at
    dispatch time."""
    d = _make_donor(db_session)
    r = client.patch(
        f"/donors/{d.id}/channel",
        json={"preferred_channel": "sms"},
    )
    assert r.status_code == 200
    assert r.json()["preferred_channel"] == "sms"
    db_session.refresh(d)
    assert getattr(d.preferred_channel, "value", d.preferred_channel) == "sms"


def test_patch_donor_channel_rejects_email(client: TestClient, db_session: Session):
    d = _make_donor(db_session)
    r = client.patch(
        f"/donors/{d.id}/channel",
        json={"preferred_channel": "email"},
    )
    assert r.status_code == 400
    assert "caregiver-only" in r.json()["detail"].lower()


def test_patch_donor_channel_404_when_missing(client: TestClient):
    r = client.patch(
        f"/donors/{uuid.uuid4()}/channel",
        json={"preferred_channel": "sms"},
    )
    assert r.status_code == 404


def test_get_caregiver_channel_default_is_whatsapp(client: TestClient, db_session: Session):
    p = _make_patient(db_session)
    r = client.get(f"/patients/{p.id}/caregiver-channel")
    assert r.status_code == 200
    body = r.json()
    assert body["caregiver_preferred_channel"] == "whatsapp"
    assert body["caregiver_email"] == "anita@example.com"


def test_patch_caregiver_channel_to_email_requires_email_on_file(
    client: TestClient, db_session: Session
):
    p = _make_patient(db_session, with_email=False)
    r = client.patch(
        f"/patients/{p.id}/caregiver-channel",
        json={"caregiver_preferred_channel": "email"},
    )
    assert r.status_code == 400


def test_patch_caregiver_channel_to_email_with_email_works(
    client: TestClient, db_session: Session
):
    p = _make_patient(db_session)
    r = client.patch(
        f"/patients/{p.id}/caregiver-channel",
        json={"caregiver_preferred_channel": "email"},
    )
    assert r.status_code == 200
    assert r.json()["caregiver_preferred_channel"] == "email"


def test_patch_caregiver_channel_sets_email_inline(
    client: TestClient, db_session: Session
):
    p = _make_patient(db_session, with_email=False)
    r = client.patch(
        f"/patients/{p.id}/caregiver-channel",
        json={
            "caregiver_preferred_channel": "email",
            "caregiver_email": "newcaregiver@example.com",
        },
    )
    assert r.status_code == 200
    assert r.json()["caregiver_email"] == "newcaregiver@example.com"
    assert r.json()["caregiver_preferred_channel"] == "email"
