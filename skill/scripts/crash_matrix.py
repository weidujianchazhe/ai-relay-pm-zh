# -*- coding: utf-8 -*-
"""crash_matrix.py —— 崩溃注入专项：**真杀进程**，验证半事务与残留能否收敛

用法：python crash_matrix.py

与 concurrency_matrix 的分工：那个测**并发**（多进程同时写），本脚本测**崩溃**——
在写盘的各个时点把进程杀掉，然后问三个问题：
  ① 目标文件被破坏了吗？  ② 留下了什么残留？  ③ 重跑能不能收敛？

三个杀点（都是真实时点，不是模拟）：
  C1 写完临时文件、尚未原子替换   → 目标应保持**旧内容**；残留 tmp + 锁；重跑收敛；sweep 可清
  C2 刚取到锁、还没写任何东西     → 锁残留；短超时写者**明确失败**；锁龄超限后可抢占
  C3 已原子替换、尚未释放锁       → **内容已更新**（不丢），锁残留；重跑正常
  C4 半个事务（冷区已写、热区没有）→ 重跑**拒绝重复**（幂等），冷区不重复 —— **需人工对齐，不是自动收敛**

"""
from __future__ import annotations

import multiprocessing as mp
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import run  # noqa: E402
import lease  # noqa: E402

HERE = Path(__file__).resolve().parent


# ── 子进程：在指定时点停住（等父进程来杀）──
def _child(root_s, mode, marker_s, q):
    import lease as L
    root = Path(root_s)
    p = root / "REVIEWS.md"
    if mode == "hold_lock":
        L.acquire_lock(p)
    elif mode == "after_tmp":
        L.acquire_lock(p)
        tmp = p.with_name("%s.tmp.%d.%s" % (p.name, os.getpid(), "c0ffee"))
        tmp.write_text("半成品（不该被看到）\n", encoding="utf-8")
    elif mode == "after_replace":
        _lk, _w = L.acquire_lock(p)
        cur = p.read_text(encoding="utf-8")
        L._write_locked(p, cur + "- 已替换\n", _lk)
    Path(marker_s).write_text(mode, encoding="utf-8")
    time.sleep(60)      # 停住，等被杀


def _crash(root, mode, wait=20.0):
    """起子进程 → 等它就位 → **terminate（真杀）**。返回是否就位成功。"""
    marker = root / ("marker_" + mode)
    q = mp.Queue()
    p = mp.Process(target=_child, args=(str(root), mode, str(marker), q))
    p.start()
    ok = False
    for _ in range(int(wait / 0.05)):
        if marker.exists():
            ok = True
            break
        time.sleep(0.05)
    p.terminate()
    p.join(10)
    return ok


def _fresh():
    root = Path(tempfile.mkdtemp(prefix="crash_"))
    (root / "tasks").mkdir(parents=True, exist_ok=True)
    (root / "reports").mkdir(parents=True, exist_ok=True)
    (root / "archives").mkdir(parents=True, exist_ok=True)
    (root / "REVIEWS.md").write_text("# 通道\n\n- 原始行\n", encoding="utf-8")
    return root


def c1_crash_after_tmp():
    root = _fresh()
    p = root / "REVIEWS.md"
    before = p.read_text(encoding="utf-8")
    ok = _crash(root, "after_tmp")
    intact = p.read_text(encoding="utf-8") == before
    tmps = list(root.glob("*.tmp.*"))
    locks = list(root.glob("*.lock"))
    # 重跑收敛：把残留锁当作崩溃残留，允许抢占
    time.sleep(0.05)
    okk, why = lease.shared_append(root, p, "- 崩溃后重跑写入", "崩溃恢复")
    converged = bool(okk) and "崩溃后重跑写入" in p.read_text(encoding="utf-8")
    swept, names = lease.sweep_temp(root, older_than=0.01)
    shutil.rmtree(root, ignore_errors=True)
    return ("C1", "崩溃于「写完 tmp、未替换」", "最终一致",
            ok and intact and len(tmps) >= 1 and len(locks) >= 1 and converged and swept >= 1,
            "就位=%s · 目标未被破坏=%s · 残留 tmp=%d 锁=%d · 重跑收敛=%s · sweep 清理=%d"
            % (ok, intact, len(tmps), len(locks), converged, swept))


