"""G3 — auto re-solve schedule on PENDING→ACTIVE flip + history endpoint."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.integrations import twilio_client
from app.models import (
    BridgeMembership,
    Donor,
    MembershipStatus,
    ScheduleResolveLog,
)
from tests.fixtures import build_test_dataset, feature_bridge_destabilizer


def _seed(db: Session):
    return build_test_dataset(db, n_patients=3, n_donors=40, seed=42)


def _aarav_bridge_with_replaceable(db_session: Session):
    data = _seed(db_session)
    db_session.commit()
    bridge = data.feature_patient.bridge
    weak = next(
        m for m in bridge.memberships
        if getattr(m.status, "value", str(m.status)) == "active"
    )
    return bridge, weak


def _outside_compatible_candidate(db_session: Session, bridge) -> Donor:
    patient = bridge.patient
    member_ids = {m.donor_id for m in bridge.memberships}
    bg = getattr(patient.blood_group, "value", str(patient.blood_group))
    return (
        db_session.query(Donor)
        .filter(~Donor.id.in_(member_ids))
        .filter(Donor.blood_group == bg)
        .filter(Donor.is_active.is_(True))
        .first()
    )


# ----- webhook YES triggers auto re-solve + log row -----


def test_webhook_yes_writes_a_schedule_resolve_log(
    client: TestClient, db_session: Session
) -> None:
    bridge, weak = _aarav_bridge_with_replaceable(db_session)
    candidate = _outside_compatible_candidate(db_session, bridge)
    client.post(
        f"/bridges/{bridge.id}/recruit",
        json={
            "candidate_donor_id": str(candidate.id),
            "replace_donor_id": str(weak.donor_id),
        },
    )

    before_logs = db_session.query(ScheduleResolveLog).filter(
        ScheduleResolveLog.bridge_id == bridge.id
    ).count()

    client.post(
        "/whatsapp/webhook",
        data={
            "From": f"whatsapp:{candidate.phone}",
            "To": twilio_client.whatsapp_from(),
            "Body": "YES",
            "MessageSid": "SM_g3_yes",
        },
    )
    db_session.expire_all()

    logs = db_session.query(ScheduleResolveLog).filter(
        ScheduleResolveLog.bridge_id == bridge.id
    ).all()
    assert len(logs) == before_logs + 1

    log = logs[-1]
    assert log.triggered_by == "webhook_yes"
    assert log.after_status in {"OPTIMAL", "FEASIBLE", "INFEASIBLE", "EMPTY"}
    assert log.before_status is not None
    # after_slot_count populated whether or not feasible
    assert log.after_slot_count is not None


def test_webhook_no_does_not_write_resolve_log(
    client: TestClient, db_session: Session
) -> None:
    bridge, _ = _aarav_bridge_with_replaceable(db_session)
    candidate = _outside_compatible_candidate(db_session, bridge)
    client.post(
        f"/bridges/{bridge.id}/recruit",
        json={"candidate_donor_id": str(candidate.id)},
    )
    before = db_session.query(ScheduleResolveLog).filter(
        ScheduleResolveLog.bridge_id == bridge.id
    ).count()

    client.post(
        "/whatsapp/webhook",
        data={
            "From": f"whatsapp:{candidate.phone}",
            "To": twilio_client.whatsapp_from(),
            "Body": "NO",
            "MessageSid": "SM_g3_no",
        },
    )
    after = db_session.query(ScheduleResolveLog).filter(
        ScheduleResolveLog.bridge_id == bridge.id
    ).count()
    assert after == before  # decline = cohort didn't change = no resolve


def test_webhook_unrelated_inbound_does_not_resolve(
    client: TestClient, db_session: Session
) -> None:
    """A donor reply unrelated to any PENDING shouldn't trigger a re-solve."""
    bridge, _ = _aarav_bridge_with_replaceable(db_session)
    member = next(
        db_session.query(Donor).filter(Donor.id == m.donor_id).one()
        for m in bridge.memberships
        if getattr(m.status, "value", str(m.status)) == "active"
    )
    before = db_session.query(ScheduleResolveLog).filter(
        ScheduleResolveLog.bridge_id == bridge.id
    ).count()

    client.post(
        "/whatsapp/webhook",
        data={
            "From": f"whatsapp:{member.phone}",
            "To": twilio_client.whatsapp_from(),
            "Body": "hello, just checking in",
            "MessageSid": "SM_g3_unrelated",
        },
    )
    after = db_session.query(ScheduleResolveLog).filter(
        ScheduleResolveLog.bridge_id == bridge.id
    ).count()
    assert after == before


# ----- /bridges/{id}/schedule-history -----


def test_schedule_history_empty_initially(client: TestClient, db_session: Session) -> None:
    data = _seed(db_session)
    db_session.commit()
    body = client.get(f"/bridges/{data.feature_patient.bridge.id}/schedule-history").json()
    assert body["events"] == []


def test_schedule_history_returns_most_recent_first(
    client: TestClient, db_session: Session
) -> None:
    bridge, weak = _aarav_bridge_with_replaceable(db_session)
    candidate = _outside_compatible_candidate(db_session, bridge)
    client.post(
        f"/bridges/{bridge.id}/recruit",
        json={
            "candidate_donor_id": str(candidate.id),
            "replace_donor_id": str(weak.donor_id),
        },
    )
    client.post(
        "/whatsapp/webhook",
        data={
            "From": f"whatsapp:{candidate.phone}",
            "To": twilio_client.whatsapp_from(),
            "Body": "YES",
            "MessageSid": "SM_g3_hist_yes",
        },
    )

    body = client.get(f"/bridges/{bridge.id}/schedule-history?limit=5").json()
    assert len(body["events"]) == 1
    ev = body["events"][0]
    assert ev["triggered_by"] == "webhook_yes"
    assert ev["after_status"]
    assert ev["before_status"]
    assert "at" in ev


def test_schedule_history_404_unknown_bridge(client: TestClient) -> None:
    resp = client.get(f"/bridges/{uuid.uuid4()}/schedule-history")
    assert resp.status_code == 404
