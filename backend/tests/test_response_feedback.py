"""G2 — donor response feedback EMA + lazy no-reply decay."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.integrations import twilio_client
from app.models import (
    CohortMemory,
    Donor,
    DonorResponseEvent,
    MessageDirection,
    MessageStatus,
    ResponseEventKind,
    WhatsAppMessage,
)
from app.services.response_feedback import (
    EMA_ALPHA,
    LOW_RESPONSE_THRESHOLD,
    RESPONSE_WINDOW,
    apply_inbound_reply,
    apply_no_reply_decay,
    response_history,
)
from tests.fixtures import build_test_dataset, feature_bridge_destabilizer


def _seed(db: Session):
    return build_test_dataset(db, n_patients=3, n_donors=40, seed=42)


def _aarav_priya(db: Session):
    data = _seed(db)
    db.commit()
    bridge = data.feature_patient.bridge
    priya = feature_bridge_destabilizer(data)
    return bridge, priya


# ----- EMA math -----


def test_inbound_bumps_response_rate_via_ema(db_session: Session) -> None:
    _, priya = _aarav_priya(db_session)
    prior = float(priya.response_rate)
    inbound = WhatsAppMessage(
        donor_id=priya.id,
        bridge_id=None,
        direction=MessageDirection.INBOUND,
        from_number=f"whatsapp:{priya.phone}",
        to_number=twilio_client.whatsapp_from(),
        body="YES",
        status=MessageStatus.RECEIVED,
        created_at=datetime.utcnow(),
    )
    db_session.add(inbound)
    db_session.flush()

    result = apply_inbound_reply(db_session, donor=priya, inbound=inbound)
    db_session.commit()

    expected = (1 - EMA_ALPHA) * prior + EMA_ALPHA * 1.0
    assert abs(result.new_response_rate - expected) < 1e-6
    assert abs(priya.response_rate - expected) < 1e-6
    assert result.prior_response_rate == prior


def test_two_inbounds_bump_twice(db_session: Session) -> None:
    _, priya = _aarav_priya(db_session)
    prior = float(priya.response_rate)
    for _ in range(2):
        inbound = WhatsAppMessage(
            donor_id=priya.id,
            bridge_id=None,
            direction=MessageDirection.INBOUND,
            from_number=f"whatsapp:{priya.phone}",
            to_number=twilio_client.whatsapp_from(),
            body="YES",
            status=MessageStatus.RECEIVED,
            created_at=datetime.utcnow(),
        )
        db_session.add(inbound)
        db_session.flush()
        apply_inbound_reply(db_session, donor=priya, inbound=inbound)
    db_session.commit()

    after_one = (1 - EMA_ALPHA) * prior + EMA_ALPHA * 1.0
    after_two = (1 - EMA_ALPHA) * after_one + EMA_ALPHA * 1.0
    assert abs(priya.response_rate - after_two) < 1e-6


def test_hours_to_response_computed_when_outbound_exists(
    db_session: Session,
) -> None:
    _, priya = _aarav_priya(db_session)
    prior_hours = float(priya.avg_response_hours)
    now = datetime.utcnow()
    outbound_at = now - timedelta(hours=12)

    db_session.add(
        WhatsAppMessage(
            donor_id=priya.id,
            bridge_id=None,
            direction=MessageDirection.OUTBOUND,
            from_number=twilio_client.whatsapp_from(),
            to_number=priya.phone,
            body="Hi Priya, please confirm next slot",
            status=MessageStatus.MOCKED,
            template_key="slot_reminder",
            created_at=outbound_at,
        )
    )
    inbound = WhatsAppMessage(
        donor_id=priya.id,
        bridge_id=None,
        direction=MessageDirection.INBOUND,
        from_number=f"whatsapp:{priya.phone}",
        to_number=twilio_client.whatsapp_from(),
        body="YES",
        status=MessageStatus.RECEIVED,
        created_at=now,
    )
    db_session.add(inbound)
    db_session.flush()
    result = apply_inbound_reply(db_session, donor=priya, inbound=inbound)
    db_session.commit()

    assert abs(result.hours_to_response - 12.0) < 0.01
    expected_avg = (1 - EMA_ALPHA) * prior_hours + EMA_ALPHA * 12.0
    assert abs(priya.avg_response_hours - expected_avg) < 1e-3


def test_inbound_without_recent_outbound_leaves_avg_hours_unchanged(
    db_session: Session,
) -> None:
    _, priya = _aarav_priya(db_session)
    prior_hours = float(priya.avg_response_hours)
    inbound = WhatsAppMessage(
        donor_id=priya.id,
        bridge_id=None,
        direction=MessageDirection.INBOUND,
        from_number=f"whatsapp:{priya.phone}",
        to_number=twilio_client.whatsapp_from(),
        body="YES",
        status=MessageStatus.RECEIVED,
        created_at=datetime.utcnow(),
    )
    db_session.add(inbound)
    db_session.flush()
    result = apply_inbound_reply(db_session, donor=priya, inbound=inbound)
    db_session.commit()
    assert result.hours_to_response is None
    assert abs(priya.avg_response_hours - prior_hours) < 1e-9


# ----- DonorResponseEvent persistence -----


def test_event_row_written_with_prior_and_new(db_session: Session) -> None:
    _, priya = _aarav_priya(db_session)
    inbound = WhatsAppMessage(
        donor_id=priya.id,
        bridge_id=None,
        direction=MessageDirection.INBOUND,
        from_number=f"whatsapp:{priya.phone}",
        to_number=twilio_client.whatsapp_from(),
        body="YES",
        status=MessageStatus.RECEIVED,
        created_at=datetime.utcnow(),
    )
    db_session.add(inbound)
    db_session.flush()
    apply_inbound_reply(db_session, donor=priya, inbound=inbound)
    db_session.commit()

    row = (
        db_session.query(DonorResponseEvent)
        .filter(DonorResponseEvent.donor_id == priya.id)
        .one()
    )
    assert getattr(row.kind, "value", str(row.kind)) == "reply"
    assert row.prior_response_rate < row.new_response_rate


# ----- Lazy no-reply decay -----


def test_no_reply_decay_drops_response_rate_for_aged_outbound(
    db_session: Session,
) -> None:
    _, priya = _aarav_priya(db_session)
    prior = float(priya.response_rate)
    # Aged outbound — older than RESPONSE_WINDOW
    aged = datetime.utcnow() - RESPONSE_WINDOW - timedelta(hours=1)
    db_session.add(
        WhatsAppMessage(
            donor_id=priya.id,
            bridge_id=None,
            direction=MessageDirection.OUTBOUND,
            from_number=twilio_client.whatsapp_from(),
            to_number=priya.phone,
            body="Hi Priya",
            status=MessageStatus.MOCKED,
            template_key="slot_reminder",
            created_at=aged,
        )
    )
    db_session.flush()
    results = apply_no_reply_decay(db_session, donor=priya)
    db_session.commit()

    assert len(results) == 1
    expected = (1 - EMA_ALPHA) * prior + EMA_ALPHA * 0.0
    assert abs(priya.response_rate - expected) < 1e-6


def test_no_reply_decay_skips_recent_outbound(db_session: Session) -> None:
    _, priya = _aarav_priya(db_session)
    prior = float(priya.response_rate)
    # Recent outbound — still inside the window, shouldn't decay yet
    db_session.add(
        WhatsAppMessage(
            donor_id=priya.id,
            bridge_id=None,
            direction=MessageDirection.OUTBOUND,
            from_number=twilio_client.whatsapp_from(),
            to_number=priya.phone,
            body="Hi Priya",
            status=MessageStatus.MOCKED,
            created_at=datetime.utcnow() - timedelta(hours=2),
        )
    )
    db_session.flush()
    results = apply_no_reply_decay(db_session, donor=priya)
    assert results == []
    assert abs(priya.response_rate - prior) < 1e-9


def test_no_reply_decay_skips_already_scored_outbound(db_session: Session) -> None:
    """Idempotent — second call with the same aged outbound is a no-op."""
    _, priya = _aarav_priya(db_session)
    aged = datetime.utcnow() - RESPONSE_WINDOW - timedelta(hours=1)
    db_session.add(
        WhatsAppMessage(
            donor_id=priya.id,
            bridge_id=None,
            direction=MessageDirection.OUTBOUND,
            from_number=twilio_client.whatsapp_from(),
            to_number=priya.phone,
            body="Hi Priya",
            status=MessageStatus.MOCKED,
            template_key="slot_reminder",
            created_at=aged,
        )
    )
    db_session.flush()
    apply_no_reply_decay(db_session, donor=priya)
    db_session.commit()
    again = apply_no_reply_decay(db_session, donor=priya)
    assert again == []


def test_no_reply_decay_crosses_low_threshold_writes_cohort_memory(
    db_session: Session,
) -> None:
    _, priya = _aarav_priya(db_session)
    # Force Priya's rate just above the floor so a single decay crosses below
    priya.response_rate = LOW_RESPONSE_THRESHOLD + 0.02  # 0.52
    aged = datetime.utcnow() - RESPONSE_WINDOW - timedelta(hours=1)
    db_session.add(
        WhatsAppMessage(
            donor_id=priya.id,
            bridge_id=None,
            direction=MessageDirection.OUTBOUND,
            from_number=twilio_client.whatsapp_from(),
            to_number=priya.phone,
            body="Hi Priya",
            status=MessageStatus.MOCKED,
            template_key="slot_reminder",
            created_at=aged,
        )
    )
    db_session.flush()
    results = apply_no_reply_decay(db_session, donor=priya)
    db_session.commit()

    assert results[0].crossed_low_threshold is True
    mem = (
        db_session.query(CohortMemory)
        .filter(CohortMemory.entity_id == priya.id)
        .order_by(CohortMemory.created_at.desc())
        .first()
    )
    assert mem is not None
    # Summary mentions the donor and a response-rate sentence — exact name varies with dataset
    assert priya.name.split()[0] in mem.summary or "Donor" in mem.summary
    assert "response rate" in mem.summary


# ----- response_history -----


def test_response_history_returns_oldest_first(db_session: Session) -> None:
    _, priya = _aarav_priya(db_session)
    base = datetime.utcnow() - timedelta(days=5)
    for i in range(3):
        db_session.add(
            DonorResponseEvent(
                donor_id=priya.id,
                kind=ResponseEventKind.REPLY,
                hours_to_response=None,
                prior_response_rate=0.30 + 0.01 * i,
                new_response_rate=0.31 + 0.01 * i,
                created_at=base + timedelta(hours=i),
            )
        )
    db_session.commit()
    events = response_history(db_session, priya.id, days=30)
    assert len(events) == 3
    assert events[0].new_response_rate < events[-1].new_response_rate


# ----- Webhook integration -----


def test_webhook_yes_persists_a_reply_event(
    client: TestClient, db_session: Session
) -> None:
    _, priya = _aarav_priya(db_session)
    prior = float(priya.response_rate)
    resp = client.post(
        "/whatsapp/webhook",
        data={
            "From": f"whatsapp:{priya.phone}",
            "To": twilio_client.whatsapp_from(),
            "Body": "YES",
            "MessageSid": "SM_g2_yes",
        },
    )
    assert resp.status_code == 200
    db_session.expire_all()
    fresh = db_session.query(Donor).filter(Donor.id == priya.id).one()
    assert fresh.response_rate > prior  # bumped up
    event = (
        db_session.query(DonorResponseEvent)
        .filter(DonorResponseEvent.donor_id == priya.id)
        .one()
    )
    assert getattr(event.kind, "value", str(event.kind)) == "reply"


# ----- Endpoint: /donors/{id}/response-history -----


def test_response_history_endpoint_returns_events(
    client: TestClient, db_session: Session
) -> None:
    _, priya = _aarav_priya(db_session)
    client.post(
        "/whatsapp/webhook",
        data={
            "From": f"whatsapp:{priya.phone}",
            "To": twilio_client.whatsapp_from(),
            "Body": "YES",
            "MessageSid": "SM_g2_hist_1",
        },
    )
    body = client.get(f"/donors/{priya.id}/response-history?days=30").json()
    assert body["donor_id"] == str(priya.id)
    assert body["current_response_rate"] > 0.32  # bumped from prior
    assert len(body["events"]) >= 1
    e = body["events"][0]
    assert e["kind"] == "reply"
    assert "new_response_rate" in e


def test_response_history_endpoint_404_unknown(client: TestClient) -> None:
    resp = client.get(f"/donors/{uuid.uuid4()}/response-history")
    assert resp.status_code == 404


def test_response_history_rejects_non_positive_days(
    client: TestClient, db_session: Session
) -> None:
    """Previously `days=-5` or `days=0` returned 200 with empty events.
    Now rejected by Query(ge=1, le=365) at the param layer."""
    _, priya = _aarav_priya(db_session)
    db_session.commit()
    assert client.get(f"/donors/{priya.id}/response-history?days=0").status_code == 422
    assert client.get(f"/donors/{priya.id}/response-history?days=-5").status_code == 422
    assert client.get(f"/donors/{priya.id}/response-history?days=400").status_code == 422
