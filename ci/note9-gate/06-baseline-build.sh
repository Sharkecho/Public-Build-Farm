#!/usr/bin/env bash
set -euo pipefail
ROOT="$GITHUB_WORKSPACE"
SRC="$ROOT/src"
OUT="$ROOT/build-baseline"
EVID="$ROOT/evidence/baseline"
CLANG="$ROOT/toolchains/clang-r416183b"
GCC="$ROOT/toolchains/aarch64-linux-android-4.9"
export PATH="$CLANG/bin:$GCC/bin:$PATH"
export ARCH=arm64
export SUBARCH=arm64
export ANDROID_MAJOR_VERSION=q
export CROSS_COMPILE="$GCC/bin/aarch64-linux-android-"
export CLANG_TRIPLE=aarch64-linux-gnu-
export CC=clang
make -C "$SRC" O="$OUT" ARCH=arm64 -j"$(nproc)" Image 2>&1 | tee "$EVID/build.log"
IMAGE="$OUT/arch/arm64/boot/Image"
test -s "$IMAGE"
sha256sum "$IMAGE" | tee "$EVID/Image.sha256"
stat -c '%s' "$IMAGE" | tee "$EVID/Image.size"
