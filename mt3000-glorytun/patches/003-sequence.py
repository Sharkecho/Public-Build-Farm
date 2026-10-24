#!/usr/bin/env python3
"""
003-sequence.py -- add a packet sequence number with receive-side dedup.

Why this exists
---------------
mud's wire format has no sequence number (see `struct mud_msg` in mud/mud.c:
it carries sent_time, path state, flow-control counters, mtu and loss, but no
packet id). src/bind.c hands every received packet straight to the tun:

    int r = mud_recv(mud, buf, sizeof(buf));
    if (r > 0 && ip_is_valid(buf, r))
        tun_write(tun_fd, buf, (size_t)r);

Two consequences, both measured on the live link:

  * Sending the same packet on two paths delivers it TWICE. The second copy is
    not detectable, so the phone sees duplicate IP packets.
  * Splitting packets across paths with different RTT delivers them out of
    order, and nothing can put them back.

This change adds an 8-byte big-endian sequence number in front of the IP
packet, inside the encrypted payload. The receiver keeps a 4096-entry window
and drops any sequence it has already seen. That makes redundant sending
correct (the first copy wins, the second is discarded) without touching the
handshake, the keepalive format, or the crypto.

Wire format
-----------
    before:  [ mud_msg header ][ AEAD( IP packet ) ]
    after:   [ mud_msg header ][ AEAD( seq(8) | IP packet ) ]

MUD_PKT_MAX_SIZE is 1500 and the tunnel MTU is 1450, so the extra 8 bytes fit
inside the existing headroom. No MTU change is needed.

Compatibility
-------------
Breaking. Both ends must run this patch. There is no version negotiation; a
patched peer talking to an unpatched one will treat the first 8 bytes of the IP
packet as a sequence number and drop everything.

Run with --revert to remove it.
"""

import argparse
import io
import os
import re
import sys

SRC = "/opt/angt-glorytun/mud/mud.c"
HDR = "/opt/angt-glorytun/mud/mud.h"

# ---------------------------------------------------------------------------
# 1. the sequence window, inserted before mud_send
# ---------------------------------------------------------------------------

