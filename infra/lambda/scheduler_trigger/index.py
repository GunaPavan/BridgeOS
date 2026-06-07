"""EventBridge Scheduler → Lambda → Bridge OS trigger endpoint.

Each EventBridge schedule sends this Lambda an event like:
    {"job_name": "auto_run_cycle"}

The Lambda POSTs to
    https://api.bridge-os.click/system/scheduler/jobs/<job_name>/trigger

so the backend runs the same handler the in-process APScheduler used to fire.
This decouples cron from the container — restarts, scaling, deploys don't
miss a tick because EventBridge fires reliably from outside.
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error

API_BASE = os.environ.get("BRIDGE_OS_API_BASE", "https://api.bridge-os.click")
TIMEOUT_SECONDS = int(os.environ.get("BRIDGE_OS_TRIGGER_TIMEOUT", "30"))


def lambda_handler(event, context):
    job_name = (event or {}).get("job_name")
    if not job_name:
        return {"statusCode": 400, "body": "missing job_name in event"}

    url = f"{API_BASE.rstrip('/')}/system/scheduler/jobs/{job_name}/trigger"
    req = urllib.request.Request(url, method="POST", headers={
        "User-Agent": "bridge-os-eventbridge-scheduler/1.0",
        "X-Trigger-Source": "eventbridge-scheduler",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            body = resp.read().decode("utf-8", errors="replace")[:500]
            return {
                "statusCode": resp.status,
                "job_name": job_name,
                "response_body": body,
            }
    except urllib.error.HTTPError as exc:
        return {
            "statusCode": exc.code,
            "job_name": job_name,
            "error": f"HTTPError: {exc.reason}",
            "body": exc.read().decode("utf-8", errors="replace")[:500],
        }
    except Exception as exc:
        return {
            "statusCode": 500,
            "job_name": job_name,
            "error": f"{type(exc).__name__}: {exc}",
        }
