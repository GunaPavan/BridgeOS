#!/usr/bin/env bash
# Quick smoke test of the deployed stack.
# Usage:
#   bash scripts/smoke_test_deploy.sh
#
# Hits the production URLs + verifies key endpoints respond correctly.

set -e

API="https://api.bridge-os.click"
APP="https://bridge-os.click"

pass=0
fail=0

check() {
    local name="$1"; local url="$2"; local expected="$3"
    local actual=$(curl -s -m 8 -o /dev/null -w "%{http_code}" "$url" 2>&1)
    if [ "$actual" = "$expected" ]; then
        echo "  ✓ $name → HTTP $actual"
        pass=$((pass+1))
    else
        echo "  ✗ $name → HTTP $actual (expected $expected)"
        fail=$((fail+1))
    fi
}

echo "=== Backend ($API) ==="
check "health" "$API/system/health/full" 200
check "donors list" "$API/donors?limit=1" 200
check "bridges list" "$API/bridges?limit=1" 200
check "patients list" "$API/patients?limit=1" 200
check "system/events/topics" "$API/system/events/topics" 200
check "system/dispatch-queue/status" "$API/system/dispatch-queue/status" 200

echo ""
echo "=== Frontend ($APP) ==="
check "landing" "$APP" 200
check "dashboard" "$APP/dashboard" 200

echo ""
echo "=== Webhooks (just check they're reachable, don't expect 200) ==="
check "whatsapp webhook" "$API/whatsapp/webhook" 405  # GET not allowed, POST is
check "emails inbound webhook" "$API/emails/inbound-webhook" 405

echo ""
echo "============================================"
echo "  Passed: $pass / Failed: $fail"
if [ "$fail" -gt 0 ]; then
    exit 1
fi
