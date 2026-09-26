# -*- coding: utf-8 -*-
"""lease.py —— 任务租约与文件级 CAS 原语（并发强制层）

用法：本文件不是命令行工具，供 closeout.py / check_closeout.py / validate_workspace.py 复用。

为什么要有这个脚本（设计动机）：
    并发篇原来只说「请遵守单写者」——那是**协议**，不是**强制**。
    本脚本把两件事变成**脚本能拒绝**的：
      ① **任务级租约**：谁在动这张卡（owner + 租约 + 到期时间），别的 AI 在租约有效期内写它 → 直接拒绝；
      ② **文件级 CAS**：写共享文件前校验 NORMALIZED-SHA256，内容被别人改过 → 拒绝写入并让人重读。

边界（**必须一起读，否则会误以为它比实际更强**）：
    本层强制的是**「经由脚本的写入」**。有人绕过脚本直接编辑文件，脚本拦不住——
    那种情况由**检测层**兜底：卡/索引上记的 NORMALIZED-SHA256 与文件实际内容不一致 → 门禁报 [问题]
    并生成 CONFLICT_<ID>_<时间戳>.md 留痕。**拦不住的，也一定看得见。**
"""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import config, read, resolve_under  # noqa: E402

#: 「并发元数据」行：owner=…；lease=…；claimed_at=…；expires_at=…；revision=…；…
#  刻意**不新增冻结字段名**——租约是既有字段「并发元数据」的内部结构，
#  这样并发控制升级不会动到冻结区（references/artifacts.md §2）。
META_RE = re.compile(r"^-\s*\*\*并发元数据\*\*\s*[：:]\s*(.*)$", re.M)
OWNER_RE = re.compile(r"^-\s*\*\*承接\*\*\s*[：:]\s*(.*)$", re.M)


def now():
    """本机时区的当前时刻（带偏移）——与 stamp.py 的机器戳同一口径。"""
    return datetime.now().astimezone()


def now_iso() -> str:
    return now().replace(microsecond=0).isoformat()


#: 自指字段：卡上记的哈希包含它自己，直接算永远不自洽。
#  **解法：算哈希前先把该字段的值抹成占位符**——抹掉之后内容与"记什么"无关，哈希才稳定。
#  这一条不写清楚，接手者会以为是"哈希算错了"，然后去改校验逻辑（把真问题改没）。
HASH_SLOT_RE = re.compile(r"(NORMALIZED-SHA256=)[^；;\n]*")


def _blank_slot(text: str) -> str:
    return HASH_SLOT_RE.sub(r"\1—", text)


def card_hash_text(text: str) -> str:
    """卡的哈希：抹掉自指槽位后再归一化算。"""
    return norm_hash_text(_blank_slot(text))


def file_hash(path: Path):
    """通用：目标含自指槽位 → 按卡算；否则按普通文本算。"""
    t = read(path)
    if t is None:
        return None
    return card_hash_text(t) if HASH_SLOT_RE.search(t) else norm_hash_text(t)


def norm_hash_text(text: str) -> str:
    """规范化文本哈希：统一换行 + 去行尾空白，取 sha256 前 16 位。"""
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    t = "\n".join(line.rstrip() for line in t.split("\n"))
    return hashlib.sha256(t.encode("utf-8")).hexdigest()[:16]



def parse_meta(card: Path) -> dict:
    """解析卡上的「并发元数据」行 → dict。缺字段返回空 dict（旧卡兼容）。"""
    txt = read(card) or ""
    m = META_RE.search(txt)
    if not m:
        return {}
    out = {}
    for seg in re.split(r"[；;]", m.group(1)):
        if "=" in seg:
            k, v = seg.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def owner_of(card: Path) -> str:
    txt = read(card) or ""
    m = OWNER_RE.search(txt)
    return (m.group(1).strip() if m else "") or "—"


