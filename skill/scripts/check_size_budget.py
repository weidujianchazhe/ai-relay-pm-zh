# -*- coding: utf-8 -*-
"""check_size_budget.py —— 入口成本预算检查（独立脚本）

用法：python check_size_budget.py <技能包根 | 实例工作区>
退出码：0 通过 · 1 超预算 · **2 取不到阈值（无法判定 → [待核]）** · 3 用法错误
阈值：`config/defaults.yml`（技能包布局）或 `config.yml`（实例工作区布局）的 `skill_max_chars`

为什么阈值查找要认两种布局（2026-10-15 实测出的缺陷）：
  本脚本此前只认 `<root>/config/defaults.yml`，而 `references/README.md` ② 规定的实例化是
  `config/defaults.yml → config.yml`——**实例工作区里没有 config/defaults.yml**。
  于是它在工作区上恒返回 3，而 `audit_all.py` 的聚合又把 3 折成 1：
  每 7 天的定期全盘核查（setup 推荐启用）在**健康工作区**上永久红灯，且成员汇总显示 `[问题] 0`。
  这正是 `scripts/README.md` 明文警告的形态——「否则核查者会把『脚本崩了』读成『项目有问题』」。

为什么取不到阈值是 2 而不是 3：
  统一约定（`scripts/README.md`）是 0 通过 · 1 有问题 · **2 仅待核** · 3 脚本自身错误。
  「找不到阈值文件」是本脚本**无法判定**，不是它自己崩了；打成 [待核] 就必须返回 2，
  否则编排层无法把「门禁没能判」与「门禁判出问题」区分开——两者在聚合里都成了红灯。

为什么是 8000（本包自定，非行业标准，写明理由以免被当成拍脑袋）:
  实测 3.9.x 入口约 7,200 字符（瘦身后），留约 10% 余量给必要增量；
  它的作用不是"越短越好"，而是【拦住入口的单调膨胀】——
  一旦超限，正确反应是先审视"这条增量是否真的值得让每次触发都付费"，
  而不是随手把预算调高（调高等于取消这道闸门）。

为什么单独成脚本：gen_views.py 内存在两个连续 return summary()，
任何插到 main() 尾部的检查都会落在死区；独立脚本避开该结构风险，
且可被变异自检（把阈值调小 -> 必须变红）证明其为真门禁。
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import note, ok, problem, tbd  # noqa: E402


def check(root):
    #  两种布局都要认（顺序即优先级）：
    #    ① `<root>/config/defaults.yml` —— 技能包出厂布局
    #    ② `<root>/config.yml`          —— 实例工作区布局（README ② 规定：defaults.yml → config.yml）
    #  **不做「回落到包内 defaults」的兜底**：本脚本量的是**传入 root 的入口**，
    #  用包内阈值去判别人的 SKILL.md 会把两个对象混成一个（锚源原则：判定依据须与被判定对象同源）。
    cfg = None
    for cand in (root / "config" / "defaults.yml", root / "config.yml"):
        if cand.exists():
            cfg = cand
            break
    if cfg is None:
        tbd("未找到阈值配置（试过 config/defaults.yml 与 config.yml），无法判定入口预算")
        return 2
    m = re.search(r"^\s*skill_max_chars:\s*(\d+)", cfg.read_text(encoding="utf-8"), re.M)
    if not m:
        tbd("%s 未声明 skill_max_chars，无法判定入口预算" % cfg.name)
        return 2
    budget = int(m.group(1))
    sk = root / "SKILL.md"
    if not sk.exists():
        problem("SKILL.md 不存在")
        return 1
    n = len(sk.read_text(encoding="utf-8"))
    if n > budget:
        problem("入口成本：SKILL.md %d 字符 > 预算 %d" % (n, budget))
        return 1
    ok("入口成本：SKILL.md %d 字符 <= 预算 %d（阈值取自 %s）" % (n, budget, cfg.name))
    return 0


def main(argv):
    if len(argv) < 2:
        print("[用法] python check_size_budget.py <技能包根 | 实例工作区>")
        return 3
    return check(Path(argv[1]).resolve())


if __name__ == "__main__":
    sys.exit(main(sys.argv))
