#!/usr/bin/env bash
set -euo pipefail
ROOT="$GITHUB_WORKSPACE"
OUT="$ROOT/build-baseline"
REF="$ROOT/rom-proc-config.txt"
EVID="$ROOT/evidence/baseline"
mkdir -p "$EVID"
test -s "$OUT/.config"
if grep -q "^CONFIG_USB_CONFIGFS_F_UAC2=y" "$OUT/.config"; then
  echo "BASELINE_CONFIG_UAC2=FAIL"
  exit 1
fi
grep -E "^CONFIG_[A-Za-z0-9_]+=" "$OUT/.config" | sort -u > "$ROOT/baseline-enabled.norm"
grep -E "^CONFIG_[A-Za-z0-9_]+=" "$REF" | sort -u > "$ROOT/rom-enabled.norm"
diff -u "$ROOT/rom-enabled.norm" "$ROOT/baseline-enabled.norm" > "$EVID/config.diff" || true
COUNT="$(grep -cE "^[+-]CONFIG_" "$EVID/config.diff" || true)"
echo "CONFIG_DIFF_COUNT=$COUNT"
if [ "$COUNT" != "0" ]; then
  echo "CONFIG_GATE=REVIEW_REQUIRED" | tee "$EVID/config-gate.txt"
  exit 1
fi
cp "$OUT/.config" "$EVID/.config"
echo "CONFIG_GATE=PASS" | tee "$EVID/config-gate.txt"
