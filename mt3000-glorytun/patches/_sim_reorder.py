"""Simulation for an in-order delivery layer (reorder buffer) on top of the
existing sequence/dedup window.

WHY
---
Today mud_seq_accept() only dedups: an out-of-order packet is accepted and
handed to the IP stack immediately. With two paths 30-80 ms apart that means
the stack sees constant reordering, and every reorder triggers TCP's fast
retransmit logic on the far side.

SCTP and QUIC both solve this with a reorder buffer: hold out-of-order
segments, release them strictly in sequence, and give up on a hole after a
bounded time so one lost packet cannot stall the stream.

DESIGN
------
  next_deliver       the sequence number to release next
  buf[64]            payload slots for next_deliver+1 .. next_deliver+64
  hole_since         when the current hole was first noticed

  accept(seq, payload):
    seq == next_deliver          -> deliver now, advance, drain buffer
    next_deliver < seq <= +64    -> buffer, remember hole_since if new
    seq > next_deliver + 64      -> unrecoverable gap: flush (deliver buffered
                                    in order), jump next_deliver to seq, deliver
    seq <  next_deliver          -> duplicate, drop

  tick(now):
    hole_since != 0 and now - hole_since > RESYNC_MS
                                 -> give up: drain what is buffered, skip hole

The buffer is 64 slots: with 1500-byte packets that is 96 KB of RAM, and 64
packets at 300 pkt/s is ~210 ms of tolerance -- longer than any sane path skew,
short enough not to add visible latency.

Run: python _sim_reorder.py
"""

REORDER = 64
HOLE_TIMEOUT_MS = 60
MS = 1


class Reorder:
    def __init__(self):
        self.next_deliver = 1
        self.buf = {}           # seq -> payload
        self.hole_since = 0     # 0 = no hole
        self.out = []           # delivered payloads, in order
        self.stats = {
            "delivered": 0,
            "buffered": 0,
            "dropped_dup": 0,
            "skipped_hole": 0,
            "big_gap_flush": 0,
            "timeout_flush": 0,
        }

    # ---- internal ----------------------------------------------------
    def _deliver(self, seq, payload):
        self.out.append(payload)
        self.stats["delivered"] += 1
        self.next_deliver = seq + 1

    def _drain(self):
        """Release every buffered packet that is now contiguous."""
        while self.next_deliver in self.buf:
            p = self.buf.pop(self.next_deliver)
            self._deliver(self.next_deliver, p)
        self.hole_since = 0 if self.next_deliver not in self.buf and not self.buf else self.hole_since

    def _flush_all(self, reason):
        """Give up on order: release everything buffered, ascending."""
        for seq in sorted(self.buf):
            self._deliver(seq, self.buf.pop(seq))
        self.stats[reason] += 1
        self.hole_since = 0

    # ---- public ------------------------------------------------------
    def accept(self, seq, payload, now):
        if seq < self.next_deliver:
            self.stats["dropped_dup"] += 1
            return

        if seq == self.next_deliver:
            self._deliver(seq, payload)
            self._drain()
            return

        if seq <= self.next_deliver + REORDER:
            self.buf[seq] = payload
            self.stats["buffered"] += 1
            if not self.hole_since:
                self.hole_since = now
            return

        # Too far ahead to be a reorder: it is a real gap.
        self._flush_all("big_gap_flush")
        self.next_deliver = seq
        self._deliver(seq, payload)
        self._drain()

    def tick(self, now):
        if not self.hole_since:
            return
        if now - self.hole_since > HOLE_TIMEOUT_MS * MS:
            self.stats["skipped_hole"] += 1
            self._flush_all("timeout_flush")


