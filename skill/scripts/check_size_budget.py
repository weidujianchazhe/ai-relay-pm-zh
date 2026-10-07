# -*- coding: utf-8 -*-
"""check_size_budget.py —— 入口成本预算检查（独立脚本）

用法：python check_size_budget.py <技能包根>
退出码：0 通过 · 1 超预算 · 3 脚本/用法错误（取不到阈值即 3，不静默兜底）
阈值：config/defaults.yml 的 skill_max_chars

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
    cfg = root / "config" / "defaults.yml"
    if not cfg.exists():
        tbd("未找到 config/defaults.yml，无法取预算")
        return 3
    m = re.search(r"^\s*skill_max_chars:\s*(\d+)", cfg.read_text(encoding="utf-8"), re.M)
    if not m:
        tbd("config/defaults.yml 未声明 skill_max_chars")
        return 3
    budget = int(m.group(1))
    sk = root / "SKILL.md"
    if not sk.exists():
        problem("SKILL.md 不存在")
        return 1
    n = len(sk.read_text(encoding="utf-8"))
    if n > budget:
        problem("入口成本：SKILL.md %d 字符 > 预算 %d" % (n, budget))
        return 1
    ok("入口成本：SKILL.md %d 字符 <= 预算 %d" % (n, budget))
    return 0


def main(argv):
    if len(argv) < 2:
        print("[用法] python check_size_budget.py <技能包根>")
        return 3
    return check(Path(argv[1]).resolve())


if __name__ == "__main__":
    sys.exit(main(sys.argv))
