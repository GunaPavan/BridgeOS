"""Full CRUD + analytics tests for /reply-classifications/*."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import (
    BloodGroup,
    Donor,
    ReplyClassification,
    ReplyIntent,
)


def _make_donor(db: Session, suffix: str = "x") -> Donor:
    d = Donor(
        name=f"Donor {suffix}",
        age=29,
        blood_group=BloodGroup.O_POS,
        rh_negative=False,
        kell_negative=False,
        phone=f"+91999900040{suffix[0]}",
        city="Hyderabad",
        state="Telangana",
        lat=17.40,
        lng=78.46,
        is_active=True,
        response_rate=0.6,
        registered_at=datetime(2025, 1, 1),
    )
    db.add(d)
    db.flush()
    return d


def _seed(
    db: Session,
    *,
    donor_id,
    intent: ReplyIntent,
    confidence: float = 0.9,
    text: str = "yes",
    classified_at: datetime | None = None,
    extracted_reason: str | None = None,
    used_fallback: bool = False,
) -> ReplyClassification:
    row = ReplyClassification(
        donor_id=donor_id,
        text_excerpt=text,
        intent=intent,
        confidence=confidence,
        extracted_reason=extracted_reason,
        used_fallback=used_fallback,
        model_used="claude-haiku",
        classified_at=classified_at or datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    return row


# ---------------------------------------------------------------------------
# List + filters + pagination
# ---------------------------------------------------------------------------


def test_list_empty(client: TestClient) -> None:
    r = client.get("/reply-classifications")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0
    assert body["items"] == []


def test_list_returns_rows_newest_first(
    client: TestClient, db_session: Session
) -> None:
    d = _make_donor(db_session)
    now = datetime.utcnow()
    _seed(db_session, donor_id=d.id, intent=ReplyIntent.ACCEPT,
          classified_at=now - timedelta(hours=2))
    _seed(db_session, donor_id=d.id, intent=ReplyIntent.OUT_OF_TOWN,
          classified_at=now - timedelta(hours=1))
    _seed(db_session, donor_id=d.id, intent=ReplyIntent.STOP,
          classified_at=now)

    r = client.get("/reply-classifications")
    body = r.json()
    assert body["total"] == 3
    intents = [i["intent"] for i in body["items"]]
    assert intents == ["stop", "out_of_town", "accept"]


def test_filter_by_donor_and_intent(
    client: TestClient, db_session: Session
) -> None:
    d1 = _make_donor(db_session, "1")
    d2 = _make_donor(db_session, "2")
    _seed(db_session, donor_id=d1.id, intent=ReplyIntent.ACCEPT)
    _seed(db_session, donor_id=d1.id, intent=ReplyIntent.STOP)
    _seed(db_session, donor_id=d2.id, intent=ReplyIntent.ACCEPT)

    r = client.get(f"/reply-classifications?donor_id={d1.id}")
    assert r.json()["total"] == 2

    r = client.get(f"/reply-classifications?intent=stop")
    assert r.json()["total"] == 1


def test_filter_by_confidence_threshold(
    client: TestClient, db_session: Session
) -> None:
    d = _make_donor(db_session)
    _seed(db_session, donor_id=d.id, intent=ReplyIntent.ACCEPT, confidence=0.95)
    _seed(db_session, donor_id=d.id, intent=ReplyIntent.UNKNOWN, confidence=0.40)

    r = client.get("/reply-classifications?confidence_gte=0.8")
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["intent"] == "accept"


def test_pagination(client: TestClient, db_session: Session) -> None:
    d = _make_donor(db_session)
    for _ in range(5):
        _seed(db_session, donor_id=d.id, intent=ReplyIntent.ACCEPT)
    r = client.get("/reply-classifications?limit=2&offset=0")
    body = r.json()
    assert len(body["items"]) == 2
    assert body["total"] == 5


# ---------------------------------------------------------------------------
# Single GET
# ---------------------------------------------------------------------------


def test_get_single(client: TestClient, db_session: Session) -> None:
    d = _make_donor(db_session)
    row = _seed(db_session, donor_id=d.id, intent=ReplyIntent.ACCEPT)
    r = client.get(f"/reply-classifications/{row.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == str(row.id)


def test_get_404_for_missing(client: TestClient) -> None:
    import uuid as _u
    r = client.get(f"/reply-classifications/{_u.uuid4()}")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# By-donor
# ---------------------------------------------------------------------------


def test_by_donor_endpoint(client: TestClient, db_session: Session) -> None:
    d = _make_donor(db_session)
    other = _make_donor(db_session, "o")
    _seed(db_session, donor_id=d.id, intent=ReplyIntent.ACCEPT)
    _seed(db_session, donor_id=other.id, intent=ReplyIntent.ACCEPT)
    r = client.get(f"/reply-classifications/by-donor/{d.id}")
    assert r.status_code == 200
    assert r.json()["total"] == 1


# ---------------------------------------------------------------------------
# Distribution analytics
# ---------------------------------------------------------------------------


def test_distribution_aggregates_correctly(
    client: TestClient, db_session: Session
) -> None:
    d = _make_donor(db_session)
    _seed(db_session, donor_id=d.id, intent=ReplyIntent.ACCEPT, confidence=0.9)
    _seed(db_session, donor_id=d.id, intent=ReplyIntent.STOP, confidence=0.95)
    _seed(
        db_session,
        donor_id=d.id,
        intent=ReplyIntent.RESCHEDULE_REQUEST,
        confidence=0.8,
        extracted_reason="school exam",
        used_fallback=True,
    )

    r = client.get("/reply-classifications/distribution?window_days=30")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    counts = {c["intent"]: c["count"] for c in body["counts"]}
    assert counts["accept"] == 1
    assert counts["stop"] == 1
    assert counts["reschedule_request"] == 1
    assert "school exam" in body["top_reschedule_reasons"]
    assert 0 <= body["avg_confidence"] <= 1
    assert 0 <= body["fallback_rate"] <= 1


def test_confidence_histogram(client: TestClient, db_session: Session) -> None:
    d = _make_donor(db_session)
    _seed(db_session, donor_id=d.id, intent=ReplyIntent.ACCEPT, confidence=0.95)
    _seed(db_session, donor_id=d.id, intent=ReplyIntent.STOP, confidence=0.10)
    r = client.get("/reply-classifications/confidence-histogram?window_days=30")
    assert r.status_code == 200
    buckets = r.json()
    assert len(buckets) == 10
    assert buckets[9]["count"] == 1
    assert buckets[1]["count"] == 1


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------


def test_feedback_correction(client: TestClient, db_session: Session) -> None:
    d = _make_donor(db_session)
    row = _seed(db_session, donor_id=d.id, intent=ReplyIntent.OUT_OF_TOWN, confidence=0.75)
    r = client.post(
        f"/reply-classifications/{row.id}/feedback",
        json={"corrected_intent": "decline", "note": "donor was lying"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["operator_corrected_intent"] == "decline"
    assert body["operator_feedback_note"] == "donor was lying"
    assert body["feedback_at"] is not None


def test_feedback_clear(client: TestClient, db_session: Session) -> None:
    d = _make_donor(db_session)
    row = _seed(db_session, donor_id=d.id, intent=ReplyIntent.OUT_OF_TOWN, confidence=0.75)
    row.operator_corrected_intent = ReplyIntent.DECLINE
    db_session.commit()
    r = client.post(
        f"/reply-classifications/{row.id}/feedback",
        json={"corrected_intent": None, "note": None},
    )
    assert r.status_code == 200
    assert r.json()["operator_corrected_intent"] is None


# ---------------------------------------------------------------------------
# Soft delete
# ---------------------------------------------------------------------------


def test_soft_delete_hides_from_list(client: TestClient, db_session: Session) -> None:
    d = _make_donor(db_session)
    row = _seed(db_session, donor_id=d.id, intent=ReplyIntent.ACCEPT)
    r = client.delete(f"/reply-classifications/{row.id}")
    assert r.status_code == 200
    assert client.get("/reply-classifications").json()["total"] == 0
    # include_deleted=true brings it back
    r = client.get("/reply-classifications?include_deleted=true")
    assert r.json()["total"] == 1
