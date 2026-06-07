"""Bedrock-generated outreach copy for the one-click demo fan-out.

The /admin/demo/fire-all endpoint composes ONE master outreach in a single
Bedrock call and reuses the result across all four channels (voice question,
WhatsApp body, SMS body, email subject + body). That way:

- Judges cross-checking the phone, SMS inbox and email see consistent wording
  rather than four near-identical template re-renderings.
- We pay for one LLM call per click, not four.
- Voice's TwiML handler can read the generated question from this module's
  in-memory cache (keyed by ping_id) so the TwiML Twilio fetches matches the
  copy we already sent over WA/SMS/email.

When Bedrock is unreachable / errors / times out we silently fall back to a
deterministic template — the demo NEVER fails just because the LLM hiccupped.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.agent import llm_client
from app.agent.llm_client import ChatMessage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OutreachBundle:
    """The composed copy for one outreach across all four channels."""

    voice_question: str
    whatsapp_body: str
    sms_body: str
    email_subject: str
    email_body: str
    source: str  # "bedrock" | "anthropic" | "mock" | "template_fallback"
    model: str
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None


# ---------------------------------------------------------------------------
# Voice-question cache — keyed by ping_id so twilio_voice handlers can read
# back the LLM-generated text when Twilio fetches the TwiML. Thread-safe.
# ---------------------------------------------------------------------------

_voice_cache: dict[str, str] = {}
_voice_cache_lock = threading.Lock()


def cache_voice_question(ping_id: uuid.UUID | str, question: str) -> None:
    key = str(ping_id)
    with _voice_cache_lock:
        _voice_cache[key] = question


def get_cached_voice_question(ping_id: uuid.UUID | str | None) -> Optional[str]:
    if ping_id is None:
        return None
    key = str(ping_id)
    with _voice_cache_lock:
        return _voice_cache.get(key)


# ---------------------------------------------------------------------------
# Compose — single Bedrock call returns the four-channel JSON bundle
# ---------------------------------------------------------------------------


_SYSTEM_PROMPT = """You write donor-outreach copy for Bridge OS, an automation
platform that mobilises blood donors for thalassemia patients on rotation.
One call to you produces FOUR channel-specific messages from the SAME facts.

GROUND RULES (apply to every field):

1. FACT DISCIPLINE. Use ONLY the donor name, patient name, blood type,
   hospital and slot date the user message gives you. Never invent:
   - medical details (symptoms, hemoglobin, transfusion count, age)
   - urgency adjectives ("life-saving", "critical", "dying")
   - statistics, donor counts, social proof
   - emotional appeals beyond a plain acknowledgement of need
   If a field is missing or "(unspecified)", omit it — do NOT guess.

