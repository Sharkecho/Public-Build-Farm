"""005: in-order delivery with a reorder buffer, via a delivery callback.

Applied after 001/002/003/004.

WHY 003 IS NOT ENOUGH
---------------------
003 dedups but delivers on arrival. With two paths 30-80 ms apart packets
arrive interleaved, so the IP stack sees constant reordering and the far side's
TCP keeps firing fast-retransmit and shrinking its window. SCTP and QUIC solve
this with a reorder buffer: hold out-of-order segments, release strictly in
sequence, give up on a hole after a bounded wait.

WHY A CALLBACK
--------------
One arrival can unblock several buffered packets, but `mud_recv()`'s contract
is "one packet per call" and the tun fd lives in bind.c, not mud.c. Measured
2026-10-24: calling tun_write() from mud.c fails to compile (`tun_fd`
undeclared, `tun_write` implicit). So mud.c gets a delivery callback that
bind.c registers with its tun fd as the context, plus mud_recv_poll() to drain
whatever is now deliverable.

MEMORY
------
64 slots x MUD_PKT_MAX_SIZE = 96 KB added to `struct mud`. Struct mud is a
file-scope global (verified), so this lands in .bss, not the stack.

TICK
----
The hole timer is aged inside mud_recv_poll(), which bind.c calls after every
arrival. That is the right frequency by construction: a hole only matters while
packets are arriving, and when none arrive there is nothing to release. This
removes the "10 Hz update loop is too coarse for a 60 ms timeout" problem that
the design note listed as the main open question.
"""

import sys
import io
import re

src = "/opt/angt-glorytun/mud/mud.c"
argv = sys.argv[1:]
if "--src" in argv:
    src = argv[argv.index("--src") + 1]

import os
src = os.path.abspath(src)
root = os.path.dirname(os.path.dirname(src))     # <root>/mud/mud.c -> <root>
HDR = os.path.join(root, "mud", "mud.h")
BIND_C = os.path.join(root, "src", "bind.c")

s = io.open(src, encoding="utf-8").read()

if "MUD_SEQ_REORDER" in s:
    print("  005: reorder buffer already present, skipping")
    raise SystemExit(0)

changed = []

# ===========================================================================
# 1. defines -- BEFORE the struct, because the struct uses them.
#    2026-10-24 bug: I put them after, and got
#      mud.c:132: error: 'MUD_SEQ_REORDER' undeclared
# ===========================================================================
OLD_DEF = "#define MUD_SEQ_WINDOW  4096"
NEW_DEF = OLD_DEF + """
#define MUD_SEQ_REORDER  64      /* payload slots held for out-of-order packets */
#define MUD_SEQ_HOLE_MS  60      /* give up on a missing packet after this long */"""

if OLD_DEF not in s:
    sys.exit("005: cannot find MUD_SEQ_WINDOW to anchor the reorder defines")
s = s.replace(OLD_DEF, NEW_DEF, 1)
changed.append("defines")

# ===========================================================================
# 2. struct fields
# ===========================================================================
OLD_STRUCT = "    unsigned char seeded;               /* an in-window packet has been accepted */"
NEW_STRUCT = OLD_STRUCT + """

    /* In-order delivery. base/slot above track *which* sequence numbers have
     * arrived; these hold the payloads so they can be released in order
     * instead of on arrival.
     *
     * 64 payloads x MUD_PKT_MAX_SIZE = 96 KB. struct mud is a file-scope
     * global, so that lands in .bss -- it would overflow the stack if struct
     * mud were ever made local. */
    uint64_t next_out;                  /* next sequence to release, 0 = unset */
    uint64_t hole_since;                /* 0 = no hole pending */
    struct {
        uint64_t seq;                   /* 0 = slot free */
        uint16_t len;
        unsigned char data[MUD_PKT_MAX_SIZE];
    } rbuf[MUD_SEQ_REORDER];"""

if OLD_STRUCT not in s:
    sys.exit("005: cannot find the seeded field to anchor the reorder struct")
s = s.replace(OLD_STRUCT, NEW_STRUCT, 1)
changed.append("struct fields")

# ===========================================================================
# 3. reorder functions -- inserted AFTER mud_timeout, which they call.
#    2026-10-24 bug: I put them earlier and got
#      mud.c:263: error: implicit declaration of 'mud_timeout'
# ===========================================================================
TIMEOUT_FN = """mud_timeout(uint64_t now, uint64_t last, uint64_t timeout)"""
idx = s.find(TIMEOUT_FN)
if idx < 0:
    sys.exit("005: cannot find mud_timeout")

