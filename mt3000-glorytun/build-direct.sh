#!/bin/sh
#
# build-direct.sh -- build glorytun for aarch64/musl with the OpenWrt SDK
#                   toolchain, bypassing the OpenWrt package framework.
#
# Why not the package Makefile (build-sdk.sh): OpenWrt 24.10's download logic
# tries dl_github_archive.py first, which builds an archive name from
# PKG_VERSION. With PKG_VERSION=0.3.4 and a bare commit SHA the URL
#   https://github.com/angt/glorytun/archive/0.3.4.tar.gz
# 404s (0.3.4 is not a tag), and the fallback path failed too:
#   glorytun-0.3.4.tar.zst: Download from ... failed
#   FATAL: cannot find build_dir/glorytun-*
#
# Cloning directly and driving ./configure against the SDK's staging dir is
# deterministic and does not depend on any of that machinery. The SDK still
# provides the musl cross-gcc and libsodium, which is the whole reason to use
# it -- a generic gcc-aarch64-linux-gnu produces glibc binaries that will not
# run on OpenWrt.
#
# Usage:
#   ./build-direct.sh                       # patch 003 applied
#   ./build-direct.sh --no-patch            # stock source (toolchain test)
#   SDK_VER=24.10.8 ./build-direct.sh
#
set -eu

WORK="${WORK:-/tmp/owrt-direct}"
SDK_VER="${SDK_VER:-24.10.8}"
SDK_TARGET="${SDK_TARGET:-mediatek/filogic}"
ARCH="${ARCH:-aarch64_cortex-a53}"
GT_REPO="${GT_REPO:-https://github.com/angt/glorytun.git}"
GT_COMMIT="${GT_COMMIT:-c113724eb0370ecd80d038192deeeb82a13ebed3}"

APPLY_PATCH=1
for a in "$@"; do
    case "$a" in
        --no-patch) APPLY_PATCH=0 ;;
        *) echo "unknown option: $a" >&2; exit 2 ;;
    esac
done

say() { printf '\n=== %s ===\n' "$*"; }
die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }

mkdir -p "$WORK"
cd "$WORK"

# ---------------------------------------------------------------------------
say "locate or fetch the SDK"
# ---------------------------------------------------------------------------
case "$SDK_VER" in
    23.05.*) SDK_GCC=12.3.0; EXT=xz ;;
    *)       SDK_GCC=13.3.0; EXT=zst ;;
esac
SDK_BASE="openwrt-sdk-${SDK_VER}-$(echo "$SDK_TARGET" | tr '/' '-')_gcc-${SDK_GCC}_musl.Linux-x86_64"
SDK="$WORK/$SDK_BASE"

if [ ! -d "$SDK" ]; then
    # Reuse whatever build-sdk.sh already downloaded, if anything.
    REUSE="${REUSE_SDK:-}"
    if [ -z "$REUSE" ] && [ -d "$WORK/../owrt-work/$SDK_BASE/staging_dir" ]; then
        REUSE="$WORK/../owrt-work/$SDK_BASE"
    fi
    if [ -z "$REUSE" ] && [ -n "${WORK_DIRECT:-}" ] && [ -d "$WORK_DIRECT/../owrt-work/$SDK_BASE/staging_dir" ]; then
        REUSE="$WORK_DIRECT/../owrt-work/$SDK_BASE"
    fi
    if [ -n "$REUSE" ]; then
        SDK="$REUSE"
        echo "reusing $SDK"
    else
        for e in "$EXT" xz zst; do
            url="https://downloads.openwrt.org/releases/${SDK_VER}/targets/${SDK_TARGET}/${SDK_BASE}.tar.${e}"
            if wget -q --spider "$url" 2>/dev/null; then
                echo "downloading $url"
                wget -O "sdk.tar.$e.part" "$url"
                mv "sdk.tar.$e.part" "sdk.tar.$e"
                case "$e" in
                    zst) tar --zstd -xf "sdk.tar.$e" ;;
                    *)   tar xf "sdk.tar.$e" ;;
                esac
                break
            fi
        done
    fi
fi
[ -d "$SDK" ] || die "SDK missing"
echo "SDK: $SDK"

# ---------------------------------------------------------------------------
say "toolchain and staging paths"
# ---------------------------------------------------------------------------
TOOLCHAIN=$(find "$SDK/staging_dir" -maxdepth 1 -type d -name 'toolchain-*' | head -1)
TARGETDIR=$(find "$SDK/staging_dir" -maxdepth 1 -type d -name "target-${ARCH}_*" | head -1)
[ -d "$TOOLCHAIN" ] || die "toolchain not found under $SDK/staging_dir"
[ -d "$TARGETDIR" ] || die "target staging dir not found"

CROSS_PREFIX=$(find "$TOOLCHAIN/bin" -maxdepth 1 -name '*-openwrt-linux-musl-gcc' | head -1)
[ -n "$CROSS_PREFIX" ] || die "cross gcc not found"
CC="$CROSS_PREFIX"
HOST_TRIPLE=$(basename "$CROSS_PREFIX" | sed 's/-gcc$//')

echo "toolchain:  $TOOLCHAIN"
echo "targetdir:  $TARGETDIR"
echo "cross gcc:  $CC"
echo "host:       $HOST_TRIPLE"
$CC --version | head -1

