#!/usr/bin/env python3
"""生成 paper/numbers.tex：把冻结数据源里的关键数字导出为 LaTeX 宏。

原则：论文正文不手抄任何实验数字，全部经 \\Xxx 宏引用本文件；
批次冻结后重跑本脚本即全文数字同步更新，避免多处口径打架。

数据源（只读、不重算）：
- tmp/batch/comparison.json      主批次（LLM 行为层）
- tests/scan_timing_result.json  规则层时机/剂量扫描
- tests/harness_loop_result.json harness 闭环
- tests/cost_report.json         真实成本

用法：python3 tools/gen_paper_numbers.py
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]
OUT = EXP / "paper" / "numbers.tex"

# LaTeX 宏名不能含数字/下划线，用驼峰词表
CONDS = {"none": "None", "casework": "Casework", "timebank": "Timebank",
         "platform": "Platform"}


def jload(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def pct(x, digits=1):
    return f"{x * 100:.{digits}f}\\%"


def pp(x, digits=1, sign=True):
    v = round(x * 100, digits)
    if v == 0:
        v = 0.0  # 归一化负零，避免渲染成 "-0.00"
    s = "+" if (sign and v >= 0) else ""
    return f"{s}{v:.{digits}f}"


def main() -> int:
    comp = jload(EXP / "tmp" / "batch" / "comparison.json")
    timing = jload(EXP / "tests" / "scan_timing_result.json")
    loop = jload(EXP / "tests" / "harness_loop_result.json")
    cost = jload(EXP / "tests" / "cost_report.json")

    L = ["% 自动生成（tools/gen_paper_numbers.py），勿手改",
         f"% 生成日期 {date.today().isoformat()}",
         f"\\newcommand{{\\ValidRuns}}{{{comp['valid_runs']}}}",
         f"\\newcommand{{\\TargetRuns}}{{12}}"]

    # 冻结判定：无待完成 run（判无效的 run 已按门槛剔除并在论文中注明）。2026-09-11 决定按 11 个有效 run 冻结。
    frozen = not comp.get("pending_runs")
    L.append("\\newcommand{\\DraftBadge}{%s}" % (
        "" if frozen else
        f"\\textbf{{草稿数字：批次未冻结（有效 run {comp['valid_runs']}/{comp['valid_runs']+len(comp.get('pending_runs',[]))+len(comp.get('invalid_runs',[]))}），"
        "冻结后本文全部数字自动更新}"))
    L.append("\\newcommand{\\DraftBadgeEn}{%s}" % (
        "" if frozen else
        f"\\textbf{{Draft figures: batch not yet frozen "
        f"({comp['valid_runs']}/12 valid runs); all numbers auto-update "
        "upon freeze}"))

    # 条件级窗口指标
    for c, name in CONDS.items():
        v = comp["conditions"].get(c) or {}
        for key, mac in [("iso_iv", "IsoIv"), ("lon_iv", "LonIv"),
                         ("iso_post", "IsoPost"), ("iso_rebound", "IsoReb")]:
            m = (v.get(key) or {}).get("mean")
            if m is None:
                continue
            if key == "iso_rebound":
                L.append(f"\\newcommand{{\\{mac}{name}}}{{{pp(m)}}}")
            else:
                L.append(f"\\newcommand{{\\{mac}{name}}}{{{m*100:.1f}}}")
        L.append(f"\\newcommand{{\\N{name}}}{{{len(v.get('seeds', []))}}}")

    # 干预期相对降幅（casework vs none）
    iv_cw = comp["conditions"]["casework"]["iso_iv"]["mean"]
    iv_no = comp["conditions"]["none"]["iso_iv"]["mean"]
    L.append(f"\\newcommand{{\\CaseworkIvReduction}}{{{(1-iv_cw/iv_no)*100:.0f}\\%}}")

    # 配对差（vs none，同 seed）
    paired = comp.get("paired_contrasts_vs_none") or {}
    for c in ["casework", "timebank", "platform"]:
        for key, mac in [("iso_iv", "PairIv"), ("iso_rebound", "PairReb")]:
            p = (paired.get(c) or {}).get(key) or {}
            if p.get("mean_difference") is not None:
                L.append(f"\\newcommand{{\\{mac}{CONDS[c]}}}"
                         f"{{{pp(p['mean_difference'])}}}")
                L.append(f"\\newcommand{{\\{mac}{CONDS[c]}N}}{{{p['n']}}}")

    # 规则层时机扫描
    P = "isolation_rate"
    dc = timing["delay_cost"]
    for c in ["casework", "timebank", "platform"]:
        L.append(f"\\newcommand{{\\DelayCost{CONDS[c]}}}"
                 f"{{{pp(dc[c]['slope_per_month'], 2)}}}")
    L.append(f"\\newcommand{{\\TimingSeeds}}"
             f"{{{len(timing['preregistered']['seeds'])}}}")
    L.append(f"\\newcommand{{\\RulesBaselineOverall}}"
             f"{{{timing['baseline']['none'][f'overall_{P}']['mean']*100:.1f}}}")
    # casework 反弹带（时长 6 与 12 两点）
    ts = timing["timing_scan"]
    reb_cw = [v[f"rebound_{P}"]["mean"] for k, v in ts.items()
              if "casework" in k and v.get("post_window_len", 0) > 0]
    if reb_cw:
        L.append(f"\\newcommand{{\\RulesRebCwLo}}{{{pp(min(reb_cw))}}}")
        L.append(f"\\newcommand{{\\RulesRebCwHi}}{{{pp(max(reb_cw))}}}")
    reb_tb = [v[f"rebound_{P}"]["mean"] for k, v in ts.items()
              if "timebank" in k and v.get("post_window_len", 0) > 0]
    if reb_tb:
        L.append(f"\\newcommand{{\\RulesRebTb}}{{{pp(sum(reb_tb)/len(reb_tb))}}}")

    # 个体叙事个案（tools/extract_cases.py 产物；仅采用来自有效 run 的个案，
    # 时间银行侧个案因唯一带结对记录的 run 未过静默门槛而缺位，正文如实说明）
    ncp = EXP / "tmp" / "batch" / "narrative_cases.json"
    if ncp.is_file():
        for case in jload(ncp)["cases"]:
            if (case.get("type") == "casework_withdrawal_rebound"
                    and case.get("evidence_level") == "exploratory"):
                m = case["months"]
                L += [
                    f"\\newcommand{{\\CaseCwRun}}"
                    f"{{{case['run'].replace('_', chr(92) + '_')}}}",
                    f"\\newcommand{{\\CaseCwAgent}}{{{case['agent_id']}}}",
                    f"\\newcommand{{\\CaseCwLonWd}}{{{m['18']['loneliness']:.2f}}}",
                    f"\\newcommand{{\\CaseCwLonEnd}}{{{m['24']['loneliness']:.2f}}}",
                    f"\\newcommand{{\\CaseCwTiesWd}}{{{m['18']['active_ties']}}}",
                    f"\\newcommand{{\\CaseCwTiesEnd}}{{{m['24']['active_ties']}}}",
                ]

    # harness 闭环
    its = [h for h in loop["iterations"] if h.get("score") is not None]
    L.append(f"\\newcommand{{\\LoopIters}}{{{len(its)}}}")
    b = loop.get("best") or {}
    if b:
        cand = b["candidate"]
        L.append(f"\\newcommand{{\\LoopBestDesc}}{{{cand['condition']} "
                 f"start={cand['iv_start']} dur={cand['duration']}}}")
        L.append(f"\\newcommand{{\\LoopBestScore}}{{{b['score']*100:.2f}}}")

    # 分层拆解（tools/layer_decomposition.py）：焦点层 vs 规则层
    lay_p = EXP / "tests" / "layer_decomposition.json"
    if lay_p.is_file():
        lay = jload(lay_p)["by_condition"]
        names = {"none": "None", "casework": "Cw", "timebank": "Tb", "platform": "Pf"}
        for c, nm in names.items():
            a = lay.get(c)
            if not a:
                continue
            L.append(f"\\newcommand{{\\FocIv{nm}}}{{{a['focal_iso_iv']*100:.1f}}}")
            L.append(f"\\newcommand{{\\FocPost{nm}}}{{{a['focal_iso_post']*100:.1f}}}")
            L.append(f"\\newcommand{{\\FocActIv{nm}}}{{{a['focal_act_iso_iv']*100:.1f}}}")
            L.append(f"\\newcommand{{\\FocActPost{nm}}}{{{a['focal_act_iso_post']*100:.1f}}}")
            L.append(f"\\newcommand{{\\RulIv{nm}}}{{{a['rule_iso_iv']*100:.1f}}}")
            L.append(f"\\newcommand{{\\RulPost{nm}}}{{{a['rule_iso_post']*100:.1f}}}")
            L.append(f"\\newcommand{{\\FocShare{nm}}}{{{a['focal_share_of_iso_iv']*100:.0f}\\%}}")
            L.append(f"\\newcommand{{\\FocLonIv{nm}}}{{{a['focal_lon_iv']:.2f}}}")
            L.append(f"\\newcommand{{\\FocLonPost{nm}}}{{{a['focal_lon_post']:.2f}}}")
            L.append(f"\\newcommand{{\\RulLonIv{nm}}}{{{a['rule_lon_iv']:.2f}}}")
            L.append(f"\\newcommand{{\\RulLonPost{nm}}}{{{a['rule_lon_post']:.2f}}}")
            pv = a.get("paired_vs_none")
            if pv:
                for k, mac in (("focal_iso_iv", "PFocIv"), ("focal_iso_reb", "PFocReb"), ("rule_iso_iv", "PRulIv"), ("rule_iso_reb", "PRulReb"), ("focal_act_iso_iv", "PFocActIv"), ("focal_act_iso_reb", "PFocActReb")):
                    L.append(f"\\newcommand{{\\{mac}{nm}}}{{{pv[k]*100:+.1f}}}")

    # 行为签名（tests/behavior_signature.json）：脚注数字不手抄
    bs_p = EXP / "tests" / "behavior_signature.json"
    if bs_p.is_file():
        bs = jload(bs_p)
        for c, nm in (("none", "None"), ("casework", "Cw"), ("timebank", "Tb"), ("platform", "Pf")):
            b = bs.get(c)
            if not b: continue
            L.append(f"\\newcommand{{\\BsN{nm}}}{{{b['n']}}}")
            L.append(f"\\newcommand{{\\BsReq{nm}}}{{{b['total_requests']}}}")
            L.append(f"\\newcommand{{\\BsOk{nm}}}{{{b['total_success']}}}")
            L.append(f"\\newcommand{{\\BsRate{nm}}}{{{b['success_rate']*100:.1f}}}")
            L.append(f"\\newcommand{{\\BsPerRun{nm}}}{{{b['avg_requests_per_run']:.1f}}}")

    # 成本
    t = cost["totals"]
    L.append(f"\\newcommand{{\\CostTotal}}{{{cost['grand_total_usd']:.0f}}}")
    L.append(f"\\newcommand{{\\CostValid}}{{{t['valid']['est_cost_usd']:.0f}}}")
    L.append(f"\\newcommand{{\\CostWasted}}{{{t['invalid']['est_cost_usd']:.0f}}}")
    mc = t.get("model_compare", {"est_cost_usd": 0.0})
    L.append(f"\\newcommand{{\\CostModelCompare}}{{{mc['est_cost_usd']:.0f}}}")
    L.append(f"\\newcommand{{\\WasteShare}}{{{cost['waste_share']*100:.0f}\\%}}")
    tot_calls = sum(t[k]["llm_calls"] for k in t)
    L.append(f"\\newcommand{{\\TotalCalls}}{{{tot_calls:,}}}")

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"已写 {OUT}（{len(L)} 行，冻结状态：{'已冻结' if frozen else '未冻结'}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
