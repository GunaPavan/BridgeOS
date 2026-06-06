"""G1: end-to-end tests for the PENDING → WhatsApp YES/NO → ACTIVE/REJECTED loop."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.integrations import twilio_client
from app.models import (
    Bridge,
    BridgeMembership,
    Donor,
    MembershipStatus,
    Patient,
    WhatsAppMessage,
)
from tests.fixtures import build_test_dataset, feature_bridge_destabilizer
from app.utils.intent import Intent, classify


# ----- intent classifier -----


def test_intent_classifier_english_accept() -> None:
    assert classify("YES") == Intent.ACCEPT
    assert classify("yes please") == Intent.ACCEPT
    assert classify("OK") == Intent.ACCEPT
    assert classify("join") == Intent.ACCEPT


def test_intent_classifier_devanagari_accept() -> None:
    assert classify("हाँ") == Intent.ACCEPT
    assert classify("haan") == Intent.ACCEPT


def test_intent_classifier_telugu_accept_decline() -> None:
    assert classify("అవును") == Intent.ACCEPT
    assert classify("కాదు") == Intent.DECLINE


def test_intent_classifier_english_decline() -> None:
    assert classify("NO") == Intent.DECLINE
    assert classify("no thanks") == Intent.DECLINE
    assert classify("stop") == Intent.DECLINE


def test_intent_classifier_other() -> None:
    assert classify("hmm let me think") == Intent.OTHER
    assert classify("") == Intent.OTHER
    assert classify("12345") == Intent.OTHER


# ----- recruit flow helpers -----


def _seed(db: Session):
    return build_test_dataset(db, n_patients=3, n_donors=40, seed=42)


def _aarav_bridge_with_replaceable_member(db_session: Session):
    data = _seed(db_session)
    db_session.commit()
    bridge = data.feature_patient.bridge
    active = [
        m for m in bridge.memberships
        if getattr(m.status, "value", str(m.status)) == "active"
    ]
    assert len(active) >= 1
    return bridge, active[0]


def _find_compatible_outside_candidate(db_session: Session, bridge: Bridge) -> Donor:
    """Find a Donor compatible with the bridge's patient who is NOT a member."""
    patient = bridge.patient
    member_ids = {m.donor_id for m in bridge.memberships}
    bg = getattr(patient.blood_group, "value", str(patient.blood_group))
    candidates = (
        db_session.query(Donor)
        .filter(~Donor.id.in_(member_ids))
        .filter(Donor.blood_group == bg)
        .filter(Donor.is_active.is_(True))
        .all()
    )
    assert candidates, "No compatible outside candidate in synthetic seed"
    return candidates[0]


# ----- POST /bridges/{id}/recruit creates PENDING + fires WhatsApp -----


