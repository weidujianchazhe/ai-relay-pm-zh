# -*- coding: utf-8 -*-
"""concurrency_matrix.py —— 并发不变量矩阵（**故障注入**，不是代码阅读）

用法：python concurrency_matrix.py [--quick]

与 selftest_gates 的分工：那个验证「门禁能否拦住错误」，本脚本验证**另一件事**——
「并发与故障下，系统究竟能保证哪些不变量」。互补，不能互相替代。

输出一张**保证等级表**，五档：强保证 / 条件保证 / 最终一致 / 仅事后检测 / 完全不保证。
依据：references/concurrency.md §0。
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import run, usage_exit  # noqa: E402
import lease  # noqa: E402


def _w_cas(root_s, i, q):
    import lease as L
    root = Path(root_s)
    try:
        okk, why, _ = L.write_cas(root / "REVIEWS.md", "W%d\n" % i, L.hash_of_text("BASE\n"))
        q.put(("ok" if okk else "rej", i, why[:60]))
    except Exception as e:
        q.put(("EXC", i, "%s: %s" % (type(e).__name__, e)))


def _w_append(root_s, i, q):
    import lease as L
    root = Path(root_s)
    try:
        okk, why = L.shared_append(root, root / "REVIEWS.md", "R%d" % i, "矩阵")
        q.put(("ok" if okk else "rej", i, why[:60]))
    except Exception as e:
        q.put(("EXC", i, "%s: %s" % (type(e).__name__, e)))


def _w_claim(root_s, i, q):
    import lease as L
    root = Path(root_s)
    try:
        okk, why = L.claim(root, root / "tasks" / "EN0001_x.md", "win-a%d" % i, 30)
        q.put(("ok" if okk else "rej", i, why[:60]))
    except Exception as e:
        q.put(("EXC", i, "%s: %s" % (type(e).__name__, e)))


def _spawn(target, root, n, timeout=120):
    """起 n 个进程跑同一动作；**共用一个队列**（Windows spawn：路径按参数传）。"""
    q = mp.Queue()
    ps = [mp.Process(target=target, args=(str(root), i, q)) for i in range(n)]
    for p in ps:
        p.start()
    for p in ps:
        p.join(timeout)
    out = []
    while not q.empty():
        out.append(q.get())
    return out


def _fresh():
    root = Path(tempfile.mkdtemp(prefix="matrix_"))
    (root / "tasks").mkdir(parents=True, exist_ok=True)
    (root / "REVIEWS.md").write_text("# 通道\n\n", encoding="utf-8")
    (root / "tasks" / "EN0001_x.md").write_text(
        "# 卡\n\n- **承接**：—\n- **并发元数据**：owner=—；revision=0；fencing=0；NORMALIZED-SHA256=—\n",
        encoding="utf-8")
    return root


# ── 用例：每个返回 (编号, 名称, 等级, 通过?, 说明) ──────────────────
def t_cas_race(n):
    """I1 并发 CAS：最多一个成功 / 其余明确失败 / 无异常 / 内容=成功者。"""
    root = _fresh()
    (root / "REVIEWS.md").write_text("BASE\n", encoding="utf-8")
    res = _spawn(_w_cas, root, n)
    ok = [r for r in res if r[0] == "ok"]
    exc = [r for r in res if r[0] == "EXC"]
    body = (root / "REVIEWS.md").read_text(encoding="utf-8").strip()
    good = len(ok) == 1 and not exc and body == "W%d" % ok[0][1]
    shutil.rmtree(root, ignore_errors=True)
    return ("I1", "并发 CAS 提交（%d 进程，同一前置）" % n, "强保证", good,
            "成功 %d · 拒绝 %d · 异常 %d · 内容=成功者 %s" % (len(ok), len(res) - len(ok) - len(exc), len(exc), body == ("W%d" % ok[0][1]) if ok else False))


def t_append_race(n):
    """I2 并发追加：成功数 == 落盘行数（不许丢写、不许误拒）。"""
    root = _fresh()
    res = _spawn(_w_append, root, n)
    ok = [r for r in res if r[0] == "ok"]
    exc = [r for r in res if r[0] == "EXC"]
    lines = [l for l in (root / "REVIEWS.md").read_text(encoding="utf-8").splitlines() if l.startswith("R")]
    good = len(ok) == n and len(lines) == n and not exc
    shutil.rmtree(root, ignore_errors=True)
    return ("I2", "并发追加（%d 进程）" % n, "强保证", good,
            "成功 %d · 落盘 %d · 异常 %d" % (len(ok), len(lines), len(exc)))


def t_claim_race():
    """I3 并发认领：恰好一个成功，且卡上 owner 就是成功者（不许假成功）。"""
    root = _fresh()
    res = _spawn(_w_claim, root, 2)
    ok = [r for r in res if r[0] == "ok"]
    owner = lease.lease_state(root / "tasks" / "EN0001_x.md")["owner"]
    good = len(ok) == 1 and owner == "win-a%d" % ok[0][1]
    shutil.rmtree(root, ignore_errors=True)
    return ("I3", "并发认领（2 进程同一张卡）", "强保证", good,
            "成功 %d · owner=%s" % (len(ok), owner))


def t_fencing_states():
    """I4 令牌三态：旧令牌拒 / 更大令牌拒 / 无令牌放行（opt-in 边界）。"""
    root = _fresh()
    card = root / "tasks" / "EN0001_x.md"
    lease.claim(root, card, "win-a", 30)
    t1 = int(lease.lease_state(card)["fencing"])
    lease.claim(root, card, "win-b", 30, steal="矩阵测试抢占")
    t2 = int(lease.lease_state(card)["fencing"])
    old_ok = lease.guard(root, card, "win-b", token=t1)[0]
    future_ok = lease.guard(root, card, "win-b", token=t2 + 1000)[0]
    no_tok_ok = lease.guard(root, card, "win-b")[0]
    good = (old_ok is False) and (future_ok is False) and (no_tok_ok is True)
    shutil.rmtree(root, ignore_errors=True)
    return ("I4", "fencing 令牌三态（旧 / 超大 / 不带）", "条件保证", good,
            "旧=%s（应拒）· 超大=%s（应拒）· 不带=%s（opt-in 放行）· 令牌 %d→%d" % (old_ok, future_ok, no_tok_ok, t1, t2))


def t_lockfile_no_owner():
    """I5 残留锁文件不阻塞：锁文件**存在**不等于有人持有——ownership 在 **fd 的 OS 建议锁**上，
    不在「文件存不存在」（本实现已无锁龄 / 抢占概念）。"""
    root = _fresh()
    p = root / "REVIEWS.md"
    lp = lease._lock_path(p)
    lp.write_text("99999 残留\n", encoding="utf-8")   # 伪造一个崩溃残留的锁文件
    import time as _t
    _t.sleep(0.05)
    okk, why = lease.shared_append(root, p, "- 残留后写入", "崩溃恢复")
    good = bool(okk)
    shutil.rmtree(root, ignore_errors=True)
    return ("I5", "崩溃残留锁文件不阻塞", "最终一致", good,
            "残留锁文件存在时写入 %s · 锁文件仍在新路径上=%s" % ("成功" if good else "失败：" + why[:40], lp.exists()))


def t_lock_timeout():
    """I6 等锁超时：**明确失败**，不挂死、不抛异常（持有者由**真锁**占住，不是伪造锁文件）。"""
    root = _fresh()
    p = root / "REVIEWS.md"
    holder, _w = lease.acquire_lock(p)      # 本进程真持锁（OS 锁：另一句柄取不到）
    old_t = lease.LOCK_TIMEOUT
    lease.LOCK_TIMEOUT = 0.3
    try:
        okk, why = lease.shared_append(root, p, "- 不该写进去", "等锁超时")
    finally:
        lease.LOCK_TIMEOUT = old_t
    body = p.read_text(encoding="utf-8")
    good = (okk is False) and ("不该写进去" not in body)
    shutil.rmtree(root, ignore_errors=True)
    return ("I6", "等锁超时的行为（明确失败，不挂死）", "强保证", good,
            "返回 %s，内容未被写入 %s" % (okk, "不该写进去" not in body))


def t_bypass_detect():
    """I7 绕过入口直接改文件：挡不住，但**一定被发现**。"""
    root = _fresh()
    card = root / "tasks" / "EN0001_x.md"
    lease.claim(root, card, "win-a", 30)
    txt = card.read_text(encoding="utf-8")
    card.write_text(txt.replace("# 卡", "# 卡（绕过脚本手改）", 1), encoding="utf-8")
    st = lease.lease_state(card)
    good = bool(st["drifted"])
    shutil.rmtree(root, ignore_errors=True)
    return ("I7", "绕过入口的直接编辑", "仅事后检测", good,
            "漂移检测 drifted=%s（改写当场挡不住）" % st["drifted"])


def t_archive_locked():
    """I8 归档的锁内行为：守卫与移动是一个整体——锁被占时**明确失败且不半做**，释放后重跑成功。"""
    import subprocess
    root = _fresh()
    card = root / "tasks" / "EN0001_x.md"
    lease.claim(root, card, "win-a", 30)
    holder, _w = lease.acquire_lock(card)   # 本进程真持卡锁（模拟另一个 Agent 正持卡）
    env = dict(os.environ, WSX_LOCK_TIMEOUT="1",
               PYTHONDONTWRITEBYTECODE="1")
    co = str(Path(__file__).resolve().parent / "closeout.py")
    r1 = subprocess.run([sys.executable, "-B", co, str(root), "card-archive", "EN0001_x.md", "--ai", "win-a"],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, timeout=120)
    moved_when_locked = not card.exists()
    lease.release_lock(holder)
    r2 = subprocess.run([sys.executable, "-B", co, str(root), "card-archive", "EN0001_x.md", "--ai", "win-a"],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, timeout=120)
    moved_after = (root / "archives" / "done" / "EN0001_x.md").exists()
    good = (r1.returncode != 0) and (not moved_when_locked) and (r2.returncode == 0) and moved_after
    shutil.rmtree(root, ignore_errors=True)
    return ("I8", "归档的锁内行为（锁被占 / 释放后重跑）", "强保证", good,
            "锁被占：exit=%d 且未移动=%s；释放后：exit=%d 且已移动=%s"
            % (r1.returncode, not moved_when_locked, r2.returncode, moved_after))

def t_pause_no_takeover():
    """I9 **暂停模型**：持有者存活但被挂起（伪造锁龄超限）→ 另一写者**不得接管**；释放后仍可接管。

    与崩溃模型的区别：崩溃时 OS 会释放锁（新写者应能接管）；挂起时锁**仍然属于持有者**。
    若按"锁龄"抢占，挂起就会被误判成崩溃——这正是本用例断言"不得接管"的理由。
    """
    root = _fresh()
    p = root / "REVIEWS.md"
    lk1, w1 = lease.acquire_lock(p)
    lp = lease._lock_path(p)
    old = time.time() - 9999
    os.utime(lp, (old, old))          # 伪造：把锁文件 mtime 改得很旧（模拟进程被挂起很久）
    old_to = lease.LOCK_TIMEOUT
    lease.LOCK_TIMEOUT = 1.0
    lk2, w2 = lease.acquire_lock(p)   # 另一个写者
    no_takeover = (lk1 is not None) and (lk2 is None)
    if lk2:
        lease.release_lock(lk2)
    lease.release_lock(lk1)
    lease.LOCK_TIMEOUT = 5.0
    lk3, _w3 = lease.acquire_lock(p)  # 持有者已释放 → 应可接管（崩溃/正常释放语义）
    if lk3:
        lease.release_lock(lk3)
    lease.LOCK_TIMEOUT = old_to
    good = no_takeover and (lk3 is not None)
    shutil.rmtree(root, ignore_errors=True)
    return ("I9", "暂停模型：挂起期间不得被接管", "强保证", good,
            "挂起时接管=%s（应拒）· 释放后接管=%s（应可）· 锁模式=%s"
            % ("成功" if lk2 else "被拒", "成功" if lk3 else "失败", getattr(lk1, "mode", "?")))


    """I10 放锁**不删锁文件**：锁文件是装置（工作区生命周期内永久），归属只由 fd 上的 OS 锁决定。"""
    root = _fresh()
    p = root / "REVIEWS.md"
    lk, _w = lease.acquire_lock(p)
    lp = lease._lock_path(p)
    lease.release_lock(lk)
    kept = lp.exists()
    lk2, _w2 = lease.acquire_lock(p)
    reusable = lk2 is not None
    lease.release_lock(lk2)
    good = kept and reusable
    shutil.rmtree(root, ignore_errors=True)
    return ("I10", "放锁不删锁文件（装置永久化）", "强保证", good,
            "放锁后文件仍在=%s（应 True）· 可再次加锁=%s（应 True）" % (kept, reusable))


def t_release_ownership():
    """I10 放锁**不删锁文件**：锁文件是装置（工作区生命周期内永久），归属只由 fd 上的 OS 锁决定。"""
    root = _fresh()
    p = root / "REVIEWS.md"
    lk, _w = lease.acquire_lock(p)
    lp = lease._lock_path(p)
    lease.release_lock(lk)
    kept = lp.exists()
    lk2, _w2 = lease.acquire_lock(p)
    reusable = lk2 is not None
    lease.release_lock(lk2)
    good = kept and reusable
    shutil.rmtree(root, ignore_errors=True)
    return ("I10", "放锁不删锁文件（装置永久化）", "强保证", good,
            "放锁后文件仍在=%s（应 True）· 可再次加锁=%s（应 True）" % (kept, reusable))

def t_handoff_invariant():
    """I11 **release↔acquire handoff 不变量**。

    **漏洞形态**：若释放路径是 unlock → close → unlink，中间可被插入——
    B 拿到 inode1 的锁后，A 的 unlink 把路径删掉，C 再建 inode2 加锁 → 同一路径两个持锁者。
    修法：从释放路径**删掉 unlink**（锁文件永久化），path→inode 不再漂移。
    本用例断言三件事：跨 handoff 仍互斥 · 路径始终指向**同一个 inode** · 锁文件始终存在。
    """
    root = _fresh()
    p = root / "REVIEWS.md"
    lp = lease._lock_path(p)
    a, _w = lease.acquire_lock(p)
    ino0 = lp.stat().st_ino if lp.exists() else 0
    lease.release_lock(a)
    b, _w2 = lease.acquire_lock(p)
    old_to = lease.LOCK_TIMEOUT
    lease.LOCK_TIMEOUT = 0.5
    c = None
    try:
        c, _w3 = lease.acquire_lock(p)
    finally:
        lease.LOCK_TIMEOUT = old_to
    ino1 = lp.stat().st_ino if lp.exists() else 0
    lease.release_lock(b)
    if c:
        lease.release_lock(c)
    exclusive = (b is not None) and (c is None)
    same_inode = (ino0 == 0) or (ino1 == 0) or (ino0 == ino1)
    persists = lp.exists()
    good = exclusive and same_inode and persists
    shutil.rmtree(root, ignore_errors=True)
    return ("I11", "release↔acquire handoff 不变量", "强保证", good,
            "B 持有时 C 被拒=%s · inode 未漂移=%s（%s→%s）· 锁文件存在=%s"
            % (exclusive, same_inode, ino0, ino1, persists))


def t_sweep_active_tmp():
    """I12 临时文件生命周期：`sweep_temp` **不删活跃写者的 tmp**（新的不删、旧的才删），且**绝不删锁文件**。"""
    root = _fresh()
    fresh = root / "REVIEWS.md.tmp.999.aaa"
    fresh.write_text("正在写\n", encoding="utf-8")          # 活跃写者的 tmp：刚创建，mtime 新
    stale = root / "REVIEWS.md.tmp.888.bbb"
    stale.write_text("崩溃残留\n", encoding="utf-8")
    old = time.time() - 3600
    os.utime(stale, (old, old))                            # 伪造成 1 小时前的崩溃残留
    lk = root / "REVIEWS.md.lock"
    lk.write_text("epoch=1 token=x\n", encoding="utf-8")
    os.utime(lk, (old, old))                               # 锁文件再旧也**绝不删**（防 path→inode 漂移）
    n, _names = lease.sweep_temp(root)
    ok_fresh, ok_stale, ok_lock = fresh.exists(), not stale.exists(), lk.exists()
    good = ok_fresh and ok_stale and ok_lock
    shutil.rmtree(root, ignore_errors=True)
    return ("I12", "sweep 不碰活跃 tmp / 不删锁文件", "强保证", good,
            "活跃 tmp 保留=%s · 旧残留清除=%s · 锁文件保留=%s（共清理 %d）"
            % (ok_fresh, ok_stale, ok_lock, n))

def main():
    ap = argparse.ArgumentParser(description="并发不变量矩阵（故障注入）")
    usage_exit(ap)
    ap.add_argument("--quick", action="store_true", help="缩小进程数")
    args = ap.parse_args()
    n = 4 if args.quick else 6
    rows = [t_cas_race(n), t_append_race(n if not args.quick else 4),
            t_claim_race(), t_fencing_states(), t_lockfile_no_owner(),
            t_lock_timeout(), t_bypass_detect(), t_archive_locked(),
            t_pause_no_takeover(), t_release_ownership(), t_handoff_invariant(),
            t_sweep_active_tmp()]
    print("== 并发不变量矩阵（%s）==" % ("quick" if args.quick else "完整"))
    print("%-4s %-34s %-10s %-6s %s" % ("编号", "不变量", "保证等级", "结果", "说明"))
    print("-" * 118)
    bad = 0
    for num, name, tier, okk, detail in rows:
        if not okk:
            bad += 1
        print("%-4s %-34s %-10s %-6s %s" % (num, name[:34], tier, "通过" if okk else "**失败**", detail[:60]))
    print("-" * 118)
    print("不变量 %d 条 · 通过 %d · 失败 %d" % (len(rows), len(rows) - bad, bad))
    print()
    print("== 未纳入本脚本的（只能声明，不能自动验证）==")
    print("   跨机器 / 网络文件系统（NFS/SMB）意义上的互斥        → 完全不保证")
    print("   证据（provenance）的真伪                            → 只能提高伪造成本，不能证明不可伪造")
    print("   多文件操作的「全或无」                              → 完全不保证（可收敛，见 references/concurrency-internals.md §1）")
    return summary(bad)


def summary(bad):
    if bad:
        print("[问题] 有 %d 条不变量未成立——并发语义退化，**不要**以此版本承诺并发安全" % bad)
        return 1
    print("[通过] 全部可自动验证的不变量成立（边界项见上）")
    return 0


if __name__ == "__main__":
    mp.freeze_support()
    sys.exit(run(main))
