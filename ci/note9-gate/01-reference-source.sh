#!/usr/bin/env bash
set -euo pipefail
ROOT="$GITHUB_WORKSPACE"
EVID="$ROOT/evidence"
mkdir -p "$EVID" "$EVID/baseline" "$EVID/uac2" "$EVID/package"

KERNEL_REPO="https://github.com/LineageOS/android_kernel_samsung_exynos9810"
KERNEL_COMMIT="6a9461f9460ca51d1217e5069a5d5556fcc79e63"
ROM_CONFIG_SIZE="164034"
ROM_CONFIG_SHA256="c291d1509b7a063b7f51113e0858bdeda94adcb5bb0698414008fbb66aa6b3d9"

REF="$ROOT/rom-proc-config.txt"
curl -fL --retry 4 --retry-all-errors -o "$REF"   "https://github.com/Sharkecho/Public-Build-Farm/releases/download/lo20-baseline-ref/rom-proc-config.txt"
test "$(stat -c '%s' "$REF")" = "$ROM_CONFIG_SIZE"
test "$(sha256sum "$REF" | awk '{print $1}')" = "$ROM_CONFIG_SHA256"
if grep -q "^CONFIG_USB_CONFIGFS_F_UAC2=y" "$REF"; then
  echo "ROM_CONFIG_PRECONDITION=FAIL" | tee "$EVID/rom-config.txt"
  exit 1
fi
COUNT="$(grep -c '^CONFIG_' "$REF" || true)"
test "$COUNT" = "1853"
{
  echo "ROM_CONFIG_IDENTITY=PASS"
  echo "ROM_CONFIG_SIZE=$ROM_CONFIG_SIZE"
  echo "ROM_CONFIG_SHA256=$ROM_CONFIG_SHA256"
  echo "ROM_ENABLED_SYMBOL_COUNT=$COUNT"
  echo "ROM_UAC2_ENABLED=NO"
} | tee "$EVID/rom-config.txt"

rm -rf "$ROOT/src"
git clone --filter=blob:none --no-checkout "$KERNEL_REPO" "$ROOT/src"
git -C "$ROOT/src" fetch --depth=1 origin "$KERNEL_COMMIT"
git -C "$ROOT/src" checkout --detach "$KERNEL_COMMIT"
ACTUAL="$(git -C "$ROOT/src" rev-parse HEAD)"
test "$ACTUAL" = "$KERNEL_COMMIT"
{
  echo "SOURCE_IDENTITY=PASS"
  echo "KERNEL_REPO=$KERNEL_REPO"
  echo "KERNEL_COMMIT=$ACTUAL"
} | tee "$EVID/source.txt"
