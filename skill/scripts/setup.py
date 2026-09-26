# -*- coding: utf-8 -*-
"""setup.py —— 首次启动的配置向导（问用户三件事，然后把决定留痕）

用法：
    python setup.py <工作区根> --plan                 # 打印询问单（AI 拿去问用户）
    python setup.py <工作区根> --apply [--git yes|no] [--audit-days N] [--commit]

为什么要有这个脚本：
    首次建工作区有几件事**只有用户能定**，而定错了要么返工、要么留下没用的空档案。
    但"问"本身不该由 AI 自由发挥——**问题的清单与推荐值应当是包的一部分**，否则每次接手的
    AI 问的东西都不一样，用户每次要重新想一遍。本脚本把询问单固定下来。

为什么 --plan 与 --apply 分开：
    AI 先跑 --plan 拿到询问单 → 问用户 → 拿到答复后跑 --apply。
    **不在脚本里做交互式提问**：脚本要能在无人值守下重跑，交互会把自动化堵死。

依据：references/onboarding.md §1（形态判定）· §3（初始化清单）· §5（首次启动的四问）
回本口径：把首次配置的询问、执行与留痕固定成两步命令，省掉每次"现场发明问题"的反复。
踩坑记录：
    · **不要覆盖已有的 .git**——已启用版本控制的工作区再 init 会报错并可能损坏 .gitignore；
    · MAP 的「工作区备份方式」是功能契约里的登记项，改它必须**只改那一行的值**，不能整段重写；
    · 首次配置的决定要写进元数据通道——否则"当时选了 git"这件事本身又是一条无据的声明。
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import note, ok, problem, read, summary, run, usage_exit  # noqa: E402
import lease as _lease  # noqa: E402  —— 共享文件写原语（CAS）
from stamp import ai_id  # noqa: E402

GITIGNORE = """# 协同工作区 .gitignore
# 只忽略可再生与临时产物；reports/ INDEX/ STATE/ tasks/ 是本工作区的价值本身，必须入库。
scripts/__pycache__/
__pycache__/
*.pyc
*.tmp
CONFLICT_*.md
"""


def _git(root: Path, *args):
    try:
        p = subprocess.run(["git", *args], cwd=str(root), stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=120, check=False)
        return p.returncode, p.stdout.decode("utf-8", "replace").strip()
    except FileNotFoundError:
        return 127, "未找到 git 可执行文件"
    except Exception as e:
        return 1, str(e)


def update_map_backup(root: Path, value: str) -> bool:
    """只改 MAP 环境段「工作区备份方式」那一行的括号值。"""
    p = root / "MAP.md"
    txt = read(p)
    if txt is None:
        return False
    out, hit = [], False
    for line in txt.splitlines():
        if "工作区备份方式" in line and not hit:
            new = re.sub(r"[\x60\[]([^\]\x60\]]*)[\]\x60]", "[\u0060%s\u0060]" % value, line, count=1)
            if new == line:   # 没有方括号/反引号包裹的占位
                new = line.rstrip() + "（备份方式 = %s）" % value
            out.append(new)
            hit = True
        else:
            out.append(line)
    if hit:
        # 共享文件（.gitignore / MAP.md）的写必须走原语：以「读到的原文」为前置条件
        _okk, _why = _lease.shared_rewrite(root, p, "\n".join(out) + "\n", txt, "首次配置写入")
        if not _okk:
            note("写入被拒：%s" % _why)
            return False
    return hit


def append_meta(root: Path, text: str):
    """往元数据通道追加一条（走 CAS 原语）。"""
    p = root / "REVIEWS.md"
    if not p.exists():
        return False
    _okk, _why = _lease.shared_append(root, p, text, "首次配置留痕")
    if not _okk:
        note("留痕被拒：%s" % _why)
    return _okk


PLAN = """首次配置询问单（请用户逐条定；括号内为推荐值与理由）

① 本地 git 备份 —— 启用吗？      推荐：【启用】
   · 它同时解锁三件事：凭证锚（改动点附 commit hash）、越界改动检查、**强机器戳**
   · 未启用时，人检/身份锚的戳只能是"弱"档（能写文件的人也能写同形戳）
   · 代价：每次提交多一条 git 命令；工作区会多一个 .git 目录

② 定期全盘核查周期 —— 几天一次？  推荐：【7 天】
   · 核查是跑脚本，**不消耗模型上下文**；周期只决定"多久没人跑就要报红"
   · 开关写着「开」而没人跑 = 假账；本包用 REVIEWS.md 里的机器戳证据自查，超期即红

③ 工作流之外的脚本 —— 要装哪些？（可全不选）
   这些不进日常接手路径，只在**用户自己想检查**时用：
   · 全盘核查      audit_all.py    一条命令跑完全部门禁并留痕          【推荐】
   · 一屏全貌      overview.py     项目现在什么状态                    【推荐】
   · 代码度量      code_metrics.py 每次改代码后跑                      【写代码的项目推荐】
   · 项目专属脚本  new_local.py    本项目特有的检查，起手生成骨架      【按需】
   · 定时提醒 / 可视化 / 报告  —— 属 tools\\ 规范，**强依赖平台，不随包实现**

④ 初始化收尾 —— 现在建第一张任务卡吗？  推荐：【建】
   · 任务卡与设计卡是**人机之间的派发接口**：由人开口、AI 落卡。
     **用户不知道它存在，功能就等于没装**——工作区建得再齐，用户照旧用"帮我改一下 XX"重新开始。
   · 交付话术（照读四句）见 references/onboarding.md §6；本节只负责**把用户的答复记下来**。
   · 答复必须由**用户**给出，AI 不得代填（锚源原则，见 references/audit.md §2.0）；
     没问到就写 unasked —— 宁可留一个 [待核]，不要一条假账。