def c2_crash_holding_lock():
    root = _fresh()
    p = root / "REVIEWS.md"
    ok = _crash(root, "hold_lock")
    locks = list(root.glob("*.lock"))
    # 现行语义：崩溃时**操作系统立即释放锁** → 新写者立刻接管，
    #  注意与暂停模型的区别：暂停时锁不释放 → 新写者只能等/失败（见 concurrency_matrix I9）。
    old_t = lease.LOCK_TIMEOUT
    lease.LOCK_TIMEOUT = 2.0
    took, why = lease.shared_append(root, p, "- 崩溃后立即接管", "崩溃恢复")
    took_over = bool(took) and ("崩溃后立即接管" in p.read_text(encoding="utf-8"))
    shutil.rmtree(root, ignore_errors=True)
    return ("C2", "崩溃于「持锁期间」", "最终一致",
            ok and len(locks) >= 1 and took_over,
            "就位=%s · 残留锁文件=%d · 崩溃后立即接管=%s（本实现已无锁龄概念）"
            % (ok, len(locks), took_over))


def c3_crash_after_replace():
    root = _fresh()
    p = root / "REVIEWS.md"
    ok = _crash(root, "after_replace")
    body = p.read_text(encoding="utf-8")
    updated = "- 已替换" in body and "- 原始行" in body
    locks = list(root.glob("*.lock"))
    time.sleep(0.05)
    again, _ = lease.shared_append(root, p, "- 再次写入", "崩溃恢复")
    shutil.rmtree(root, ignore_errors=True)
    return ("C3", "崩溃于「替换之后、放锁之前」", "最终一致",
            ok and updated and len(locks) >= 1 and bool(again),
            "就位=%s · 内容已更新且旧行保留=%s · 锁残留=%d · 重跑=%s"
            % (ok, updated, len(locks), bool(again)))


def c4_half_transaction():
    """冷区已写、热区没有：重跑必须**拒绝重复**（幂等），冷区不重复 —— 人工对齐。"""
    root = _fresh()
    (root / "MAP.md").write_text("# MAP\n\n## 二、规则\n\n- 协作模式：light\n", encoding="utf-8")
    (root / "STATE.md").write_text("# 状态\n", encoding="utf-8")
    (root / "REVIEWS.md").write_text("# 通道\n\n", encoding="utf-8")
    (root / "INDEX.md").write_text(
        "# 索引\n\n| 编号 | 日期 | 类型 | 主题 | AI | 交接文件 |\n|---|---|---|---|---|---|\n",
        encoding="utf-8")
    (root / "archives" / "INDEX_archived.md").write_text(
        "# 索引冷区\n\n| 编号 | 日期 | 类型 | 主题 | AI | 交接文件 |\n|---|---|---|---|---|---|\n",
        encoding="utf-8")
    (root / "reports" / "2026-09-20_x.md").write_text("# x\n", encoding="utf-8")
    co = str(HERE / "closeout.py")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    args = [sys.executable, co, str(root), "index-add", "--id", "EN0007", "--type", "[接力]",
            "--topic", "半事务测试", "--record", "reports/2026-09-20_x.md", "--ai", "win-a"]
    r1 = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, timeout=120)
    cold_with_row = sum(1 for l in (root / "archives" / "INDEX_archived.md").read_text(encoding="utf-8").splitlines() if "EN0007" in l)
    hot_lines = [l for l in (root / "INDEX.md").read_text(encoding="utf-8").splitlines() if "EN0007" not in l]
    (root / "INDEX.md").write_text("\n".join(hot_lines) + "\n", encoding="utf-8")   # 模拟热区丢失
    r2 = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, timeout=120)
    cold_after = sum(1 for l in (root / "archives" / "INDEX_archived.md").read_text(encoding="utf-8").splitlines() if "EN0007" in l)
    shutil.rmtree(root, ignore_errors=True)
    return ("C4", "半事务（冷区已写 / 热区缺失）", "最终一致",
            r1.returncode == 0 and r2.returncode != 0 and cold_after == 1,
            "首次=%d · 重跑被幂等拒=%s · 冷区 %d→%d（未重复）——由 repair 补偿，见 C5"
            % (r1.returncode, r2.returncode != 0, cold_with_row, cold_after))


