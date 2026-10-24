"""004: duplicate onto legs whose probes go unanswered.

Applied after 001/002/003. 001's loop skipped any leg with !alt->ok:

    if (alt == path || !alt->ok)
        continue;

`ok` is cleared at the top of every mud_update() tick and set again only when
that leg's probe messages are being answered:

    if (path->msg.sent >= MUD_MSG_SENT_MAX) { ... }   <- ok stays 0
    else if (mud_path_is_ok(mud, path)) path->ok = 1;

A leg behind a lossy carrier NAT mapping sits at msg.sent == 5 permanently, so
its ok never becomes 1 and duplication skips it for ever. Measured 2026-10-24
on the iPhone leg: state UP, mtu.ok 1472, tx.loss 0, yet path->ok == 0 (printed
DEGRADED) and the eth0:eth2 packet ratio was 11.7:1 instead of 1:1 -- with the
flag file correctly reading "1".

That leg is exactly why redundancy exists: unreliable probes, working data
path. Sending the copy anyway costs bandwidth when the leg is dead, but the
receiver dedups, so it can never cost correctness.
"""

import sys
import io

src = "/opt/angt-glorytun/mud/mud.c"
argv = sys.argv[1:]
if "--src" in argv:
    src = argv[argv.index("--src") + 1]

s = io.open(src, encoding="utf-8").read()

if "alt->state < MUD_UP" in s:
    print("  004: already relaxed, skipping")
    raise SystemExit(0)

OLD = """            if (alt == path || !alt->ok)
                continue;
"""

NEW = """            /* Judge a leg by its state and MTU, not by its `ok` flag.
             *
             * `ok` is cleared at the top of every mud_update() tick and set
             * again only when that leg's probe messages are being answered:
             *
             *     if (path->msg.sent >= MUD_MSG_SENT_MAX) { ... }  <- no ok
             *     else if (mud_path_is_ok(mud, path)) path->ok = 1;
             *
             * A leg behind a lossy carrier NAT mapping sits at msg.sent == 5
             * permanently, so its `ok` never becomes 1 and duplication skips it
             * for ever. Measured 2026-10-24 on the iPhone leg: state UP, mtu.ok
             * 1472, tx.loss 0, yet path->ok == 0 (printed DEGRADED) and the
             * eth0:eth2 packet ratio was 11.7:1 instead of 1:1, with the flag
             * file correctly reading "1".
             *
             * That leg is exactly why redundancy exists: unreliable probes,
             * working data path. Sending the copy anyway costs bandwidth when
             * the leg is dead, but the receiver dedups, so it can never cost
             * correctness.
             */
            if (alt == path)
                continue;

            if (alt->state < MUD_UP || !alt->mtu.ok)
                continue;
"""

if OLD not in s:
    print("  004: pattern not found -- 001 may not be applied")
    raise SystemExit(1)

s = s.replace(OLD, NEW, 1)
io.open(src, "w", encoding="utf-8", newline="\n").write(s)
print("  004: relaxed the duplication condition")
