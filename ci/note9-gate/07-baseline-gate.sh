#!/usr/bin/env bash
set -euo pipefail
ROOT="$GITHUB_WORKSPACE"
EVID="$ROOT/evidence/baseline"
IMAGE="$ROOT/build-baseline/arch/arm64/boot/Image"
EXPECTED_SIZE="29028372"
EXPECTED_SHA="96b54bc6a37c8b1b3504018e688c3d6ca34779a47b34e38f2b2442531174f073"
SIZE="$(stat -c '%s' "$IMAGE")"
SHA="$(sha256sum "$IMAGE" | awk '{print $1}')"
{
  echo "BASELINE_IMAGE_SIZE=$SIZE"
  echo "BASELINE_IMAGE_SHA256=$SHA"
  echo "ROM_KERNEL_SIZE=$EXPECTED_SIZE"
  echo "ROM_KERNEL_SHA256=$EXPECTED_SHA"
} | tee "$EVID/gate.txt"
if [ "$SIZE" != "$EXPECTED_SIZE" ] || [ "$SHA" != "$EXPECTED_SHA" ]; then
  echo "BASELINE_GATE=REVIEW_REQUIRED" | tee -a "$EVID/gate.txt"
  exit 1
fi
echo "BASELINE_GATE=PASS" | tee -a "$EVID/gate.txt"