def _parse_ts(s: str):
    if not s or s in ("—", "-"):
        return None
    try:
        v = s[:-1] + "+00:00" if s.endswith("Z") else s
        dt = datetime.fromisoformat(v)
        return dt if dt.tzinfo else dt.replace(tzinfo=now().tzinfo)
    except Exception:
        return None


def lease_state(card: Path) -> dict:
    """租约现状：{active, expired, owner, expires_at, revision, recorded_hash, actual_hash, drifted}"""
    meta = parse_meta(card)
    exp = _parse_ts(meta.get("expires_at", ""))
    _t = now()
    actual = file_hash(card)
    recorded = meta.get("NORMALIZED-SHA256", "")
    rec = recorded if recorded and recorded not in ("—", "-") else ""
    return {
        "owner": meta.get("owner", "") or owner_of(card),
        "claimer": owner_of(card),
        "lease": meta.get("lease", ""),
        "claimed_at": meta.get("claimed_at", ""),
        "expires_at": meta.get("expires_at", ""),
        "revision": meta.get("revision", ""),
        # fencing：**单调只增的令牌序号**。与 owner 的区别——
        #   owner 回答"这张卡归谁"，fencing 回答"第几次认领"。
        #   同一个 AI 先后认领两次（中间过期/被抢占），光比 owner 分不出来，比 fencing 就能。
        "fencing": meta.get("fencing", "0") or "0",
        "recorded_hash": rec,
        "actual_hash": actual or "",
        "drifted": bool(rec) and bool(actual) and rec != actual,
        "active": bool(exp) and exp > _t,
        "expired": bool(exp) and exp <= _t,
        # 占位符 ≠ 有租约：释放后写的是「—」。把占位符当"有"会让释放过的卡继续被拦。
        "has_lease": str(meta.get("lease", "")).strip() not in ("", "—", "-"),
    }


def _render_meta(meta: dict) -> str:
    order = ["owner", "lease", "claimed_at", "expires_at", "revision",
             "NORMALIZED-SHA256", "写入方式", "冲突文件"]
    keys = order + [k for k in meta if k not in order]
    return "；".join("%s=%s" % (k, meta.get(k, "—")) for k in keys if k in meta or k in order)


def _set_meta_line(txt: str, meta: dict) -> str:
    line = "- **并发元数据**：%s" % _render_meta(meta)
    if META_RE.search(txt):
        return META_RE.sub(lambda _m: line, txt, count=1)
    return txt.rstrip("\n") + "\n" + line + "\n"


def _set_owner_line(txt: str, ai: str) -> str:
    if OWNER_RE.search(txt):
        return OWNER_RE.sub(lambda _m: "- **承接**：%s" % ai, txt, count=1)
    return txt


#: 锁参数（可用环境变量覆盖，便于测试与调参）
# ── 并发原语已拆到 locks.py（层界分离）──────────────────────
#  这里只做**再导出**，让既有调用点平滑过渡；新代码请用 locks.exclusive_resource()。
from locks import (  # noqa: E402,F401
    LOCK_TIMEOUT, Lock, _lock_path,
    acquire_lock, exclusive_resource, release_lock, verify_lock,
)

def _write_locked(path: Path, new_text: str, lock=None):
    """**假定已持锁**：唯一临时名写入 + 写后回读校验。返回 (ok, 说明, 哈希)。

    **写前与写后各校验一次锁归属**（token + epoch）——本函数的核心不变量。
      · 写前不符 → 直接拒绝（"我还以为自己持有锁"的旧写者在此被挡住）；
      · 写后不符 → 检查与替换之间发生了接管 → 明确失败，交上层留痕。
    **诚实说明**：最后一道窗口（校验通过后、replace 之前被暂停**超过锁的生命周期**）无法用纯文件 API 消除；
    但走 OS 建议锁时它实际上不出现——暂停不释放建议锁，新写者根本拿不到锁（见 _os_lock）。
    """
    if lock is not None and not verify_lock(lock):
        return False, ("锁已易主（token/epoch 不符）——**拒绝写入**：你已不是当前写者"
                       "（典型成因：进程被暂停超过锁生命周期后被他人接管）"), ""
    tmp = path.with_name("%s.tmp.%d.%s" % (path.name, os.getpid(), secrets.token_hex(4)))
    try:
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            f.write(new_text)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    after = file_hash(path)
    want = hash_of_text(new_text)
    if lock is not None and not verify_lock(lock):
        return False, "写后校验：锁已易主——存在未被互斥挡住的并发写者", after
    if after != want:
        return False, ("写后校验失败（写入 %s，读到 %s）——有未加锁的写者并发改动过"
                       % (want, after)), after
    return True, "已写入", after


