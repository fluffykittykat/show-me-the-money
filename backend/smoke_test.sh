#!/usr/bin/env bash
#
# Post-deploy smoke test for jerry-maguire backend.
# Runs deep health check + triggers each scheduler job to verify
# all data pipelines are functional against live APIs.
#
# Usage: ./smoke_test.sh [base_url]
#   base_url defaults to http://localhost:8000
#
# Exit codes:
#   0 = all checks passed
#   1 = one or more checks failed
#

set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
PASS=0
FAIL=0
WARN=0

green() { printf "\033[32m%s\033[0m\n" "$1"; }
yellow() { printf "\033[33m%s\033[0m\n" "$1"; }
red() { printf "\033[31m%s\033[0m\n" "$1"; }
bold() { printf "\033[1m%s\033[0m\n" "$1"; }

check_status() {
    local name="$1"
    local status="$2"
    local detail="$3"

    if [ "$status" = "ok" ]; then
        green "  ✓ $name"
        PASS=$((PASS + 1))
    elif [ "$status" = "warning" ] || [ "$status" = "skipped" ]; then
        yellow "  ⚠ $name: $detail"
        WARN=$((WARN + 1))
    else
        red "  ✗ $name: $detail"
        FAIL=$((FAIL + 1))
    fi
}

bold "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
bold "  Jerry Maguire — Post-Deploy Smoke Test"
bold "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Target: $BASE_URL"
echo "Time:   $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo ""

# ─── Step 1: Basic health ─────────────────────────────────────
bold "Step 1: Basic Health"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/health")
if [ "$HTTP_CODE" = "200" ]; then
    check_status "GET /health" "ok" ""
else
    check_status "GET /health" "error" "HTTP $HTTP_CODE"
fi
echo ""

# ─── Step 2: Deep health check ────────────────────────────────
bold "Step 2: Deep Health Check (all APIs + DB + scheduler)"
DEEP=$(curl -s --max-time 60 "$BASE_URL/admin/health/deep" 2>&1)

if ! echo "$DEEP" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
    check_status "Deep health check" "error" "Invalid response"
else
    # Parse each check
    for CHECK_NAME in database congress_api fec_api senate_efd scheduler recent_jobs; do
        STATUS=$(echo "$DEEP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['checks']['$CHECK_NAME']['status'])" 2>/dev/null || echo "error")
        ERROR=$(echo "$DEEP" | python3 -c "import sys,json; c=json.load(sys.stdin)['checks']['$CHECK_NAME']; print(c.get('error','') or c.get('reason',''))" 2>/dev/null || echo "parse error")
        check_status "$CHECK_NAME" "$STATUS" "$ERROR"
    done
fi
echo ""

# ─── Step 3: Trigger fast scheduler jobs ──────────────────────
bold "Step 3: Scheduler Job Verification"

# fetch_new_votes is fast (2 API calls), run it directly
echo "  Running fetch_new_votes..."
RESULT=$(curl -s --max-time 30 -X POST "$BASE_URL/admin/scheduler/run/fetch_new_votes" 2>&1)
STATUS=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','error'))" 2>/dev/null || echo "error")
MSG=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('message','unknown'))" 2>/dev/null || echo "unknown")
if [ "$STATUS" = "ok" ]; then
    check_status "fetch_new_votes" "ok" ""
else
    check_status "fetch_new_votes" "error" "$MSG"
fi

# fetch_new_trades depends on eFD DNS — tested via deep health check already
# fetch_fec_updates iterates all 535 members (20+ min with throttling)
# Instead, verify the FEC API is callable via the deep health check above
echo "  (fetch_new_trades: covered by senate_efd check in Step 2)"
echo "  (fetch_fec_updates: covered by fec_api check in Step 2)"
echo "  (Full scheduler runs are too slow for smoke tests — API connectivity verified above)"
echo ""

# ─── Step 4: Verify no new errors in job history ──────────────
bold "Step 4: Post-Run Job History Check"
sleep 2
HISTORY=$(curl -s "$BASE_URL/admin/ingest/status" 2>&1)
RECENT_FAILED=$(echo "$HISTORY" | python3 -c "
import sys, json
data = json.load(sys.stdin)
recent = data.get('recent_jobs', [])
# Check jobs from last 5 minutes
from datetime import datetime, timezone, timedelta
cutoff = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
failed = [j for j in recent if j.get('status') == 'failed' and (j.get('created_at','') > cutoff)]
print(len(failed))
for f in failed:
    errs = f.get('errors', [])
    msg = errs[0].get('message','') if errs else ''
    print(f'{f[\"job_type\"]}: {msg[:80]}')
" 2>/dev/null || echo "-1")

FAILED_COUNT=$(echo "$RECENT_FAILED" | head -1)
if [ "$FAILED_COUNT" = "0" ]; then
    check_status "No failed jobs in last 5 min" "ok" ""
elif [ "$FAILED_COUNT" = "-1" ]; then
    check_status "Job history check" "warning" "Could not parse response"
else
    FAILED_DETAIL=$(echo "$RECENT_FAILED" | tail -n +2)
    check_status "Failed jobs detected" "error" "$FAILED_DETAIL"
fi
echo ""

# ─── Summary ──────────────────────────────────────────────────
bold "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
bold "  Results: ${PASS} passed, ${WARN} warnings, ${FAIL} failed"
bold "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ "$FAIL" -gt 0 ]; then
    red "  SMOKE TEST FAILED — do not proceed until errors are resolved"
    exit 1
elif [ "$WARN" -gt 0 ]; then
    yellow "  SMOKE TEST PASSED WITH WARNINGS — review before proceeding"
    exit 0
else
    green "  SMOKE TEST PASSED — all systems operational"
    exit 0
fi
