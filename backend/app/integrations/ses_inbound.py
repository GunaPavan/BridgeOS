"""SES inbound email parser + S3 fetch helpers.

ARCHITECTURE
------------
SES receipt rules route incoming mail (to a verified domain) into an S3
bucket. We poll the bucket (or, post-deploy, subscribe to its notification
topic) and parse each raw RFC 822 message into a structured payload that
the same Bedrock classifier we use for WhatsApp can consume.

The classifier output → SNS publish → existing in-process subscribers fan
out → side effects (cancel pending outreach for the patient, etc.). One
classifier, two channels, same loop.

HACKATHON FALLBACK
------------------
We don't have a verified domain yet. Until we do, the ``/emails/inbound-webhook``
endpoint (api/inbound_email.py) accepts a structured JSON payload that
mimics the parser output — letting us demo the loop without SES routing
infrastructure. The same processing code path runs.

When the deployed domain is wired, swap the route source from the webhook
to the S3 poller — zero changes to the classifier / publisher layer.
"""

from __future__ import annotations

import email
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from email.utils import getaddresses, parsedate_to_datetime
from typing import Optional

from app.integrations.aws import (
    aws_available,
    get_boto3_client,
    get_region,
    resource_prefix,
)

logger = logging.getLogger(__name__)


def inbound_bucket_name() -> str:
    """S3 bucket name for storing raw inbound emails."""
    return f"{resource_prefix()}-inbound-emails"


@dataclass(frozen=True)
class ParsedInboundEmail:
    """Structured view of one inbound email.

    The Bedrock classifier reads ``body_text``; the side-effect handlers
    use ``from_email`` to find the matching Patient row (by caregiver_email).
    ``received_at`` and ``message_id`` are for the EmailMessage audit row.
    """

    from_email: str
    to_email: str
    subject: str
    body_text: str
    body_html: Optional[str]
    message_id: str
    received_at: datetime
    in_reply_to: Optional[str] = None
    raw_size_bytes: int = 0


# ---------------------------------------------------------------------------
# MIME parser
# ---------------------------------------------------------------------------


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def parse_raw_email(raw: bytes) -> ParsedInboundEmail:
    """Parse an RFC 822 byte stream into our internal shape.

    Falls back gracefully: missing headers, missing text part (HTML only),
    or non-UTF-8 bodies all produce a sensible result instead of throwing.
    """
    msg = email.message_from_bytes(raw)

    # Sender — strip display name, keep just the address
    from_pairs = getaddresses(msg.get_all("From", []) or [])
    from_email = from_pairs[0][1].lower() if from_pairs else ""

    to_pairs = getaddresses(msg.get_all("To", []) or [])
    to_email = to_pairs[0][1].lower() if to_pairs else ""

    subject = (msg.get("Subject") or "").strip()
    message_id = (msg.get("Message-ID") or msg.get("Message-Id") or "").strip("<>")
    in_reply_to = (msg.get("In-Reply-To") or None)

    # Date
    received_at = datetime.utcnow()
    date_hdr = msg.get("Date")
    if date_hdr:
        try:
            received_at = parsedate_to_datetime(date_hdr).replace(tzinfo=None)
        except Exception:
            pass

    body_text = ""
    body_html = None

    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disposition = (part.get("Content-Disposition") or "").lower()
            if "attachment" in disposition:
                continue
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            try:
                charset = part.get_content_charset() or "utf-8"
                text = payload.decode(charset, errors="replace")
            except Exception:
                text = payload.decode("utf-8", errors="replace")
            if ctype == "text/plain" and not body_text:
                body_text = text
            elif ctype == "text/html" and body_html is None:
                body_html = text
    else:
        payload = msg.get_payload(decode=True)
        if payload is not None:
            try:
                charset = msg.get_content_charset() or "utf-8"
                text = payload.decode(charset, errors="replace")
            except Exception:
                text = payload.decode("utf-8", errors="replace")
            if msg.get_content_type() == "text/html":
                body_html = text
                body_text = strip_html(text)
            else:
                body_text = text

    if not body_text and body_html:
        body_text = strip_html(body_html)

    return ParsedInboundEmail(
        from_email=from_email,
        to_email=to_email,
        subject=subject,
        body_text=body_text.strip(),
        body_html=body_html,
        message_id=message_id,
        received_at=received_at,
        in_reply_to=in_reply_to,
        raw_size_bytes=len(raw),
    )


def strip_html(s: str) -> str:
    """Crude but adequate — strip tags, collapse whitespace, decode entities."""
    import html as _html

    no_tags = _HTML_TAG_RE.sub(" ", s)
    decoded = _html.unescape(no_tags)
    return _WHITESPACE_RE.sub(" ", decoded).strip()


# ---------------------------------------------------------------------------
# S3 poller (live mode)
# ---------------------------------------------------------------------------


def list_pending_inbound_emails(*, max_keys: int = 50) -> list[str]:
    """List S3 keys for unprocessed inbound emails.

    Live mode only. Returns empty in mock mode. Worker loops calling this
    + ``fetch_and_parse`` once we deploy the SES receipt rule.
    """
    if not aws_available():
        return []
    try:
        client = get_boto3_client("s3", region=get_region())
        bucket = inbound_bucket_name()
        resp = client.list_objects_v2(Bucket=bucket, MaxKeys=max_keys, Prefix="inbox/")
        return [obj["Key"] for obj in resp.get("Contents", [])]
    except Exception:  # pragma: no cover
        logger.exception("S3 list_objects failed for inbound emails")
        return []


def fetch_and_parse(key: str) -> Optional[ParsedInboundEmail]:
    """Fetch one raw email object from S3 and parse it."""
    if not aws_available():
        return None
    try:
        client = get_boto3_client("s3", region=get_region())
        bucket = inbound_bucket_name()
        obj = client.get_object(Bucket=bucket, Key=key)
        raw = obj["Body"].read()
        return parse_raw_email(raw)
    except Exception:  # pragma: no cover
        logger.exception("S3 fetch_and_parse failed for key=%s", key)
        return None


def mark_processed(key: str) -> bool:
    """Move processed key from inbox/ to processed/ prefix so the poller
    doesn't pick it up again."""
    if not aws_available():
        return True
    try:
        client = get_boto3_client("s3", region=get_region())
        bucket = inbound_bucket_name()
        new_key = key.replace("inbox/", "processed/", 1)
        client.copy_object(
            Bucket=bucket,
            CopySource={"Bucket": bucket, "Key": key},
            Key=new_key,
        )
        client.delete_object(Bucket=bucket, Key=key)
        return True
    except Exception:  # pragma: no cover
        logger.exception("S3 mark_processed failed for key=%s", key)
        return False
