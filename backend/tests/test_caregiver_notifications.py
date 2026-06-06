"""G5 — caregiver fields on Patient, auto-fire on YES, manual endpoint, conversations."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.integrations import twilio_client
from app.models import (
    CaregiverRelation,
    Donor,
    Language,
    Patient,
    WhatsAppMessage,
)
from app.services.whatsapp_templates import (
    CAREGIVER_TEMPLATE_KEYS,
    render,
)
from tests.fixtures import build_test_dataset, feature_bridge_destabilizer


def _seed(db: Session):
    return build_test_dataset(db, n_patients=3, n_donors=40, seed=42)


# ----- Synthetic generator populates caregiver fields -----



def test_every_synthetic_patient_has_caregiver_fields(db_session: Session) -> None:
    data = _seed(db_session)
    db_session.commit()
    for p in data.patients:
        assert p.caregiver_name, f"{p.name} missing caregiver_name"
        assert p.caregiver_phone, f"{p.name} missing caregiver_phone"
        assert p.caregiver_relation is not None, f"{p.name} missing relation"


# ----- Templates registered + supported across all 8 languages -----


def test_three_caregiver_templates_registered() -> None:
    assert CAREGIVER_TEMPLATE_KEYS == {
        "recruit_success_caregiver",
        "bridge_covered_caregiver",
        "transfusion_confirmed_caregiver",
    }


def test_recruit_success_renders_with_caregiver_vars_in_hindi() -> None:
    r = render(
        "recruit_success_caregiver",
        language="hi",
        caregiver_first="Lakshmi",
        patient_name="Aarav",
        added_donor_name="Aishwarya Murthy",
        active_donor_count=8,
    )
    # Hindi script + variable substitutions
    assert "Lakshmi" in r.body
    assert "Aarav" in r.body
    assert "Aishwarya Murthy" in r.body
    assert "8" in r.body
    assert any("ऀ" <= c <= "ॿ" for c in r.body)
    assert r.language_used == "hi"


# ----- Webhook YES auto-fires caregiver notification -----


def test_webhook_yes_fires_recruit_success_caregiver(
    client: TestClient, db_session: Session
) -> None:
    data = _seed(db_session)
    db_session.commit()
    bridge = data.feature_patient.bridge
    aarav = data.feature_patient

    # Find a B+ donor not on Aarav's bridge to recruit
    member_ids = {m.donor_id for m in bridge.memberships}
    candidate = (
        db_session.query(Donor)
        .filter(~Donor.id.in_(member_ids))
        .filter(Donor.blood_group == "B+")
        .filter(Donor.is_active.is_(True))
        .first()
    )
    assert candidate

    client.post(
        f"/bridges/{bridge.id}/recruit",
        json={"candidate_donor_id": str(candidate.id)},
    )
    # Confirm YES
    client.post(
        "/whatsapp/webhook",
        data={
            "From": f"whatsapp:{candidate.phone}",
            "To": twilio_client.whatsapp_from(),
            "Body": "YES",
            "MessageSid": "SM_g5_caregiver_yes",
        },
    )
    db_session.expire_all()

    # Caregiver outbound row should exist
    caregiver_msg = (
        db_session.query(WhatsAppMessage)
        .filter(
            WhatsAppMessage.patient_id == aarav.id,
            WhatsAppMessage.donor_id.is_(None),
            WhatsAppMessage.template_key == "recruit_success_caregiver",
        )
        .one()
    )
    assert caregiver_msg.to_number == aarav.caregiver_phone
    assert candidate.name in caregiver_msg.body
    # Body is rendered in the patient's preferred language — exact script varies.


def test_webhook_no_does_not_fire_caregiver_notification(
    client: TestClient, db_session: Session
) -> None:
    data = _seed(db_session)
    db_session.commit()
    bridge = data.feature_patient.bridge
    aarav = data.feature_patient
    candidate = (
        db_session.query(Donor)
        .filter(~Donor.id.in_({m.donor_id for m in bridge.memberships}))
        .filter(Donor.blood_group == "B+")
        .first()
    )
    client.post(
        f"/bridges/{bridge.id}/recruit",
        json={"candidate_donor_id": str(candidate.id)},
    )
    client.post(
        "/whatsapp/webhook",
        data={
            "From": f"whatsapp:{candidate.phone}",
            "To": twilio_client.whatsapp_from(),
            "Body": "NO",
            "MessageSid": "SM_g5_caregiver_no",
        },
    )
    count = (
        db_session.query(WhatsAppMessage)
        .filter(
            WhatsAppMessage.patient_id == aarav.id,
            WhatsAppMessage.template_key == "recruit_success_caregiver",
        )
        .count()
    )
    assert count == 0


# ----- Manual /patients/{id}/notify-caregiver endpoint -----


def test_notify_caregiver_manual_send(client: TestClient, db_session: Session) -> None:
    data = _seed(db_session)
    db_session.commit()
    aarav = data.feature_patient
    body = client.post(
        f"/patients/{aarav.id}/notify-caregiver",
        json={
            "template_key": "bridge_covered_caregiver",
            "language": "en",
        },
    ).json()
    assert body["template_key"] == "bridge_covered_caregiver"
    assert body["language_used"] == "en"
    assert (aarav.caregiver_name.split()[0] if aarav.caregiver_name else "Caregiver") in body["body"]
    assert aarav.name.split()[0] in body["body"]


def test_notify_caregiver_rejects_non_caregiver_template(
    client: TestClient, db_session: Session
) -> None:
    data = _seed(db_session)
    db_session.commit()
    resp = client.post(
        f"/patients/{data.feature_patient.id}/notify-caregiver",
        json={"template_key": "slot_reminder"},
    )
    assert resp.status_code == 400
    assert "caregiver template" in resp.json()["detail"]


def test_notify_caregiver_404_for_unknown_patient(client: TestClient) -> None:
    resp = client.post(
        f"/patients/{uuid.uuid4()}/notify-caregiver",
        json={"template_key": "bridge_covered_caregiver"},
    )
    assert resp.status_code == 404


def test_notify_caregiver_400_when_no_phone_configured(
    client: TestClient, db_session: Session
) -> None:
    data = _seed(db_session)
    db_session.commit()
    aarav = data.feature_patient
    aarav.caregiver_phone = None
    db_session.commit()
    resp = client.post(
        f"/patients/{aarav.id}/notify-caregiver",
        json={"template_key": "bridge_covered_caregiver"},
    )
    assert resp.status_code == 400
    assert "no caregiver_phone" in resp.json()["detail"]


# ----- /patients/{id} exposes caregiver fields -----


def test_patient_detail_returns_caregiver(client: TestClient, db_session: Session) -> None:
    data = _seed(db_session)
    db_session.commit()
    aarav = data.feature_patient
    body = client.get(f"/patients/{aarav.id}").json()
    assert body["caregiver_name"] == aarav.caregiver_name
    assert body["caregiver_phone"] == aarav.caregiver_phone
    assert body["caregiver_relation"] == "mother"


# ----- /whatsapp/conversations includes caregiver rows -----



def test_caregiver_thread_returns_messages(
    client: TestClient, db_session: Session
) -> None:
    data = _seed(db_session)
    db_session.commit()
    aarav = data.feature_patient
    for _ in range(2):
        client.post(
            f"/patients/{aarav.id}/notify-caregiver",
            json={"template_key": "bridge_covered_caregiver", "language": "en"},
        )
    body = client.get(f"/whatsapp/conversations/caregiver/{aarav.id}").json()
    assert body["caregiver"]["patient_name"] == aarav.name
    assert len(body["messages"]) == 2


def test_caregiver_thread_404_unknown_patient(client: TestClient) -> None:
    resp = client.get(f"/whatsapp/conversations/caregiver/{uuid.uuid4()}")
    assert resp.status_code == 404
