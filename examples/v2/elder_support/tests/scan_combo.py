#!/usr/bin/env python3
"""规则层干预组合扫描：社工探访 × 互助结对的交互、顺序与接续（不耗 LLM）。

== 预注册（2026-11-10 运行前写定并提交；跑完不改假设、指标、种子与判定）==========
研究问题：在独居老人支持网络中，社工探访（正式支持）与互助结对（非正式互助）
组合实施，是否有超出两者之和的协同？实施顺序是否改变撤出后的持续性？
“社工开路、互助接续”需要多强的接续机制才成立？

组别（干预期总体为第 7–18 月；观察到第 30 月，撤出后 12 个月）：
  A  none                                   基线
  B  casework 7–18                          12 服务月
  C  timebank 7–18                          12 服务月
  E  casework 7–18 + timebank 7–18（同月内社工先执行）   24 服务月（2×2 析因的交互格）
  D  casework 7–12 → timebank 13–18         12 服务月，“社工开路、互助接续”
  F  timebank 7–12 → casework 13–18         12 服务月，与 D 等量、仅顺序相反
接续机制（显式假设，无文献点估计，只扫描）：handover_boost b ∈ {0, 0.25, 0.5, 1}。
  结对建立时受助者已被社工探访过，则该结对撤出后的延续概率 p → p + b·(1−p)。
  只作用于 D、E（F 中结对先于探访，按定义不受影响；B、C 不含两种成分）。
  b = 0 为置零对照：组合只是两种成分按时间窗叠加。
敏感性：互助结对撤出后延续概率 post_persist ∈ {0.5（默认）, 0}，作用于 C、D、E。

机制推导的预测（依据当前模型规则，跑前写定；结果按原样报告，不论是否吻合）：
  P1 交互（干预期 7–18 孤立率均值，加法尺度）：I = (E−A) − [(B−A) + (C−A)] < 0，
     即次可加。理由：两种干预都优先覆盖高风险老人，孤立率只看当月有无情感接触，
     重复接触不再降低指标，且社工探访已接近地板。logit 尺度同时报告，不预测方向。
  P2 顺序（撤出后 19–30，b = 0）：D 低于 F。理由：撤出后留下的是最后实施的成分，
     D 以互助结对收尾、结对按 post_persist 延续，F 以社工收尾、撤出即消失。
  P3 接续（撤出后 19–30，b = 0）：D 不优于 C（D − C ≥ 0）。理由：b = 0 时社工探访
     对结对的形成与延续没有作用，D 的结对建立更晚、积累更短。
  P4 阈值：报告 D − C（撤出后）配对差 95% 置信区间上界 < 0 的最小 b；
     网格内均不满足则报告“未达到”，不事后扩网格。

指标：主指标 isolation_rate；窗口均值——干预期 7–18、撤出后 19–30（主）、
  撤出后 19–24（与正式批次口径可比）、撤出后月均变化率（19–30 对月份的最小二乘斜率）。
  avg_loneliness 同口径报告；deep_isolation_rate、avg_active_ties 仅描述。
统计：种子 1–20 同种子配对差；均值、标准差与 bootstrap 95% 置信区间
  （10000 次重抽，随机种子 20261110）。规则层确定性运行，无效度门槛。
设定：全部 20 名老人在规则层；decay = 0.06；动力学取默认值（与正式批次一致，
  不使用事后校准值）；画像主分析用 calibrated，placeholder 作敏感性。
解读边界：P1–P3 是现有规则的推论，吻合只说明模型按规则运行，不是独立发现；
  b 是作者设定的假设参数，D 优于 C 的任何结论都以“接续机制至少为 b”为条件。

用法：
  AGENTSOCIETY_LLM_API_KEY=dummy AGENTSOCIETY_LLM_API_BASE=http://127.0.0.1:9 \\
    <runtime-venv-python> tests/scan_combo.py [--profiles calibrated|placeholder]
输出：tests/scan_combo_result_calibrated.json（主）；--profiles placeholder 时为 tests/scan_combo_result.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
import statistics
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = EXP_DIR.parents[2]
sys.path.insert(0, str(REPO_ROOT / "custom" / "envs"))
sys.path.insert(0, str(EXP_DIR / "init"))

from elder_support_env import ElderSupportEnv  # noqa: E402
from gen_profiles import add_profiles_arg, make_elders, result_path, set_profile_source  # noqa: E402

MONTHS = 30
N_ELDERS = 20
DECAY = 0.06
SEEDS = list(range(1, 21))
BOOSTS = [0.0, 0.25, 0.5, 1.0]
POST_PERSIST = [0.5, 0.0]
WINDOWS = {"iv": (7, 18), "post": (19, 30), "post6": (19, 24), "overall": (1, 30)}
KEYS = ["isolation_rate", "avg_loneliness", "deep_isolation_rate", "avg_active_ties"]
BOOTSTRAP_N = 10000
BOOTSTRAP_SEED = 20261110
LOGIT_EPS = 0.005


def _c(kind: str, start: int, end: int, pp: float | None = None) -> dict:
    params = {"post_persist": pp} if kind == "timebank" and pp is not None else {}
    return {"type": kind, "start_month": start, "end_month": end, "params": params}


def arms(pp: float) -> dict[str, dict | None]:
    """组名 → 干预配置。名字里带 b 的是 D、E 的接续扫描。"""
    out: dict[str, dict | None] = {"A": None, "B": _c("casework", 7, 18), "C": _c("timebank", 7, 18, pp)}
    out["F"] = {"type": "combo", "components": [_c("timebank", 7, 12, pp), _c("casework", 13, 18)],
                "coupling": {"handover_boost": 0.0}}
    for b in BOOSTS:
        out[f"D_b{b}"] = {"type": "combo", "components": [_c("casework", 7, 12), _c("timebank", 13, 18, pp)],
                          "coupling": {"handover_boost": b}}
        out[f"E_b{b}"] = {"type": "combo", "components": [_c("casework", 7, 18), _c("timebank", 7, 18, pp)],
                          "coupling": {"handover_boost": b}}
    return out


async def run_once(seed: int, iv: dict | None) -> dict[int, dict]:
    elders = make_elders(random.Random(seed), N_ELDERS)
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / "ws"
        env = ElderSupportEnv(elders=elders, seed=seed, decay_rate=DECAY, intervention=iv)
        env._bind_workspace(ws)
        t = datetime(2026, 1, 1, 8)
        for tick in range(MONTHS + 1):
            await env.step(tick, t)
            t += timedelta(days=30)
        rows = [json.loads(x) for x in (ws / "state" / "metrics.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    return {r["month"]: r for r in rows}


def summarize(by_month: dict[int, dict]) -> dict:
    out = {}
    for k in KEYS:
        for w, (lo, hi) in WINDOWS.items():
            vals = [by_month[m][k] for m in range(lo, hi + 1)]
            out[f"{w}_{k}"] = sum(vals) / len(vals)
        xs = list(range(19, MONTHS + 1))
        ys = [by_month[m][k] for m in xs]
        mx, my = statistics.mean(xs), statistics.mean(ys)
        out[f"post_slope_{k}"] = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    return out


def logit(p: float) -> float:
    p = min(max(p, LOGIT_EPS), 1 - LOGIT_EPS)
    return math.log(p / (1 - p))


def describe(vals: list[float], rng: random.Random) -> dict:
    n = len(vals)
    boots = sorted(statistics.mean(rng.choices(vals, k=n)) for _ in range(BOOTSTRAP_N))
    return {"mean": round(statistics.mean(vals), 5), "sd": round(statistics.stdev(vals), 5),
            "ci95": [round(boots[int(0.025 * BOOTSTRAP_N)], 5), round(boots[int(0.975 * BOOTSTRAP_N) - 1], 5)],
            "n": n}


def analyse(res: dict[str, dict[int, dict]], rng: random.Random) -> dict:
    """res[arm][seed] = summarize(...)。"""
    def col(arm: str, key: str) -> list[float]:
        return [res[arm][s][key] for s in SEEDS]

    def paired(a: str, b: str, key: str) -> list[float]:
        return [x - y for x, y in zip(col(a, key), col(b, key))]

    out: dict = {"arms": {}, "interaction": {}, "order": {}, "handover": {}}
    for arm in res:
        out["arms"][arm] = {k: describe(col(arm, k), rng) for k in res[arm][SEEDS[0]]}
    for b in BOOSTS:
        e = f"E_b{b}"
        for w in ("iv", "post", "post6"):
            key = f"{w}_isolation_rate"
            add = [ (eab - a) - ((bb - a) + (c - a)) for eab, a, bb, c in
                    zip(col(e, key), col("A", key), col("B", key), col("C", key)) ]
            lg = [ (logit(eab) - logit(a)) - ((logit(bb) - logit(a)) + (logit(c) - logit(a)))
                   for eab, a, bb, c in zip(col(e, key), col("A", key), col("B", key), col("C", key)) ]
            out["interaction"][f"{e}_{w}"] = {"additive": describe(add, rng), "logit": describe(lg, rng)}
        for w in ("iv", "post", "post6"):
            key = f"{w}_isolation_rate"
            out["order"][f"D_b{b}_minus_F_{w}"] = describe(paired(f"D_b{b}", "F", key), rng)
            out["handover"][f"D_b{b}_minus_C_{w}"] = describe(paired(f"D_b{b}", "C", key), rng)
            out["handover"][f"E_b{b}_minus_B_{w}"] = describe(paired(e, "B", key), rng)
        out["order"][f"D_b{b}_minus_F_post_slope"] = describe(
            paired(f"D_b{b}", "F", "post_slope_isolation_rate"), rng)
    reached = [b for b in BOOSTS if out["handover"][f"D_b{b}_minus_C_post"]["ci95"][1] < 0]
    out["threshold_P4"] = min(reached) if reached else "not_reached"
    return out


async def main() -> int:
    ap = argparse.ArgumentParser()
    add_profiles_arg(ap)
    args = ap.parse_args()
    profiles = set_profile_source(args.profiles or "calibrated")
    result: dict = {
        "preregistered": {"seeds": SEEDS, "months": MONTHS, "windows": WINDOWS, "boosts": BOOSTS,
                          "post_persist": POST_PERSIST, "decay": DECAY, "profiles": profiles,
                          "bootstrap": {"n": BOOTSTRAP_N, "seed": BOOTSTRAP_SEED},
                          "dynamics": "default (frozen main-batch dynamics)"},
        "by_post_persist": {},
    }
    for pp in POST_PERSIST:
        res: dict[str, dict[int, dict]] = {}
        for arm, iv in arms(pp).items():
            res[arm] = {s: summarize(await run_once(s, iv)) for s in SEEDS}
        rng = random.Random(BOOTSTRAP_SEED)
        result["by_post_persist"][f"pp{pp}"] = analyse(res, rng)
        a = result["by_post_persist"][f"pp{pp}"]
        print(f"== post_persist={pp}")
        for arm in res:
            m = a["arms"][arm]
            print(f"  {arm:8s} iv {m['iv_isolation_rate']['mean']:.3f}  post {m['post_isolation_rate']['mean']:.3f}  "
                  f"slope {m['post_slope_isolation_rate']['mean']:+.4f}")
        for b in BOOSTS:
            i = a["interaction"][f"E_b{b}_iv"]
            print(f"  b={b}: I_add(iv) {i['additive']['mean']:+.4f} {i['additive']['ci95']}  "
                  f"I_logit(iv) {i['logit']['mean']:+.3f}  D−F post {a['order'][f'D_b{b}_minus_F_post']['mean']:+.4f}  "
                  f"D−C post {a['handover'][f'D_b{b}_minus_C_post']['mean']:+.4f} {a['handover'][f'D_b{b}_minus_C_post']['ci95']}")
        print(f"  P4 threshold: {a['threshold_P4']}")
    dest = result_path(Path(__file__).with_name("scan_combo_result.json"), profiles)
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"结果已写入 {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