def write_cas(path: Path, new_text: str, expected_hash: str):
    """**真 CAS**：锁内 compare → write → verify。返回 (ok, 说明, 新哈希)。

    **必须记住的三条实测结论**：
      ① 原来用固定名 `path + ".tmp"` —— 并发写者共用同一个临时文件，互相覆盖、
         replace 时对方已移走 → `FileNotFoundError` **外抛**、内容错位、**假成功**。
      ② 只把临时文件改成唯一名**也不够**：两个写者可以都读到同一个 expected、都通过比对、
         先后 replace —— 仍是 lost update。**唯一名只治异常，不治语义。**
      ③ 正确做法：把「比对」与「写入」放进**同一个临界区**（锁内）＋写后回读校验；
         任何失败都**返回 False 而不是抛异常**。
    """
    if not path.exists():
        return False, "文件不存在或不可读", ""
    try:
        with exclusive_resource(path) as lock:
            if lock is None:
                return False, "取锁失败（可能被其他写者占用）", ""
            cur = file_hash(path)
            if cur is None:
                return False, "文件不存在或不可读", ""
            if expected_hash and cur != expected_hash:
                return False, "文件已被他人修改（记 %s，实际 %s）" % (expected_hash, cur), cur
            return _write_locked(path, new_text, lock)
    except Exception as e:
        # **异常不外抛**：调用方拿到的必须是「明确失败」，不是一个堆栈
        return False, "写入异常（已捕获）：%s: %s" % (type(e).__name__, e), ""



def conflict_file(root: Path, task_id: str, detail: str) -> Path:
    """生成冲突文件（模式取自 config.audit.conflict_file_pattern）。

    冲突文件不删不改——它是**并发现场的第一手证据**：谁、什么时候、想改什么、被谁挡住。
    """
    pat = str(config(root, "audit.conflict_file_pattern", "CONFLICT_<ID>_<timestamp>.md"))
    ts = now().strftime("%Y%m%dT%H%M%S")
    name = pat.replace("<ID>", re.sub(r"[^0-9A-Za-z_-]", "", task_id) or "TASK").replace("<timestamp>", ts)
    p = root / name
    body = ("# 并发冲突记录\n\n"
            "> 由 `scripts/lease.py` 自动生成，**不删不改**——它是并发现场的第一手证据。\n\n"
            "- **时间**：%s\n- **对象**：%s\n\n## 经过\n\n%s\n" % (now_iso(), task_id, detail))
    p.write_text(body.replace("`", chr(96)), encoding="utf-8", newline="")
    return p