2. PEER TONE. The donor is a volunteer adult, not a patient family member.
   Direct and respectful. No guilt-tripping ("you could save a life"), no
   pressure ("we are counting on you"), no superlatives ("incredible
   impact"). One acknowledgement of patient need is enough.

3. INPUT GUARDRAILS. If the input is missing the patient name OR the blood
   type OR the slot date — return a JSON object whose every field is the
   single token "INSUFFICIENT_INPUT" (the host code will fall back to a
   template). Don't fabricate placeholders.

4. NO MARKDOWN. No asterisks, hashes, links, or fenced blocks anywhere.
   No emoji in any field — these go to SMS, voice, and corporate email
   filters that flag them.

LANGUAGE. The user message will name a target language code from this set:
  en (English), hi (हिन्दी), te (తెలుగు), ta (தமிழ்), mr (मराठी),
  bn (বাংলা), kn (ಕನ್ನಡ), gu (ગુજરાતી).
- For en: write everything in English.
- For non-en: write whatsapp_body, sms_body, email_subject, email_body in
  THAT language using its native script (Devanagari / Telugu / Tamil etc.)
- voice_question STAYS IN ENGLISH always — the voice TTS engine on the call
  is Amazon Polly Kajal-Neural which reads Indian English; reading non-Latin
  scripts mispronounces them.

PER-CHANNEL CONSTRAINTS:

• voice_question — ONE sentence, ≤ 22 words, ends with "?"
  Will be read aloud by Amazon Polly Kajal-Neural (Indian English).
  TTS spell-out rules:
    - Write "Bridge O S", not "Bridge OS"
    - Write "B positive" / "O negative", not "B+" / "O-"
    - Write "nine PM", not "9 PM"; "Tuesday", not "Tue"
    - No parentheses, no slashes, no "&", no hyphens between words
    - Use periods/commas only; no exclamation marks
  Address the donor by first name once. End with the ask, not the thanks.

• whatsapp_body — 1-2 short sentences. Includes blood type, patient first
  name, hospital (if known), slot date. End with the literal string
  "Reply YES / NO / MAYBE" (translated to the target language for non-en —
  e.g. Hindi "जवाब दें: हाँ / नहीं / शायद").
  Total: ≤ 320 chars for ASCII; ≤ 220 chars for Unicode scripts.

• sms_body — ONE sentence, no greeting. **SMS is outbound-only over AWS
  SNS** — the donor cannot reply via SMS, so NEVER ask for one ("Reply Y
  / N", "Text back YES" etc. are forbidden). Treat it as a one-way alert
  that funnels confirmation to a two-way channel.
  Must fit one SMS segment:
    - ASCII English: ≤ 145 chars
    - Devanagari / Telugu / Tamil / Bengali / Kannada / Gujarati: ≤ 60 chars
      (Unicode SMS segments are only 70 chars and we leave headroom)
  Include the three key facts (blood, patient first name, slot date) only
  if they fit; drop hospital first if tight.
  End with "Confirm on WhatsApp" (or its localised equivalent for non-en —
  Hindi "WhatsApp पर पुष्टि करें", Telugu "WhatsAppలో నిర్ధారించండి", etc.).

• email_subject — ≤ 60 chars. Must contain the blood type AND the
  patient's first name. No emoji, no clickbait ("URGENT!!!", "OPEN NOW").
  Translate the subject for non-en.

• email_body — 3 short paragraphs separated by blank lines, plain text:
    Para 1: One-line ask, addressing the donor by first name.
    Para 2: Patient context — hospital (if known) + slot date.
    Para 3: Single closing line ending with "— Bridge OS"
      (or for non-en, the localised equivalent ending with "— Bridge OS").
  No signature block, no unsubscribe footer, no PS, no quotes.

OUTPUT FORMAT — return raw JSON with EXACTLY these five string keys,
nothing else. No prose before or after. No code fences. Example shape
(values illustrative; do not copy this wording verbatim):

{"voice_question":"Hi Asha, can you donate O positive blood for Ravi at City Hospital on Tuesday?","whatsapp_body":"Hi Asha, we need an O+ donor for Ravi at City Hospital on Tue 09 June. Reply YES / NO / MAYBE","sms_body":"Asha, O+ needed for Ravi on Tue 09 June, City Hospital. Confirm on WhatsApp","email_subject":"O+ donor needed for Ravi - Tue 09 June","email_body":"Hi Asha,\\n\\nWe have a wave open for Ravi who needs O positive blood.\\n\\nSlot is at City Hospital on Tuesday 09 June.\\n\\nReply YES, NO, or MAYBE — Bridge OS"}"""


_VALID_LANGS = {"en", "hi", "te", "ta", "mr", "bn", "kn", "gu"}


def _user_prompt(
    *,
    donor_name: str,
    patient_name: str,
    blood_type: str,
    hospital: str,
    slot_str: str,
    language: str,
) -> str:
    lang = (language or "en").lower().strip()
    if lang not in _VALID_LANGS:
        lang = "en"
    donor_first = donor_name.split()[0] if donor_name else ""
    patient_first = patient_name.split()[0] if patient_name else ""
    return (
        "Compose the four-channel outreach for this donor.\n\n"
        f"target_language: {lang}\n"
        f"donor_first_name: {donor_first or '(missing)'}\n"
        f"patient_full_name: {patient_name or '(missing)'}\n"
        f"patient_first_name: {patient_first or '(missing)'}\n"
        f"blood_type: {blood_type or '(missing)'}\n"
        f"hospital: {hospital or '(unspecified)'}\n"
        f"slot_date: {slot_str or '(missing)'}\n\n"
        "Return the JSON object now. No prose, no code fences."
    )


def _template_fallback(
    *,
    donor_name: str,
    patient_name: str,
    blood_type: str,
    hospital: str,
    slot_str: str,
) -> OutreachBundle:
    """Deterministic fallback if Bedrock errors out — same wording the
    pre-LLM demo used so the surface stays identical to judges."""
    pf = patient_name.split()[0] if patient_name else "the patient"
    voice_blood = blood_type.replace("+", " positive").replace("-", " negative")
    voice_q = (
        f"Hello, this is Bridge O S calling on behalf of Blood Warriors. "
        f"We have an urgent requirement for blood type {voice_blood} at "
        f"{hospital} on {slot_str}, for a child named {patient_name}. "
        f"Are you available to donate?"
    )
    short = (
        f"Bridge OS automation: {blood_type} donor needed for {pf} at "
        f"{hospital} on {slot_str}. Reply YES / NO / MAYBE."
    )
    sms = f"Bridge OS: {blood_type} needed for {pf}, {slot_str}, {hospital}. Reply Y / N"
    subject = f"Urgent: {blood_type} donor needed for {pf}"
    body = (
        f"Hello {donor_name.split()[0] if donor_name else 'there'},\n\n"
        f"We have an urgent need for a {blood_type} blood donation for "
        f"{patient_name}.\n\n"
        f"Hospital: {hospital}. Slot: {slot_str}.\n\n"
        f"Reply YES, NO, or MAYBE — Bridge OS"
    )
    return OutreachBundle(
        voice_question=voice_q,
        whatsapp_body=short,
        sms_body=sms,
        email_subject=subject,
        email_body=body,
        source="template_fallback",
        model="bridge-os-template-v1",
    )


_JSON_KEYS = ("voice_question", "whatsapp_body", "sms_body", "email_subject", "email_body")


def _parse_bundle(raw: str) -> Optional[dict[str, str]]:
    """Pull the JSON object out of the model output. Tolerates a code-fence
    wrapper and trailing commentary — both happen even when we ask the model
    not to do them."""
    if not raw:
        return None
    # Strip ```json fences if the model couldn't help itself.
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    # Grab the outermost {...} block — survives leading/trailing prose.
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if match is None:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    out: dict[str, str] = {}
    for k in _JSON_KEYS:
        v = parsed.get(k)
        if not isinstance(v, str) or not v.strip():
            return None
        out[k] = v.strip()
    return out


def compose_outreach(
    *,
    donor_name: str,
    patient_name: str,
    blood_type: str,
    hospital: str,
    slot_str: str,
    language: str = "en",
) -> OutreachBundle:
    """Compose all four channel messages in ONE Bedrock call. Always returns
    a usable bundle — template fallback on any failure.

    The LLM is told to write voice_question in English regardless (Polly
    Kajal-Neural is Indian English), and to write WA / SMS / email in
    ``language`` (one of en, hi, te, ta, mr, bn, kn, gu)."""
    started = datetime.utcnow()
    fallback_args = dict(
        donor_name=donor_name,
        patient_name=patient_name,
        blood_type=blood_type,
        hospital=hospital,
        slot_str=slot_str,
    )

    # Hard input guardrail mirroring the LLM's own check — keeps the fallback
    # deterministic even when the model is unavailable.
    if not patient_name or not blood_type or not slot_str:
        logger.warning("demo_outreach: insufficient input — using template fallback")
        return _template_fallback(**fallback_args)

    try:
        provider = llm_client.get_active_provider()
        if provider == "mock":
            logger.info("demo_outreach: LLM in mock mode — using template fallback")
            return _template_fallback(**fallback_args)

        resp = llm_client.chat(
            system_prompt=_SYSTEM_PROMPT,
            messages=[
                ChatMessage(
                    role="user",
                    content=_user_prompt(**fallback_args, language=language),
                )
            ],
            max_tokens=900,
            temperature=0.3,
            task="chat",
        )
    except Exception:
        logger.exception("demo_outreach: Bedrock call raised — falling back to template")
        return _template_fallback(**fallback_args)

    parsed = _parse_bundle(resp.text)
    if parsed is None:
        logger.warning(
            "demo_outreach: could not parse %s response; falling back. raw=%r",
            resp.provider, resp.text[:300],
        )
        return _template_fallback(**fallback_args)

    # Honour the LLM's own INSUFFICIENT_INPUT signal — falls back to template.
    if any(v.strip() == "INSUFFICIENT_INPUT" for v in parsed.values()):
        logger.info("demo_outreach: model flagged INSUFFICIENT_INPUT — using template fallback")
        return _template_fallback(**fallback_args)

    elapsed_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
    logger.info(
        "demo_outreach: composed via %s/%s lang=%s in %dms (%s in / %s out tokens)",
        resp.provider, resp.model, language, elapsed_ms, resp.tokens_in, resp.tokens_out,
    )
    return OutreachBundle(
        voice_question=parsed["voice_question"],
        whatsapp_body=parsed["whatsapp_body"],
        sms_body=parsed["sms_body"],
        email_subject=parsed["email_subject"],
        email_body=parsed["email_body"],
        source=resp.provider,
        model=resp.model,
        tokens_in=resp.tokens_in,
        tokens_out=resp.tokens_out,
    )


# ===========================================================================
# Inbound reply composer — Bedrock writes the auto-reply WhatsApp/SMS sees
# when a donor responds to an outreach. Previously every reply path fell
# through to a static "Thanks {donor_first} — got your message" template.
# ===========================================================================


_INBOUND_SYSTEM_PROMPT = """You write SHORT donor-facing WhatsApp / SMS / email
acknowledgements for Bridge OS. The donor has just replied to an outreach.

INPUTS you'll get: the donor's first name, the patient's first name, the
classified intent (one of: ACCEPT / DECLINE / MAYBE / QUESTION / STOP /
UNCLEAR), the donor's actual reply text, an optional next-step hint, and a
target language code (en / hi / te / ta / mr / bn / kn / gu).

GROUND RULES:

1. FACT DISCIPLINE. Never invent slot dates, hospitals, blood units, prior
   donation counts, or coordinator names. If the next-step hint doesn't
   give you a fact, omit it — don't guess.

2. TONE. Peer-to-peer, warm but direct. No "you saved a life", no "we
   urgently need you", no exclamation marks beyond one greeting if any.

3. PER-INTENT SHAPE (each reply ≤ 2 short sentences):
   - ACCEPT  → confirm the donor is on the list; mention the coordinator
     will share exact time + place separately. Don't promise specific times.
   - DECLINE → thank the donor for replying so we can find an alternate.
     No guilt, no second-ask, no "are you sure".
   - MAYBE   → say the slot stays open and you'll follow up closer to the
     date. Don't ask any new questions.
   - QUESTION → acknowledge you'll forward to a coordinator who'll reply
     within a few hours. Don't try to answer medical questions yourself.
   - STOP    → confirm you're cancelling future outreach for this person.
     No "are you sure" — respect the opt-out the first time.
   - UNCLEAR → brief acknowledgement + say a coordinator will follow up.

4. LANGUAGE. For non-en codes, write in the native script (Devanagari /
   Telugu / Tamil etc.). Names and the literal "Bridge OS" stay in Latin.

5. NO MARKDOWN, NO EMOJI, NO LINKS, NO PHONE NUMBERS, NO TIMESTAMPS.

OUTPUT: just the reply text, nothing else — no JSON, no quote marks, no
prefix like "Reply:". A single paragraph. ≤ 220 chars for ASCII, ≤ 160
chars for Unicode scripts. End in a full stop, never a question mark
unless the intent is QUESTION."""


@dataclass(frozen=True)
class InboundReply:
    text: str
    source: str  # "bedrock" | "anthropic" | "mock" | "template_fallback"
    model: str
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None


_INBOUND_INTENT_TEMPLATES: dict[str, str] = {
    # Used only when Bedrock is unreachable or returns garbage. Kept tight
    # so the fallback reads cleanly even though it's not LLM-written.
    "ACCEPT": "Thanks {donor} — confirmed for {patient}. Our coordinator will share the exact time and hospital separately.",
    "DECLINE": "Got it {donor}, thanks for replying — we'll line up an alternate donor for {patient}. You stay on the bridge for future cycles.",
    "MAYBE": "Thanks {donor} — we'll keep the slot open and follow up closer to the date.",
    "QUESTION": "Thanks {donor} — a coordinator will get back to you within a few hours on this.",
    "STOP": "Understood, {donor} — we've stopped future outreach for you. Reply START anytime to resume.",
    "UNCLEAR": "Thanks {donor} — a coordinator will follow up shortly.",
}


def _normalise_intent(raw: str) -> str:
    """Map the various Intent / ReplyIntent enums onto the 6 canonical
    inbound-reply intents the prompt knows about."""
    up = (raw or "").upper()
    if up in {"ACCEPT", "YES", "RESOLVED_ACCEPT"}:
        return "ACCEPT"
    if up in {"DECLINE", "NO", "RESOLVED_DECLINE"}:
        return "DECLINE"
    if up in {"MAYBE", "TENTATIVE"}:
        return "MAYBE"
    if up in {"QUESTION", "UNRELATED_QUESTION"}:
        return "QUESTION"
    if up in {"STOP", "OPT_OUT", "UNSUBSCRIBE"}:
        return "STOP"
    return "UNCLEAR"


def _inbound_template_fallback(*, donor_first: str, patient_first: str, intent: str) -> InboundReply:
    template = _INBOUND_INTENT_TEMPLATES.get(intent, _INBOUND_INTENT_TEMPLATES["UNCLEAR"])
    text = template.format(donor=donor_first or "there", patient=patient_first or "the patient")
    return InboundReply(
        text=text,
        source="template_fallback",
        model="bridge-os-template-v1",
    )


def compose_inbound_reply(
    *,
    donor_name: str,
    patient_name: str,
    intent: str,
    inbound_body: str,
    language: str = "en",
    next_step_hint: Optional[str] = None,
) -> InboundReply:
    """Bedrock-compose the auto-reply to a donor's inbound message.

    Returns InboundReply.text (single short paragraph, target-language).
    Falls back to a deterministic template on any LLM failure so the donor
    never sees a half-broken acknowledgement.
    """
    donor_first = ((donor_name or "").split() or ["there"])[0]
    patient_first = ((patient_name or "").split() or ["the patient"])[0]
    canonical = _normalise_intent(intent)
    lang = (language or "en").lower().strip()
    if lang not in _VALID_LANGS:
        lang = "en"

    try:
        provider = llm_client.get_active_provider()
        if provider == "mock":
            return _inbound_template_fallback(
                donor_first=donor_first, patient_first=patient_first, intent=canonical,
            )
        user_prompt = (
            f"donor_first_name: {donor_first}\n"
            f"patient_first_name: {patient_first}\n"
            f"intent: {canonical}\n"
            f"inbound_message: {(inbound_body or '').strip()[:400]}\n"
            f"next_step_hint: {(next_step_hint or '').strip()[:200] or '(none)'}\n"
            f"target_language: {lang}\n\n"
            "Write the reply now. One paragraph, no quotes, no JSON."
        )
        resp = llm_client.chat(
            system_prompt=_INBOUND_SYSTEM_PROMPT,
            messages=[ChatMessage(role="user", content=user_prompt)],
            max_tokens=200,
            temperature=0.3,
            task="chat",
        )
    except Exception:
        logger.exception("compose_inbound_reply: LLM call raised — using template")
        return _inbound_template_fallback(
            donor_first=donor_first, patient_first=patient_first, intent=canonical,
        )

    text = (resp.text or "").strip()
    # Strip stray quote marks / json braces the model sometimes adds.
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1]
    if text.startswith("{") or len(text) < 8:
        # Model misfired — fall back rather than ship garbage.
        logger.warning(
            "compose_inbound_reply: %s returned unusable text=%r — falling back",
            resp.provider, text[:200],
        )
        return _inbound_template_fallback(
            donor_first=donor_first, patient_first=patient_first, intent=canonical,
        )

    return InboundReply(
        text=text,
        source=resp.provider,
        model=resp.model,
        tokens_in=resp.tokens_in,
        tokens_out=resp.tokens_out,
    )
