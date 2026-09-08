#!/usr/bin/env python3
"""ElderSupport 原型实验分析：读取 run 产物，输出月度曲线与定性决策摘要。

用法：
  python analyze.py --run-dir ../tmp/run

读取：
- <run_dir>/env/ElderSupportEnv/state/metrics.jsonl   宏观月度指标
- <run_dir>/env/ElderSupportEnv/state/decisions.jsonl 焦点老人决策与理由
输出：
- 终端打印月度曲线表 + 行动类型分布 + 理由样例
- <run_dir>/analysis/summary.json 汇总（供 harness 后续自迭代使用）
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--run-dir", default=str(Path(__file__).resolve().parent.parent / "tmp" / "run")
    )
    args = ap.parse_args()
    run_dir = Path(args.run_dir).resolve()
    env_state = run_dir / "env" / "ElderSupportEnv" / "state"

    metrics = load_jsonl(env_state / "metrics.jsonl")
    decisions = load_jsonl(env_state / "decisions.jsonl")

    if not metrics:
        print(f"未找到指标文件：{env_state / 'metrics.jsonl'}")
        return

    print("=" * 72)
    print("月度宏观指标")
    print("=" * 72)
    header = f"{'月':>3} {'孤立率':>8} {'深度孤立率':>10} {'平均孤独感':>10} {'平均关系数':>10} {'求助':>4} {'成功':>4}"
    print(header)
    for m in metrics:
        print(
            f"{m['month']:>3} {m['isolation_rate']:>9.2%} {m['deep_isolation_rate']:>11.2%} "
            f"{m['avg_loneliness']:>11.3f} {m['avg_active_ties']:>11.2f} "
            f"{m.get('help_requests', 0):>4} {m.get('help_success', 0):>4}"
        )

    first, last = metrics[0], metrics[-1]
    print("\n基线 → 期末变化：")
    for key, label in [
        ("isolation_rate", "孤立率"),
        ("deep_isolation_rate", "深度孤立率"),
        ("avg_loneliness", "平均孤独感"),
        ("avg_active_ties", "平均活跃关系数"),
    ]:
        print(f"  {label}: {first[key]:.3f} → {last[key]:.3f} (Δ{last[key] - first[key]:+.3f})")

    print("\n" + "=" * 72)
    print(f"焦点老人决策（共 {len(decisions)} 条）")
    print("=" * 72)
    action_counter = Counter(d["action"] for d in decisions)
    for action, count in action_counter.most_common():
        print(f"  {action}: {count}")

    # 求助结局分布
    seeks = [d for d in decisions if d["action"] == "seek_help"]
    if seeks:
        outcome_counter = Counter(d.get("outcome", "?") for d in seeks)
        print(f"\n求助结局：{dict(outcome_counter)}")

    # 理由样例（定性分析素材）
    print("\n理由样例（每类行动最多 3 条）：")
    by_action: dict[str, list] = defaultdict(list)
    for d in decisions:
        reason = d.get("reason")
        if reason and len(by_action[d["action"]]) < 3:
            by_action[d["action"]].append(d)
    for action, rows in by_action.items():
        print(f"\n  [{action}]")
        for d in rows:
            target = d.get("target") or d.get("activity") or ""
            print(f"    m{d['month']} agent{d['agent_id']} {target}: {d['reason']}")

    # ---------- 校准打靶：模拟末期 vs 调查靶标 ----------
    replay_dir = run_dir / "replay"
    agent_rows = []
    for f in sorted(replay_dir.glob("elder_support_agent_state.*.jsonl")):
        agent_rows += load_jsonl(f)
    calib = {}
    if agent_rows:
        last_t = max(r["t"] for r in agent_rows)
        final_agents = [r for r in agent_rows if r["t"] == last_t]
        n = len(final_agents)
        lonely_often = sum(1 for r in final_agents if r["loneliness"] >= 0.6) / n
        lonely_some = sum(1 for r in final_agents if r["loneliness"] >= 0.45) / n
        calib = {
            "n_agents": n,
            "lonely_often_share": {"sim": round(lonely_often, 3), "target": 0.15,
                                   "source": "CLHLS b38 总是+经常 15.4%"},
            "lonely_sometimes_plus_share": {"sim": round(lonely_some, 3), "target": 0.40,
                                            "source": "CLHLS b38 有时及以上 40.3%"},
        }
        print("\n" + "=" * 72)
        print("校准打靶（模拟末期截面 vs 调查靶标）")
        print("=" * 72)
        for key, v in calib.items():
            if key == "n_agents":
                continue
            diff = v["sim"] - v["target"]
            flag = "✓" if abs(diff) <= 0.10 else "⚠"
            print(f"  {flag} {key}: 模拟 {v['sim']:.1%} vs 靶标 {v['target']:.0%} "
                  f"(Δ{diff:+.1%})  [{v['source']}]")
        print("  （容差 ±10pp；月度衰减速率对 Harmonized 3 年转移率的比对需多种子重复后做）")

    # ---------- 异常检测（harness 自监控：发现→沉淀→下一轮修正） ----------
    anomalies = []
    if decisions:
        months_seen = sorted({d["month"] for d in decisions})
        focal_ids = sorted({d["agent_id"] for d in decisions if d["agent_id"] > 0})
        full_range = range(min(months_seen), max(m["month"] for m in metrics))
        by_agent_month = {(d["agent_id"], d["month"]) for d in decisions}
        for aid in focal_ids:
            silent = [mo for mo in full_range if (aid, mo) not in by_agent_month]
            if len(silent) >= 2:
                anomalies.append(
                    f"焦点老人 agent{aid} 在月 {silent} 无任何决策记录——"
                    "可能是 LLM 调用失败丢失行动，检查该时段 output.log 的重试/超时"
                )
        # 总体静默率 gate：stay_home 是会被记录的动作，完全无记录即 agent 未产出
        # 任何工具调用。baseline12 实测 28.2%，根因是误激活 daily-guidance。
        all_months = sorted({m["month"] for m in metrics})
        cells = len(focal_ids) * len(all_months)
        if cells:
            silent_cells = sum(
                1 for a in focal_ids for mo in all_months
                if (a, mo) not in by_agent_month
            )
            rate = silent_cells / cells
            silence_rate = round(rate, 3)
            if rate > 0.10:
                anomalies.append(
                    f"整体静默率 {rate:.1%}（{silent_cells}/{cells} 个 agent-月无决策）"
                    "超过 10% 阈值——检查是否误激活了 daily-guidance 等不适用技能，"
                    "或 LLM 未产出工具调用；该 run 的行为指标与质性素材均不可直接使用"
                )
        else:
            silence_rate = None
    else:
        silence_rate = None
        anomalies.append("决策记录为空：该 run 缺少焦点老人行为，不能作为有效实验重复")
    # 语言纯度：reason 混入英文会污染质性引语分析（baseline12 实测 3.9%）
    if decisions:
        reasons = [d["reason"] for d in decisions if d.get("reason")]
        impure = [
            r for r in reasons
            if len(re.findall(r"[一-鿿]", r)) < len(r) * 0.3
        ]
        if reasons and len(impure) / len(reasons) > 0.02:
            anomalies.append(
                f"决策理由中 {len(impure)}/{len(reasons)} "
                f"（{len(impure) / len(reasons):.1%}）非中文或中英混写，"
                "超过 2% 阈值——检查 profile 的语言要求是否生效，质性引语不可直接使用"
            )

    # LLM trace gate: high completion error rates indicate infrastructure failure,
    # not genuine behavioral seed variation.
    llm_calls = 0
    llm_errors = 0
    for trace_file in (run_dir / "trace").glob("trace_*.jsonl"):
        for span in load_jsonl(trace_file):
            if span.get("name") != "llm.completion":
                continue
            llm_calls += 1
            if span.get("status", {}).get("code") not in (None, "ok", 0):
                llm_errors += 1
    llm_error_rate = llm_errors / llm_calls if llm_calls else None
    if llm_error_rate is not None and llm_error_rate > 0.05:
        anomalies.append(
            f"LLM completion 错误率 {llm_error_rate:.1%}（{llm_errors}/{llm_calls}）"
            "超过 5% 阈值——该 run 可能反映网关故障而非真实行为差异"
        )

    if metrics:
        for m in metrics:
            if m["avg_loneliness"] < 0.05:
                anomalies.append(f"月{m['month']} 孤独感塌缩(<0.05)，稳态机制疑似失效")
            if m["deep_isolation_rate"] > 0.5:
                anomalies.append(f"月{m['month']} 深度孤立率 {m['deep_isolation_rate']:.0%} 异常偏高")
    if anomalies:
        print("\n" + "=" * 72)
        print("异常检测（需人工确认或下一轮修正）")
        print("=" * 72)
        for a in anomalies:
            print(f"  ⚠ {a}")
    else:
        print("\n异常检测：未发现异常")

    out_dir = run_dir / "analysis"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "reflections.md").write_text(
        "# 本轮运行反思（自动生成）\n\n"
        + ("\n".join(f"- ⚠ {a}" for a in anomalies) if anomalies else "- 未发现异常")
        + "\n\n打靶结果见 summary.json 的 calibration 字段。\n",
        encoding="utf-8",
    )
    summary = {
        "months": len(metrics),
        "baseline": first,
        "final": last,
        "action_distribution": dict(action_counter),
        "seek_help_outcomes": dict(Counter(d.get("outcome", "?") for d in seeks)),
        "num_decisions": len(decisions),
        "silence_rate": silence_rate,
        "llm_calls": llm_calls,
        "llm_errors": llm_errors,
        "llm_error_rate": round(llm_error_rate, 4) if llm_error_rate is not None else None,
        "calibration": calib,
        "anomalies": anomalies,
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n汇总已写入 {out_dir / 'summary.json'}")


if __name__ == "__main__":
    main()