def claim(root: Path, card: Path, ai: str, minutes: int, steal: str = ""):
    """认领任务：写入 owner + 租约 + 到期时间。返回 (ok, 说明)。

    **为什么整段收进临界区**：若写成「guard 读状态 → read 读内容 → write_cas 再写」三个时刻，
    两个进程都能读到「无租约」的前置然后都写进去——**互斥在锁层成立，业务判定却不是原子的**
    （并发矩阵 I3 实测：两个 claim 都成功）。
    现在把整段收进 `exclusive_resource(card)` 一个临界区：锁内读、锁内判、锁内写（用 `_write_locked`，
    不再二次取锁，避免自死锁）。**业务层只碰 `exclusive_resource` 这一个原语。**
    """
    with exclusive_resource(card) as lock:
        if lock is None:
            return False, "取锁失败（%s）——请稍后重试" % card.name
        txt = read(card) or ""
        st = lease_state(card)
        if st["drifted"]:
            p = conflict_file(root, card.stem,
                              "认领前发现卡内容与「并发元数据」记录的哈希不一致（有人绕过脚本改过）：\n"
                              "- 记录 %s\n- 实际 %s" % (st["recorded_hash"], st["actual_hash"]))
            return False, "卡内容与记录哈希不一致（有人绕过脚本改过）——已生成 %s，请先核对再认领" % p.name
        if st["active"] and st["owner"] not in (ai, "—", ""):
            if not steal:
                return False, ("租约被 %s 持有至 %s —— 拒绝认领。到期后自动可认领；"
                               "确有需要请用 --steal 并写明理由（会留痕）" % (st["owner"], st["expires_at"]))
            conflict_file(root, card.stem,
                          "**抢占租约**：%s 抢占了 %s 持有的租约。\n\n- 原到期：%s\n- 抢占理由：%s"
                          % (ai, st["owner"], st["expires_at"], steal))
        exp = (now() + timedelta(minutes=int(minutes))).replace(microsecond=0).isoformat()
        meta = parse_meta(card)
        meta["owner"] = ai
        meta["lease"] = hashlib.sha256(("%s|%s|%s" % (ai, card.stem, now_iso())).encode()).hexdigest()[:8]
        meta["claimed_at"] = now_iso()
        meta["expires_at"] = exp
        try:
            meta["revision"] = str(int(meta.get("revision", "0") or 0) + 1)
        except ValueError:
            meta["revision"] = "1"
        # fencing 令牌：每次认领自增、永不回退（revision 记「文件被改了几次」，fencing 记「被认领了几次」）
        try:
            meta["fencing"] = str(int(meta.get("fencing", "0") or 0) + 1)
        except ValueError:
            meta["fencing"] = "1"
        meta.setdefault("写入方式", "atomic rename")
        meta.setdefault("冲突文件", "—")
        # 自指字段：先留占位符 → 抹槽位算哈希 → 回填
        meta["NORMALIZED-SHA256"] = "—"
        new = _set_meta_line(_set_owner_line(txt, ai), meta)
        meta["NORMALIZED-SHA256"] = card_hash_text(new)
        new = _set_meta_line(_set_owner_line(txt, ai), meta)
        # 锁内写：不再走 write_cas（那会二次取锁）；_write_locked 会做写后回读与归属校验
        okk, why2, _h = _write_locked(card, new, lock)
        if not okk:
            return False, why2
        return True, ("已认领：owner=%s · 租约至 %s · revision=%s · **fencing 令牌=%s**"
                      "（后续写入请带 --token %s，否则挡不住过期写者）"
                      % (ai, exp, meta["revision"], meta["fencing"], meta["fencing"]))

def release(root: Path, card: Path, ai: str, force: bool = False):
    """释放租约（保留「承接」——认领关系是历史，租约是当下的占用）。

    与 `claim` 同一手法：**判归属与改内容必须在同一把锁内**——
    否则「A 释放的同时 B 认领」会让 B 的租约被 A 的写覆盖（check-then-act）。
    """
    with exclusive_resource(card) as lock:
        if lock is None:
            return False, "取锁失败（%s）——请稍后重试" % card.name
        st = lease_state(card)
        if not st["has_lease"]:
            return True, "无租约，无需释放"
        if st["owner"] not in (ai, "—", "") and not force:
            return False, "租约属于 %s，不能由 %s 释放（确需请用 --force，会留痕）" % (st["owner"], ai)
        txt = read(card) or ""
        meta = parse_meta(card)
        for k in ("lease", "claimed_at", "expires_at"):
            meta[k] = "—"
        meta["owner"] = st["owner"] if st["owner"] != ai else ai
        try:
            meta["revision"] = str(int(meta.get("revision", "0") or 0) + 1)
        except ValueError:
            meta["revision"] = "1"
        meta["NORMALIZED-SHA256"] = "—"
        new = _set_meta_line(txt, meta)
        meta["NORMALIZED-SHA256"] = card_hash_text(new)
        new = _set_meta_line(txt, meta)
        # 锁内写（不再二次取锁）；_write_locked 会做写后回读与归属校验
        okk, why2, _h = _write_locked(card, new, lock)
        if not okk:
            return False, why2
        if force and st["owner"] not in (ai, "—", ""):
            conflict_file(root, card.stem, "**强制释放**：%s 释放了 %s 的租约" % (ai, st["owner"]))
        return True, "已释放租约（承接保留为 %s）" % meta.get("owner", "—")


