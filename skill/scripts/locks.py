# NOPMD: 并发原语的契约与失败模式必须就地写清，否则接手者无法判断边界条件。
# -*- coding: utf-8 -*-
"""locks.py —— 并发原语层（互斥的**唯一物理实现**所在）

为什么单独成文件（层界分离的结论）：
  原先 lease.py 一个模块同时扛「锁取放 / CAS 写入 / 租约 fencing / 崩溃恢复 / 清理」五类职责，
  每次审计都在它里面再加一层——这正是「往屎山走」的信号。
  现在把「互斥 + 平台分支 + 崩溃/暂停语义」圈进本文件，作为**小黑盒**：
    业务层只该看到 with exclusive_resource(path): ...
    不该知道 flock / msvcrt / O_EXCL / epoch / inode / stale / fd / unlink。

本层对外的承诺（可执行用例见 scripts/concurrency_matrix.py）：
  · 同一路径同一时刻最多一个有效 OS 锁代（I11）；
  · 暂停（进程未死）不得被接管（I9）；崩溃（进程死亡）可立即接管（C2）；
  · 放锁**不删锁文件**——锁文件是装置，删除会造成 path→inode 漂移（I10 / I11）；
  · **锁文件里的 epoch / token 只是「锁代标识 + 排障信息」，不是 ownership 权威**——
    判 ownership **只看 fd 上的 OS 建议锁**（防止未来维护者把它误当第二套锁权威）。

依据：references/concurrency-internals.md §2.2
"""
from __future__ import annotations

import os
import re
import secrets
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def now_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()
LOCK_TIMEOUT = float(os.environ.get("WSX_LOCK_TIMEOUT", "10"))   # 等锁上限（秒）；超时即**明确失败**，不无限等待


def _lock_path(path: Path) -> Path:
    return path.with_name(path.name + ".lock")


def _lock_text(epoch: int, token: str) -> str:
    return "epoch=%d token=%s pid=%d at=%s\n" % (epoch, token, os.getpid(), now_iso())


def _read_lock(lp: Path):
    """读锁文件里的 (epoch, token)；读不到返回 (None, None)。尾随垃圾不影响（正则取首次出现）。"""
    try:
        txt = lp.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, None
    me = re.search(r"epoch=(\d+)", txt)
    mt = re.search(r"token=([0-9A-Za-z_\-]+)", txt)
    return (int(me.group(1)) if me else None), (mt.group(1) if mt else None)


def _os_lock(fd):
    """在已打开的 fd 上取**操作系统级**非阻塞排他锁。True 成功 / False 被占 / None 不支持。

    为什么这是关键：**建议锁跟着 fd 走**——进程被挂起 / 冻结 / 调试器暂停时，
    锁**仍属于它**（不因"暂停"而释放）；而进程死亡时**操作系统自动释放**。
    这正好把两种故障模型分开：
      · 暂停：新写者**取不到锁** → 等或明确失败（不会"接管后旧写者复活覆盖"）；
      · 崩溃：OS 释放锁 → 新写者立刻接管（残留锁文件不再是障碍）。
    """
    try:
        if os.name == "nt":
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False
    except Exception:
        return None


def _os_unlock(fd) -> None:
    try:
        if os.name == "nt":
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_UN)
    except Exception:
        pass


class Lock:
    """一次取锁的句柄：fd + 锁文件（+ 仅供排障的 token / epoch）。

    **所有权的唯一权威是 fd 上的 OS 建议锁**；token / epoch 只是写进锁文件的**代数记录与排障信息**，**不参与归属判定**。原因：
    上一代实现用它们判定「锁是否易主」（旧写者复活 / 别人接管 / epoch 落后），那套判定已随 EXCL 退化路径**整体删除**。
    """
    __slots__ = ("fd", "path", "token", "epoch", "mode", "released")

    def __init__(self, fd, path, token, epoch, mode):
        self.fd, self.path, self.token, self.epoch, self.mode = fd, path, token, epoch, mode
        self.released = False


def verify_lock(lock) -> bool:
    """**写前与写后各问一次**：现在这把锁还是我的吗？

    分模式实现（**这是被 Windows 的强制锁教出来的**）：
      · `os-lock` 模式：归属由**操作系统**保证——锁在 fd 关闭前一直有效，别人拿不到，
        所以"我是否仍是持有者"＝"我的 fd 还没释放"。**不要再去读锁文件核对 token**：
        Windows 的字节范围锁是**强制**的，另开句柄读会直接 PermissionError，
        那样会把自己的锁误判成"已易主"（实测：全部写入被拒，10 个用例挂 8 个）。
      · **（已移除）** 上一代还有 `excl` 退化模式——靠锁文件里的 token/epoch 判定归属。
        该路径已整体删除：不支持建议锁时**明确失败**，因为降级给出的是无法兑现的保证。
    """
    if lock is None:
        return True
    return not getattr(lock, "released", False)


