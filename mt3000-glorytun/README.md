# glorytun mud build

Cross-compiles [angt/glorytun](https://github.com/angt/glorytun) for
aarch64/musl (OpenWrt 23.05, GL-MT3000) with the OpenWrt SDK, and uploads the
resulting `.ipk` as a build artifact.

## Why

The GL-MT3000 cannot compile natively — OpenWrt's package feed ships no
compiler, no `make`, no `libsodium-dev`. A musl cross toolchain is required,
and `gcc-aarch64-linux-gnu` produces glibc binaries that will not run there.
The OpenWrt SDK carries both the musl cross-gcc and the package feeds.

This repository exists only to give that build a reproducible environment.

## Contents

| File | Purpose |
|---|---|
| `build-sdk.sh` | downloads the SDK, sets up feeds, builds, collects the ipk |
| `patches/003-sequence.py` | optional patch: 8-byte packet sequence + receive-side dedup |
| `.github/workflows/build-glorytun.yml` | the CI entry point |

## The patch

`angt/glorytun`'s data packets carry no sequence number, so a receiver cannot
detect duplicates (redundant sending) or restore order (split sending). The
patch prepends an 8-byte big-endian sequence inside the encrypted payload and
adds a 4096-entry dedup window on the receive side.

It touches six places in `mud/mud.c`:

1. the `mud_seq` struct and `mud_seq_accept()`
2. `mud_send()` — prepend the sequence
3. `mud_recv()` — dedup on the data branch
4. `mud_recv()` — return the reduced length
5. `mud_get_mtu()` — reserve the 8 bytes (otherwise full-size packets exceed
   the negotiated MTU and are silently dropped)
6. `struct mud` — the `seq` field

The window logic is verified by a 12-case simulation before any C is compiled
(`_sim_seq.py` in the parent project).

**Wire format changes, so both ends must run the patch.** There is no version
negotiation.

## Running it

`Actions → build glorytun (aarch64 musl) → Run workflow`

Tick `apply_patch` to build the patched binary, untick it to verify the
toolchain alone.

## Upstream

This repository does not modify angt/glorytun upstream. It clones a pinned
commit read-only and keeps its changes as the patch above.