export STAGING_DIR="$SDK/staging_dir"
export PATH="$TOOLCHAIN/bin:$PATH"

# ---------------------------------------------------------------------------
say "libsodium (needed to link)"
# ---------------------------------------------------------------------------
if [ -f "$TARGETDIR/usr/lib/libsodium.a" ] || [ -f "$TARGETDIR/usr/lib/libsodium.so" ]; then
    echo "already in staging:"
    ls -la "$TARGETDIR"/usr/lib/libsodium* 2>/dev/null | sed 's/^/  /'
else
    echo "building libsodium from the feed (first run only)"
    cd "$SDK"
    # The SDK tarball does not always ship host/, and toplevel.mk then dies on
    #   touch: cannot touch 'host/.prereq-build': No such file or directory
    # before compiling anything. Creating the directory is all it needs.
    mkdir -p host
    [ -f .config ] || make defconfig
    ./scripts/feeds update -a
    ./scripts/feeds install libsodium
    make package/libsodium/compile V=s 2>&1 | tail -15
    cd "$WORK"
    ls -la "$TARGETDIR"/usr/lib/libsodium* 2>/dev/null | sed 's/^/  /' || die "libsodium not in staging"
fi

# ---------------------------------------------------------------------------
say "glorytun source"
# ---------------------------------------------------------------------------
GTSRC="$WORK/glorytun"
if [ ! -d "$GTSRC" ]; then
    git clone "$GT_REPO" "$GTSRC"
    cd "$GTSRC"
    git checkout "$GT_COMMIT"
    # mud is a submodule; without it there is nothing to link
    git submodule update --init --recursive
    cd "$WORK"
else
    echo "already cloned"
fi
cd "$GTSRC"

if [ -d mud ] && [ -n "$(ls -A mud 2>/dev/null)" ]; then
    echo "mud submodule present: $(ls mud | head -3 | tr '\n' ' ')"
else
    die "mud submodule is empty -- git submodule update failed"
fi

# ---------------------------------------------------------------------------
say "patch 003"
# ---------------------------------------------------------------------------
if [ "$APPLY_PATCH" = "1" ]; then
    if [ -z "${PATCHER:-}" ]; then
        case "$0" in
            */*) PATCHER="$(cd "$(dirname "$0")" && pwd)/patches/003-sequence.py" ;;
            *)   PATCHER="./patches/003-sequence.py" ;;
        esac
    fi
    [ -f "$PATCHER" ] || die "patcher not found: $PATCHER"
    python3 "$PATCHER" --src "$GTSRC/mud/mud.c"
else
    echo "skipped (--no-patch)"
fi

# ---------------------------------------------------------------------------
say "build"
# ---------------------------------------------------------------------------
# autogen/configure need the SDK's staging headers and libs.
CFLAGS="-I$TARGETDIR/usr/include -Os -pipe"
LDFLAGS="-L$TARGETDIR/usr/lib -Wl,-rpath-link=$TARGETDIR/usr/lib"

if [ -x ./autogen.sh ]; then
    ./autogen.sh
elif [ ! -x ./configure ]; then
    die "no autogen.sh and no configure -- unexpected source tree"
fi

./configure \
    --host="$HOST_TRIPLE" \
    --prefix=/usr \
    CC="$CC" \
    CFLAGS="$CFLAGS" \
    LDFLAGS="$LDFLAGS"

make -j"$(nproc 2>/dev/null || echo 2)" \
    CC="$CC" CFLAGS="$CFLAGS" LDFLAGS="$LDFLAGS" 2>&1 | tail -30

# ---------------------------------------------------------------------------
say "result"
# ---------------------------------------------------------------------------
BIN="$GTSRC/src/glorytun"
[ -f "$BIN" ] || BIN=$(find "$GTSRC" -maxdepth 2 -type f -name glorytun -perm -u+x | head -1)
[ -n "${BIN:-}" ] && [ -f "$BIN" ] || die "binary not produced"

ls -la "$BIN"
md5sum "$BIN"
echo
echo "--- must be aarch64 + musl, and must NOT need libsodium.so ---"
"$TOOLCHAIN/bin/$HOST_TRIPLE-readelf" -h "$BIN" 2>/dev/null | grep -E 'Machine|Class' | sed 's/^/  /' || true
"$TOOLCHAIN/bin/$HOST_TRIPLE-readelf" -d "$BIN" 2>/dev/null | grep NEEDED | sed 's/^/  /' || true

cp "$BIN" "$WORK/glorytun-aarch64"
echo
echo "=== done ==="
echo "binary: $WORK/glorytun-aarch64"
echo
echo "install (no ipk, plain copy -- keep the old one first):"
echo "  scp $WORK/glorytun-aarch64 root@ROUTER_IP:/tmp/"
echo "  ssh root@ROUTER_IP 'cp /usr/sbin/glorytun /root/glorytun.old && \\"
echo "      /etc/init.d/mt3000-mud stop && cp /tmp/glorytun-aarch64 /usr/sbin/glorytun && \\"
echo "      chmod +x /usr/sbin/glorytun && /etc/init.d/mt3000-mud start'"
