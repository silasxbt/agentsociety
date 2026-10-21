#!/usr/bin/env python3
"""动力学自动校准回路：训练靶标拟合 + 留出靶标检验（规则层，不耗 LLM）。

这是 harness 提案--评估闭环的下一阶段：提案对象从“干预排期”换成“动力学参数”，
评估仍由确定性规则层完成，每个候选全量落盘，留出靶标只看不调。

== 预注册（2026-10-21，运行前写定，跑后不改）=================================
动机：画像消融（tests/profile_ablation_report.md）显示三年孤独持续率约 98%（靶标 53.3%），
  模型缺少孤独状态转移。新增参数 lonely_noise_sd（月度个体扰动，默认 0）。
候选空间（网格，全部评估，不提前停止）：
  lonely_relaxation ∈ {0.2, 0.3, 0.4, 0.5}
  lonely_noise_sd   ∈ {0, 0.04, 0.08, 0.12, 0.16, 0.20}
  lonely_target_base ∈ {0.80, 0.85, 0.90}
  共 72 个候选；其余动力学与干预参数取默认值。
评估设置：校准画像，种子 101–120（与消融的 1–20 不重叠），每种子 20 人，none，
  48 个月，前 12 个月预热；指标定义同 scan_profile_ablation.py 的 B1–B4。
训练目标：B1（15%）、B2（40%）、B3（27.2%）三项绝对误差均值（pp），越小越好。
留出靶标：B4 三年持续率 53.3%，**不进入目标函数**，只报告。
选择规则：训练误差最小者；并列取 noise 较小、relaxation 较大者（更接近原模型）。
验收（全部报告，不论通过与否）：
  V1 选中候选的留出误差 < 默认参数（relaxation 0.5, noise 0, base 0.90）的留出误差；
  V2 72 个候选上训练误差与留出误差的 Spearman 相关 > 0（训练变好时留出不变差）。
输出：init/dynamics_v2_tuned.json（只含被调参数）、tests/calibrate_dynamics_log.jsonl（逐候选）、
  tests/calibrate_dynamics_result.json（汇总与验收）。
==========================================================================
用法：AGENTSOCIETY_LLM_API_KEY=dummy AGENTSOCIETY_LLM_API_BASE=http://localhost \\
       <venv-python> tools/calibrate_dynamics.py
"""
from __future__ import annotations

import asyncio
import itertools
import json
import random
import statistics
import sys
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXP / "tests"))
import scan_profile_ablation as ab  # noqa: E402
from gen_profiles import make_elders  # noqa: E402

SEEDS = list(range(101, 121))
GRID = {"lonely_relaxation": [0.2, 0.3, 0.4, 0.5],
        "lonely_noise_sd": [0.0, 0.04, 0.08, 0.12, 0.16, 0.20],
        "lonely_target_base": [0.80, 0.85, 0.90]}
DEFAULT = {"lonely_relaxation": 0.5, "lonely_noise_sd": 0.0, "lonely_target_base": 0.90}
TRAIN = ["B1_lonely_often", "B2_lonely_sometimes_plus", "B3_incidence_3y"]
HOLD = "B4_persistence_3y"


async def evaluate(params: dict) -> dict:
    ab.DYNAMICS.clear()
    ab.DYNAMICS.update(params)
    b1, b2 = [], []
    inc_n = inc_k = per_n = per_k = 0
    for s in SEEDS:
        elders = make_elders(random.Random(s), ab.N_ELDERS, 0, "calibrated")
        _, sn = await ab.run_env(elders, s, "none", ab.HORIZON, snap=(ab.BURN_IN, ab.HORIZON))
        l0, l1 = sn[ab.BURN_IN], sn[ab.HORIZON]
        b1.append(sum(x >= 0.6 for x in l0) / len(l0))
        b2.append(sum(x >= 0.45 for x in l0) / len(l0))
        for a, b in zip(l0, l1):
            if a < 0.6:
                inc_n += 1
                inc_k += b >= 0.6
            else:
                per_n += 1
                per_k += b >= 0.6
    sim = {"B1_lonely_often": statistics.mean(b1), "B2_lonely_sometimes_plus": statistics.mean(b2),
           "B3_incidence_3y": inc_k / inc_n if inc_n else float("nan"),
           "B4_persistence_3y": per_k / per_n if per_n else float("nan")}
    err = {k: abs(sim[k] - ab.TARGETS[k]) * 100 for k in ab.TARGETS}
    return {"params": params, "sim": {k: round(v, 4) for k, v in sim.items()},
            "err_pp": {k: round(v, 2) for k, v in err.items()},
            "train_err": round(statistics.mean(err[k] for k in TRAIN), 3),
            "holdout_err": round(err[HOLD], 2), "at_risk": [inc_n, per_n]}


def spearman(x: list, y: list) -> float:
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        for pos, i in enumerate(order):
            r[i] = pos
        return r
    rx, ry = rank(x), rank(y)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else float("nan")


async def main() -> int:
    log_p = EXP / "tests" / "calibrate_dynamics_log.jsonl"
    rows = []
    with log_p.open("w", encoding="utf-8") as f:
        for vals in itertools.product(*GRID.values()):
            r = await evaluate(dict(zip(GRID, vals)))
            rows.append(r)
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            print(f"{r['params']} train={r['train_err']:.2f} hold={r['holdout_err']:.1f}", flush=True)
    best = min(rows, key=lambda r: (r["train_err"], r["params"]["lonely_noise_sd"],
                                    -r["params"]["lonely_relaxation"]))
    default = next(r for r in rows if r["params"] == DEFAULT)
    rho = spearman([r["train_err"] for r in rows], [r["holdout_err"] for r in rows])
    result = {"preregistered": "见脚本头部（2026-10-21）", "seeds": SEEDS, "grid": GRID,
              "best": best, "default": default, "spearman_train_vs_holdout": round(rho, 3),
              "V1_holdout_improves": best["holdout_err"] < default["holdout_err"],
              "V2_positive_spearman": rho > 0}
    (EXP / "tests" / "calibrate_dynamics_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (EXP / "init" / "dynamics_v2_tuned.json").write_text(
        json.dumps(best["params"], ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("best", "spearman_train_vs_holdout",
                                             "V1_holdout_improves", "V2_positive_spearman")},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
