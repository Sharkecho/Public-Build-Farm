"""Simulate mud_seq_accept WITH resynchronisation.

The first version had no resync, which deadlocked a live tunnel on 2026-10-24:
one side restarted, its base reset to 0, the peer's tx was already far ahead,
every packet fell outside the window and was dropped forever. Upload kept
working (7.8 Mbit/s) while download collapsed to 81 kbit/s, and ping stayed at
0% loss because measurement messages never reach this code.

Rule under test: MUD_SEQ_RESYNC consecutive out-of-window packets realign the
window to the current sequence.

Run:  python _sim_seq.py
"""

WINDOW = 4096
RESYNC = 4


class Seq:
    def __init__(self):
        self.base = 0
        self.slot = [0] * WINDOW
        self.seen = 0
        self.outside = 0
        self.resync = 0
        self.streak = 0

    def accept(self, seq):
        if not seq:
            return False

        if seq <= self.base or seq > self.base + WINDOW:
            self.outside += 1
            self.streak += 1
            if self.streak >= RESYNC:
                self.resync += 1
                self.base = seq - 1
                self.slot = [0] * WINDOW
                self.streak = 0
                # fall through: accept this packet
            else:
                return False
        else:
            self.streak = 0

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

    print("=== 1. sequential ===")
    s = Seq()
    ok &= check("all 10 accepted", all(s.accept(i) for i in range(1, 11)), True)
    ok &= check("base=10", s.base, 10)
    ok &= check("no dup/drop", (s.seen, s.outside), (0, 0))

    print("\n=== 2. duplicate ===")
    s = Seq()
    ok &= check("first accepted", s.accept(1), True)
    ok &= check("copy rejected", s.accept(1), False)
    ok &= check("copy dropped (below base -> outside)", s.outside, 1)

    print("\n=== 3. redundant send (copy lags 3) ===")
    s = Seq()
    delivered = []
    for seq in range(1, 21):
        if s.accept(seq):
            delivered.append(seq)
        lag = seq - 3
        if lag >= 1 and s.accept(lag):
            delivered.append(lag)
    ok &= check("delivered exactly 1..20", delivered, list(range(1, 21)))

    print("\n=== 4. WE restarted: peer seq far ABOVE our base ===")
    s = Seq()
    for i in range(1, 9):
        r = s.accept(50000 + i)
        if i < RESYNC:
            ok &= check(f"far #{i} rejected", r, False)
        else:
            ok &= check(f"far #{i} resynced+accepted", r, True)
    ok &= check("one resync", s.resync, 1)
    ok &= check("next sequential accepted", s.accept(50009), True)

    print("\n=== 5. PEER restarted: seq far BELOW our base ===")
    s = Seq()
    for i in range(1, 50001):
        s.accept(i)
    ok &= check("base=50000", s.base, 50000)
    delivered = []
    for i in range(1, 9):
        if s.accept(i):
            delivered.append(i)
    ok &= check("starts accepting after resync", len(delivered) > 0, True)
    ok &= check("one resync", s.resync, 1)
    ok &= check("base realigned near 1", s.base < 100, True)

    print("\n=== 6. a single stray packet does not resync ===")
    s = Seq()
    for i in range(1, 101):
        s.accept(i)
    base_before = s.base
    for _ in range(RESYNC - 1):
        s.accept(999999)
    ok &= check("window unchanged", s.base, base_before)
    ok &= check("resync=0", s.resync, 0)

    print("\n=== 7. after resync, genuinely old packets still rejected ===")
    s = Seq()
    for i in range(1, 9):
        s.accept(60000 + i)
    ok &= check("resynced", s.resync, 1)
    ok &= check("pre-resync seq rejected", s.accept(100), False)

    print("\n=== 8. long run ===")
    s = Seq()
    delivered = 0
    for i in range(1, 100001):
        if s.accept(i):
            delivered += 1
        if i % 100 == 0 and s.accept(i):
            delivered += 1
    ok &= check("delivered 100000", delivered, 100000)
    ok &= check("dropped 1000 copies (counted in outside)", s.outside, 1000)
    ok &= check("no spurious resync", s.resync, 0)

    print("\n=== 9. repeated restarts ===")
    s = Seq()
    for cycle in range(5):
        start = 1 + cycle * 10000
        for i in range(start, start + 100):
            s.accept(i)
    ok &= check("4 resyncs", s.resync, 4)
    accepted = any(s.accept(50000 + i) for i in range(1, 6))
    ok &= check("still accepting after 4 more", accepted, True)

    print("\n=== 10. resync keeps the packet that triggered it ===")
    s = Seq()
    for i in range(1, 5):
        s.accept(100000 + i)
    ok &= check("base = 100004", s.base, 100004)

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