# ── 共享文件写原语（**所有对共享文件的写都必须走这里**）────────────────
#  为什么必须收拢到一处：本包声称「共享文件写前比对哈希」，但实测存在多条直接
#  原子替换的写路径（audit_all / lang_gates / stamp / setup / closeout 归档），
#  它们**没有 CAS**——协议说一套、实现做一套，正是本包最反对的形态。
#  收拢后由 gen_views 第 10 节机检「谁写了共享文件、用的是不是原语」，漏的报红。
SHARED_FILES = ("REVIEWS.md", "INDEX.md", "STATE.md", "MAP.md",
                "archives/INDEX_archived.md", "archives/REVIEWS_archived.md")


#: **共享文件写者登记表**（由 gen_views 第 10 节机检）。
#  规则：脚本里同时出现①共享文件名 与 ②写调用，就必须在此登记它用的**原语**。
#  为什么需要：本包声称「共享文件写前比对哈希」，但历史上存在多条直接 os.replace 的写路径——
#  协议一套、实现一套。收编之后，**漏登记的写者会被门禁抓出来**，而不是靠人记得。
SHARED_WRITERS = {
    "lease.py": "原语本体（write_cas / shared_append / shared_rewrite）",
    "closeout.py": "lease.write_cas（经 _cas_write 与 lease.hash_of_text）",
    "lang_gates.py": "lease.shared_append",
    "stamp.py": "lease.shared_append",
    "audit_all.py": "lease.shared_append",
    "setup.py": "lease.shared_rewrite",
    "selftest_gates.py": "夹具：在临时目录里造共享文件（不写真实工作区，故不走 CAS）",
    "concurrency_matrix.py": "夹具：故障注入用临时工作区（同样不写真实工作区）",
    "crash_matrix.py": "夹具：崩溃注入用临时工作区（真杀子进程，不碰真实工作区）",
    # gen_views 只写**包内派生视图**（README 的生成区），不写工作区共享文件；
    #  它之所以命中第 10 节，是因为源码注释里提到了 INDEX.md / MAP.md（第 10 节按文本扫描，认注释）。
    "gen_views.py": "只写包内派生视图（README 生成区）；不写工作区共享文件",
}

SWEEP_OLD_SECONDS = 60.0      # 临时/尸体文件的清理门槛（秒）；**锁文件不在清理范围内**


def sweep_temp(root: Path, older_than=None):
    """清理崩溃残留的临时文件（`*.tmp.<pid>.<rand>`）。返回 (清理数, 清单)。

    为什么需要：写入是「唯一临时名 + 原子替换」——进程在写 tmp 之后被 kill，
    tmp 就成了孤儿（替换没发生，目标文件没被破坏，但垃圾留在原地）。
    **崩溃不破坏数据，但会留垃圾**；垃圾不清会随崩溃次数累积，且误导排查。
    只清「比 older_than（默认 SWEEP_OLD_SECONDS）更旧」的，避免误删正在写的临时文件。
    """
    import glob as _glob
    age_limit = SWEEP_OLD_SECONDS if older_than is None else float(older_than)
    removed = []
    #  **绝不删锁文件**（防 path→inode 漂移）：删掉一个「看起来没人持有」的锁文件，
    #  就是给 path→inode 漂移开门——别人随后新建同名文件并加锁，会出现两个互斥对象。
    #  只清：崩溃留下的半成品临时文件 + rename 抢占留下的 *.lock.stale.* 尸体。
    for pat in ("*.tmp.*", "*.tmp", "*.lock.stale.*"):
        for f in _glob.glob(str(Path(root) / "**" / pat), recursive=True):
            p = Path(f)
            try:
                if time.time() - p.stat().st_mtime > age_limit:
                    p.unlink()
                    removed.append(p.name)
            except OSError:
                continue
    return len(removed), removed