定完请执行：
   python setup.py <工作区根> --apply --git yes --audit-days 7 --cards yes [--commit]
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="首次启动配置向导（先 --plan 问，再 --apply 执行）")
    usage_exit(ap)
    ap.add_argument("root")
    ap.add_argument("--plan", action="store_true", help="打印询问单后退出")
    ap.add_argument("--apply", action="store_true", help="执行配置")
    ap.add_argument("--git", choices=["yes", "no"], default="no")
    ap.add_argument("--audit-days", type=int, default=7)
    ap.add_argument("--commit", action="store_true", help="git 启用后立即做首次提交")
    ap.add_argument("--cards", choices=["yes", "no", "unasked"], default="unasked",
                    help="初始化收尾：用户是否要现在建第一张任务卡（unasked = 没问到，记待核）")
    a = ap.parse_args()

    if a.plan or not a.apply:
        print(PLAN)
        return 0

    root = Path(a.root)
    if not root.is_dir():
        problem("工作区根不存在：%s" % root)
        return 3
    decided = []

    print("== 1. 本地 git 备份 ==")
    if a.git == "yes":
        if (root / ".git").exists():
            note("已存在 .git —— 跳过 init（不覆盖既有版本控制）")
            decided.append("git=已有")
        else:
            rc, out = _git(root, "--version")
            if rc != 0:
                problem("git 不可用：%s —— 备份未启用" % out)
            else:
                _git(root, "init", "-q")
                (root / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
                ok("已 git init 并写入 .gitignore（只忽略可再生与临时产物）")
                decided.append("git=新启用")
                if a.commit:
                    _git(root, "add", "-A")
                    rc2, out2 = _git(root, "commit", "-q", "-m",
                                     "chore: 初始化协同工作区")
                    if rc2 != 0 and "identity unknown" in out2:
                        # 不伪造身份：用具名"机器代理"身份，并在输出里讲清它是机器产生的。
                        # 这与 audit.md §2.0 的锚源原则一致——身份要么是真的人，要么是机器；
                        # 不要拿一个编造的人名去冒充提交者。
                        _git(root, "config", "user.name", "ai-relay")
                        _git(root, "config", "user.email", "ai-relay@%s.local" % ai_id())
                        rc2, out2 = _git(root, "commit", "-q", "-m",
                                         "chore: 初始化协同工作区")
                        note("git 未配置提交身份 → 已设**仓库级**机器身份 ai-relay@%s.local（不改全局配置）"
                             % ai_id())
                        note("要让提交归属到你个人，请自行改写：git config user.name / user.email")
                    (ok if rc2 == 0 else note)("首次提交完成" if rc2 == 0 else "首次提交跳过：%s" % out2.splitlines()[0])
        if update_map_backup(root, "git"):
            ok("MAP 环境段「工作区备份方式」已登记为 git")
        else:
            note("MAP 里未找到「工作区备份方式」行 —— 请手工登记")
    else:
        note("未启用 git —— 凭证锚与越界改动检查不可用，机器戳只能到「弱」档")
        decided.append("git=未启用")
        update_map_backup(root, "无")

    print()
    print("== 2. 定期核查周期 ==")
    n = 0
    p = root / "MAP.md"
    txt = read(p)
    if txt:
        out, hit = [], False
        for line in txt.splitlines():
            if "定期排查" in line and not hit:
                new = re.sub(r"(开|关)", "开", line, count=1)
                if "周期" not in new:
                    new = new.rstrip() + ("（周期 %d 天）" % a.audit_days)
                else:
                    new = re.sub(r"周期\s*\d+\s*天", "周期 %d 天" % a.audit_days, new)
                out.append(new)
                hit = True
                n += 1
            else:
                out.append(line)
        if hit:
            _okk, _why = _lease.shared_rewrite(root, p, "\n".join(out) + "\n", txt, "MAP 规则段改写")
            if not _okk:
                problem("MAP 写入被拒：%s" % _why)
                return summary()
            ok("MAP 规则段「定期排查」已设为 开（周期 %d 天）" % a.audit_days)
            decided.append("audit_days=%d" % a.audit_days)
    if not n:
        note("MAP 里未找到「定期排查」行 —— 请手工登记")

    print()
    print("== 3. 初始化收尾：首张任务卡（话术见 references/onboarding.md §6） ==")
    if a.cards == "yes":
        ok("用户答复：现在建第一张任务卡")
        note('执行：python scripts/closeout.py <工作区根> new-card "<任务名>"')
        note("要先定方案就先建设计卡：同一命令加 --design（**未批准的设计不生成执行卡**）")
        decided.append("首张任务卡=用户答『要』")
    elif a.cards == "no":
        note("用户答复：暂不建卡（下次对话可再问一次，不重复念）")
        decided.append("首张任务卡=用户答『暂不』")
    else:
        tbd("未记录用户答复（--cards unasked）——**不得代填**；下次对话补问，话术见 references/onboarding.md §6")
        decided.append("首张任务卡=未问")

    print()
    print("== 4. 决定留痕 ==")
    now = datetime.now(timezone.utc).astimezone().replace(microsecond=0).isoformat()
    if append_meta(root, "- %s · 首次配置 · %s · %s" % (now, ai_id(), " ".join(decided))):
        ok("配置决定已写入元数据通道（REVIEWS.md）——「当时选了什么」本身也要有据")
    else:
        note("无 REVIEWS.md —— 配置决定未留痕")
    print()
    note("下一步：python scripts/validate_workspace.py <工作区根> —— 退出码 0 才算建好")
    note("再跑一次全盘核查留底：python scripts/audit_all.py <工作区根>")
    return summary()


if __name__ == "__main__":
    sys.exit(run(main))
