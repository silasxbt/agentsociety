#!/usr/bin/env python3
"""生成画像消融的逐种子输入保真表（只输出 TVD，无个体记录）。

设计沿用 tests/scan_profile_ablation.py 头部预注册：来源 calibrated / uniform / resample，
种子 1--20，每种子 20 人；五维 TVD 为年龄、性别、健康、孤独、子女数 TVD 的均值。
输出：tests/profile_fidelity_by_seed.csv / .md。resample 需要受限记录文件，只在数据机器运行。
"""
from __future__ import annotations

import csv
import random
import sys
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXP / "tests"))
sys.path.insert(0, str(EXP / "init"))
from gen_profiles import load_dist, make_elders  # noqa: E402
from scan_profile_ablation import input_fidelity  # noqa: E402

SEEDS = range(1, 21)
SOURCES = ("calibrated", "uniform", "resample")


def main() -> None:
    dist = load_dist()
    rows = []
    for seed in SEEDS:
        row = {"seed": seed}
        for source in SOURCES:
            elders = make_elders(random.Random(seed), 20, 0, source)
            f = input_fidelity(elders, dist)
            row[source] = round(f["mean"], 4)
            for key, val in f.items():
                if key != "mean":
                    row[f"{source}_{key}"] = round(val, 4)
        rows.append(row)
    csv_p = EXP / "tests" / "profile_fidelity_by_seed.csv"
    with csv_p.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    lines = ["# 画像输入保真：逐种子 TVD", "",
             "五维 TVD 均值，越小越贴近 CLHLS 边际分布；每种子 20 人。", "",
             "| seed | 校准边际 | 普通随机 | 记录重抽 |", "|---:|---:|---:|---:|"]
    lines += [f"| {r['seed']} | {r['calibrated']:.4f} | {r['uniform']:.4f} | {r['resample']:.4f} |" for r in rows]
    (EXP / "tests" / "profile_fidelity_by_seed.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(csv_p)


if __name__ == "__main__":
    main()
