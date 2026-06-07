"""Lambda subscriber for `team019-bridge-os-caregiver-reply-resolved`.

When SNS delivers a caregiver-reply-resolved event, this Lambda logs it
and (optionally) calls back to the backend to cancel outreach.

This is the cross-process redundant copy of the in-process subscriber
caregiver_resolved_cancel_outreach — both fire on every event, the
backend's idempotency check (CallEscalation existing row, wave already
expired, etc.) prevents double-action.

Why both? Lambda subscribers survive backend restarts/deploys; the
in-process one survives Lambda concurrency limits. Belt + suspenders.
"""

from __future__ import annotations

import json
import os
import urllib.request

API_BASE = os.environ.get("BRIDGE_OS_API_BASE", "https://api.bridge-os.click")


def lambda_handler(event, context):
    records = event.get("Records", [])
    processed = 0
    for record in records:
        try:
            sns = record.get("Sns", {})
            message = json.loads(sns.get("Message", "{}"))
            patient_id = message.get("patient_id")
            print(
                "caregiver-reply-resolved received: patient=%s, message_id=%s"
                % (patient_id, sns.get("MessageId", "?"))
            )
            # Idempotent: backend handler verifies wave isn't already cancelled
            _trigger_resolved_handler(patient_id, sns.get("MessageId", "?"))
            processed += 1
        except Exception as exc:
            print(f"Failed to process record: {exc}")
    return {"processed": processed, "total": len(records)}


def _trigger_resolved_handler(patient_id: str, sns_id: str) -> None:
    """Tell the backend an SNS event arrived. Backend's existing
    subscriber chain handles dedup + side effects."""
    if not patient_id:
        return
    url = f"{API_BASE.rstrip('/')}/system/events/lambda-callback"
    payload = json.dumps({
        "topic": "caregiver-reply-resolved",
        "patient_id": patient_id,
        "lambda_message_id": sns_id,
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Trigger-Source": "lambda-subscriber",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"backend callback -> {resp.status}")
    except Exception as exc:
        # Don't fail the Lambda — the in-process subscriber will also fire
        print(f"backend callback failed (non-fatal): {exc}")
