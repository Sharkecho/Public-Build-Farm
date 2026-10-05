#!/usr/bin/env bash
set -euo pipefail
ROOT="$GITHUB_WORKSPACE"
EVID="$ROOT/evidence"
COMMIT="bd96dfe349c962681f0e5388af874c771ef96670"
DIR="$ROOT/toolchains/clang-r416183b"
rm -rf "$DIR"
mkdir -p "$DIR"
curl -fL --retry 4 --retry-all-errors   "https://android.googlesource.com/platform/prebuilts/clang/host/linux-x86/+archive/$COMMIT/clang-r416183b.tar.gz"   | tar -xz -C "$DIR"
test -x "$DIR/bin/clang"
RAW="$("$DIR/bin/clang" --version | head -3)"
echo "$RAW"
echo "$RAW" | grep -q "12.0.5"
echo "$RAW" | grep -qi "r416183b"
{
  echo "CLANG_IDENTITY=PASS"
  echo "CLANG_COMMIT=$COMMIT"
  echo "CLANG_VERSION=$(echo "$RAW" | head -1)"
} | tee "$EVID/clang.txt"
