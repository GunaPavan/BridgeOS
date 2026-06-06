"""Phase B — verify the 3 new follow-up templates render in all 8 languages
with both full and minimal variable sets."""

from __future__ import annotations

import pytest

from app.services import whatsapp_templates as tmpl
from app.services.whatsapp_templates import ALL_LANGUAGES


NEW_KEYS = ("pending_ping_nudge", "pre_donation_reminder", "post_donation_thank_you")


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_new_templates_are_registered() -> None:
    for key in NEW_KEYS:
        t = tmpl.get_template(key)
        assert t is not None, f"Template {key} not registered"
        assert t.requires_bridge


def test_each_template_has_all_8_languages() -> None:
    for key in NEW_KEYS:
        t = tmpl.get_template(key)
        langs = tmpl.supported_languages(t)
        missing = [l for l in ALL_LANGUAGES if l not in langs]
        assert not missing, f"{key} missing languages: {missing}"
        # Every body should reference {donor_first} or {donor_name}
        for lang, body in t.bodies.items():
            assert "{donor_first}" in body or "{donor_name}" in body, (
                f"{key}/{lang} has no donor placeholder"
            )


# ---------------------------------------------------------------------------
# Rendering — full variable set
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("lang", list(ALL_LANGUAGES))
def test_pending_ping_nudge_renders_full(lang: str) -> None:
    r = tmpl.render(
        "pending_ping_nudge",
        language=lang,
        donor_first="Aarav",
        donor_name="Aarav Reddy",
        patient_name="Riya",
        patient_age=12,
        patient_blood_group="B+",
        slot_date="2026-06-08",
    )
    assert r.language_used == lang
    assert "Aarav" in r.body
    assert "Riya" in r.body
    assert "2026-06-08" in r.body


@pytest.mark.parametrize("lang", list(ALL_LANGUAGES))
def test_pre_donation_reminder_renders_with_hospital(lang: str) -> None:
    r = tmpl.render(
        "pre_donation_reminder",
        language=lang,
        donor_first="Priya",
        donor_name="Priya Iyer",
        patient_name="Karthik",
        patient_age=9,
        patient_blood_group="O+",
        slot_date="2026-06-09",
        hospital="Apollo Hospitals",
    )
    assert "Apollo Hospitals" in r.body
    assert "Priya" in r.body
    assert "Karthik" in r.body


@pytest.mark.parametrize("lang", list(ALL_LANGUAGES))
def test_post_donation_thank_you_renders_with_next_eligible(lang: str) -> None:
    r = tmpl.render(
        "post_donation_thank_you",
        language=lang,
        donor_first="Rohan",
        donor_name="Rohan Bhat",
        patient_name="Anaya",
        patient_age=7,
        patient_blood_group="A+",
        next_eligible_date="2026-09-06",
    )
    assert "Rohan" in r.body
    assert "Anaya" in r.body
    assert "2026-09-06" in r.body


# ---------------------------------------------------------------------------
# Rendering — minimal variable set + fallback
# ---------------------------------------------------------------------------


def test_render_falls_back_to_english_for_unknown_lang() -> None:
    r = tmpl.render(
        "pending_ping_nudge",
        language="fr",  # unsupported — should fall back
        donor_first="X",
        donor_name="X Y",
        patient_name="P",
        patient_age=10,
        patient_blood_group="O+",
        slot_date="2026-06-08",
    )
    assert r.was_fallback
    assert r.language_used == "en"


def test_minimal_vars_still_render() -> None:
    """Caller may pass empty strings — the renderer shouldn't choke."""
    r = tmpl.render(
        "post_donation_thank_you",
        language="en",
        donor_first="X",
        donor_name="",
        patient_name="P",
        patient_age=0,
        patient_blood_group="",
        next_eligible_date="",
    )
    assert "X" in r.body
    assert "P" in r.body