def acquire_lock(path: Path):
    """取锁。返回 (Lock | None, 说明)。

    顺序体现取舍：**先试操作系统级建议锁**（暂停安全 + 死亡安全），
    平台/文件系统不支持建议锁时**明确失败**（返回 None + 说明）——**不降级**：降级会给出无法兑现的互斥保证。
    """
    lp = _lock_path(path)
    token = "%d-%s" % (os.getpid(), secrets.token_hex(8))
    deadline = time.time() + LOCK_TIMEOUT
    while True:
        try:
            fd = os.open(str(lp), os.O_CREAT | os.O_RDWR)
        except OSError as e:
            return None, "无法打开锁文件（%s）：%s" % (lp, e)
        got = _os_lock(fd)
        if got is True:
            epoch = (_read_lock(lp)[0] or 0) + 1
            try:
                os.lseek(fd, 0, os.SEEK_SET)
                os.write(fd, _lock_text(epoch, token).encode("utf-8"))
            except OSError:
                pass
            return Lock(fd, lp, token, epoch, "os-lock"), ""
        if got is None:
            # **不降级**（不存在 EXCL/stale 退化路径）。
            #  理由：那条路径要引入锁龄抢占 + epoch 继承 + 另一次 rename 竞态，
            #  而它换来的只是"在一个不保证建议锁的文件系统上假装有互斥"。
            #  宁可**明确失败**：让人看到"这里不能用"，而不是以为受保护。
            try:
                os.close(fd)
            except OSError:
                pass
            return None, ("本工作区所在文件系统**不支持操作系统建议锁**——共享写不可用。"
                          "请把工作区放在本地文件系统（NFS/SMB 与部分容器卷不支持）。"
                          "**明确失败，不降级**：降级会给出无法兑现的保证。")
        try:
            os.close(fd)
        except OSError:
            pass
        if time.time() >= deadline:
            return None, ("锁被占用超过 %.0f 秒（%s）——拒绝写入；持有者可能只是被暂停，"
                          "抢占会破坏互斥，故本实现选择失败而不是抢" % (LOCK_TIMEOUT, lp.name))
        time.sleep(0.02 + (os.getpid() % 7) * 0.003)


def release_lock(lock) -> None:
    """放锁：**只删属于自己的锁**。

    **为什么要核对归属**：若**无条件 unlink**，旧持有者恢复后执行 finally，
    会把抢占者刚建的锁删掉，于是第三个进程可径直进入临界区（互斥被破坏）。
    **本实现根本不删锁文件**（release = unlock + close），故 token/epoch **不再参与放锁判定**；
    上一代「先核对再删」的做法已随 `unlink` 一起移除。
    """
    if lock is None:
        return
    # **释放路径里没有 unlink**——这是「删机制」而不是「加判断」。
    #
    #  为什么必须删：POSIX 下 path → inode 不是稳定映射。若释放时删锁文件，会出现：
    #    A: verify -> flock(UN) -> close ->            （窗口）
    #                     B: open(path) -> flock(EX) 成功（拿到 inode1）
    #    A: unlink(path)                              <= 删掉的是 **B 的锁文件**
    #                     C: open(path, O_CREAT) 造出 inode2 -> flock(EX) 成功
    #  => B 与 C 各持**不同 inode** 的锁，同一路径出现两个「合法持锁者」，互斥被破坏。
    #  （Windows 看不到这个窗口：文件被打开时 unlink 会失败——所以它只在 POSIX 暴露。）
    #
    #  删掉 unlink 之后，锁文件成为**工作区生命周期内的永久产物**：
    #    归属只由 fd 上的 OS 锁决定，**不由「文件是否存在」决定**——路径与锁对象重新一一对应。
    #  代价：工作区里会留下 *.lock 文件（它们是**装置**，不是垃圾）。
    try:
        _os_unlock(lock.fd)
    except Exception:
        pass
    try:
        os.close(lock.fd)
    except Exception:
        pass
    lock.released = True




@contextmanager
def exclusive_resource(path):
    """**唯一原语入口**：with exclusive_resource(p) as lock: ...

    取不到锁时 yielded 值为 None——**调用方必须检查并放弃操作**，不要继续往下写。
    这是业务层唯一该碰的东西。
    """
    lock, why = acquire_lock(Path(path))
    try:
        yield lock
    finally:
        if lock is not None:
            release_lock(lock)