# find the closing brace of mud_timeout
brace = s.find("{", idx)
depth = 0
end = None
i = brace
while i < len(s):
    if s[i] == "{":
        depth += 1
    elif s[i] == "}":
        depth -= 1
        if depth == 0:
            end = i + 1
            break
    i += 1
if not end:
    sys.exit("005: cannot find the end of mud_timeout")

FUNCS = r'''

/* ------------------------------------------------------------------------
 * In-order delivery (005).
 *
 * mud_seq_in()      enqueue one received payload; duplicates are dropped,
 *                   out-of-order arrivals are buffered.
 * mud_seq_poll()    release everything whose turn it is, through the callback
 *                   bind.c registered. Ages the hole timer.
 *
 * The hole timer is aged here rather than in a separate timer because
 * mud_seq_poll() is called once per received packet: a hole can only be
 * noticed while packets arrive, and when none arrive there is nothing to
 * release.
 * ---------------------------------------------------------------------- */

static void
mud_seq_in(struct mud_seq *s, uint64_t seq, const void *data, size_t len,
           uint64_t now)
{
    if (len > MUD_PKT_MAX_SIZE)
        return;

    if (!s->next_out)
        s->next_out = seq;              /* very first packet seen */

    if (seq < s->next_out)
        return;                          /* already released: duplicate */

    if (seq > s->next_out + MUD_SEQ_REORDER) {
        /* Too far ahead to be reordering: a real gap. Drop what is buffered
         * and jump, otherwise the stream never resumes. */
        memset(s->rbuf, 0, sizeof(s->rbuf));
        s->hole_since = 0;
        s->next_out = seq;
    }

    const unsigned off = (unsigned) (seq % MUD_SEQ_REORDER);

    if (s->rbuf[off].seq == seq)
        return;                          /* duplicate of a buffered packet */

    s->rbuf[off].seq = seq;
    s->rbuf[off].len = (uint16_t) len;
    memcpy(s->rbuf[off].data, data, len);

    if (seq > s->next_out && !s->hole_since)
        s->hole_since = now;
}

static int
mud_seq_poll(struct mud *mud)
{
    struct mud_seq *s = &mud->seq;
    int released = 0;

    if (!mud->deliver)
        return 0;

    for (;;) {
        const unsigned off = (unsigned) (s->next_out % MUD_SEQ_REORDER);

        if (s->rbuf[off].seq == s->next_out) {
            const uint16_t len = s->rbuf[off].len;
            s->rbuf[off].seq = 0;
            s->next_out++;
            s->hole_since = 0;

            if (mud->deliver(mud->deliver_ctx, s->rbuf[off].data, len) > 0)
                released++;
            continue;
        }

        /* A hole. Wait, unless it has been open too long -- then release what
         * is buffered above it, in order, and move past it. */
        if (s->hole_since &&
            mud_timeout(now_mud, s->hole_since, MUD_SEQ_HOLE_MS * MUD_ONE_MSEC)) {

            uint64_t best = 0;
            for (unsigned i = 0; i < MUD_SEQ_REORDER; i++) {
                const uint64_t q = s->rbuf[i].seq;
                if (q > s->next_out && (!best || q < best))
                    best = q;
            }
            if (!best)
                return released;         /* nothing above the hole either */

            s->next_out = best;
            s->hole_since = 0;
            continue;
        }

        return released;
    }
}

void
mud_set_deliver(struct mud *mud, mud_deliver_fn fn, void *ctx)
{
    mud->deliver = fn;
    mud->deliver_ctx = ctx;
}

int
mud_recv_poll(struct mud *mud)
{
    now_mud = mud_now(mud);
    return mud_seq_poll(mud);
}
'''

s = s[:end] + FUNCS + s[end:]
changed.append("reorder functions after mud_timeout")

# the poll helper needs a 'now'; keep it in a file-scope variable set by
# mud_recv_poll so mud_seq_poll stays a one-argument function
s = s.replace(
    "static int\nmud_seq_poll(struct mud *mud)",
    "static uint64_t now_mud;             /* set by mud_recv_poll() */\n\nstatic int\nmud_seq_poll(struct mud *mud)",
    1)

# ===========================================================================
# 4. struct mud gains the callback
# ===========================================================================
OLD_MUD = "    struct mud_seq seq;"
NEW_MUD = """    struct mud_seq seq;

    /* 005: bind.c registers this so buffered packets can be delivered without
     * mud.c knowing anything about the tun device. */
    mud_deliver_fn deliver;
    void *deliver_ctx;"""
if OLD_MUD in s:
    s = s.replace(OLD_MUD, NEW_MUD, 1)
    changed.append("struct mud callback")
else:
    print("  WARN: struct mud seq field not found; callback not added")

