#!/usr/bin/env python3
"""规则层按关系层拆分：撤出后各层关系还剩什么（不耗 LLM、不改环境代码）。

== 预注册（2026-11-14 运行前写定并提交；跑完不改指标、窗口、种子与判定）=========
研究问题：三种服务撤出后，留下的是哪一层被改变的关系？对应“服务会结束，关系去哪了”
的三层叙事：内层家庭、中层同辈（邻里朋友与互助伙伴）、外层弱关系（志愿者）。

关系层（按关系账本中的 kind）：
  内层 family；中层 friend、neighbor、timebank（互助伙伴单列）；外层 volunteer；
  正式节点 social_worker 单列。
测量（每月月末结算后、下月行动前快照，见 _install_probe）：
  每位老人当月经该层获得的情感接触次数（emotional_count 增量）、
  当月至少有一次该层情感接触的老人占比、该层现存关系数、该层关系平均强度。
窗口：干预前 1–6、干预期 7–18、撤出后 19–30（主）、撤出后 19–24（与正式批次可比）。
组别（干预期均为 7–18，观察到第 30 月）：
  none；casework；timebank；platform；
  casework_nolink（社工不联结家庭，family_link_p = 0，用于分离“家庭激活”）；
  timebank_pp0（结对撤出后不延续，post_persist = 0，置零对照）。
统计：种子 1–20，同种子配对差，bootstrap 95% 置信区间（10000 次，随机种子 20261114）。
画像：校准画像为主，占位画像为敏感性；默认动力学，decay = 0.06。

图中各格对应的判定（跑前写定，结果按原样报告）：
  内层-激活：casework − none 的撤出后（19–30）家庭情感接触；
    casework − casework_nolink 分离出“联结家庭”这一项的贡献。
  内层-挤出：模型中没有任何规则会减少子女联系，挤出按设计不可检验；
    报告干预期 casework − none 的家庭情感接触，仅作核对（预期 ≥ 0）。
  中层-延续：timebank 撤出后经互助伙伴的情感接触；timebank_pp0 应为 0（按设计）。
  外层-沉淀：platform 撤出后经志愿者的情感接触（预期为 0，按设计），以及账本中残留的
    志愿者关系数（预期仍在、按衰减缓慢变弱）；模型没有弱关系转为中层的机制，
    “转化率”按设计不可检验。
定稿说明：写定本头部前，用 seed 1 跑过一次探针核对快照时点；发现撤出后关系在 12 个月内
  不会跌破删除阈值（0.4×0.94^12 > 0.05），因此把外层指标从“关系数降到每人 0.05 条所需
  月数”改为“情感接触 + 账本残留”。此后不再改动。
解读边界：各层撤出后的走势由对应参数决定（family_link_p 与关系衰减、post_persist、
  志愿者强度上限与衰减），本扫描只把这些规则推论按层量化，不构成独立发现。

用法：
  AGENTSOCIETY_LLM_API_KEY=dummy AGENTSOCIETY_LLM_API_BASE=http://127.0.0.1:9 \\
    <runtime-venv-python> tests/scan_layers.py [--profiles calibrated|placeholder]
输出：tests/scan_layers_result_calibrated.json（主）；placeholder 时为 tests/scan_layers_result.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
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
LAYERS = {"family": ("family",), "middle": ("friend", "neighbor", "timebank"), "peer": ("friend", "neighbor"),
          "timebank": ("timebank",), "volunteer": ("volunteer",), "social_worker": ("social_worker",)}
WINDOWS = {"pre": (1, 6), "iv": (7, 18), "post": (19, 30), "post6": (19, 24)}
BOOTSTRAP_N = 10000
BOOTSTRAP_SEED = 20261114


def _iv(kind: str, params: dict | None = None) -> dict:
    return {"type": kind, "start_month": 7, "end_month": 18, "params": params or {}}


ARMS: dict[str, dict | None] = {
    "none": None,
    "casework": _iv("casework"),
    "timebank": _iv("timebank"),
    "platform": _iv("platform"),
    "casework_nolink": _iv("casework", {"family_link_p": 0.0}),
    "timebank_pp0": _iv("timebank", {"post_persist": 0.0}),
}


def _snapshot(env: ElderSupportEnv) -> dict:
    """{elder_id: {tie_name: (kind, strength, emotional_count)}}"""
    return {eid: {n: (t["kind"], t["strength"], t["emotional_count"]) for n, t in e["ties"].items()}
            for eid, e in env._elders.items()}


def _install_probe(env: ElderSupportEnv, snaps: list) -> None:
    """_community_metrics 在月末结算之后、下月行动之前调用：在此快照关系账本。"""
    original = env._community_metrics

    def probed():
        snaps.append(_snapshot(env))
        return original()

    env._community_metrics = probed


def month_layers(prev: dict, cur: dict) -> dict:
    """由相邻两次快照得到当月各层指标（按老人平均）。"""
    n = len(cur)
    out = {}
    for layer, kinds in LAYERS.items():
        emo_total, any_emo, count, strength_sum, strength_n = 0, 0, 0, 0.0, 0
        for eid, ties in cur.items():
            emo = 0
            for name, (kind, s, ec) in ties.items():
                if kind not in kinds:
                    continue
                count += 1
                strength_sum += s
                strength_n += 1
                before = prev.get(eid, {}).get(name)
                emo += ec - (before[2] if before and before[0] == kind else 0)
            emo_total += emo
            any_emo += emo > 0
        out[layer] = {"emotional_per_elder": emo_total / n, "share_with_emotional": any_emo / n,
                      "ties_per_elder": count / n,
                      "mean_strength": strength_sum / strength_n if strength_n else 0.0}
    return out


async def run_once(seed: int, iv: dict | None) -> list[dict]:
    elders = make_elders(random.Random(seed), N_ELDERS)
    snaps: list = []
    with tempfile.TemporaryDirectory() as td:
        env = ElderSupportEnv(elders=elders, seed=seed, decay_rate=DECAY, intervention=iv)
        env._bind_workspace(Path(td) / "ws")
        _install_probe(env, snaps)
        t = datetime(2026, 1, 1, 8)
        for tick in range(MONTHS + 1):
            await env.step(tick, t)
            t += timedelta(days=30)
    return [month_layers(snaps[m - 1], snaps[m]) for m in range(1, MONTHS + 1)]  # 第 1..30 月


def windowed(series: list[dict]) -> dict:
    out = {}
    for layer in LAYERS:
        for key in ("emotional_per_elder", "share_with_emotional", "ties_per_elder", "mean_strength"):
            for w, (lo, hi) in WINDOWS.items():
                vals = [series[m - 1][layer][key] for m in range(lo, hi + 1)]
                out[f"{layer}.{key}.{w}"] = sum(vals) / len(vals)
    return out


def describe(vals: list[float], rng: random.Random) -> dict:
    boots = sorted(statistics.mean(rng.choices(vals, k=len(vals))) for _ in range(BOOTSTRAP_N))
    return {"mean": round(statistics.mean(vals), 5), "sd": round(statistics.stdev(vals), 5),
            "ci95": [round(boots[int(0.025 * BOOTSTRAP_N)], 5), round(boots[int(0.975 * BOOTSTRAP_N) - 1], 5)]}


CONTRASTS = {
    "inner_activation_post": ("casework", "none", "family.emotional_per_elder.post"),
    "inner_activation_post6": ("casework", "none", "family.emotional_per_elder.post6"),
    "inner_link_share_post": ("casework", "casework_nolink", "family.emotional_per_elder.post"),
    "inner_family_strength_post": ("casework", "none", "family.mean_strength.post"),
    "inner_crowding_check_iv": ("casework", "none", "family.emotional_per_elder.iv"),
    "middle_pair_post": ("timebank", "none", "timebank.emotional_per_elder.post"),
    "middle_pair_vs_pp0_post": ("timebank", "timebank_pp0", "timebank.emotional_per_elder.post"),
    "middle_peer_post": ("timebank", "none", "peer.emotional_per_elder.post"),
    "outer_volunteer_ties_post": ("platform", "none", "volunteer.ties_per_elder.post"),
    "outer_volunteer_emotional_post": ("platform", "none", "volunteer.emotional_per_elder.post"),
}


async def main() -> int:
    ap = argparse.ArgumentParser()
    add_profiles_arg(ap)
    profiles = set_profile_source(ap.parse_args().profiles or "calibrated")
    per_arm = {arm: {s: windowed(await run_once(s, iv)) for s in SEEDS} for arm, iv in ARMS.items()}
    rng = random.Random(BOOTSTRAP_SEED)
    keys = list(per_arm["none"][SEEDS[0]])
    arms_out = {arm: {k: describe([per_arm[arm][s][k] for s in SEEDS], rng) for k in keys} for arm in ARMS}
    contrasts = {}
    for name, (a, b, key) in CONTRASTS.items():
        contrasts[name] = describe([per_arm[a][s][key] - per_arm[b][s][key] for s in SEEDS], rng)
    result = {
        "preregistered": {"seeds": SEEDS, "months": MONTHS, "windows": WINDOWS, "layers": LAYERS,
                          "arms": ARMS, "decay": DECAY, "profiles": profiles,
                          "bootstrap": {"n": BOOTSTRAP_N, "seed": BOOTSTRAP_SEED}},
        "arms": arms_out,
        "contrasts": contrasts,
    }
    dest = result_path(Path(__file__).with_name("scan_layers_result.json"), profiles)
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    for name, c in contrasts.items():
        print(f"{name:32s} {c['mean']:+.4f}  {c['ci95']}")
    print(f"结果已写入 {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
