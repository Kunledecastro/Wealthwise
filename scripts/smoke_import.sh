#!/usr/bin/env bash
# Signs in to a running stack and imports the sample statement through the web origin.
# Usage: scripts/smoke_import.sh EMAIL PASSWORD [BASE_URL]
set -euo pipefail
EMAIL=$1; PASSWORD=$2; B=${3:-http://localhost:3000}
J=$(mktemp); trap 'rm -f "$J"' EXIT
S="$(cd "$(dirname "$0")/.." && pwd)/docs/samples/sample-gtbank-style-statement.csv"
tok() { awk '$6=="ww_csrf"{print $7}' "$J" | tail -1; }
call() { local m=$1 u=$2; shift 2; curl -fsS -c "$J" -b "$J" -H "Origin: $B" -H "X-CSRF-Token: $(tok)" -X "$m" "$B$u" "$@"; }
curl -fsS -c "$J" "$B/api/auth/csrf" >/dev/null
call POST /api/auth/login -H "Content-Type: application/json" -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" >/dev/null
ACC=$(call POST /api/accounts -H "Content-Type: application/json" \
  -d '{"type":"bank","display_name":"Smoke test","opening_balance_minor":0,"opening_balance_date":"2026-09-30"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
BID=$(call POST /api/imports -F "account_id=$ACC" -F "file=@$S" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
call POST "/api/imports/$BID/commit" -H "Content-Type: application/json" -d '{"set_opening_from_statement":true}' \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['created'] == 9, d
assert d['reconciliation']['matches'], d
print('import smoke test OK: 9 rows, balance matches statement')"