# ===========================================================================
# 5. mud_recv: stop delivering inline; enqueue and let poll release
# ===========================================================================
OLD_RECV = """        if (!mud_seq_accept(&mud->seq, seq, now))
            return 0;"""
NEW_RECV = """        if (!mud_seq_accept(&mud->seq, seq, now))
            return 0;

        /* 005: buffer the payload. bind.c calls mud_recv_poll() right after,
         * which releases every packet that is now in sequence. Returning 0
         * means "nothing to deliver directly" -- delivery is the callback's
         * job now. */
        mud_seq_in(&mud->seq, seq, payload + MUD_SEQ_SIZE,
                   (size_t) (ret - MUD_SEQ_SIZE), now);
        return 0;"""

if OLD_RECV not in s:
    sys.exit("005: cannot find the 003 delivery hook to replace")
s = s.replace(OLD_RECV, NEW_RECV, 1)
changed.append("mud_recv enqueue")

# ===========================================================================
# 6. header declarations
# ===========================================================================
h = io.open(HDR, encoding="utf-8").read()
if "mud_deliver_fn" not in h:
    OLD_H = "int mud_recv (struct mud *, void *, size_t);"
    NEW_H = """/* 005: in-order delivery. bind.c supplies a sink for buffered packets so
 * mud.c never needs to know about the tun device. mud_recv_poll() must be
 * called after each mud_recv() to release whatever is now in sequence. */
typedef int (*mud_deliver_fn)(void *ctx, const void *data, size_t size);
void mud_set_deliver(struct mud *, mud_deliver_fn, void *);
int  mud_recv_poll   (struct mud *);

int mud_recv (struct mud *, void *, size_t);"""
    if OLD_H not in h:
        sys.exit("005: cannot find mud_recv declaration in mud.h")
    h = h.replace(OLD_H, NEW_H, 1)
    io.open(HDR, "w", encoding="utf-8", newline="\n").write(h)
    changed.append("mud.h declarations")

# ===========================================================================
# 7. bind.c: register the sink and poll after each recv
# ===========================================================================
b = io.open(BIND_C, encoding="utf-8").read()
if "mud_set_deliver" not in b:
    # 7a. the sink function, placed after the last #include so it can see
    #     tun_write() and ip_is_valid().
    last_inc = 0
    for m in re.finditer(r'^#include .*$', b, re.M):
        last_inc = m.end()
    if not last_inc:
        sys.exit("005: bind.c has no #include lines")

    SINK = """

/* 005: sink for reorder-buffered packets. mud.c calls this for each packet it
 * releases in sequence, so mud.c never needs to know about the tun device. */
static int
mud_tun_deliver(void *ctx, const void *data, size_t size)
{
    const int fd = (int) (intptr_t) ctx;

    if (!size || !ip_is_valid(data, size))
        return 0;

    return tun_write(fd, data, size);
}
"""
    b = b[:last_inc] + SINK + b[last_inc:]
    changed.append("bind.c sink")

    # 7b. register it once the tun fd exists
    OLD_REG = "if (tun_set_persist(tun_fd, persist) == -1) {"
    NEW_REG = """/* 005: hand mud a way to deliver reorder-buffered packets. */
    mud_set_deliver(mud, mud_tun_deliver, (void *) (intptr_t) tun_fd);

    if (tun_set_persist(tun_fd, persist) == -1) {"""
    if OLD_REG not in b:
        sys.exit("005: cannot find tun_set_persist to register the sink")
    b = b.replace(OLD_REG, NEW_REG, 1)
    changed.append("bind.c register")

    # 7c. drain the buffer after every arrival
    OLD_CALL = """            int r = mud_recv(mud, buf, sizeof(buf));

            if (r > 0 && ip_is_valid(buf, r)) {
                tun_write(tun_fd, buf, (size_t)r);
                tun_can_write = 0;
            }"""
    NEW_CALL = """            int r = mud_recv(mud, buf, sizeof(buf));

            if (r > 0 && ip_is_valid(buf, r)) {
                tun_write(tun_fd, buf, (size_t)r);
                tun_can_write = 0;
            }

            /* 005: release whatever the reorder buffer can deliver in order.
             * non-zero return means at least one packet went out. */
            if (mud_recv_poll(mud) > 0)
                tun_can_write = 0;"""
    if OLD_CALL not in b:
        sys.exit("005: cannot find the mud_recv call site in bind.c")
    b = b.replace(OLD_CALL, NEW_CALL, 1)
    changed.append("bind.c poll call")

    io.open(BIND_C, "w", encoding="utf-8", newline="\n").write(b)

io.open(src, "w", encoding="utf-8", newline="\n").write(s)
print("  005: " + ", ".join(changed))
