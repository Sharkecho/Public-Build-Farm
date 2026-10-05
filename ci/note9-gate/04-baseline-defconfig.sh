#!/usr/bin/env bash
set -euo pipefail
ROOT="$GITHUB_WORKSPACE"
SRC="$ROOT/src"
OUT="$ROOT/build-baseline"
CLANG="$ROOT/toolchains/clang-r416183b"
GCC="$ROOT/toolchains/aarch64-linux-android-4.9"
export PATH="$CLANG/bin:$GCC/bin:$PATH"
export ARCH=arm64
export SUBARCH=arm64
export ANDROID_MAJOR_VERSION=q
export CROSS_COMPILE="$GCC/bin/aarch64-linux-android-"
export CLANG_TRIPLE=aarch64-linux-gnu-
export CC=clang
rm -rf "$OUT"
make -C "$SRC" O="$OUT" ARCH=arm64 exynos9810-crownlte_defconfig