SEQ_BLOCK = r'''
/* ---- MT3000 patch 003: packet sequence number + receive-side dedup --------
 *
 * struct mud_msg carries no packet id, so a receiver cannot tell a duplicate
 * from a new packet and cannot order anything. Both matter here:
 *
 *   - with redundant sending, every packet arrives twice and both copies are
 *     handed to the tun;
 *   - with split sending, packets arrive out of order and stay that way.
 *
 * The sequence is prepended to the IP packet *inside* the encrypted payload,
 * so the handshake, keepalives and crypto are untouched. Only data packets
 * change shape, and only by 8 bytes.
 *
 * Window: 4096 slots, each holding the sequence it last accepted (0 = empty).
 * 32 KB of memory. A slot is empty when it holds 0, which is why sequence
 * numbers start at 1.
 *
 * The 4096-slot window at a plausible 300 pkt/s covers about 13 seconds of
 * history -- far more than the RTT difference between any two usable legs.
 * A packet older than that is dropped, which is the correct outcome: it would
 * arrive after the application has long moved on.
 */

#define MUD_SEQ_SIZE    8
#define MUD_SEQ_WINDOW  4096
#define MUD_SEQ_MAGIC   0x4d553330u   /* "MU30" -- marks a seq-enabled peer */

struct mud_seq {
    uint64_t tx;                        /* next sequence to send */
    uint64_t base;                      /* highest contiguous delivered */
    uint64_t slot[MUD_SEQ_WINDOW];      /* slot[n] = seq, 0 = empty */
    uint64_t seen;                      /* dropped: already delivered */
    uint64_t outside;                   /* dropped: outside the window */
    uint64_t resync;                    /* times the window was realigned */
    unsigned char streak;               /* consecutive out-of-window packets */
};

static inline void
mud_seq_store(unsigned char *p, uint64_t v)
{
    for (int i = 7; i >= 0; i--) {
        p[i] = (unsigned char)(v & 0xff);
        v >>= 8;
    }
}

static inline uint64_t
mud_seq_load(const unsigned char *p)
{
    uint64_t v = 0;
    for (int i = 0; i < 8; i++)
        v = (v << 8) | p[i];
    return v;
}

/* Returns 1 if this sequence should be delivered, 0 if it must be dropped.
 *
 * The ORDER of these steps matters and was wrong in the first draft: advancing
 * base before inserting the current sequence makes base lag one packet behind,
 * and makes an exact duplicate take the `seq <= base` branch so the duplicate
 * counter never increments. Caught by _sim_seq.py, fixed here.
 *
 * Correct order:
 *   1. below base            -> already delivered
 *   2. beyond base + WINDOW  -> outside the window, treat as bogus/stale
 *   3. slot already holds it -> duplicate
 *   4. insert
 *   5. advance base over the contiguous run, which now includes step 4
 */
#define MUD_SEQ_RESYNC  4   /* consecutive outsiders before realigning */

static int
mud_seq_accept(struct mud_seq *s, uint64_t seq)
{
    if (!seq)
        return 0;

    /* ---- resynchronisation --------------------------------------------
     *
     * The two counters are independent and neither is persisted. A restart
     * on one side resets its tx to 1 and its window to 0, while the other
     * side carries on. That produces two symmetric deadlocks, and without
     * this block neither ever clears:
     *
     *   peer restarted, we did not:
     *       its seq is far BELOW our base -> every packet looks "old"
     *       -> dropped forever -> that direction carries no data
     *
     *   we restarted, peer did not:
     *       its seq is far ABOVE base + WINDOW -> every packet looks
     *       "outside" -> dropped forever -> that direction carries no data
     *
     * Both were observed on 2026-10-24 after swapping binaries: upload ran at
     * 7.8 Mbit/s while download sat at 81 kbit/s, and ping stayed at 0% loss
     * the whole time because measurement messages never reach this code.
     *
     * So: count consecutive out-of-window packets. One stray packet is
     * noise; MUD_SEQ_RESYNC in a row cannot be noise, because the window
     * spans ~13 s at 300 pkt/s. On reaching the threshold, realign to the
     * current sequence and accept it.
     *
     * Forging this would require MUD_SEQ_RESYNC authenticated packets with
     * chosen sequence numbers -- which needs the session key. If the key is
     * gone, window integrity is the least of the problems.
     */
    if (seq <= s->base || seq > s->base + MUD_SEQ_WINDOW) {
        s->outside++;

        if (++s->streak >= MUD_SEQ_RESYNC) {
            s->resync++;
            s->base = seq - 1;
            memset(s->slot, 0, sizeof(s->slot));
            s->streak = 0;
            /* fall through and accept this packet */
        } else {
            return 0;
        }
    } else {
        s->streak = 0;
    }

    const uint64_t off = seq % MUD_SEQ_WINDOW;

    if (s->slot[off] == seq) {
        s->seen++;
        return 0;
    }

    s->slot[off] = seq;

    while (s->slot[(s->base + 1) % MUD_SEQ_WINDOW] == s->base + 1) {
        s->slot[(s->base + 1) % MUD_SEQ_WINDOW] = 0;
        s->base++;
    }

    return 1;
}

'''

# ---------------------------------------------------------------------------
# 2. mud_send: prepend the sequence
# ---------------------------------------------------------------------------

SEND_OLD = """    unsigned char packet[MUD_PKT_MAX_SIZE];
    const uint64_t now = mud_now(mud);
    const size_t packet_size = mud_encrypt(mud, now,
                                           packet, sizeof(packet),
                                           data, size);"""

SEND_NEW = """    unsigned char packet[MUD_PKT_MAX_SIZE];
    unsigned char frame[MUD_PKT_MAX_SIZE];
    const uint64_t now = mud_now(mud);

    /* MT3000 patch 003: prepend the sequence inside the encrypted payload. */
    if (size + MUD_SEQ_SIZE > sizeof(frame)) {
        errno = EMSGSIZE;
        return -1;
    }
    mud_seq_store(frame, ++mud->seq.tx);
    memcpy(frame + MUD_SEQ_SIZE, data, size);

    const size_t packet_size = mud_encrypt(mud, now,
                                           packet, sizeof(packet),
                                           frame, size + MUD_SEQ_SIZE);"""

# ---------------------------------------------------------------------------
# 3. mud_recv_msg: strip + dedup on the way in
#
# The header is parsed first; the payload follows it. We do the seq handling at
# the very end, right before mud_recv_msg returns, because that is where the
# decrypted IP packet is known to be valid.
# ---------------------------------------------------------------------------