def hash_of_text(text: str) -> str:
    """一份文本的前置哈希（自适应自指槽位：卡抹槽位，普通文件不抹）。

    关键：**期望哈希必须来自「你读到的那份文本」**，不能回头再读一次文件——
    回头再读会把别人刚写入的新内容算成前置条件，等于把别人的改动当自己的一部分写下去（丢写）。
    """
    return card_hash_text(text) if HASH_SLOT_RE.search(text or "") else norm_hash_text(text or "")


def shared_append(root: Path, path: Path, line: str, what: str = "追加"):
    """共享文件的**追加**：**在锁内读—改—写**。返回 (ok, 说明)。

    为什么必须锁内读：追加是**可交换**操作——别人也追加，不该导致我失败。
    早先在锁外读、锁内比，结果 6 个并发追加只有 1~2 个成功（其余被 CAS 拒），
    虽然"没丢写"，但**把正常的并发用成了失败**。锁内读之后，N 个追加会依次成功、一条不丢。
    """
    return _mutate_locked(root, path, lambda cur: cur + ("" if (cur == "" or cur.endswith("\n")) else "\n") + line + "\n", what)


def shared_rewrite(root: Path, path: Path, new_text: str, base_text: str, what: str = "重写"):
    """共享文件的**重写**：以 base_text（你实际读过的那份）为前置条件，**比对在锁内**。"""
    base_h = hash_of_text(base_text)

    def _check(cur):
        if hash_of_text(cur) != base_h:
            return None      # 前置不符 → 放弃（_mutate_locked 会生成冲突文件）
        return new_text

    return _mutate_locked(root, path, _check, what)


def _mutate_locked(root: Path, path: Path, mutate, what: str = "改写"):
    """锁内 read → mutate → write → verify。mutate 返回 None 表示「放弃改动」。"""
    if not path.exists():
        return False, "文件不存在或不可读：%s" % path
    try:
        with exclusive_resource(path) as lock:
            if lock is None:
                return False, "取锁失败（可能被其他写者占用）"
            cur = read(path)
            if cur is None:
                return False, "文件不存在或不可读：%s" % path
            new = mutate(cur)
            if new is None:
                p = conflict_file(root, path.name,
                                  "**被拒（CAS 失败）**：%s 的目标 %s 在读取之后被改动。\n\n- 处置：重读后重做" % (what, path.name))
                return False, "写入被拒：目标 %s 在读取之后被改动 —— 已生成 %s，请重读后重做" % (path.name, p.name)
            okk, why2, _h = _write_locked(path, new, lock)
            return (True, "已写入") if okk else (False, why2)
    except Exception as e:
        return False, "写入异常（已捕获）：%s: %s" % (type(e).__name__, e)

