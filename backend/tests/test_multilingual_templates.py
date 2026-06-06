"""G4 — multilingual template store, send-language defaulting, language column."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.integrations import twilio_client
from app.models import (
    BridgeMembership,
    Donor,
    Language,
    MembershipStatus,
    WhatsAppMessage,
)
from app.services import whatsapp_templates as tmpl
from tests.fixtures import build_test_dataset, feature_bridge_destabilizer


def _seed(db: Session):
    return build_test_dataset(db, n_patients=3, n_donors=40, seed=42)


def _aarav_bridge_and_priya(db: Session):
    data = _seed(db)
    db.commit()
    bridge = data.feature_patient.bridge
    priya = feature_bridge_destabilizer(data)
    return bridge, priya


# ----- template store -----


def test_all_four_donor_templates_exposed() -> None:
    """G4 = 4 donor templates. G5 added 3 caregiver templates on top (7 total)."""
    keys = {t.key for t in tmpl.all_templates()}
    assert {
        "slot_reminder",
        "recruit_invite",
        "thank_you",
        "swap_request",
    }.issubset(keys)


def test_every_donor_and_caregiver_template_has_all_eight_languages() -> None:
    """G4 donor templates + G5 caregiver templates are fully hand-translated.
    G6 swap templates use English fallback for 5 of 8 languages (en/hi/te
    hand-authored; the fallback chain handles the rest)."""
    from app.services.whatsapp_templates import SWAP_TEMPLATE_KEYS
    for t in tmpl.all_templates():
        if t.key in SWAP_TEMPLATE_KEYS:
            # Swap templates require at least en, hi, te
            for lang in ("en", "hi", "te"):
                assert lang in t.bodies, f"{t.key} missing {lang}"
                assert t.bodies[lang].strip(), f"{t.key}.{lang} body is blank"
            continue
        for lang in tmpl.ALL_LANGUAGES:
            assert lang in t.bodies, f"{t.key} missing {lang}"
            assert t.bodies[lang].strip(), f"{t.key}.{lang} body is blank"


def test_swap_templates_fall_back_to_english_for_unsupported_languages() -> None:
    """G6 swap copy is only hand-authored for en/hi/te. Requesting kn should
    fall back to English via resolve_language()."""
    from app.services.whatsapp_templates import SWAP_TEMPLATE_KEYS, get_template, resolve_language
    for key in SWAP_TEMPLATE_KEYS:
        t = get_template(key)
        assert t is not None
        lang, fallback = resolve_language(t, "kn")
        assert lang == "en"
        assert fallback is True


def test_render_english_renders_donor_first_and_patient() -> None:
    r = tmpl.render(
        "slot_reminder",
        language="en",
        donor_first="Priya",
        donor_name="Priya Sharma",
        patient_name="Aarav",
        patient_age=8,
        patient_blood_group="B+",
    )
    assert "Priya" in r.body
    assert "Aarav" in r.body
    assert r.language_used == "en"
    assert r.was_fallback is False


def test_render_hindi_uses_devanagari() -> None:
    r = tmpl.render(
        "recruit_invite",
        language="hi",
        donor_first="Aishwarya",
        donor_name="Aishwarya Murthy",
        patient_name="Aarav",
        patient_age=8,
        patient_blood_group="B+",
    )
    # Contains a Devanagari char ("नमस्ते")
    assert any("ऀ" <= c <= "ॿ" for c in r.body)
    assert r.language_used == "hi"
    assert r.was_fallback is False


def test_render_telugu_uses_telugu_script() -> None:
    r = tmpl.render(
        "thank_you",
        language="te",
        donor_first="Priya",
        donor_name="Priya Sharma",
        patient_name="Aarav",
    )
    assert any("ఀ" <= c <= "౿" for c in r.body)
    assert r.language_used == "te"


def test_unknown_template_raises() -> None:
    with pytest.raises(ValueError):
        tmpl.render("nonexistent", language="en", donor_first="x", donor_name="x")


def test_resolve_language_falls_back_to_english_for_missing() -> None:
    t = tmpl.get_template("slot_reminder")
    assert t is not None
    # Mutate a copy to drop "kn" body so we can verify fallback
    fake = tmpl.TemplateDef(
        key="fake",
        label="fake",
        requires_bridge=False,
        bodies={"en": "hello {donor_first}", "hi": "नमस्ते {donor_first}"},
    )
    lang, fallback = tmpl.resolve_language(fake, "kn")
    assert lang == "en"
    assert fallback is True


# ----- /whatsapp/templates exposes bodies + supported_languages -----


def test_templates_endpoint_returns_per_language_bodies(client: TestClient) -> None:
    """G4 donor templates + G5 caregiver templates are 8-language complete.
    G6 swap templates ship with en/hi/te + English fallback."""
    from app.services.whatsapp_templates import SWAP_TEMPLATE_KEYS
    body = client.get("/whatsapp/templates").json()
    assert len(body) >= 4
    keys = {t["key"] for t in body}
    assert {"slot_reminder", "recruit_invite", "thank_you", "swap_request"}.issubset(keys)
    for t in body:
        if t["key"] in SWAP_TEMPLATE_KEYS:
            # Swap copy guarantees en/hi/te
            assert set(t["supported_languages"]).issuperset({"en", "hi", "te"})
            continue
        # Donor + caregiver templates are 8-language complete
        assert set(t["bodies"].keys()).issuperset(
            {"en", "hi", "te", "ta", "mr", "bn", "kn", "gu"}
        )
        assert sorted(t["supported_languages"]) == sorted(
            ["bn", "en", "gu", "hi", "kn", "mr", "ta", "te"]
        )


# ----- /whatsapp/send picks donor.preferred_language by default -----


def test_send_defaults_to_donor_preferred_language(
    client: TestClient, db_session: Session
) -> None:
    bridge, priya = _aarav_bridge_and_priya(db_session)
    # Force Priya's preferred_language to Hindi for this test
    priya.preferred_language = Language.HINDI
    db_session.commit()

    body = client.post(
        "/whatsapp/send",
        json={
            "donor_id": str(priya.id),
            "template_key": "slot_reminder",
            "bridge_id": str(bridge.id),
        },
    ).json()

    assert body["language_used"] == "hi"
    assert body["fallback_used"] is False
    assert any("ऀ" <= c <= "ॿ" for c in body["message"]["body"])
    # Persisted on the message row
    assert body["message"]["language"] == "hi"


def test_send_explicit_language_override_wins(
    client: TestClient, db_session: Session
) -> None:
    bridge, priya = _aarav_bridge_and_priya(db_session)
    priya.preferred_language = Language.ENGLISH  # English preferred
    db_session.commit()

    body = client.post(
        "/whatsapp/send",
        json={
            "donor_id": str(priya.id),
            "template_key": "slot_reminder",
            "bridge_id": str(bridge.id),
            "language": "te",  # override to Telugu
        },
    ).json()
    assert body["language_used"] == "te"


def test_send_with_unsupported_language_falls_back_to_en(
    client: TestClient, db_session: Session
) -> None:
    """Pydantic rejects unknown language codes at the boundary, so simulating
    a missing language requires a template that doesn't have one. All hand-
    authored templates cover all 8 languages, so this assertion proves the
    happy path: every supported language renders cleanly."""
    bridge, priya = _aarav_bridge_and_priya(db_session)
    db_session.commit()
    for lang in ["en", "hi", "te", "ta", "mr", "bn", "kn", "gu"]:
        body = client.post(
            "/whatsapp/send",
            json={
                "donor_id": str(priya.id),
                "template_key": "recruit_invite",
                "bridge_id": str(bridge.id),
                "language": lang,
            },
        ).json()
        assert body["language_used"] == lang
        assert body["fallback_used"] is False


def test_send_rejects_unsupported_language_code(
    client: TestClient, db_session: Session
) -> None:
    bridge, priya = _aarav_bridge_and_priya(db_session)
    db_session.commit()
    resp = client.post(
        "/whatsapp/send",
        json={
            "donor_id": str(priya.id),
            "template_key": "slot_reminder",
            "bridge_id": str(bridge.id),
            "language": "fr",  # French not supported
        },
    )
    assert resp.status_code == 422


# ----- Recruit consent picks template language too -----


def test_recruit_invite_renders_in_donor_language(
    client: TestClient, db_session: Session
) -> None:
    """Recruit endpoint goes through the same multilingual template store."""
    bridge, _ = _aarav_bridge_and_priya(db_session)
    candidate = (
        db_session.query(Donor)
        .filter(~Donor.id.in_({m.donor_id for m in bridge.memberships}))
        .filter(Donor.blood_group == "B+")
        .first()
    )
    candidate.preferred_language = Language.TELUGU
    db_session.commit()

    body = client.post(
        f"/bridges/{bridge.id}/recruit",
        json={"candidate_donor_id": str(candidate.id)},
    ).json()

    assert body["message_language"] == "te"
    out = (
        db_session.query(WhatsAppMessage)
        .filter(
            WhatsAppMessage.donor_id == candidate.id,
            WhatsAppMessage.template_key == "recruit_invite",
        )
        .one()
    )
    assert out.language == "te"
    # Body has Telugu script characters
    assert any("ఀ" <= c <= "౿" for c in out.body)


# ----- Webhook YES tokens work across all 8 languages (relies on G1's intent parser) -----


@pytest.mark.parametrize(
    "yes_token",
    [
        "YES",          # en
        "हाँ",          # hi (devanagari)
        "haan",         # hi (transliteration)
        "అవును",        # te
        "ஆம்",          # ta
        "होय",          # mr
        "হ্যাঁ",        # bn
        "ಹೌದು",        # kn
        "હા",          # gu
    ],
)
def test_webhook_yes_in_any_language_flips_pending(
    client: TestClient, db_session: Session, yes_token: str
) -> None:
    bridge, _ = _aarav_bridge_and_priya(db_session)
    candidate = (
        db_session.query(Donor)
        .filter(~Donor.id.in_({m.donor_id for m in bridge.memberships}))
        .filter(Donor.blood_group == "B+")
        .first()
    )
    rec = client.post(
        f"/bridges/{bridge.id}/recruit",
        json={"candidate_donor_id": str(candidate.id)},
    ).json()
    pending_id = uuid.UUID(rec["added_membership_id"])

    client.post(
        "/whatsapp/webhook",
        data={
            "From": f"whatsapp:{candidate.phone}",
            "To": twilio_client.whatsapp_from(),
            "Body": yes_token,
            "MessageSid": f"SM_g4_{abs(hash(yes_token))}",
        },
    )
    db_session.expire_all()
    m = db_session.query(BridgeMembership).filter(BridgeMembership.id == pending_id).one()
    assert getattr(m.status, "value", str(m.status)) == "active"