def test_recruit_creates_pending_membership_and_fires_whatsapp(
    client: TestClient, db_session: Session
) -> None:
    bridge, weak = _aarav_bridge_with_replaceable_member(db_session)
    candidate = _find_compatible_outside_candidate(db_session, bridge)

    resp = client.post(
        f"/bridges/{bridge.id}/recruit",
        json={
            "candidate_donor_id": str(candidate.id),
            "replace_donor_id": str(weak.donor_id),
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert body["waiting_for_donor_reply"] is True
    assert body["message_sid"]  # MOCK… SID or real
    assert body["replace_donor_id"] == str(weak.donor_id)

    # New PENDING membership exists
    m = (
        db_session.query(BridgeMembership)
        .filter(BridgeMembership.id == uuid.UUID(body["added_membership_id"]))
        .one()
    )
    assert getattr(m.status, "value", str(m.status)) == "pending"
    assert m.replaces_donor_id == weak.donor_id
    assert m.invite_message_sid == body["message_sid"]

    # Old member still ACTIVE — we don't EXIT until YES arrives
    weak_now = db_session.query(BridgeMembership).filter(
        BridgeMembership.id == weak.id
    ).one()
    assert getattr(weak_now.status, "value", str(weak_now.status)) == "active"

    # Outbound WhatsApp row exists with template_key recruit_invite
    out = (
        db_session.query(WhatsAppMessage)
        .filter(
            WhatsAppMessage.donor_id == candidate.id,
            WhatsAppMessage.template_key == "recruit_invite",
        )
        .one()
    )
    assert out.direction.value == "outbound" if hasattr(out.direction, "value") else out.direction == "outbound"


def test_recruit_active_donor_count_does_not_include_pending(
    client: TestClient, db_session: Session
) -> None:
    bridge, weak = _aarav_bridge_with_replaceable_member(db_session)
    candidate = _find_compatible_outside_candidate(db_session, bridge)
    before = sum(
        1 for m in bridge.memberships
        if getattr(m.status, "value", str(m.status)) == "active"
    )

    body = client.post(
        f"/bridges/{bridge.id}/recruit",
        json={"candidate_donor_id": str(candidate.id)},
    ).json()
    # Active count is the same — PENDING doesn't count, and we haven't EXITED anyone
    assert body["new_active_donor_count"] == before


def test_double_pending_for_same_donor_rejected(
    client: TestClient, db_session: Session
) -> None:
    bridge, _ = _aarav_bridge_with_replaceable_member(db_session)
    candidate = _find_compatible_outside_candidate(db_session, bridge)
    first = client.post(
        f"/bridges/{bridge.id}/recruit",
        json={"candidate_donor_id": str(candidate.id)},
    )
    assert first.status_code == 200
    second = client.post(
        f"/bridges/{bridge.id}/recruit",
        json={"candidate_donor_id": str(candidate.id)},
    )
    assert second.status_code == 409
    assert "PENDING" in second.json()["detail"]


# ----- /bridges/{id}/pending-recruits -----


def test_pending_recruits_lists_pending_membership(
    client: TestClient, db_session: Session
) -> None:
    bridge, weak = _aarav_bridge_with_replaceable_member(db_session)
    candidate = _find_compatible_outside_candidate(db_session, bridge)
    client.post(
        f"/bridges/{bridge.id}/recruit",
        json={
            "candidate_donor_id": str(candidate.id),
            "replace_donor_id": str(weak.donor_id),
        },
    )

    body = client.get(f"/bridges/{bridge.id}/pending-recruits").json()
    assert len(body) == 1
    row = body[0]
    assert row["candidate_donor_id"] == str(candidate.id)
    assert row["replaces_donor_id"] == str(weak.donor_id)
    assert row["invite_language"]
    assert row["invite_message_sid"]


def test_pending_recruits_empty_when_none_pending(
    client: TestClient, db_session: Session
) -> None:
    bridge, _ = _aarav_bridge_with_replaceable_member(db_session)
    body = client.get(f"/bridges/{bridge.id}/pending-recruits").json()
    assert body == []


# ----- /donors/{id}/pending-actions -----


def test_donor_pending_actions_shows_invite(
    client: TestClient, db_session: Session
) -> None:
    bridge, _ = _aarav_bridge_with_replaceable_member(db_session)
    candidate = _find_compatible_outside_candidate(db_session, bridge)
    client.post(
        f"/bridges/{bridge.id}/recruit",
        json={"candidate_donor_id": str(candidate.id)},
    )

    body = client.get(f"/donors/{candidate.id}/pending-actions").json()
    assert len(body) == 1
    assert body[0]["kind"] == "recruit"
    assert body[0]["bridge_id"] == str(bridge.id)
    assert body[0]["patient_name"]


def test_pending_actions_404_on_unknown_donor(client: TestClient) -> None:
    """Previously returned 200 [] which masked 'donor doesn't exist' as
    'donor has no pending actions'. Every other /donors/{id}/* endpoint
    returns 404 on unknown id — this one must too."""
    import uuid as _uuid

    resp = client.get(f"/donors/{_uuid.uuid4()}/pending-actions")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


# ----- /whatsapp/webhook YES flips PENDING -> ACTIVE -----


def test_webhook_yes_promotes_pending_to_active_and_exits_replaced(
    client: TestClient, db_session: Session
) -> None:
    bridge, weak = _aarav_bridge_with_replaceable_member(db_session)
    candidate = _find_compatible_outside_candidate(db_session, bridge)
    rec = client.post(
        f"/bridges/{bridge.id}/recruit",
        json={
            "candidate_donor_id": str(candidate.id),
            "replace_donor_id": str(weak.donor_id),
        },
    ).json()
    pending_id = uuid.UUID(rec["added_membership_id"])

    # Inbound YES from the candidate
    resp = client.post(
        "/whatsapp/webhook",
        data={
            "From": f"whatsapp:{candidate.phone}",
            "To": twilio_client.whatsapp_from(),
            "Body": "YES",
            "MessageSid": "SM_test_yes",
        },
    )
    assert resp.status_code == 200
    assert "<Response>" in resp.text

    # Membership is now ACTIVE
    db_session.expire_all()
    m = db_session.query(BridgeMembership).filter(BridgeMembership.id == pending_id).one()
    assert getattr(m.status, "value", str(m.status)) == "active"

    # Replaced donor is now EXITED
    weak_now = db_session.query(BridgeMembership).filter(BridgeMembership.id == weak.id).one()
    assert getattr(weak_now.status, "value", str(weak_now.status)) == "exited"


def test_webhook_yes_in_hindi_token_also_flips(
    client: TestClient, db_session: Session
) -> None:
    bridge, _ = _aarav_bridge_with_replaceable_member(db_session)
    candidate = _find_compatible_outside_candidate(db_session, bridge)
    rec = client.post(
        f"/bridges/{bridge.id}/recruit",
        json={"candidate_donor_id": str(candidate.id), "language": "hi"},
    ).json()
    pending_id = uuid.UUID(rec["added_membership_id"])

    client.post(
        "/whatsapp/webhook",
        data={
            "From": f"whatsapp:{candidate.phone}",
            "To": twilio_client.whatsapp_from(),
            "Body": "हाँ",
            "MessageSid": "SM_test_haan",
        },
    )
    db_session.expire_all()
    m = db_session.query(BridgeMembership).filter(BridgeMembership.id == pending_id).one()
    assert getattr(m.status, "value", str(m.status)) == "active"


# ----- /whatsapp/webhook NO flips PENDING -> REJECTED -----


def test_webhook_no_rejects_pending_and_keeps_replaced_active(
    client: TestClient, db_session: Session
) -> None:
    bridge, weak = _aarav_bridge_with_replaceable_member(db_session)
    candidate = _find_compatible_outside_candidate(db_session, bridge)
    rec = client.post(
        f"/bridges/{bridge.id}/recruit",
        json={
            "candidate_donor_id": str(candidate.id),
            "replace_donor_id": str(weak.donor_id),
        },
    ).json()
    pending_id = uuid.UUID(rec["added_membership_id"])

    client.post(
        "/whatsapp/webhook",
        data={
            "From": f"whatsapp:{candidate.phone}",
            "To": twilio_client.whatsapp_from(),
            "Body": "NO",
            "MessageSid": "SM_test_no",
        },
    )
    db_session.expire_all()
    m = db_session.query(BridgeMembership).filter(BridgeMembership.id == pending_id).one()
    assert getattr(m.status, "value", str(m.status)) == "rejected"
    # Replaced donor stays ACTIVE
    w = db_session.query(BridgeMembership).filter(BridgeMembership.id == weak.id).one()
    assert getattr(w.status, "value", str(w.status)) == "active"


# ----- /whatsapp/webhook OTHER leaves PENDING alone -----


def test_webhook_other_leaves_pending_unchanged(
    client: TestClient, db_session: Session
) -> None:
    bridge, _ = _aarav_bridge_with_replaceable_member(db_session)
    candidate = _find_compatible_outside_candidate(db_session, bridge)
    rec = client.post(
        f"/bridges/{bridge.id}/recruit",
        json={"candidate_donor_id": str(candidate.id)},
    ).json()
    pending_id = uuid.UUID(rec["added_membership_id"])

    resp = client.post(
        "/whatsapp/webhook",
        data={
            "From": f"whatsapp:{candidate.phone}",
            "To": twilio_client.whatsapp_from(),
            "Body": "let me check my schedule",
            "MessageSid": "SM_test_other",
        },
    )
    assert resp.status_code == 200
    db_session.expire_all()
    m = db_session.query(BridgeMembership).filter(BridgeMembership.id == pending_id).one()
    assert getattr(m.status, "value", str(m.status)) == "pending"


# ----- Webhook from unknown donor falls through to generic ack -----


def test_webhook_unknown_sender_generic_ack(
    client: TestClient, db_session: Session
) -> None:
    resp = client.post(
        "/whatsapp/webhook",
        data={
            "From": "whatsapp:+15550000000",
            "To": twilio_client.whatsapp_from(),
            "Body": "YES",
            "MessageSid": "SM_test_unknown",
        },
    )
    assert resp.status_code == 200
    assert "couldn't find your number" in resp.text or "couldn" in resp.text