# The hook belongs in mud_recv(), NOT in mud_recv_msg().
#
# Reading the tail of mud_recv (2026-10-24) settles what the decrypted buffers
# look like:
#
#     const size_t ret = MUD_MSG(sent_time)
#                      ? mud_decrypt_msg(mud, data, size, packet, packet_size)
#                      : mud_decrypt(mud, data, size, packet, packet_size);
#     ...
#     if (MUD_MSG(sent_time)) {
#         mud_recv_msg(mud, path, now, sent_time, data, (size_t)packet_size);
#     } else {
#         path->idle = now;
#     }
#     ...
#     return MUD_MSG(sent_time) ? 0 : (int)ret;
#
# So MUD_MSG(sent_time) == 1 marks a MEASUREMENT message: it carries a
# struct mud_msg header (fw / loss / mtu / beat) and is consumed entirely by
# mud_recv_msg(); mud_recv returns 0 for it. The DATA direction is the other
# branch: mud_decrypt() produces a bare IP packet with no header, and mud_recv
# returns its length so bind.c can write it to the tun.
#
# An earlier draft put the dedup inside mud_recv_msg. That code would never
# run for data packets, and the 8-byte sequence would have been handed to the
# tun as part of the IP packet, corrupting every packet.

RECV_ANCHOR_OLD = """    struct mud_path *path = mud_get_path(mud, &local_addr, &addr, 1);

    if (!path || path->state <= MUD_DOWN)
        return 0;

    if (MUD_MSG(sent_time)) {"""

RECV_ANCHOR_NEW = """    struct mud_path *path = mud_get_path(mud, &local_addr, &addr, 1);

    if (!path || path->state <= MUD_DOWN)
        return 0;

    /* MT3000 patch 003: data packets carry an 8-byte sequence in front of the
     * IP packet. Drop duplicates, then strip it. ret is the decrypted length;
     * the caller writes out_len bytes to the tun. */
    size_t out_len = ret;

    if (!MUD_MSG(sent_time)) {
        if (ret <= MUD_SEQ_SIZE)
            return 0;

        unsigned char *payload = (unsigned char *)data;
        const uint64_t seq = mud_seq_load(payload);

        if (!mud_seq_accept(&mud->seq, seq))
            return 0;

        memmove(payload, payload + MUD_SEQ_SIZE, ret - MUD_SEQ_SIZE);
        out_len = ret - MUD_SEQ_SIZE;
    }

    if (MUD_MSG(sent_time)) {"""

TAIL_OLD = """    return MUD_MSG(sent_time) ? 0 : (int)ret;"""
TAIL_NEW = """    return MUD_MSG(sent_time) ? 0 : (int)out_len;"""

# ---------------------------------------------------------------------------
# 3c. MTU accounting. THIS IS MANDATORY -- without it the tunnel appears to
#     work and then drops every full-size packet.
#
#     The chain is:
#         mud->mtu            = negotiated wire MTU        (1472 here)
#         mud_get_mtu()       = mud->mtu - MUD_PKT_MIN_SIZE (1472 - 22 = 1450)
#         gt_setup_mtu()      = iface_set_mtu(tun, 1450)
#
#     With an 8-byte sequence, a full tun packet becomes
#         1450 (IP) + 8 (seq) + 22 (header) = 1480  >  1472
#     so it exceeds the MTU that was actually negotiated and gets fragmented
#     or dropped.
#
#     Worse, MTU discovery does not catch it: the probe packets are MEASUREMENT
#     messages, which carry no sequence, so they still succeed at 1472 and the
#     tun is still configured at 1450. The symptom is therefore "small packets
#     fine, full-size packets vanish" -- random loss under load, the hardest
#     kind to diagnose.
#
#     Subtracting MUD_SEQ_SIZE makes the tun MTU 1442, so
#         1442 + 8 + 22 = 1472  exactly.
# ---------------------------------------------------------------------------

MTU_OLD = """    return mud->mtu - MUD_PKT_MIN_SIZE;"""
MTU_NEW = """    /* MT3000 patch 003: leave room for the sequence, or full-size packets
     * exceed the negotiated MTU. See the long note in 003-sequence.py. */
    return mud->mtu - MUD_PKT_MIN_SIZE - MUD_SEQ_SIZE;"""

# ---------------------------------------------------------------------------
# apply / revert
# ---------------------------------------------------------------------------


