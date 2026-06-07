"""Lambda subscriber for `team019-bridge-os-donor-reply-out-of-town`.

Mirror of the in-process subscriber. Logs the event + (optionally) calls
back to the backend to apply the cooldown. Backend uses idempotency
checks so double-fire is safe.
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
            donor_id = message.get("donor_id")
            print(
                "donor-reply-out-of-town received: donor=%s, message_id=%s"
                % (donor_id, sns.get("MessageId", "?"))
            )
            _trigger_cooldown(donor_id, sns.get("MessageId", "?"))
            processed += 1
        except Exception as exc:
            print(f"Failed to process record: {exc}")
    return {"processed": processed, "total": len(records)}


def _trigger_cooldown(donor_id: str, sns_id: str) -> None:
    if not donor_id:
        return
    url = f"{API_BASE.rstrip('/')}/system/events/lambda-callback"
    payload = json.dumps({
        "topic": "donor-reply-out-of-town",
        "donor_id": donor_id,
        "lambda_message_id": sns_id,
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={"Content-Type": "application/json", "X-Trigger-Source": "lambda-subscriber"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"backend callback -> {resp.status}")
    except Exception as exc:
        print(f"backend callback failed (non-fatal): {exc}")
