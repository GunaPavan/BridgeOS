"""G6 — swap state machine tests."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.integrations import twilio_client
from app.models import (
    Bridge,
    BridgeMembership,
    Donor,
    MembershipStatus,
    SlotSwapRequest,
    SwapStatus,
    WhatsAppMessage,
)
from app.services import swap_engine
from tests.fixtures import build_test_dataset, feature_bridge_destabilizer
from app.utils.swap_parser import parse_date, parse_swap


def _seed(db: Session):
    return build_test_dataset(db, n_patients=3, n_donors=40, seed=42)


def _aarav_bridge_and_priya(db: Session):
    """Returns (bridge, Priya). Use _healthy_requester() when you need a donor
    that the OR-Tools scheduler actually assigns a slot to."""
    data = _seed(db)
    db.commit()
    bridge = data.feature_patient.bridge
    priya = feature_bridge_destabilizer(data)
    return bridge, priya


def _healthy_requester(bridge):
    """A donor on the bridge with a high response_rate (the scheduler will
    pick them, so initiate_swap can find their next slot)."""
    actives = [
        m.donor
        for m in bridge.memberships
        if getattr(m.status, "value", str(m.status)) == "active"
        and m.donor.name != "Priya Sharma"
    ]
    # Highest response_rate first
    actives.sort(key=lambda d: -float(d.response_rate or 0))
    return actives[0]


# ----- date + intent parser -----


def test_parse_date_handles_multiple_formats() -> None:
    today = date(2026, 6, 1)
    assert parse_date("swap 2026-08-15 priya", today) == date(2026, 8, 15)
    assert parse_date("swap aug 15 priya", today) == date(2026, 8, 15)
    assert parse_date("swap 15 august priya", today) == date(2026, 8, 15)
    assert parse_date("swap 15/08 priya", today) == date(2026, 8, 15)
    assert parse_date("tomorrow", today) == date(2026, 6, 2)
    assert parse_date("no date here") is None


def test_parse_swap_only_when_swap_keyword_and_date_present() -> None:
    today = date(2026, 6, 1)
    p = parse_swap("swap with priya on aug 15", today)
    assert p is not None and p.name_fragment == "priya" and p.date == date(2026, 8, 15)

    assert parse_swap("hi just checking in", today) is None
    assert parse_swap("swap with priya", today) is None  # no date
    assert parse_swap("aug 15 priya", today) is None  # no swap keyword


# ----- initiate_swap -----


def test_initiate_swap_proposes_and_notifies_target(db_session: Session) -> None:
    bridge, priya = _aarav_bridge_and_priya(db_session)
    requester = _healthy_requester(bridge)
    target = next(
        m.donor
        for m in bridge.memberships
        if getattr(m.status, "value", str(m.status)) == "active"
        and m.donor.id != requester.id
        and m.donor.id != priya.id
    )
    # Give the target a unique name so the fuzzy match resolves to exactly them
    target.name = "TargetUniqueOne Patel"
    db_session.commit()

    target_slot = date.today() + timedelta(days=30)
    outcome = swap_engine.initiate_swap(
        db_session,
        from_donor=requester,
        bridge=bridge,
        name_fragment="targetuniqueone",
        to_slot_date=target_slot,
        commit=True,
    )
    assert outcome.result == swap_engine.InitiateResult.PROPOSED, (
        f"Expected PROPOSED, got {outcome.result.value}: {outcome.reply_body}"
    )
    assert outcome.swap is not None
    assert outcome.swap.from_donor_id == requester.id
    assert outcome.swap.to_donor_id == target.id

    notify = (
        db_session.query(WhatsAppMessage)
        .filter(
            WhatsAppMessage.donor_id == target.id,
            WhatsAppMessage.template_key == "swap_request_inbound",
        )
        .one()
    )
    assert requester.name in notify.body or requester.name.split()[0] in notify.body


def test_initiate_swap_unknown_donor_returns_friendly_reply(
    db_session: Session,
) -> None:
    bridge, _priya = _aarav_bridge_and_priya(db_session)
    requester = _healthy_requester(bridge)
    outcome = swap_engine.initiate_swap(
        db_session,
        from_donor=requester,
        bridge=bridge,
        name_fragment="zzznotrealdonor",
        to_slot_date=date.today() + timedelta(days=20),
    )
    assert outcome.result == swap_engine.InitiateResult.NO_TARGET_FOUND
    assert outcome.swap is None
    assert "couldn't find" in outcome.reply_body.lower() or "zzznotrealdonor" in outcome.reply_body.lower()


def test_initiate_swap_ambiguous_name_returns_clarification(
    db_session: Session,
) -> None:
    bridge, _priya = _aarav_bridge_and_priya(db_session)
    requester = _healthy_requester(bridge)
    # Force two OTHER donors on this bridge to share a common substring "verma"
    others = [
        m.donor
        for m in bridge.memberships
        if getattr(m.status, "value", str(m.status)) == "active"
        and m.donor.id != requester.id
    ]
    others[0].name = "Asha Verma"
    others[1].name = "Ravi Verma"
    db_session.commit()

    outcome = swap_engine.initiate_swap(
        db_session,
        from_donor=requester,
        bridge=bridge,
        name_fragment="verma",
        to_slot_date=date.today() + timedelta(days=20),
    )
    assert outcome.result == swap_engine.InitiateResult.AMBIGUOUS_TARGET
    assert outcome.swap is None
    assert "Asha Verma" in outcome.reply_body
    assert "Ravi Verma" in outcome.reply_body


def test_initiate_swap_rejects_self_swap(db_session: Session) -> None:
    bridge, _priya = _aarav_bridge_and_priya(db_session)
    requester = _healthy_requester(bridge)
    outcome = swap_engine.initiate_swap(
        db_session,
        from_donor=requester,
        bridge=bridge,
        name_fragment=requester.name.lower(),
        to_slot_date=date.today() + timedelta(days=10),
    )
    assert outcome.result == swap_engine.InitiateResult.AMBIGUOUS_TARGET
    assert "yourself" in outcome.reply_body.lower()


def test_initiate_swap_rejects_non_member(db_session: Session) -> None:
    bridge, priya = _aarav_bridge_and_priya(db_session)
    outsider = (
        db_session.query(Donor)
        .filter(~Donor.id.in_({m.donor_id for m in bridge.memberships}))
        .first()
    )
    outcome = swap_engine.initiate_swap(
        db_session,
        from_donor=outsider,
        bridge=bridge,
        name_fragment=priya.name.split()[0].lower(),
        to_slot_date=date.today() + timedelta(days=10),
    )
    assert outcome.result == swap_engine.InitiateResult.NOT_A_MEMBER


# ----- accept_swap -----


def test_accept_swap_flips_status_and_notifies_both(db_session: Session) -> None:
    bridge, _priya = _aarav_bridge_and_priya(db_session)
    requester = _healthy_requester(bridge)
    target = next(
        m.donor
        for m in bridge.memberships
        if getattr(m.status, "value", str(m.status)) == "active"
        and m.donor.id != requester.id
        and m.donor.name != "Priya Sharma"
    )
    target.name = "AcceptTargetUnique Singh"
    db_session.commit()

    out = swap_engine.initiate_swap(
        db_session,
        from_donor=requester,
        bridge=bridge,
        name_fragment="accepttargetunique",
        to_slot_date=date.today() + timedelta(days=20),
    )
    swap = out.swap
    assert swap is not None

    swap_engine.accept_swap(db_session, swap=swap)
    db_session.commit()

    refreshed = db_session.get(SlotSwapRequest, swap.id)
    assert getattr(refreshed.status, "value", str(refreshed.status)) == "accepted"
    assert refreshed.accepted_at is not None

    confirms = (
        db_session.query(WhatsAppMessage)
        .filter(WhatsAppMessage.template_key == "swap_confirmed")
        .all()
    )
    donor_ids = {m.donor_id for m in confirms}
    assert requester.id in donor_ids
    assert target.id in donor_ids


# ----- reject_swap -----


def test_reject_swap_flips_status_and_notifies_requester(
    db_session: Session,
) -> None:
    bridge, _priya = _aarav_bridge_and_priya(db_session)
    requester = _healthy_requester(bridge)
    target = next(
        m.donor
        for m in bridge.memberships
        if getattr(m.status, "value", str(m.status)) == "active"
        and m.donor.id != requester.id
        and m.donor.name != "Priya Sharma"
    )
    target.name = "RejectTargetUnique Roy"
    db_session.commit()

    out = swap_engine.initiate_swap(
        db_session,
        from_donor=requester,
        bridge=bridge,
        name_fragment="rejecttargetunique",
        to_slot_date=date.today() + timedelta(days=20),
    )
    swap = out.swap
    swap_engine.reject_swap(db_session, swap=swap)
    db_session.commit()

    refreshed = db_session.get(SlotSwapRequest, swap.id)
    assert getattr(refreshed.status, "value", str(refreshed.status)) == "rejected"
    assert refreshed.rejected_at is not None

    rejected_to_a = (
        db_session.query(WhatsAppMessage)
        .filter(
            WhatsAppMessage.donor_id == requester.id,
            WhatsAppMessage.template_key == "swap_rejected_to_requester",
        )
        .one()
    )
    assert target.name in rejected_to_a.body


# ----- expiry sweep -----


def test_expire_stale_swaps_flips_old_proposed(db_session: Session) -> None:
    bridge, priya = _aarav_bridge_and_priya(db_session)
    target = next(
        m.donor for m in bridge.memberships
        if getattr(m.status, "value", str(m.status)) == "active"
        and m.donor.id != priya.id
    )
    old_swap = SlotSwapRequest(
        bridge_id=bridge.id,
        from_donor_id=priya.id,
        to_donor_id=target.id,
        from_slot_date=date.today() + timedelta(days=10),
        to_slot_date=date.today() + timedelta(days=15),
        status=SwapStatus.PROPOSED,
        expires_at=datetime.utcnow() - timedelta(hours=1),  # already expired
    )
    fresh_swap = SlotSwapRequest(
        bridge_id=bridge.id,
        from_donor_id=priya.id,
        to_donor_id=target.id,
        from_slot_date=date.today() + timedelta(days=20),
        to_slot_date=date.today() + timedelta(days=25),
        status=SwapStatus.PROPOSED,
        expires_at=datetime.utcnow() + timedelta(hours=12),  # still fresh
    )
    db_session.add_all([old_swap, fresh_swap])
    db_session.commit()

    count = swap_engine.expire_stale_swaps(db_session, bridge_id=bridge.id)
    db_session.commit()
    assert count == 1
    db_session.refresh(old_swap)
    db_session.refresh(fresh_swap)
    assert getattr(old_swap.status, "value", str(old_swap.status)) == "expired"
    assert getattr(fresh_swap.status, "value", str(fresh_swap.status)) == "proposed"


# ----- /whatsapp/webhook integration: full A->propose, B->YES -----


def test_webhook_full_swap_flow(client: TestClient, db_session: Session) -> None:
    bridge, _priya = _aarav_bridge_and_priya(db_session)
    requester = _healthy_requester(bridge)
    target = next(
        m.donor
        for m in bridge.memberships
        if getattr(m.status, "value", str(m.status)) == "active"
        and m.donor.id != requester.id
        and m.donor.name != "Priya Sharma"
    )
    target.name = "ZoltanUniqueName Patel"
    db_session.commit()

    target_date = date.today() + timedelta(days=30)
    client.post(
        "/whatsapp/webhook",
        data={
            "From": f"whatsapp:{requester.phone}",
            "To": twilio_client.whatsapp_from(),
            "Body": f"swap with zoltanuniquename on {target_date.isoformat()}",
            "MessageSid": "SM_g6_initiate",
        },
    )
    db_session.expire_all()

    swap = (
        db_session.query(SlotSwapRequest)
        .filter(SlotSwapRequest.from_donor_id == requester.id)
        .one()
    )
    assert getattr(swap.status, "value", str(swap.status)) == "proposed"

    client.post(
        "/whatsapp/webhook",
        data={
            "From": f"whatsapp:{target.phone}",
            "To": twilio_client.whatsapp_from(),
            "Body": "YES",
            "MessageSid": "SM_g6_accept",
        },
    )
    db_session.expire_all()
    db_session.refresh(swap)
    assert getattr(swap.status, "value", str(swap.status)) == "accepted"


def test_webhook_swap_NO_rejects(client: TestClient, db_session: Session) -> None:
    bridge, _priya = _aarav_bridge_and_priya(db_session)
    requester = _healthy_requester(bridge)
    target = next(
        m.donor
        for m in bridge.memberships
        if getattr(m.status, "value", str(m.status)) == "active"
        and m.donor.id != requester.id
        and m.donor.name != "Priya Sharma"
    )
    target.name = "AnotherUniqueName Iyer"
    db_session.commit()

    target_date = date.today() + timedelta(days=30)
    client.post(
        "/whatsapp/webhook",
        data={
            "From": f"whatsapp:{requester.phone}",
            "To": twilio_client.whatsapp_from(),
            "Body": f"swap anotheruniquename {target_date.isoformat()}",
            "MessageSid": "SM_g6_init_no",
        },
    )
    client.post(
        "/whatsapp/webhook",
        data={
            "From": f"whatsapp:{target.phone}",
            "To": twilio_client.whatsapp_from(),
            "Body": "NO",
            "MessageSid": "SM_g6_target_no",
        },
    )
    db_session.expire_all()
    swap = (
        db_session.query(SlotSwapRequest)
        .filter(SlotSwapRequest.from_donor_id == requester.id)
        .one()
    )
    assert getattr(swap.status, "value", str(swap.status)) == "rejected"


# ----- /bridges/{id}/swap-requests endpoint -----


def test_swap_requests_endpoint_lists_rows(
    client: TestClient, db_session: Session
) -> None:
    bridge, _priya = _aarav_bridge_and_priya(db_session)
    requester = _healthy_requester(bridge)
    target = next(
        m.donor
        for m in bridge.memberships
        if getattr(m.status, "value", str(m.status)) == "active"
        and m.donor.id != requester.id
        and m.donor.name != "Priya Sharma"
    )
    target.name = "ListEndpointUnique Bose"
    db_session.commit()
    swap_engine.initiate_swap(
        db_session,
        from_donor=requester,
        bridge=bridge,
        name_fragment="listendpointunique",
        to_slot_date=date.today() + timedelta(days=20),
    )
    db_session.commit()

    body = client.get(f"/bridges/{bridge.id}/swap-requests").json()
    assert len(body["swaps"]) >= 1
    row = body["swaps"][0]
    assert row["from_donor_name"] == requester.name
    assert row["status"] == "proposed"
    assert row["from_slot_date"]
    assert row["to_slot_date"]


def test_swap_requests_endpoint_404_for_unknown_bridge(client: TestClient) -> None:
    resp = client.get(f"/bridges/{uuid.uuid4()}/swap-requests")
    assert resp.status_code == 404
