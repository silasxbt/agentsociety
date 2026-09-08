#!/usr/bin/env python3
"""规则层介入时机扫描：iv_start × 时长 × 条件 → 结局指标（不耗 LLM）。

== 预注册（运行前写定，禁止事后改动挑指标）==================================
研究问题：在 24 个月时程内，社会支持干预的启动时机与时长如何影响
独居老人的孤立结局？

机制假设（源自本项目关系衰减模型，见 references_verified.md D 节）：
- T1 启动时机：关系按月衰减且久疏的关系更难重新激活，因此在衰减早期
  启动（维护存量）应优于衰减深化后启动（重建增量）——全时程平均孤立率
  随启动月推迟而上升。
- T2 时长/剂量：同一启动点下，更长时长降低干预期与期末孤立率；
  但撤出后反弹幅度（post − iv）不必然随时长增加而减小（H4 相关）。

主指标：isolation_rate 在第 1–24 月的全时程均值（各候选窗口可比）。
次指标：干预期均值、撤出后均值、反弹（post − iv）、期末值；avg_loneliness 同口径。
deep_isolation_rate 仅敏感性；avg_active_ties 仅描述。

混杂披露（如实报告，不掩盖）：
- 启动越晚 → 撤出后观察窗越短（start=12 时仅第 24 月）；比较反弹时
  必须连同窗口长度一起报告。
- 时长 18（7–24 月）无撤出后窗口，反弹指标记 NaN。
- 全部 20 位老人在规则层（无 LLM agent），绝对水平与正式 LLM 批次
  不可直接比较；可比较的是时机/时长/条件之间的方向与量级。
  正式批次（iv 7–18）可作为本扫描 start=7 配置的行为层锚点。

设计：
- A 时机扫描：iv_start ∈ {3, 5, 7, 9, 12}，时长固定 12 月，
  条件 ∈ {casework, timebank, platform}；none 基线每 seed 跑一次共用。
- B 剂量扫描：iv_start 固定 7，时长 ∈ {6, 12, 18} 月，条件同上。
- 种子 1–20（规则层免费，给出远稳于正式批次 n=3 的机制层区间）。
- decay=0.06（正式批次默认）；其他参数与正式批次一致。

实践叙事产出：每条件的"延迟成本"——启动每推迟 1 个月，全时程孤立率
上升多少（对 start 做最小二乘斜率），供筛查与轮候政策讨论引用。

可复现性：种子、参数、窗口全部写入结果 JSON；脚本确定性运行；
报告 scan_timing_report.md 由 JSON 生成，不手改。

用法：
  AGENTSOCIETY_LLM_API_KEY=dummy AGENTSOCIETY_LLM_API_BASE=https://tokenflux.dev/v1 \
    <runtime-venv-python> tests/scan_timing.py

输出：终端表格 + tests/scan_timing_result.json + tests/scan_timing_report.md
"""

from __future__ import annotations

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
from gen_profiles import gen_elder  # noqa: E402

MONTHS = 24
N_ELDERS = 20
DECAY = 0.06                      # 正式批次默认
SEEDS = list(range(1, 21))        # 预注册：20 个种子，跑前写定
STARTS = [3, 5, 7, 9, 12]         # A 扫描：启动月（时长固定 12）
DUR_START = 7                     # B 扫描：启动固定 7
DURATIONS = [6, 12, 18]           # B 扫描：时长
CONDITIONS = ["casework", "timebank", "platform"]
KEYS = ["isolation_rate", "deep_isolation_rate", "avg_loneliness", "avg_active_ties"]
PRIMARY = "isolation_rate"


async def run_once(seed: int, cond: str | None, iv_start: int, iv_end: int) -> list[dict]:
    """跑一个 (seed, condition, window)，返回逐月 metrics 行。"""
    rng = random.Random(seed)
    elders = [gen_elder(rng, i + 1, focal=False) for i in range(N_ELDERS)]
    iv = None
    if cond:
        iv = {"type": cond, "start_month": iv_start, "end_month": iv_end, "params": {}}
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / "ws"
        env = ElderSupportEnv(elders=elders, seed=seed, decay_rate=DECAY,
                              intervention=iv)
        env._bind_workspace(ws)
        t = datetime(2026, 1, 1, 8)
        for tick in range(MONTHS + 1):
            await env.step(tick, t)
            t += timedelta(days=30)
        rows = [
            json.loads(line)
            for line in (ws / "state" / "metrics.jsonl").read_text(
                encoding="utf-8").splitlines() if line.strip()
        ]
    return rows


