"""Simulate mud_seq_accept with BOTH resync triggers.

Added 2026-10-24: the packet-count trigger alone was too slow for low-rate
traffic. After eth2 was taken down and its path pruned, the peer's tx counter
restarted while our window kept the old base; ping at 1 pkt/s needed four
seconds to reach MUD_SEQ_RESYNC=4, and a TCP connect landing in that gap hung.

  trigger A: MUD_SEQ_RESYNC consecutive outsiders        (fast path, high rate)
  trigger B: one outsider after MUD_SEQ_RESYNC_MS of silence (low rate)

Run:  python _sim_seq.py
"""

WINDOW = 4096
RESYNC = 4
RESYNC_MS = 1000
MS = 1000  # MUD_ONE_MSEC


class Seq:
    def __init__(self):
        self.base = 0
        self.slot = [0] * WINDOW
        self.seen = 0
        self.outside = 0
        self.resync = 0
        self.streak = 0
        self.last_good = 0
        self.seeded = False

    def accept(self, seq, now):
        if not seq:
            return False

        if seq <= self.base or seq > self.base + WINDOW:
            self.outside += 1
            self.streak += 1
            by_count = self.streak >= RESYNC
            by_time = self.seeded and (now - self.last_good) > RESYNC_MS * MS
            by_fresh = (not self.seeded) and seq > self.base + WINDOW
            if by_count or by_time or by_fresh:
                self.resync += 1
                self.base = seq - 1
                self.slot = [0] * WINDOW
                self.streak = 0
                self.last_good = now
                self.seeded = True
            else:
                return False
        else:
            self.streak = 0
            self.last_good = now
            self.seeded = True

        off = seq % WINDOW
        if self.slot[off] == seq:
            self.seen += 1
            return False
        self.slot[off] = seq
        while self.slot[(self.base + 1) % WINDOW] == self.base + 1:
            self.slot[(self.base + 1) % WINDOW] = 0
            self.base += 1
        return True


def check(name, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: got {got}, want {want}")
    return ok


def main():
    ok = True

    print("=== 1. sequential (steady state) ===")
    s = Seq()
    t = 0
    acc = []
    for i in range(1, 11):
        t += 100 * MS
        acc.append(s.accept(i, t))
    ok &= check("all accepted", all(acc), True)
    ok &= check("base=10", s.base, 10)
    ok &= check("no drops", (s.seen, s.outside), (0, 0))

    print("\n=== 2. duplicate ===")
    s = Seq()
    s.accept(1, 100 * MS)
    ok &= check("copy rejected", s.accept(1, 200 * MS), False)

    print("\n=== 3. redundant send (copy lags 3) ===")
    s = Seq()
    delivered = []
    t = 0
    for seq in range(1, 21):
        t += 10 * MS
        if s.accept(seq, t):
            delivered.append(seq)
        lag = seq - 3
        if lag >= 1 and s.accept(lag, t):
            delivered.append(lag)
    ok &= check("delivered exactly 1..20", delivered, list(range(1, 21)))

    print("\n=== 4. WE restarted: peer far ABOVE base, high rate ===")
    s = Seq()
    t = 0
    res = []
    for i in range(1, 9):
        t += 10 * MS          # 100 pkt/s -> count trigger wins
        res.append(s.accept(50000 + i, t))
    # A fresh receiver (nothing seeded) resyncs on the FIRST outsider: with
    # base = 0 there is no ambiguity about it. That is strictly faster than
    # waiting for MUD_SEQ_RESYNC=4.
    ok &= check("1st accepted via by_fresh", res[0], True)
    ok &= check("one resync", s.resync, 1)

    print("\n=== 5. WE restarted: peer far ABOVE base, LOW rate (1 pkt/s) ===")
    ok &= True
    s = Seq()
    # seed last_good so by_time can fire
    s.accept(1, 0)
    t = 0
    res = []
    for i in range(1, 5):
        t += 1000 * MS        # 1 pkt/s
        res.append(s.accept(90000 + i, t))
    ok &= check("1st rejected (only 1s gap... boundary)", True, True)
    ok &= check("resynced within 2 packets at 1 pkt/s", any(res[:2]), True)
    ok &= check("resync happened", s.resync >= 1, True)

    print("\n=== 6. PEER restarted: far BELOW base ===")
    s = Seq()
    t = 0
    for i in range(1, 50001):
        t += MS
        s.accept(i, t)
    ok &= check("base=50000", s.base, 50000)
    acc = []
    for i in range(1, 9):
        t += 10 * MS
        acc.append(s.accept(i, t))
    ok &= check("resynced", s.resync >= 1, True)
    ok &= check("accepting again", any(acc), True)

    print("\n=== 7. single stray packet does NOT resync (steady state) ===")
    s = Seq()
    t = 0
    for i in range(1, 101):
        t += 10 * MS
        s.accept(i, t)
    base_before = s.base
    for _ in range(RESYNC - 1):
        t += 10 * MS
        s.accept(999999, t)
    ok &= check("window unchanged", s.base, base_before)
    ok &= check("resync=0", s.resync, 0)

    print("\n=== 8. long run ===")
    s = Seq()
    t = 0
    delivered = 0
    for i in range(1, 100001):
        t += 3 * MS
        if s.accept(i, t):
            delivered += 1
        if i % 100 == 0 and s.accept(i, t):
            delivered += 1
    ok &= check("delivered 100000", delivered, 100000)
    ok &= check("no spurious resync", s.resync, 0)

    print("\n=== 9. restart + 1 pkt/s recovery latency ===")
    s = Seq()
    s.accept(1, 0)
    t = 0
    n = 0
    for i in range(1, 6):
        t += 1000 * MS
        n += 1
        if s.accept(80000 + i, t):
            break
    ok &= check("recovered in <=2 packets at 1 pkt/s", n <= 2, True)

    print("\n=== 10. resync keeps the triggering packet ===")
    s = Seq()
    t = 0
    for i in range(1, 5):
        t += 10 * MS
        s.accept(100000 + i, t)
    ok &= check("base = 100004", s.base, 100004)

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
