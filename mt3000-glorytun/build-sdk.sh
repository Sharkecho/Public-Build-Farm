#!/bin/sh
#
# build-sdk.sh -- cross-compile glorytun (aarch64/musl) with the OpenWrt SDK.
#
# Why an SDK and not a plain cross toolchain: glorytun links libsodium, and on
# this target libsodium must be built against musl for aarch64. The SDK carries
# both the musl cross-gcc and the package feeds, so `make package/glorytun/compile`
# produces a binary that actually runs on the router. A hand-rolled
# gcc-aarch64-linux-gnu (glibc) toolchain would not.
#
# Verified constraints on this device (2026-10-24):
#   - router : aarch64_cortex-a53, musl, OpenWrt 23.05.5, mediatek/filogic
#   - router cannot compile natively: no gcc/make/binutils/libsodium-dev in
#     the packages feed
#   - current binary md5 34bfacdf5bda4bc9439964d985ec6e75 (230,264 B)
#
# Usage (inside WSL Ubuntu, or any Linux with ~4 GB free):
#
#   ./build-sdk.sh                 # build, apply patch 003
#   ./build-sdk.sh --no-patch      # build stock source (toolchain smoke test)
#   ./build-sdk.sh --clean         # wipe the SDK and start over
#
# Everything lives under $WORK so nothing outside it is touched.
#
set -eu

WORK="${WORK:-/tmp/owrt-build}"
SDK_VER="${SDK_VER:-23.05.5}"
SDK_TARGET="${SDK_TARGET:-mediatek/filogic}"

# The SDK file name changes between release branches, so derive it rather than
# hardcode it. Verified against downloads.openwrt.org on 2026-10-24:
#
#   23.05.x -> gcc-12.3.0, .tar.xz
#   24.10.x -> gcc-13.3.0, .tar.zst     (both changed at once)
#   25.12.x -> gcc-13.3.0, .tar.zst
#
# Hardcoding 12.3.0 + .xz made the 24.10.8 build die on a 404 twenty seconds in.
case "$SDK_VER" in
    23.05.*) SDK_GCC="${SDK_GCC:-12.3.0}" ;;
    *)       SDK_GCC="${SDK_GCC:-13.3.0}" ;;
esac

SDK_BASE="openwrt-sdk-${SDK_VER}-$(echo "$SDK_TARGET" | tr '/' '-')_gcc-${SDK_GCC}_musl.Linux-x86_64"
SDK_URL_BASE="https://downloads.openwrt.org/releases/${SDK_VER}/targets/${SDK_TARGET}/${SDK_BASE}"

# Prefer zst (current), fall back to xz (older branches).
if [ -n "${SDK_EXT:-}" ]; then
    SDK_EXT="$SDK_EXT"
    SDK_URL="${SDK_URL_BASE}.tar.${SDK_EXT}"
else
    SDK_EXT=xz
    SDK_URL="${SDK_URL_BASE}.tar.xz"
    for e in zst xz; do
        if wget -q --spider "${SDK_URL_BASE}.tar.${e}" 2>/dev/null; then
            SDK_EXT="$e"
            SDK_URL="${SDK_URL_BASE}.tar.${e}"
            break
        fi
    done
fi
SDK_NAME="$SDK_BASE"
echo "SDK: ${SDK_URL}"

# glorytun upstream: angt/glorytun (the REAL multipath project), NOT Ysurac/glorytun
GT_REPO="https://github.com/angt/glorytun.git"
GT_COMMIT="c113724eb0370ecd80d038192deeeb82a13ebed3"

APPLY_PATCH=1
for a in "$@"; do
    case "$a" in
        --no-patch) APPLY_PATCH=0 ;;
        --clean)    echo "removing $WORK"; rm -rf "$WORK"; exit 0 ;;
        -h|--help)  sed -n '2,40p' "$0"; exit 0 ;;
        *) echo "unknown option: $a" >&2; exit 2 ;;
    esac
done

say() { printf '\n=== %s ===\n' "$*"; }
die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }

