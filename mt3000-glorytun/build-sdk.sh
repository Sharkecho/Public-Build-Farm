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
SDK_GCC="${SDK_GCC:-12.3.0}"
SDK_NAME="openwrt-sdk-${SDK_VER}-$(echo "$SDK_TARGET" | tr '/' '-')_gcc-${SDK_GCC}_musl.Linux-x86_64"
SDK_URL="https://downloads.openwrt.org/releases/${SDK_VER}/targets/${SDK_TARGET}/${SDK_NAME}.tar.xz"

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
for t in wget tar xz make gcc g++ git patch; do need "$t"; echo "  $t ok"; done

mkdir -p "$WORK"
cd "$WORK"

# ---------------------------------------------------------------------------
say "OpenWrt SDK ${SDK_VER} (${SDK_TARGET}, gcc ${SDK_GCC}, musl)"
# ---------------------------------------------------------------------------
if [ ! -d "$SDK_NAME" ]; then
    if [ ! -f "${SDK_NAME}.tar.xz" ]; then
        echo "downloading ${SDK_URL}"
        wget -O "${SDK_NAME}.tar.xz.part" "$SDK_URL"
        mv "${SDK_NAME}.tar.xz.part" "${SDK_NAME}.tar.xz"
    fi
    echo "extracting (this takes a minute)"
    tar xf "${SDK_NAME}.tar.xz"
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