def summarize(rows: list[dict], iv_start: int, iv_end: int) -> dict:
    """单 run 摘要：全时程均值（主）、干预期、撤出后、反弹、期末。"""
    by_month = {r["month"]: r for r in rows}

    def mean_over(months: range, key: str) -> float:
        vals = [by_month[m][key] for m in months if m in by_month]
        return sum(vals) / len(vals) if vals else float("nan")

    out = {}
    for k in KEYS:
        out[f"overall_{k}"] = mean_over(range(1, MONTHS + 1), k)   # 主口径
        out[f"iv_{k}"] = mean_over(range(iv_start, iv_end + 1), k)
        out[f"post_{k}"] = mean_over(range(iv_end + 1, MONTHS + 1), k)
        out[f"rebound_{k}"] = out[f"post_{k}"] - out[f"iv_{k}"]
        out[f"final_{k}"] = by_month[max(by_month)][k]
    return out


def agg(per_seed: list[dict]) -> dict:
    out = {}
    for k in per_seed[0]:
        vals = [s[k] for s in per_seed if not math.isnan(s[k])]
        if not vals:
            out[k] = {"mean": float("nan"), "sd": float("nan"), "n": 0}
            continue
        out[k] = {"mean": round(statistics.mean(vals), 4),
                  "sd": round(statistics.stdev(vals), 4) if len(vals) > 1 else 0.0,
                  "n": len(vals)}
    return out


def slope(xs: list[float], ys: list[float]) -> float:
    """最小二乘斜率：延迟成本（每推迟 1 月的主指标变化）。"""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    denom = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom


async def main() -> int:
    results: dict = {"baseline": {}, "timing_scan": {}, "duration_scan": {}}

    # ---- none 基线（每 seed 一次，摘要窗口按 7–18 报告以便与正式批次对齐）----
    base_per_seed = []
    for seed in SEEDS:
        rows = await run_once(seed, None, 7, 18)
        base_per_seed.append(summarize(rows, 7, 18))
    results["baseline"]["none"] = agg(base_per_seed)
    print("基线 none 完成")

    # ---- A 时机扫描 ----
    for start in STARTS:
        end = start + 11
        for cond in CONDITIONS:
            per_seed = []
            for seed in SEEDS:
                rows = await run_once(seed, cond, start, end)
                per_seed.append(summarize(rows, start, end))
            results["timing_scan"][f"start{start}_{cond}"] = {
                "iv_window": [start, end], "post_window_len": MONTHS - end,
                **agg(per_seed)}
        print(f"start={start} 完成")

    # ---- B 剂量扫描（时长 12 复用 A 的 start=7 结果）----
    for dur in DURATIONS:
        end = DUR_START + dur - 1
        for cond in CONDITIONS:
            key = f"dur{dur}_{cond}"
            if dur == 12:
                src = results["timing_scan"][f"start{DUR_START}_{cond}"]
                results["duration_scan"][key] = src
                continue
            per_seed = []
            for seed in SEEDS:
                rows = await run_once(seed, cond, DUR_START, end)
                per_seed.append(summarize(rows, DUR_START, end))
            results["duration_scan"][key] = {
                "iv_window": [DUR_START, end], "post_window_len": MONTHS - end,
                **agg(per_seed)}
        print(f"duration={dur} 完成")

    # ---- 延迟成本（实践叙事用）----
    delay_cost = {}
    for cond in CONDITIONS:
        xs = [float(s) for s in STARTS]
        ys = [results["timing_scan"][f"start{s}_{cond}"][f"overall_{PRIMARY}"]["mean"]
              for s in STARTS]
        delay_cost[cond] = {
            "slope_per_month": round(slope(xs, ys), 5),
            "overall_by_start": dict(zip(map(str, STARTS), [round(y, 4) for y in ys])),
        }
    results["delay_cost"] = delay_cost

    # ---- 打印 ----
    print(f"\nA 时机扫描（overall_{PRIMARY}，mean±sd，{len(SEEDS)} 种子；"
          f"none 基线 overall={results['baseline']['none'][f'overall_{PRIMARY}']['mean']:.3f}）")
    print(f"{'配置':<20} {'全时程':>12} {'干预期':>12} {'撤出后':>12} {'反弹':>9} {'后窗月数':>6}")
    for name, v in results["timing_scan"].items():
        print(f"{name:<20} "
              f"{v[f'overall_{PRIMARY}']['mean']:>7.3f}±{v[f'overall_{PRIMARY}']['sd']:.3f} "
              f"{v[f'iv_{PRIMARY}']['mean']:>7.3f}±{v[f'iv_{PRIMARY}']['sd']:.3f} "
              f"{v[f'post_{PRIMARY}']['mean']:>7.3f}±{v[f'post_{PRIMARY}']['sd']:.3f} "
              f"{v[f'rebound_{PRIMARY}']['mean']:>+8.3f} "
              f"{v['post_window_len']:>6}")
    print(f"\nB 剂量扫描（start=7）")
    for name, v in results["duration_scan"].items():
        reb = v[f"rebound_{PRIMARY}"]["mean"]
        reb_s = f"{reb:+.3f}" if not math.isnan(reb) else "  无后窗"
        print(f"{name:<20} overall={v[f'overall_{PRIMARY}']['mean']:.3f} "
              f"iv={v[f'iv_{PRIMARY}']['mean']:.3f} rebound={reb_s}")
    print("\n延迟成本（overall isolation_rate / 每推迟 1 月）")
    for cond, dc in delay_cost.items():
        print(f"  {cond:<10} {dc['slope_per_month']:+.5f}")

    out = {
        "preregistered": {
            "primary_metric": f"overall_{PRIMARY} (months 1-24 mean)",
            "hypotheses": ["T1 早启动优于晚启动（全时程孤立率）",
                            "T2 更长时长降低干预期/期末孤立率，反弹不必然减小"],
            "seeds": SEEDS, "starts": STARTS, "durations": DURATIONS,
            "decay": DECAY, "n_elders": N_ELDERS, "months": MONTHS,
        },
        "caveats": [
            "规则层（无 LLM），绝对水平不可与正式批次直接比较，仅比较方向与量级",
            "启动越晚撤出后观察窗越短，反弹比较须连同 post_window_len 报告",
            "dur18 无撤出后窗口，反弹为 NaN",
        ],
        **results,
    }
    out_path = Path(__file__).with_name("scan_timing_result.json")
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"\n结果已写入 {out_path}")
    write_report(out)
    return 0