need() { command -v "$1" >/dev/null 2>&1 || die "missing command: $1"; }
say "checking host tools"
for t in wget tar make gcc g++ git patch; do need "$t"; echo "  $t ok"; done
# xz for 23.05 SDKs, zstd for 24.10+. Both are cheap; missing one only matters
# for the branch that needs it, so warn rather than die.
for t in xz zstd; do
    if command -v "$t" >/dev/null 2>&1; then echo "  $t ok"; else echo "  $t MISSING (needed for some SDK versions)"; fi
done

mkdir -p "$WORK"
cd "$WORK"

# ---------------------------------------------------------------------------
say "OpenWrt SDK ${SDK_VER} (${SDK_TARGET}, gcc ${SDK_GCC}, musl)"
# ---------------------------------------------------------------------------
if [ ! -d "$SDK_NAME" ]; then
    TARBALL="${SDK_NAME}.tar.${SDK_EXT}"
    if [ ! -s "$TARBALL" ]; then
        echo "downloading ${SDK_URL}"
        wget -O "${TARBALL}.part" "$SDK_URL" || die "SDK download failed: ${SDK_URL}"
        [ -s "${TARBALL}.part" ] || die "downloaded file is empty"
        mv "${TARBALL}.part" "$TARBALL"
    fi
    echo "extracting (this takes a minute)"
    case "$SDK_EXT" in
        zst) tar --zstd -xf "$TARBALL" ;;
        *)   tar xf "$TARBALL" ;;
    esac
else
    echo "already extracted"
fi
SDK="$WORK/$SDK_NAME"
[ -d "$SDK" ] || die "SDK directory missing: $SDK"
cd "$SDK"

# ---------------------------------------------------------------------------
say "feeds (libsodium lives in packages)"
# ---------------------------------------------------------------------------
if [ ! -f .feeds-updated ]; then
    ./scripts/feeds update -a
    ./scripts/feeds install libsodium
    touch .feeds-updated
else
    echo "already done"
fi

# ---------------------------------------------------------------------------
say "seed .config (without this, every package target runs menuconfig)"
# ---------------------------------------------------------------------------
# The SDK has no .config on first use. Any `make package/X/...` target then
# falls into `menuconfig`, which needs a terminal -- and CI has none:
#
#   Error opening terminal: unknown.
#   make[1]: *** [include/toplevel.mk:95: .config] Error 2
#
# `make defconfig` generates a valid default .config non-interactively, which
# is all a single-package build needs. Package selection is implicit: naming
# `package/glorytun/compile` pulls in the package and its dependencies.
if [ ! -f .config ]; then
    make defconfig
else
    echo "already present"
fi

# ---------------------------------------------------------------------------
say "glorytun package source"
# ---------------------------------------------------------------------------
PKG="package/glorytun"
if [ ! -d "$PKG" ]; then
    mkdir -p "$PKG"
    # A minimal OpenWrt package: fetch our exact commit, build with the SDK's
    # musl toolchain. Mirrors firmware/glorytun-mud/Makefile in the repo.
    cat > "$PKG/Makefile" <<EOF
include \$(TOPDIR)/rules.mk

PKG_NAME:=glorytun
PKG_VERSION:=0.3.4
PKG_RELEASE:=1

PKG_SOURCE_PROTO:=git
PKG_SOURCE_URL:=${GT_REPO}
PKG_SOURCE_VERSION:=${GT_COMMIT}
PKG_MIRROR_HASH:=skip

PKG_LICENSE:=BSD-2-Clause
PKG_BUILD_PARALLEL:=1

include \$(INCLUDE_DIR)/package.mk

define Package/glorytun
  SECTION:=net
  CATEGORY:=Network
  SUBMENU:=VPN
  TITLE:=Glorytun multipath VPN (mud engine)
  URL:=https://github.com/angt/glorytun
  DEPENDS:=+kmod-tun +libsodium
endef

define Package/glorytun/description
 Multipath UDP tunnel over the mud engine.
endef

define Build/Configure
	( cd \$(PKG_BUILD_DIR) && ./autogen.sh && \\
	  ./configure --host=\$(GNU_TARGET_NAME) --prefix=/usr )
endef