def guard(root: Path, card: Path, ai: str, need_lease: bool = True, token=None):
    """写前守卫：返回 (ok, 说明)。供 closeout.py 的写命令调用。

    **fencing 令牌（可选但推荐）**：只比 owner 分不出「同一个 AI 先后两次认领」——
    例如 A 认领(令牌1) → 过期 → B 抢占(令牌2) → A 的旧进程仍以为自己在做 → 此时 owner 可能又变回 A，
    光比 owner 就放行了，而那次写基于过期状态。带上 token 后：**旧令牌 < 当前令牌即拒绝**。
    不带 token 时不做这层判断（向后兼容），但也就等于放弃了对僵尸写者的防护。
    """
    st = lease_state(card)
    if st["drifted"]:
        p = conflict_file(root, card.stem,
                          "写入被拒：卡内容与「并发元数据」记录哈希不一致（有人绕过脚本改过）\n"
                          "- 记录 %s\n- 实际 %s" % (st["recorded_hash"], st["actual_hash"]))
        return False, "卡内容与记录哈希不一致——已生成 %s" % p.name
    if token is not None and str(token).strip():
        try:
            mine = int(str(token).strip())
            cur_tok = int(st.get("fencing", "0") or 0)
        except ValueError:
            return False, "--token 必须是整数（认领时回显的那个 fencing 令牌）"
        if mine != cur_tok:
            why_txt = ("租约令牌过期（你的 %d < 当前 %d）：你的租约已被抢占或重新认领过，这次写基于过期状态"
                       % (mine, cur_tok)) if mine < cur_tok else \
                      ("令牌不存在（你报 %d，当前只有 %d）：**不接受比当前更大的令牌**"
                       % (mine, cur_tok))
            p = conflict_file(root, card.stem,
                              "**写入被拒（fencing，严格相等）**：%s\n\n"
                              "- 处置：重新读卡 → 重新 claim → 用回显的令牌重做" % why_txt)
            return False, "%s —— 已生成 %s，请重新 claim 后重做" % (why_txt, p.name)
    if not need_lease:
        return True, ""
    if not st["has_lease"]:
        return True, "提示：该卡尚未认领（无租约）——建议先跑 closeout.py claim"
    if st["active"] and st["owner"] not in (ai, "—", ""):
        return False, "卡被 %s 持有（租约至 %s），拒绝写入" % (st["owner"], st["expires_at"])
    if st["expired"]:
        return True, "租约已过期（%s）——按过期可写处理，建议随后 claim 续约" % st["expires_at"]
    return True, ""
    st = lease_state(card)
    if st["drifted"]:
        p = conflict_file(root, card.stem,
                          "写入被拒：卡内容与「并发元数据」记录哈希不一致（有人绕过脚本改过）\n"
                          "- 记录 %s\n- 实际 %s" % (st["recorded_hash"], st["actual_hash"]))
        return False, "卡内容与记录哈希不一致——已生成 %s" % p.name
    if not need_lease:
        return True, ""
    if not st["has_lease"]:
        return True, "提示：该卡尚未认领（无租约）——建议先跑 closeout.py claim"
    if st["active"] and st["owner"] not in (ai, "—", ""):
        return False, "卡被 %s 持有（租约至 %s），拒绝写入" % (st["owner"], st["expires_at"])
    if st["expired"]:
        return True, "租约已过期（%s）——按过期可写处理，建议随后 claim 续约" % st["expires_at"]
    return True, ""


# ── 并发原语的边界（**必须与实现一起读**）─────────────────────────────
#  · **互斥的物理基础是操作系统建议锁**（Windows `msvcrt.locking` / POSIX `fcntl.flock`，非阻塞）：
#    锁跟着 fd 走 → **暂停不释放、进程死亡由 OS 释放**。这两条正好对应两种故障模型：
#      · 暂停（SIGSTOP / 调试器 / 容器冻结）：新写者**取不到锁**，只能等或明确失败（不得接管）；
#      · 崩溃：OS 释放 → 新写者**立即接管，不依赖锁龄**。
#  · 仅当平台/文件系统**不支持**建议锁时，退化为 `O_CREAT|O_EXCL` + rename 抢占（`mode=excl`）：
#  · **网络文件系统（NFS / SMB）** 的建议锁语义同样不保证 → 按退化模式对待。
#  · 跨机器并发写同一份目录**不在保证范围内**：本包的前提是「一个工作区一份本地文件系统」。
#  · 崩溃残留的锁文件**不再阻塞**（锁在 fd 上，不在文件存在性上）；它只是垃圾，`sweep_temp` 可清。
#  · 绕过本模块直接改文件的写者不受任何保护，只能被漂移检测抓到（详见 references/concurrency.md §0）。