def write_report(res: dict) -> None:
    """由结果 JSON 生成报告（不手改；重跑脚本即重生成）。"""
    p = res["preregistered"]
    L = []
    L.append("# 介入时机与剂量：规则层扫描报告\n")
    L.append(f"自动生成自 scan_timing_result.json；{len(p['seeds'])} 种子，"
             f"N={p['n_elders']} 老人（全规则层），{p['months']} 月，decay={p['decay']}。\n")
    L.append("## 预注册\n")
    L.append(f"- 主指标：{p['primary_metric']}\n- 假设：" + "；".join(p["hypotheses"]) + "\n")
    L.append("## 限制（先读这里）\n")
    for c in res["caveats"]:
        L.append(f"- {c}")
    base = res["baseline"]["none"][f"overall_{PRIMARY}"]
    L.append(f"\n## A. 启动时机（时长 12 月）\n")
    L.append(f"none 基线全时程孤立率 {base['mean']:.3f}±{base['sd']:.3f}。\n")
    L.append("| 配置 | 全时程 | 干预期 | 撤出后 | 反弹 | 后窗月数 |")
    L.append("|---|---|---|---|---|---|")
    for name, v in res["timing_scan"].items():
        L.append(f"| {name} | {v[f'overall_{PRIMARY}']['mean']:.3f}±{v[f'overall_{PRIMARY}']['sd']:.3f} "
                 f"| {v[f'iv_{PRIMARY}']['mean']:.3f} | {v[f'post_{PRIMARY}']['mean']:.3f} "
                 f"| {v[f'rebound_{PRIMARY}']['mean']:+.3f} | {v['post_window_len']} |")
    L.append("\n## B. 剂量（start=7）\n")
    L.append("| 配置 | 全时程 | 干预期 | 反弹 |")
    L.append("|---|---|---|---|")
    for name, v in res["duration_scan"].items():
        reb = v[f"rebound_{PRIMARY}"]["mean"]
        reb_s = f"{reb:+.3f}" if not math.isnan(reb) else "无后窗"
        L.append(f"| {name} | {v[f'overall_{PRIMARY}']['mean']:.3f} "
                 f"| {v[f'iv_{PRIMARY}']['mean']:.3f} | {reb_s} |")
    L.append("\n## C. 延迟成本（实践叙事）\n")
    L.append("启动每推迟 1 个月，全时程孤立率的变化（最小二乘斜率，机制层估计）：\n")
    L.append("| 条件 | 斜率/月 |")
    L.append("|---|---|")
    for cond, dc in res["delay_cost"].items():
        L.append(f"| {cond} | {dc['slope_per_month']:+.5f} |")
    L.append("\n解读口径：本表来自规则层机制模型，用于回答『时机是否重要、"
             "量级几何』；不用于宣称真实老年人群的因果效应。指向实践的叙事应写成："
             "『在本模型的衰减机制下，筛查与介入每延迟一月，两年平均孤立率"
             "上升约 X 个百分点，提示轮候时间本身是干预设计变量』。")
    path = Path(__file__).with_name("scan_timing_report.md")
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"报告已写入 {path}")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
