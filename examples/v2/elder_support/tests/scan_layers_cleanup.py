#!/usr/bin/env python3
"""对照：服务撤出时清掉旧服务关系，“求助通道”是否随之消失（不耗 LLM、不改环境代码）。

== 预注册（2026-11-14 运行前写定并提交）=====================================
背景：tests/scan_layers.py 发现撤出后老人仍经旧社工、旧志愿者、旧结对伙伴获得少量接触，
  推测原因是撤出时这些关系仍留在关系账本上，老人遇事时按强度向最强的几条关系求助。
对照：在第 18 月月末结算后（撤出前一刻）删除该干预产生的关系：
  casework → social_worker；platform → volunteer；timebank_pp0 → timebank
  （timebank 默认组不清理，因其撤出后延续本身依赖账本中的结对关系）。
比较：同种子“清理 − 不清理”，撤出后 19–30 月：
  (1) 经该层的情感接触（预测：降为 0）；
  (2) 孤立率与孤独感（不作方向预测，如实报告“求助通道”对撤出后结局的贡献）。
设定：与 scan_layers.py 相同（种子 1–20，校准画像为主、占位画像为敏感性，默认动力学，
  decay = 0.06，bootstrap 10000 次，随机种子 20261114）。
解读边界：清理是假设性的对照，不代表现实中服务结束后关系会被抹去；它只用来确认
  “求助通道”来自账本残留这一规则推论。

用法：
  AGENTSOCIETY_LLM_API_KEY=dummy AGENTSOCIETY_LLM_API_BASE=http://127.0.0.1:9 \\
    <runtime-venv-python> tests/scan_layers_cleanup.py [--profiles calibrated|placeholder]
输出：tests/scan_layers_cleanup_result_calibrated.json（主）；placeholder 时为
  tests/scan_layers_cleanup_result.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scan_layers as sl  # noqa: E402

CLEAN_AT_MONTH = 18
ARMS = {"casework": "social_worker", "platform": "volunteer", "timebank_pp0": "timebank"}
LAYER_OF_KIND = {"social_worker": "social_worker", "volunteer": "volunteer", "timebank": "timebank"}


async def run_once(seed: int, arm: str, clean: bool) -> tuple[list[dict], dict[int, dict]]:
    elders = sl.make_elders(random.Random(seed), sl.N_ELDERS)
    snaps: list = []
    kind = ARMS[arm]
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / "ws"
        env = sl.ElderSupportEnv(elders=elders, seed=seed, decay_rate=sl.DECAY, intervention=sl.ARMS[arm])
        env._bind_workspace(ws)
        original = env._community_metrics

        def probed():
            if clean and len(snaps) == CLEAN_AT_MONTH:  # 第 18 月月末结算之后
                for e in env._elders.values():
                    for name in [n for n, t in e["ties"].items() if t["kind"] == kind]:
                        del e["ties"][name]
            snaps.append(sl._snapshot(env))
            return original()

        env._community_metrics = probed
        t = datetime(2026, 1, 1, 8)
        for tick in range(sl.MONTHS + 1):
            await env.step(tick, t)
            t += timedelta(days=30)
        rows = [json.loads(x) for x in (ws / "state" / "metrics.jsonl").read_text(encoding="utf-8").splitlines()
                if x.strip()]
    layers = [sl.month_layers(snaps[m - 1], snaps[m]) for m in range(1, sl.MONTHS + 1)]
    return layers, {r["month"]: r for r in rows}


def post_mean(values: dict[int, float]) -> float:
    xs = [values[m] for m in range(19, sl.MONTHS + 1)]
    return sum(xs) / len(xs)


async def main() -> int:
    ap = argparse.ArgumentParser()
    sl.add_profiles_arg(ap)
    profiles = sl.set_profile_source(ap.parse_args().profiles or "calibrated")
    rng = random.Random(sl.BOOTSTRAP_SEED)
    out: dict = {"preregistered": {"clean_at_month_end": CLEAN_AT_MONTH, "arms": ARMS, "seeds": sl.SEEDS,
                                   "profiles": profiles}, "arms": {}}
    for arm, kind in ARMS.items():
        diffs: dict[str, list[float]] = {"layer_emotional_post": [], "isolation_post": [], "loneliness_post": []}
        base_vals: dict[str, list[float]] = {k: [] for k in diffs}
        for s in sl.SEEDS:
            res = {}
            for clean in (False, True):
                layers, metrics = await run_once(s, arm, clean)
                layer = LAYER_OF_KIND[kind]
                res[clean] = {
                    "layer_emotional_post": post_mean({m: layers[m - 1][layer]["emotional_per_elder"]
                                                       for m in range(1, sl.MONTHS + 1)}),
                    "isolation_post": post_mean({m: metrics[m]["isolation_rate"] for m in range(1, sl.MONTHS + 1)}),
                    "loneliness_post": post_mean({m: metrics[m]["avg_loneliness"] for m in range(1, sl.MONTHS + 1)}),
                }
            for k in diffs:
                diffs[k].append(res[True][k] - res[False][k])
                base_vals[k].append(res[False][k])
        out["arms"][arm] = {"removed_kind": kind,
                            "baseline_no_clean": {k: sl.describe(v, rng) for k, v in base_vals.items()},
                            "clean_minus_no_clean": {k: sl.describe(v, rng) for k, v in diffs.items()}}
        c = out["arms"][arm]["clean_minus_no_clean"]
        print(f"{arm:13s} layer {c['layer_emotional_post']['mean']:+.4f} {c['layer_emotional_post']['ci95']}  "
              f"iso {c['isolation_post']['mean']:+.4f} {c['isolation_post']['ci95']}  "
              f"lon {c['loneliness_post']['mean']:+.4f} {c['loneliness_post']['ci95']}")
    dest = sl.result_path(Path(__file__).with_name("scan_layers_cleanup_result.json"), profiles)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"结果已写入 {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