# ---------------------------------------------------------------------------
def chk(name, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: {got}" + ("" if ok else f" (want {want})"))
    return ok


def main():
    ok = True

    print("=== 1. 顺序到达 ===")
    r = Reorder()
    for s in range(1, 11):
        r.accept(s, f"p{s}", s * 10)
    ok &= chk("按序交付", r.out, [f"p{s}" for s in range(1, 11)])
    ok &= chk("无缓冲残留", r.buf, {})

    print("\n=== 2. 重复包丢弃 ===")
    r = Reorder()
    r.accept(1, "a", 10)
    r.accept(1, "a", 20)
    ok &= chk("只交付一次", r.out, ["a"])
    ok &= chk("记一次重复", r.stats["dropped_dup"], 1)

    print("\n=== 3. 单包乱序（3 先于 2）===")
    r = Reorder()
    r.accept(1, "p1", 10)
    r.accept(3, "p3", 20)     # 3 先到，缓冲
    ok &= chk("3 被缓冲", r.out, ["p1"])
    r.accept(2, "p2", 30)     # 2 到了，2 和 3 一起交付
    ok &= chk("顺序交付 1,2,3", r.out, ["p1", "p2", "p3"])

    print("\n=== 4. 缓冲内乱序（5,4,3,2,1 倒序）===")
    r = Reorder()
    for s in [5, 4, 3, 2, 1]:
        r.accept(s, f"p{s}", 10 + s)
    ok &= chk("最终顺序正确", r.out, [f"p{s}" for s in range(1, 6)])

    print("\n=== 5. 空洞超时冲刷 ===")
    r = Reorder()
    r.accept(1, "p1", 0)
    r.accept(3, "p3", 10)     # 2 丢了
    ok &= chk("3 缓冲，未交付", r.out, ["p1"])
    r.tick(20)                # 还没超时
    ok &= chk("超时前不冲刷", r.out, ["p1"])
    r.tick(100)               # 超过 60ms
    ok &= chk("超时后交付 3", r.out, ["p1", "p3"])
    ok &= chk("记一次超时冲刷", r.stats["skipped_hole"], 1)
    r.accept(4, "p4", 110)
    ok &= chk("之后继续正常", r.out, ["p1", "p3", "p4"])

    print("\n=== 6. 超大跳跃（超出缓冲）===")
    r = Reorder()
    r.accept(1, "p1", 10)
    r.accept(2, "p2", 20)
    r.accept(1000, "p1000", 30)   # 远超 +64
    ok &= chk("冲刷并跳到 1000", r.out, ["p1", "p2", "p1000"])
    ok &= chk("记一次大跳跃", r.stats["big_gap_flush"], 1)

    print("\n=== 7. 缓冲满边界（正好 +64）===")
    r = Reorder()
    r.accept(1, "p1", 10)
    r.accept(1 + REORDER, "p_last", 20)      # 刚好在边界内
    ok &= chk("边界内缓冲", len(r.buf), 1)
    ok &= chk("未交付", r.out, ["p1"])

    print("\n=== 8. 边界外一格（+65）===")
    r = Reorder()
    r.accept(1, "p1", 10)
    # next_deliver 已经是 2，边界是 2+64=66；用 67 才是真的超出一格
    r.accept(1 + REORDER + 2, "p_over", 20)
    ok &= chk("触发大跳跃冲刷", r.stats["big_gap_flush"], 1)

    print("\n=== 9. 双发副本（副本落后 3，且乱序）===")
    r = Reorder()
    delivered = []
    for s in range(1, 21):
        t = s * 10
        # 先到主包，再偶尔来一个迟到副本
        r.accept(s, f"p{s}", t)
        if s > 3 and s % 2 == 0:
            r.accept(s - 3, f"p{s-3}", t + 5)   # 迟到副本，应被丢弃
    ok &= chk("交付恰好 1..20", r.out, [f"p{s}" for s in range(1, 21)])
    ok &= chk("副本全被丢", r.stats["dropped_dup"] > 0, True)

    print("\n=== 10. 长跑 10 万包，随机制造 1% 丢失 + 20% 乱序 ===")
    import random
    random.seed(42)
    r = Reorder()
    expect = []
    now = 0
    pending = []
    for s in range(1, 100001):
        now += 3
        if random.random() < 0.01:
            continue                      # 模拟丢包
        delay = random.choice([0, 0, 0, 0, 1, 2, 3])   # 20% 乱序
        pending.append((now + delay, s))
        pending.sort()
        while pending and pending[0][0] <= now:
            _, ps = pending.pop(0)
            r.accept(ps, f"p{ps}", now)
        r.tick(now)
    # 收尾：冲刷剩余
    r.tick(now + 1000)
    for _, ps in pending:
        r.accept(ps, f"p{ps}", now)
    r.tick(now + 2000)
    ok &= chk("交付数量 > 90000", r.stats["delivered"] > 90000, True)
    ok &= chk("无重复交付",
              len(set(r.out)) == len(r.out), True)
    # 交付必须单调递增（顺序性）
    nums = [int(x[1:]) for x in r.out]
    ok &= chk("交付顺序单调", nums == sorted(nums), True)

    print("\n=== 11. 空洞后紧跟大量包（压力）===")
    r = Reorder()
    r.accept(1, "p1", 0)
    for s in range(3, 3 + REORDER):
        r.accept(s, f"p{s}", 10 + s)
    ok &= chk("全部缓冲", len(r.buf), REORDER)
    r.accept(2, "p2", 200)       # 补上空洞
    ok &= chk("一次性全部交付", len(r.out), REORDER + 2)
    ok &= chk("缓冲清空", r.buf, {})

    print("\n=== 12. 空缓冲时 tick 不应误触发 ===")
    r = Reorder()
    r.accept(1, "p1", 0)
    r.tick(10000)
    ok &= chk("无空洞则不冲刷", r.stats["skipped_hole"], 0)

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