define Build/Compile
	\$(MAKE) -C \$(PKG_BUILD_DIR) \\
		CC="\$(TARGET_CC)" CFLAGS="\$(TARGET_CFLAGS)" \\
		LDFLAGS="\$(TARGET_LDFLAGS)" \\
		DESTDIR="\$(PKG_INSTALL_DIR)"
endef

define Package/glorytun/install
	\$(INSTALL_DIR) \$(1)/usr/sbin
	\$(INSTALL_BIN) \$(PKG_BUILD_DIR)/src/glorytun \$(1)/usr/sbin/glorytun
endef

\$(eval \$(call BuildPackage,glorytun))
EOF
    echo "package Makefile written"
fi

# ---------------------------------------------------------------------------
say "patch 003 (sequence + dedup)"
# ---------------------------------------------------------------------------
if [ "$APPLY_PATCH" = "1" ]; then
    echo "NOTE: the patch is applied to the DOWNLOADED tarball inside"
    echo "      build_dir/, which only exists after the first fetch."
    echo "      So: fetch once, patch, then compile again."
fi

# ---------------------------------------------------------------------------
say "fetch (first pass)"
# ---------------------------------------------------------------------------
make "package/glorytun/download" V=s || die "download failed"

BUILD_DIR=$(find build_dir -maxdepth 2 -type d -name 'glorytun-*' | head -1)
[ -d "$BUILD_DIR" ] || die "cannot find build_dir/glorytun-*"
echo "build dir: $BUILD_DIR"

if [ "$APPLY_PATCH" = "1" ]; then
    # PATCHER may be overridden; otherwise look next to this script, which works
    # both locally and in CI (no absolute /mnt/... paths).
    if [ -z "${PATCHER:-}" ]; then
        case "$0" in
            */*) PATCHER="$(cd "$(dirname "$0")" && pwd)/patches/003-sequence.py" ;;
            *)   PATCHER="./patches/003-sequence.py" ;;
        esac
    fi
    if [ -f "$PATCHER" ]; then
        echo "applying $PATCHER"
        python3 "$PATCHER" --src "$BUILD_DIR/mud/mud.c" || die "patch failed"
    else
        echo "WARNING: patcher not found at $PATCHER -- building stock source" >&2
    fi
fi

# ---------------------------------------------------------------------------
say "compile"
# ---------------------------------------------------------------------------
make "package/glorytun/compile" V=s 2>&1 | tail -40

# ---------------------------------------------------------------------------
say "collect the ipk"
# ---------------------------------------------------------------------------
IPK=$(find bin -name 'glorytun*.ipk' | head -1)
if [ -z "$IPK" ]; then
    die "no ipk produced -- check the compile log above"
fi
cp "$IPK" "$WORK/glorytun-new.ipk"

echo
echo "ipk : $WORK/glorytun-new.ipk"
ls -la "$WORK/glorytun-new.ipk"
md5sum "$WORK/glorytun-new.ipk"

# extract the binary and sanity-check its architecture
rm -rf "$WORK/x" && mkdir -p "$WORK/x"
cd "$WORK/x"
tar xzf "$WORK/glorytun-new.ipk" 2>/dev/null || {
    ar x "$WORK/glorytun-new.ipk" && tar xzf data.tar.gz
}
BIN=$(find . -name glorytun -type f | head -1)
if [ -n "$BIN" ]; then
    echo
    echo "binary: $BIN"
    ls -la "$BIN"
    md5sum "$BIN"
    echo
    echo "--- architecture (must say ARM aarch64, musl) ---"
    strings "$BIN" | grep -m3 'ld-musl\|GCC:' || true
fi

echo
echo "=== done ==="
echo "install on the router with:"
echo "  scp $WORK/glorytun-new.ipk root@ROUTER_IP:/tmp/"
echo "  ssh root@ROUTER_IP 'opkg install --force-reinstall /tmp/glorytun-new.ipk'"
echo
echo "roll back with (already on the router):"
echo "  ssh root@ROUTER_IP 'opkg install --force-reinstall /root/glorytun-mud_0.0.2-1_aarch64.ipk'"
