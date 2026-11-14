#!/usr/bin/env python3
"""按关系层拆分（第 5.3 节）的数字宏（只读，确定性）。

输入：tests/scan_layers_result_calibrated.json、tests/scan_layers_result.json（占位画像）、
      tests/scan_layers_cleanup_result_calibrated.json、tests/llm_layer_actions.json
输出：paper/numbers.tex 中 LAYERS 标记块（\\Ly... 宏）
"""
from __future__ import annotations

import json
import re
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]
BEGIN, END = "% BEGIN LAYERS (tools/layer_numbers.py)", "% END LAYERS"
ARM_TAG = {"none": "None", "casework": "Cw", "casework_nolink": "CwNolink", "timebank": "Tb",
           "timebank_pp0": "TbZero", "platform": "Pf"}
LAYER_TAG = {"family": "Fam", "peer": "Peer", "timebank": "Pair", "volunteer": "Vol", "social_worker": "Sw"}


def jload(name: str) -> dict:
    return json.loads((EXP / "tests" / name).read_text(encoding="utf-8"))


def f2(x: float) -> str:
    return f"{x:.2f}"


def f3(x: float) -> str:
    return f"{x:.3f}"


def ci3(c: list[float]) -> str:
    return f"[{c[0]:+.3f}, {c[1]:+.3f}]"


def main() -> int:
    cal = jload("scan_layers_result_calibrated.json")
    ph = jload("scan_layers_result.json")
    clean = jload("scan_layers_cleanup_result_calibrated.json")["arms"]
    llm = jload("llm_layer_actions.json")["by_condition"]
    L = [BEGIN]
    for arm, at in ARM_TAG.items():
        for layer, lt in LAYER_TAG.items():
            for w, wt in (("iv", "Iv"), ("post", "Post")):
                v = cal["arms"][arm][f"{layer}.emotional_per_elder.{w}"]["mean"]
                L.append(f"\\newcommand{{\\Ly{at}{lt}{wt}}}{{{f3(v)}}}")
    L.append(f"\\newcommand{{\\LyVolTiesPost}}{{{f2(cal['arms']['platform']['volunteer.ties_per_elder.post']['mean'])}}}")
    for name, tag in (("inner_crowding_check_iv", "ActIv"), ("inner_activation_post", "ActPost"),
                      ("middle_pair_post", "PairPost"), ("middle_pair_vs_pp0_post", "PairVsZero"),
                      ("middle_peer_post", "PeerPost"), ("outer_volunteer_emotional_post", "VolPost")):
        c = cal["contrasts"][name]
        L += [f"\\newcommand{{\\LyC{tag}}}{{{c['mean']:+.3f}}}", f"\\newcommand{{\\LyC{tag}CI}}{{{ci3(c['ci95'])}}}"]
    L.append(f"\\newcommand{{\\LyCActPostPh}}{{{ph['contrasts']['inner_activation_post']['mean']:+.3f}}}")
    for arm, tag in (("casework", "Cw"), ("platform", "Pf"), ("timebank_pp0", "TbZero")):
        d = clean[arm]["clean_minus_no_clean"]
        L += [f"\\newcommand{{\\LyClean{tag}Layer}}{{{d['layer_emotional_post']['mean']:+.3f}}}",
              f"\\newcommand{{\\LyClean{tag}Iso}}{{{d['isolation_post']['mean'] * 100:+.1f}}}",
              f"\\newcommand{{\\LyClean{tag}IsoCI}}{{[{d['isolation_post']['ci95'][0] * 100:+.1f}, "
              f"{d['isolation_post']['ci95'][1] * 100:+.1f}]}}",
              f"\\newcommand{{\\LyClean{tag}Lon}}{{{d['loneliness_post']['mean']:+.3f}}}"]
    for cond, ct in (("none", "None"), ("casework", "Cw"), ("timebank", "Tb"), ("platform", "Pf")):
        pm = llm[cond]["per_elder_month"]
        L.append(f"\\newcommand{{\\LyLlmN{ct}}}{{{len(llm[cond]['runs'])}}}")
        for layer, lt in LAYER_TAG.items():
            for w, wt in (("iv", "Iv"), ("post", "Post")):
                L.append(f"\\newcommand{{\\LyLlm{ct}{lt}{wt}}}{{{f3(pm[w][layer]['contacts'])}}}")
    L.append(f"\\newcommand{{\\LyLlmLinkIv}}{{{f2(llm['casework']['casework_link_per_focal_month']['iv'])}}}")
    L.append(END)
    block = "\n".join(L)
    nt = EXP / "paper" / "numbers.tex"
    text = nt.read_text(encoding="utf-8")
    pat = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.S)
    text = pat.sub(lambda _: block, text) if pat.search(text) else text.rstrip("\n") + "\n" + block + "\n"
    nt.write_text(text, encoding="utf-8")
    print(f"{len(L) - 2} macros")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
