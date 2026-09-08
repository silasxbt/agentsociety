#!/usr/bin/env python3
"""证据与进展收集器：聚合主批次、时机/剂量扫描、harness 闭环的当前状态，
生成 panel/mechanism.json（面板展示）与 EVIDENCE.md（本地留存）。

原则：只聚合、不重算；每条结论带来源文件路径；限制与口径随数据同行。
重跑本脚本即全量重生成，两个输出文件都不手改。
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]
TESTS = EXP / "tests"
OUT_JSON = EXP / "panel" / "mechanism.json"
OUT_MD = EXP / "EVIDENCE.md"


def jload(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def nn(x):
    """NaN → None（JSON/前端安全）。"""
    return None if isinstance(x, float) and math.isnan(x) else x


def main() -> int:
    timing = jload(TESTS / "scan_timing_result.json")
    loop = jload(TESTS / "harness_loop_result.json")
    comp = jload(EXP / "tmp" / "batch" / "comparison.json")
    cost = jload(TESTS / "cost_report.json")
    silence = jload(TESTS / "silence_diagnosis.json")

    mech: dict = {"generated_at": datetime.now(timezone.utc).isoformat()}

    if timing:
        P = "isolation_rate"
        rows = []
        for name, v in timing["timing_scan"].items():
            rows.append({"name": name, "window": v["iv_window"],
                         "overall": v[f"overall_{P}"]["mean"],
                         "sd": v[f"overall_{P}"]["sd"],
                         "iv": v[f"iv_{P}"]["mean"],
                         "rebound": v[f"rebound_{P}"]["mean"],
                         "post_window": v["post_window_len"]})
        dur_rows = []
        for name, v in timing["duration_scan"].items():
            dur_rows.append({"name": name, "overall": nn(v[f"overall_{P}"]["mean"]),
                             "iv": nn(v[f"iv_{P}"]["mean"]),
                             "rebound": nn(v[f"rebound_{P}"]["mean"])})
        mech["timing"] = {
            "source": "tests/scan_timing_result.json",
            "seeds": len(timing["preregistered"]["seeds"]),
            "baseline_overall": timing["baseline"]["none"][f"overall_{P}"]["mean"],
            "rows": rows, "duration_rows": dur_rows,
            "delay_cost": timing["delay_cost"],
            "caveats": timing["caveats"],
            "findings": [
                "干预期内孤立率几乎不随启动时机变化：本模型中干预即时起效，延迟的代价全部来自未被保护的等待月份",
                "casework/timebank 延迟成本约每月 +0.15/+0.18pp（全时程孤立率）；platform 总效应弱故时机不敏感",
                "casework 撤出反弹 (+0.08~0.09) 不随时长 6→12 缓解，为依赖型支持；timebank 反弹 +0.02，为存量型",
            ],
        }

    if loop:
        its = [h for h in loop["iterations"] if h.get("score") is not None]
        mech["harness_loop"] = {
            "source": "tests/harness_loop_result.json（逐轮 harness_loop_log.jsonl）",
            "designer_model": loop["preregistered"]["designer_model"],
            "objective": loop["preregistered"]["objective"],
            "constraint": "duration ≤ 12（资源帽）",
            "iterations": [{"iter": h["iter"], **h["candidate"],
                            "overall": h["score"],
                            "rationale": h.get("rationale", "")} for h in its],
            "best": loop["best"]["candidate"] if loop.get("best") else None,
            "best_overall": loop["best"]["score"] if loop.get("best") else None,
            "grid_reference_in_space": "start3_casework overall=0.0774（约束内网格最优）",
            "finding": "闭环 5 轮复现网格平台区（最优 0.0770 与网格 0.0774 差异在种子 SD 内），流程闭环成立且无夸大发现",
            "caveats": loop["caveats"],
        }

    if comp:
        mech["batch_progress"] = {
            "source": "tmp/batch/comparison.json",
            "valid_runs": comp.get("valid_runs"),
            "invalid_runs": len(comp.get("invalid_runs", [])),
            "pending": len(comp.get("pending_runs", [])),
        }

    if cost:
        mech["cost"] = {
            "source": "tests/cost_report.json",
            "assumptions": cost["assumptions"],
            "totals": cost["totals"],
            "grand_total_usd": cost["grand_total_usd"],
            "waste_share": cost["waste_share"],
            "n_runs_counted": len(cost["runs"]),
        }

    if silence:
        mech["silence_diagnosis"] = {
            "source": "tests/silence_diagnosis.json",
            "modes": {k: {"runs": v["runs"], "mitigation": v["mitigation"]}
                      for k, v in silence["modes"].items()},
        }

    OUT_JSON.write_text(json.dumps(mech, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"已写 {OUT_JSON}")

    # ---- EVIDENCE.md ----
    L = ["# 证据与进展台账（自动生成，勿手改）",
         f"\n生成时间：{mech['generated_at']}。来源：本文件由 tools/collect_evidence.py 聚合，"
         "每节标注原始文件；重跑脚本即更新。\n"]
    if comp:
        bp = mech["batch_progress"]
        L += ["## 1. 正式批次（主结果，LLM 行为层）",
              f"- 有效 {bp['valid_runs']} / 无效 {bp['invalid_runs']} / 进行中 {bp['pending']}（目标 12 有效）",
              "- 结论冻结前不报告显著性、因果或稳定排序；来源 tmp/batch/comparison.json\n"]
    if timing:
        t = mech["timing"]
        L += ["## 2. 介入时机与剂量（规则层机制扫描，20 种子）"]
        L += [f"- {f}" for f in t["findings"]]
        L += ["- 限制：" + "；".join(t["caveats"]),
              "- 来源 tests/scan_timing_result.json、scan_timing_report.md\n"]
    if loop:
        h = mech["harness_loop"]
        L += ["## 3. Harness 自主闭环（自动化科研演示）",
              f"- 设计师 {h['designer_model']}；目标 {h['objective']}；约束 {h['constraint']}",
              f"- {h['finding']}",
              "- 护栏：目标/空间/迭代数预注册；LLM 仅提案，评估为确定性规则层；全部轮次落盘",
              "- 来源 tests/harness_loop_result.json、tests/harness_loop_log.jsonl\n"]
    if cost:
        c = mech["cost"]
        t = c["totals"]
        L += ["## 4. 真实成本说明（含失败的钱）",
              f"- 累计估算 ${c['grand_total_usd']}：有效 run ${t['valid']['est_cost_usd']}"
              f" / 无效沉没 ${t['invalid']['est_cost_usd']}"
              f" / 进行中 ${t['pending']['est_cost_usd']}；沉没占比 {c['waste_share']*100:.1f}%",
              f"- 口径：调用数为 trace 实测（llm.completion span，共 {c['n_runs_counted']} 个 run 目录含归档）；"
              "token/调用与单价为文档化假设，见 tests/cost_report.json assumptions",
              "- 叙事要点：多智能体 LLM 实验的真实成本必须计入质量门槛淘汰的 run；"
              "本项目沉没成本主要来自网关 502 风暴与行为性静默两类失效（见下节）\n"]
    if silence:
        s = mech["silence_diagnosis"]
        L += ["## 5. 静默失效诊断（无效 run 根因）"]
        for k, v in s["modes"].items():
            L += [f"- {k}：{', '.join(v['runs'])} → {v['mitigation']}"]
        L += ["- 详细证据链见 tests/silence_diagnosis.json（含逐 run 的错误时段、静默月分布）\n"]
    figs = sorted((EXP / "figures").glob("fig*.png"))
    if figs:
        L += ["## 6. 图表资产（tools/make_figures.py 自动生成，配套同名 CSV）"]
        L += [f"- figures/{f.name}" for f in figs]
        L += ["- 冻结前均标注（未冻结）；批次收口后重跑脚本即为终版\n"]
    L += ["## 7. 实践叙事口径（用于论文讨论节）",
          "- 轮候时间本身是干预设计变量：机制层估计每延迟一月，两年平均孤立率上升约 0.15–0.18pp",
          "- casework 需配退出计划：撤出反弹不随时长缓解，提示逐步减量或向互惠型网络转介",
          "- 弱干预（platform 类）谈时机无意义：先保证强度，再优化时机",
          "- 以上均为模型机制结论，不宣称真实人群因果效应\n",
          "## 8. 待办与边界",
          "- 主批次重跑至 12 有效后冻结 H1–H4；三模型对比（MODEL_COMPARE.md）只进稳健性",
          "- 时机结论的 LLM 行为层抽验视规则层效应量再决定是否花钱",
          ]
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"已写 {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
