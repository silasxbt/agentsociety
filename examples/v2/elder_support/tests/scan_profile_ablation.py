#!/usr/bin/env python3
"""画像消融：调查校准画像 vs 普通随机 vs 真实记录重抽（规则层，不耗 LLM）。

== 预注册（2026-10-21，运行前写定，跑后不改）=================================
问题：按调查分布生成的画像，是否比“普通随机”更贴近现实？保留维度间相关是否更好？
画像来源（gen_profiles.PROFILE_SOURCES）：
  calibrated —— CLHLS 2021 独居 65+ 边际分布逐维独立抽样（主批次所用）
  uniform    —— 锚定维度在同一取值范围内均匀随机（普通随机基线）
  resample   —— CLHLS 2021 独居受访者整条重抽（保留联合分布；受限数据）
未锚定维度（外向性、邻里关系、子女距离与联系频率规则）三种来源完全相同。
设计：每种来源 20 个种子（1–20），每种子 20 位老人，全部为规则层；decay=0.06；
  环境动力学与干预参数均取默认值（DEFAULT_DYNAMICS / INTERVENTION_DEFAULTS）。

指标 A（输入保真）：每个种子 20 人相对 CLHLS 边际分布的总变差距离（TVD），
  维度为年龄段、性别、自评健康、孤独感五档、在世子女数（0–6，6 含 6+），取五维均值。
指标 B（输出靶标，主指标）：none 条件运行 48 个月，前 12 个月为预热（初值向模型稳态回归）。
  B1 第 12 月截面 ℓ≥0.6 占比，靶标 15%（CLHLS b38 总是+经常）
  B2 第 12 月截面 ℓ≥0.45 占比，靶标 40%（b38 总是+经常+有时）
  B3 三年孤独发生率：第 12 月 ℓ<0.6 者中第 48 月 ℓ≥0.6 的比例，靶标 27.2%（Harmonized CHARLS）
  B4 三年孤独持续率：第 12 月 ℓ≥0.6 者中第 48 月仍 ≥0.6 的比例，靶标 53.3%（同上）
  B3/B4 在 20 个种子合并（400 人）后计算；B1/B2 报告种子均值±SD。
  主指标 = 四项绝对误差的均值（百分点）。判定：主指标越小越贴近现实；
  不做显著性检验，同时报告逐项误差，不只报告合计。
指标 C（结论稳定性）：24 个月、四条件，比较三种来源下
  干预期 / 撤出期孤立率相对 none 的同种子配对差（均值±SD）与干预排序是否一致。
已知局限（预先写明）：ℓ 的切点 0.6 / 0.45 是建模映射，未经调查标定；三年靶标来自
  CHARLS（60+）而画像来自 CLHLS（65+）；动力学未经校准，本实验只比较画像来源。
==========================================================================

用法：AGENTSOCIETY_LLM_API_KEY=dummy AGENTSOCIETY_LLM_API_BASE=http://localhost \\
       <venv-python> tests/scan_profile_ablation.py [--sources calibrated,uniform,resample]
输出：tests/profile_ablation_result.json（只含汇总，不含个体记录）
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import sys
import tempfile
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = EXP_DIR.parents[2]
sys.path.insert(0, str(REPO_ROOT / "custom" / "envs"))
sys.path.insert(0, str(EXP_DIR / "init"))
from elder_support_env import ElderSupportEnv  # noqa: E402
from gen_profiles import _HEALTH_MAP, _LONELY_MAP, load_dist, make_elders  # noqa: E402

SEEDS = list(range(1, 21))
N_ELDERS = 20
DECAY = 0.06
BURN_IN, HORIZON = 12, 48
IV_START, IV_END, MONTHS = 7, 18, 24
CONDITIONS = ["none", "casework", "timebank", "platform"]
TARGETS = {"B1_lonely_often": 0.15, "B2_lonely_sometimes_plus": 0.40,
           "B3_incidence_3y": 0.272, "B4_persistence_3y": 0.533}
AGE_BANDS = [("65-69", 65, 69), ("70-74", 70, 74), ("75-79", 75, 79), ("80-84", 80, 84),
             ("85-89", 85, 89), ("90-94", 90, 94), ("95+", 95, 200)]


def _nearest(x: float, mapping: dict) -> str:
    return min(mapping, key=lambda k: abs(mapping[k] - x))


def _tvd(sample: Counter, target: dict) -> float:
    n = sum(sample.values())
    keys = set(target) | {str(k) for k in sample}
    return 0.5 * sum(abs(sample.get(k, 0) / n - target.get(k, 0.0)) for k in keys)


def input_fidelity(elders: list, dist: dict) -> dict:
    age = Counter(next(b for b, lo, hi in AGE_BANDS if lo <= e["age"] <= hi) for e in elders)
    sex = Counter("1" if e["gender"] == "男" else "2" for e in elders)
    health = Counter(_nearest(e["health"], _HEALTH_MAP) for e in elders)
    lonely = Counter(_nearest(e["loneliness"], _LONELY_MAP) for e in elders)
    kids = Counter(str(min(len(e["children"]), 6)) for e in elders)
    kid_target: dict = {}
    for k, v in dist["alive_children_count"].items():
        key = str(min(int(k), 6))
        kid_target[key] = kid_target.get(key, 0.0) + v
    d = {"age_band": _tvd(age, dist["age_band"]), "sex": _tvd(sex, dist["sex"]),
         "health_b12": _tvd(health, dist["self_rated_health_b12"]),
         "loneliness_b38": _tvd(lonely, dist["loneliness_b38"]),
         "children": _tvd(kids, kid_target)}
    d["mean"] = statistics.mean(d.values())
    return d


async def run_env(elders: list, seed: int, cond: str, months: int, snap: tuple = ()) -> tuple:
    iv = None if cond == "none" else {"type": cond, "start_month": IV_START,
                                      "end_month": IV_END, "params": {}}
    snaps = {}
    with tempfile.TemporaryDirectory() as td:
        env = ElderSupportEnv(elders=elders, seed=seed, decay_rate=DECAY, intervention=iv)
        env._bind_workspace(Path(td) / "ws")
        t = datetime(2026, 1, 1, 8)
        for tick in range(months + 1):
            await env.step(tick, t)
            t += timedelta(days=30)
            if tick in snap:
                snaps[tick] = [e["loneliness"] for e in env._elders.values()]
        rows = [json.loads(x) for x in (Path(td) / "ws" / "state" / "metrics.jsonl")
                .read_text(encoding="utf-8").splitlines() if x.strip()]
    return rows, snaps


def window_mean(rows: list, lo: int, hi: int, key: str = "isolation_rate") -> float:
    return statistics.mean(r[key] for r in rows if lo <= r["month"] <= hi)


def agg(vals: list) -> dict:
    return {"mean": round(statistics.mean(vals), 4), "sd": round(statistics.stdev(vals), 4)}


async def run_source(source: str, dist: dict) -> dict:
    fid, b1, b2 = [], [], []
    inc_n = inc_k = per_n = per_k = 0
    paired = {c: {"iv": [], "post": []} for c in CONDITIONS[1:]}
    for s in SEEDS:
        elders = make_elders(random.Random(s), N_ELDERS, 0, source)
        fid.append(input_fidelity(elders, dist))
        _, snaps = await run_env(json.loads(json.dumps(elders)), s, "none", HORIZON,
                                 snap=(BURN_IN, HORIZON))
        l0, l1 = snaps[BURN_IN], snaps[HORIZON]
        b1.append(sum(x >= 0.6 for x in l0) / len(l0))
        b2.append(sum(x >= 0.45 for x in l0) / len(l0))
        for a, b in zip(l0, l1):
            if a < 0.6:
                inc_n += 1
                inc_k += b >= 0.6
            else:
                per_n += 1
                per_k += b >= 0.6
        base, _ = await run_env(json.loads(json.dumps(elders)), s, "none", MONTHS)
        for c in CONDITIONS[1:]:
            rows, _ = await run_env(json.loads(json.dumps(elders)), s, c, MONTHS)
            paired[c]["iv"].append(window_mean(rows, IV_START, IV_END) - window_mean(base, IV_START, IV_END))
            paired[c]["post"].append(window_mean(rows, IV_END + 1, MONTHS) - window_mean(base, IV_END + 1, MONTHS))
    sim = {"B1_lonely_often": statistics.mean(b1), "B2_lonely_sometimes_plus": statistics.mean(b2),
           "B3_incidence_3y": inc_k / inc_n if inc_n else float("nan"),
           "B4_persistence_3y": per_k / per_n if per_n else float("nan")}
    err = {k: abs(sim[k] - TARGETS[k]) * 100 for k in TARGETS}
    return {
        "A_input_tvd": {k: agg([f[k] for f in fid]) for k in fid[0]},
        "B_output": {k: {"sim": round(sim[k], 4), "target": TARGETS[k],
                         "abs_err_pp": round(err[k], 2)} for k in TARGETS},
        "B_seed_sd": {"B1": round(statistics.stdev(b1), 4), "B2": round(statistics.stdev(b2), 4)},
        "B_counts": {"incidence_at_risk": inc_n, "persistence_at_risk": per_n},
        "B_primary_mean_abs_err_pp": round(statistics.mean(err.values()), 2),
        "C_paired_vs_none": {c: {w: agg(v) for w, v in paired[c].items()} for c in paired},
        "C_iv_ranking": sorted(paired, key=lambda c: statistics.mean(paired[c]["iv"])),
    }


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default="calibrated,uniform,resample")
    srcs = ap.parse_args().sources.split(",")
    dist = load_dist()
    out = {"preregistered": "见脚本头部（2026-10-21）", "seeds": SEEDS, "n_elders": N_ELDERS,
           "decay": DECAY, "burn_in": BURN_IN, "horizon": HORIZON, "targets": TARGETS,
           "results": {}}
    for src in srcs:
        out["results"][src] = await run_source(src, dist)
        r = out["results"][src]
        print(f"{src:<11} 输入TVD {r['A_input_tvd']['mean']['mean']:.3f}  "
              f"输出主误差 {r['B_primary_mean_abs_err_pp']:.1f}pp  "
              + "  ".join(f"{k.split('_')[0]}={v['sim']:.1%}" for k, v in r["B_output"].items()))
    p = Path(__file__).with_name("profile_ablation_result.json")
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