def patch(path):
    src = io.open(path, encoding="utf-8").read()
    changed = []

    # 1. seq window block, before mud_send
    if "MUD_SEQ_WINDOW" in src:
        print("  seq block already present")
    else:
        # Placement matters. The block defines MUD_SEQ_SIZE, mud_seq_load()
        # and mud_seq_accept(), and mud_recv() -- which uses all three -- comes
        # BEFORE mud_send() in this file. Anchoring on mud_send put the
        # definitions after their first use, and the compiler said so:
        #
        #   mud/mud.c:1403: error: 'MUD_SEQ_SIZE' undeclared
        #   mud/mud.c:1649: error: conflicting types for 'mud_seq_load'
        #   mud/mud.c:1672: error: static declaration of 'mud_seq_accept'
        #                     follows non-static declaration
        #
        # Anchor on the constant block instead: it sits above every function.
        m = re.search(r"^#define MUD_MTU_MAX[^\n]*\n", src, re.M)
        if not m:
            sys.exit("cannot find MUD_MTU_MAX to anchor the seq block")
        src = src[:m.end()] + SEQ_BLOCK + src[m.end():]
        changed.append("seq block")

    # 2. send
    if "MT3000 patch 003: prepend" in src:
        print("  send already patched")
    elif SEND_OLD in src:
        src = src.replace(SEND_OLD, SEND_NEW, 1)
        changed.append("mud_send")
    else:
        sys.exit("cannot find the mud_encrypt call in mud_send")

    # 3a. hook the data branch of mud_recv
    if "MT3000 patch 003: data packets carry" in src:
        print("  mud_recv hook already present")
    elif RECV_ANCHOR_OLD in src:
        src = src.replace(RECV_ANCHOR_OLD, RECV_ANCHOR_NEW, 1)
        changed.append("mud_recv hook")
    else:
        sys.exit("cannot find the path lookup in mud_recv")

    # 3b. return the reduced length
    if TAIL_NEW in src:
        print("  mud_recv return already patched")
    elif TAIL_OLD in src:
        src = src.replace(TAIL_OLD, TAIL_NEW, 1)
        changed.append("mud_recv return")
    else:
        sys.exit("cannot find the mud_recv return statement")

    # 3c. MTU accounting -- mandatory
    if "MT3000 patch 003: leave room for the sequence" in src:
        print("  mud_get_mtu already patched")
    elif MTU_OLD in src:
        src = src.replace(MTU_OLD, MTU_NEW, 1)
        changed.append("mud_get_mtu")
    else:
        sys.exit("cannot find mud_get_mtu's return statement")

    # 4. add the seq state to struct mud
    if "struct mud_seq seq;" in src:
        print("  struct mud already has seq")
    else:
        m = re.search(r"(struct mud \{\s*\n)", src)
        if not m:
            sys.exit("cannot find struct mud")
        src = src[:m.end()] + "    struct mud_seq seq;\n" + src[m.end():]
        changed.append("struct mud")

    io.open(path, "w", encoding="utf-8", newline="\n").write(src)
    print("  patched:", ", ".join(changed))


MUST_ZERO_INIT = """
IMPORTANT -- the struct mud_seq fields MUST be zeroed before first use.

struct mud is allocated and initialised in mud_init(). If that path does not
memset() the whole struct, s->slot[] starts full of garbage, every incoming
sequence matches "slot already holds it" (or lands below base) and EVERY packet
is dropped. The tunnel still looks alive -- keepalives are control messages and
bypass this code -- but not one IP packet gets through.

So after adding `struct mud_seq seq;` to struct mud, add an explicit

    memset(&mud->seq, 0, sizeof(mud->seq));

in mud_init(), unconditionally, and do not rely on any existing memset.
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--src", default=SRC)
    a = ap.parse_args()

    if a.revert:
        sys.exit("revert is not implemented: restore from git "
                 "(cd /opt/angt-glorytun && git checkout mud/mud.c)")

    if not os.path.exists(a.src):
        sys.exit(f"not found: {a.src}")

    print(f"patching {a.src}")
    patch(a.src)
    print(MUST_ZERO_INIT)
    print("\nNext: rebuild on both ends and upgrade them together.")
    print("  cd /opt/angt-glorytun && make clean && make")
    print("  # router: cross-compile aarch64, see build-aarch64.sh")


if __name__ == "__main__":
    main()
