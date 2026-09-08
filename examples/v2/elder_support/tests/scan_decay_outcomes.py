#!/usr/bin/env python3
"""规则层敏感性扫描：decay_rate × 干预条件 → 结局指标（不耗 LLM）。

背景（见 data_pipeline/out/references_verified.md 的 D/E 参数结论）：
- decay_rate 与 caseload 均无文献单点标定依据，按敏感性维度扫描：
  decay ∈ {0.06, 0.15, 0.25}；caseload ∈ {4, 8, 12}（casework 专用，
  对应 N=20 下 40%/80%/100% 覆盖率）。
- 本脚本把全部 20 位老人放在规则层（不创建 LLM agent），因此绝对水平
  与正式 LLM 批次不可直接比较；**可比较的是 decay / caseload / 条件
  之间的对比方向与量级**。需要 LLM 行为层证据时用
  `DECAY=... ./run_batch.sh`（成本 ×3，见其头部说明）。

用法：
  AGENTSOCIETY_LLM_API_KEY=dummy AGENTSOCIETY_LLM_API_BASE=https://tokenflux.dev/v1 \
    <runtime-venv-python> tests/scan_decay_outcomes.py

输出：终端表格 + tests/scan_decay_outcomes_result.json
"""

from __future__ import annotations

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
from gen_profiles import gen_elder  # noqa: E402

MONTHS = 24          # 与正式批次一致
IV_START, IV_END = 7, 18
N_ELDERS = 20
SEEDS = list(range(1, 11))  # 规则层免费，跑 10 个种子取均值±SD
DECAYS = [0.06, 0.15, 0.25]
CONDITIONS = ["none", "casework", "timebank", "platform"]
CASELOADS = [4, 8, 12]  # E 扫描：casework 覆盖率 40%/80%/100%（decay 固定 0.06）
KEYS = ["isolation_rate", "deep_isolation_rate", "avg_loneliness", "avg_active_ties"]


async def run_once(seed: int, decay: float, cond: str, params: dict) -> list[dict]:
    """跑一个 (seed, decay, condition)，返回逐月 metrics 行。"""
    rng = random.Random(seed)
    elders = [gen_elder(rng, i + 1, focal=False) for i in range(N_ELDERS)]
    iv = None
    if cond != "none":
        iv = {"type": cond, "start_month": IV_START, "end_month": IV_END,
              "params": params}
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / "ws"
        env = ElderSupportEnv(elders=elders, seed=seed, decay_rate=decay,
                              intervention=iv)
        env._bind_workspace(ws)
        t = datetime(2026, 1, 1, 8)
        for tick in range(MONTHS + 1):  # tick k 结算第 k 月
            await env.step(tick, t)
            t += timedelta(days=30)
        rows = [
            json.loads(line)
            for line in (ws / "state" / "metrics.jsonl").read_text(
                encoding="utf-8").splitlines() if line.strip()
        ]
    return rows


def summarize(rows: list[dict]) -> dict:
    """一个 run 的结局摘要：期末 + 干预期均值 + 撤出后均值。"""
    by_month = {r["month"]: r for r in rows}
    def mean_over(months: range, key: str) -> float:
        vals = [by_month[m][key] for m in months if m in by_month]
        return sum(vals) / len(vals) if vals else float("nan")
    out = {}
    for k in KEYS:
        out[f"final_{k}"] = by_month[max(by_month)][k]
        out[f"iv_{k}"] = mean_over(range(IV_START, IV_END + 1), k)
        out[f"post_{k}"] = mean_over(range(IV_END + 1, MONTHS + 1), k)
    return out


def agg(per_seed: list[dict]) -> dict:
    """跨种子 mean±sd。"""
    out = {}
    for k in per_seed[0]:
        vals = [s[k] for s in per_seed]
        out[k] = {"mean": round(statistics.mean(vals), 4),
                  "sd": round(statistics.stdev(vals), 4) if len(vals) > 1 else 0.0}
    return out


async def main() -> int:
    results = {"decay_scan": {}, "caseload_scan": {}}

    # ---- D 扫描：decay × condition ----
    for decay in DECAYS:
        for cond in CONDITIONS:
            per_seed = []
            for seed in SEEDS:
                rows = await run_once(seed, decay, cond, params={})
                per_seed.append(summarize(rows))
            results["decay_scan"][f"d{decay}_{cond}"] = agg(per_seed)
        print(f"decay={decay} 完成")

    # ---- E 扫描：caseload（casework，decay=0.06）----
    for cl in CASELOADS:
        per_seed = []
        for seed in SEEDS:
            rows = await run_once(seed, 0.06, "casework", params={"caseload": cl})
            per_seed.append(summarize(rows))
        results["caseload_scan"][f"cl{cl}"] = agg(per_seed)
    print("caseload 扫描完成\n")

    # ---- 打印 ----
    def show(title: str, block: dict, metric: str) -> None:
        print(f"\n{title}（{metric}，mean±sd，{len(SEEDS)} 种子）")
        print(f"{'配置':<18} {'干预期(7-18月)':>16} {'撤出后(19-24月)':>16} {'期末(24月)':>12}")
        for name, v in block.items():
            print(f"{name:<18} "
                  f"{v['iv_' + metric]['mean']:>9.3f}±{v['iv_' + metric]['sd']:.3f} "
                  f"{v['post_' + metric]['mean']:>9.3f}±{v['post_' + metric]['sd']:.3f} "
                  f"{v['final_' + metric]['mean']:>7.3f}±{v['final_' + metric]['sd']:.3f}")

    for metric in ["avg_loneliness", "isolation_rate"]:
        show("D 扫描 decay×条件", results["decay_scan"], metric)
        show("E 扫描 caseload（casework, decay=0.06）",
             results["caseload_scan"], metric)

    out_path = Path(__file__).with_name("scan_decay_outcomes_result.json")
    out_path.write_text(json.dumps(
        {"months": MONTHS, "iv_window": [IV_START, IV_END], "n_elders": N_ELDERS,
         "seeds": SEEDS, "note": "全部老人为规则层（无 LLM），只用于条件间对比方向",
         **results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已写入 {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
