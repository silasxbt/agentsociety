#!/usr/bin/env python3
"""干预组合与接续（第 6.3 节）的数字宏与 LLM 描述性汇总（只读，确定性）。

输入：
- tests/scan_combo_result_calibrated.json、tests/scan_combo_result.json   规则层组合扫描
- tests/harness_loop_combo_result.json                                   组合排期闭环
- tests/llm_calls_ledger.json                                            调用次数台账
- tmp/astra_router_v1/{none,casework,timebank}_s1（A、B、C）与
  tmp/astra_router_combo_v1/{D,E}_s1（gitignore，只含 metrics/decisions）  新路由 Astra seed 1
输出：
- tests/astra_combo_llm.json   LLM 层聚合结果（不含微观数据）
- paper/numbers.tex 中 COMBO 标记块（\\Cb... 宏）

LLM 层为单 seed、单 run 的描述性对照，只与同一新路由的 Astra seed 1 比较。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXP / "tools"))
from compare_conditions import validate  # noqa: E402

BEGIN, END = "% BEGIN COMBO (tools/combo_numbers.py)", "% END COMBO"
LLM_RUNS = {
    "A": EXP / "tmp" / "astra_router_v1" / "none_s1",
    "B": EXP / "tmp" / "astra_router_v1" / "casework_s1",
    "C": EXP / "tmp" / "astra_router_v1" / "timebank_s1",
    "D": EXP / "tmp" / "astra_router_combo_v1" / "D_s1",
    "E": EXP / "tmp" / "astra_router_combo_v1" / "E_s1",
}
ARM_TAG = {"A": "A", "B": "B", "C": "C", "D_b0.0": "D", "E_b0.0": "E", "F": "F"}


def jload(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def pct(x: float) -> str:
    return f"{x * 100:.1f}"


def pp(x: float) -> str:
    return f"{x * 100:+.1f}"


def ci(c: list[float]) -> str:
    return f"[{c[0] * 100:+.1f}, {c[1] * 100:+.1f}]"


def llm_layer() -> dict:
    out = {}
    for name, run in LLM_RUNS.items():
        v = validate(run)
        ms = v["metrics"]

        def avg(key: str, lo: int, hi: int) -> float:
            xs = [m[key] for m in ms if lo <= m["month"] <= hi]
            return sum(xs) / len(xs)

        out[name] = {
            "silence_rate": v["silence_rate"], "months": v["months"],
            "valid": v["silence_rate"] <= 0.10 and v["months"] == 24,
            "iso_iv": round(avg("isolation_rate", 7, 18), 6), "iso_post": round(avg("isolation_rate", 19, 24), 6),
            "lon_iv": round(avg("avg_loneliness", 7, 18), 6), "lon_post": round(avg("avg_loneliness", 19, 24), 6),
        }
    if not all(r["valid"] for r in out.values()):
        raise SystemExit("LLM 层存在未通过门槛的 run")
    a, b, c, d, e = (out[k] for k in "ABCDE")
    contrasts = {}
    for key in ("iso_iv", "iso_post", "lon_iv", "lon_post"):
        contrasts[f"interaction_{key}"] = round((e[key] - a[key]) - ((b[key] - a[key]) + (c[key] - a[key])), 6)
        contrasts[f"D_minus_C_{key}"] = round(d[key] - c[key], 6)
    return {"runs": out, "contrasts": contrasts,
            "note": "gpt-6-astra seed 1，新路由，单 run 描述性；A/B/C 复用 astra_router_v1，D/E 为 astra_router_combo_v1；"
                    "干预期 7–18，撤出后 19–24"}


def main() -> int:
    cal = jload(EXP / "tests" / "scan_combo_result_calibrated.json")["by_post_persist"]["pp0.5"]
    cal0 = jload(EXP / "tests" / "scan_combo_result_calibrated.json")["by_post_persist"]["pp0.0"]
    ph = jload(EXP / "tests" / "scan_combo_result.json")["by_post_persist"]["pp0.5"]
    hl = jload(EXP / "tests" / "harness_loop_combo_result.json")
    led = jload(EXP / "tests" / "llm_calls_ledger.json")
    llm = llm_layer()
    (EXP / "tests" / "astra_combo_llm.json").write_text(json.dumps(llm, ensure_ascii=False, indent=2) + "\n")

    L = [BEGIN]
    for arm, tag in ARM_TAG.items():
        a = cal["arms"][arm]
        L += [f"\\newcommand{{\\CbIv{tag}}}{{{pct(a['iv_isolation_rate']['mean'])}}}",
              f"\\newcommand{{\\CbPost{tag}}}{{{pct(a['post_isolation_rate']['mean'])}}}",
              f"\\newcommand{{\\CbOverall{tag}}}{{{pct(a['overall_isolation_rate']['mean'])}}}",
              f"\\newcommand{{\\CbLonIv{tag}}}{{{a['iv_avg_loneliness']['mean']:.3f}}}",
              f"\\newcommand{{\\CbLonPost{tag}}}{{{a['post_avg_loneliness']['mean']:.3f}}}"]
    i_iv, i_post = cal["interaction"]["E_b0.0_iv"], cal["interaction"]["E_b0.0_post"]
    L += [f"\\newcommand{{\\CbIntIv}}{{{pp(i_iv['additive']['mean'])}}}",
          f"\\newcommand{{\\CbIntIvCI}}{{{ci(i_iv['additive']['ci95'])}}}",
          f"\\newcommand{{\\CbIntIvLogit}}{{{i_iv['logit']['mean']:+.2f}}}",
          f"\\newcommand{{\\CbIntIvLogitCI}}{{[{i_iv['logit']['ci95'][0]:+.2f}, {i_iv['logit']['ci95'][1]:+.2f}]}}",
          f"\\newcommand{{\\CbIntPost}}{{{pp(i_post['additive']['mean'])}}}",
          f"\\newcommand{{\\CbIntPostCI}}{{{ci(i_post['additive']['ci95'])}}}",
          f"\\newcommand{{\\CbIntIvPh}}{{{pp(ph['interaction']['E_b0.0_iv']['additive']['mean'])}}}"]
    o = cal["order"]["D_b0.0_minus_F_post"]
    L += [f"\\newcommand{{\\CbDF}}{{{pp(o['mean'])}}}", f"\\newcommand{{\\CbDFCI}}{{{ci(o['ci95'])}}}"]
    for b, tag in (("0.0", "Zero"), ("0.25", "Quarter"), ("0.5", "Half"), ("1.0", "One")):
        h = cal["handover"][f"D_b{b}_minus_C_post"]
        L += [f"\\newcommand{{\\CbDC{tag}}}{{{pp(h['mean'])}}}", f"\\newcommand{{\\CbDC{tag}CI}}{{{ci(h['ci95'])}}}"]
    h0 = cal0["handover"]["D_b0.0_minus_C_post"]
    L += [f"\\newcommand{{\\CbDCZeroPpZero}}{{{pp(h0['mean'])}}}",
          f"\\newcommand{{\\CbDCZeroPh}}{{{pp(ph['handover']['D_b0.0_minus_C_post']['mean'])}}}",
          f"\\newcommand{{\\CbDCZeroPhCI}}{{{ci(ph['handover']['D_b0.0_minus_C_post']['ci95'])}}}",
          f"\\newcommand{{\\CbThreshPh}}{{{ph['threshold_P4']}}}"]
    best, first = hl["best"], hl["iterations"][0]
    bc = best["candidate"]
    L += [f"\\newcommand{{\\CbHlRounds}}{{{len(hl['iterations'])}}}",
          f"\\newcommand{{\\CbHlBest}}{{{pct(best['score'])}}}",
          f"\\newcommand{{\\CbHlBestTb}}{{{bc['timebank_start']}--{bc['timebank_start'] + bc['timebank_duration'] - 1}}}",
          f"\\newcommand{{\\CbHlBestCw}}{{{bc['casework_start']}--{bc['casework_start'] + bc['casework_duration'] - 1}}}",
          f"\\newcommand{{\\CbHlFirst}}{{{pct(first['score'])}}}",
          f"\\newcommand{{\\CbHlGridBest}}{{{pct(hl['grid_best_for_reference']['overall'])}}}"]
    r, c = llm["runs"], llm["contrasts"]
    for k in "ABCDE":
        L += [f"\\newcommand{{\\CbLlmIv{k}}}{{{pct(r[k]['iso_iv'])}}}",
              f"\\newcommand{{\\CbLlmPost{k}}}{{{pct(r[k]['iso_post'])}}}",
              f"\\newcommand{{\\CbLlmLonIv{k}}}{{{r[k]['lon_iv']:.3f}}}",
              f"\\newcommand{{\\CbLlmLonPost{k}}}{{{r[k]['lon_post']:.3f}}}",
              f"\\newcommand{{\\CbLlmSil{k}}}{{{pct(r[k]['silence_rate'])}}}"]
    L += [f"\\newcommand{{\\CbLlmIntIv}}{{{pp(c['interaction_iso_iv'])}}}",
          f"\\newcommand{{\\CbLlmIntLonIv}}{{{c['interaction_lon_iv']:+.3f}}}",
          f"\\newcommand{{\\CbLlmDCPost}}{{{pp(c['D_minus_C_iso_post'])}}}",
          f"\\newcommand{{\\CbLlmDCLonPost}}{{{c['D_minus_C_lon_post']:+.3f}}}"]
    combo = led["astra_router_combo_v1"]
    L += [f"\\newcommand{{\\CallsAstraCombo}}{{{sum(v['calls'] for v in combo.values()):,}}}",
          f"\\newcommand{{\\ErrorsAstraCombo}}{{{sum(v['errors'] for v in combo.values())}}}",
          f"\\newcommand{{\\CallsHarnessCombo}}{{{led['harness_combo_designer']['calls']}}}",
          END]
    block = "\n".join(L)
    nt = EXP / "paper" / "numbers.tex"
    text = nt.read_text(encoding="utf-8")
    pat = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.S)
    text = pat.sub(lambda _: block, text) if pat.search(text) else text.rstrip("\n") + "\n" + block + "\n"
    nt.write_text(text, encoding="utf-8")
    print(json.dumps(c, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