def c5_repair_converges():
    """半事务 → closeout.py repair → 收敛；再跑一遍 → 报「无需修复」（幂等）。"""
    root = _fresh()
    (root / "MAP.md").write_text("# MAP\n\n## 二、规则\n\n- 协作模式：light\n", encoding="utf-8")
    (root / "STATE.md").write_text("# 状态\n", encoding="utf-8")
    (root / "INDEX.md").write_text(
        "# 索引\n\n| 编号 | 日期 | 类型 | 主题 | AI | 交接文件 |\n|---|---|---|---|---|---|\n",
        encoding="utf-8")
    (root / "archives" / "INDEX_archived.md").write_text(
        "# 冷区\n\n| 编号 | 日期 | 类型 | 主题 | AI | 交接文件 |\n|---|---|---|---|---|---|\n",
        encoding="utf-8")
    (root / "reports" / "2026-09-20_x.md").write_text("# x\n", encoding="utf-8")
    co = str(HERE / "closeout.py")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    args = [sys.executable, co, str(root), "index-add", "--id", "EN0007", "--type", "[接力]",
            "--topic", "半事务", "--record", "reports/2026-09-20_x.md", "--ai", "win-a"]
    subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, timeout=120)
    t = (root / "INDEX.md").read_text(encoding="utf-8")
    (root / "INDEX.md").write_text("\n".join(l for l in t.splitlines() if "EN0007" not in l) + "\n",
                                    encoding="utf-8")
    before_hot = "EN0007" in (root / "INDEX.md").read_text(encoding="utf-8")
    r1 = subprocess.run([sys.executable, co, str(root), "repair"],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, timeout=120)
    hot = (root / "INDEX.md").read_text(encoding="utf-8")
    cold = (root / "archives" / "INDEX_archived.md").read_text(encoding="utf-8")
    #  **幂等性必须断言语义状态，不能查本地化 stdout**：
    #  用 `r2.stdout.decode("gbk")` 再找「无需修复」——在 UTF-8 环境里解码即乱码，断言必挂；
    #  更糟的是：那是把「文案」当契约，改一个字就红。**契约是状态，不是输出。**
    #  正确判据：第二次 repair 后**冷热两区一行的增减都没有**，且退出码正常。
    r2 = subprocess.run([sys.executable, co, str(root), "repair"],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, timeout=120)
    hot2 = (root / "INDEX.md").read_text(encoding="utf-8")
    cold2 = (root / "archives" / "INDEX_archived.md").read_text(encoding="utf-8")
    converged = (not before_hot) and r1.returncode == 0 and "EN0007" in hot and cold.count("EN0007") == 1
    no_change = (hot2 == hot) and (cold2 == cold)          # 幂等：第二次什么都不该改
    idempotent = (r2.returncode == 0) and no_change
    shutil.rmtree(root, ignore_errors=True)
    return ("C5", "半事务 → repair 补偿", "最终一致",
            converged and idempotent,
            "补偿前热区缺=%s · repair#1=%d 已补回=%s · 冷区=%d · repair#2=%d 状态零变化(幂等)=%s"
            % (not before_hot, r1.returncode, "EN0007" in hot, cold.count("EN0007"),
               r2.returncode, no_change))

def main():
    rows = [c1_crash_after_tmp(), c2_crash_holding_lock(), c3_crash_after_replace(),
            c4_half_transaction(), c5_repair_converges()]
    print("== 崩溃注入矩阵（真杀进程）==")
    print("%-4s %-30s %-10s %-6s %s" % ("编号", "时点", "等级", "结果", "说明"))
    print("-" * 130)
    bad = 0
    for num, name, tier, okk, detail in rows:
        if not okk:
            bad += 1
        print("%-4s %-30s %-10s %-6s %s" % (num, name[:30], tier, "通过" if okk else "**失败**", detail[:74]))
    print("-" * 130)
    print("时点 %d 个 · 通过 %d · 失败 %d" % (len(rows), len(rows) - bad, bad))
    if bad:
        print("[问题] 有崩溃时点未收敛——**不要**以该版本声称崩溃安全")
        return 1
    print("[通过] 五个时点：数据均未被破坏，残留可清理，半事务可由 closeout.py repair 幂等补偿")
    return 0


if __name__ == "__main__":
    mp.freeze_support()
    sys.exit(run(main))