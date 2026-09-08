#!/usr/bin/env python3
"""从 Harmonized CHARLS (Version D) 提取校准分布与纵向转移。

输入：data/raw/harmonized/H_CHARLS_D_Data.dta（微观数据，不入 git）
输出：examples/v2/elder_support/data_pipeline/out/harmonized_charls.json / .md

两部分：
1. 2018 (Wave 4) 加权截面：60+ 独居老人（h4hhres==1）的年龄/性别/城乡/孤独/
   自评健康/子女数/周联系率分布，用 r4wtrespb 个体权重（修正抽样偏差）。
2. 2015→2018 纵向转移（不加权，报告需注明）：
   - 孤独感转移矩阵：w3 不孤独 → w4 孤独 的发生率（网络衰减速率锚点）
   - 丧偶冲击：w3 有配偶 & w4 丧偶者 的孤独感变化 vs 婚姻不变者（H1 关键节点流失）
   - 独居进入率：w3 非独居 → w4 独居

变量：r4agey ragender h4rural r4flonel r4shlta r4mstat h4child h4hhres
     h4kcnt h4kcntf h4coresd h4lvnear r4wtrespb + w3 对应项
编码：flonel CES-D「感到孤独」1=Rarely/none 2=Some days 3=Occasionally 4=Most time
     shlta 1=Excellent..5=Poor; mstat 1=married..7=widowed 8=never married
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[4]
RAW = REPO / "data" / "raw" / "harmonized" / "H_CHARLS_D_Data.dta"
OUT_DIR = Path(__file__).resolve().parent / "out"

COLS = [
    "r4agey", "ragender", "h4rural", "r4flonel", "r4shlta", "r4mstat",
    "h4child", "h4hhres", "h4kcnt", "h4kcntf", "h4coresd", "h4lvnear",
    "r4wtrespb",
    "r3agey", "r3flonel", "r3mstat", "h3hhres", "r3shlta",
]


def wpct(series: pd.Series, weights: pd.Series) -> dict:
    """加权百分比分布（剔除缺失）。"""
    mask = series.notna() & weights.notna()
    s, w = series[mask], weights[mask]
    total = w.sum()
    if total == 0:
        return {}
    def key(val) -> str:
        try:
            f = float(val)
            return str(int(f)) if f.is_integer() else str(f)
        except (TypeError, ValueError):
            return str(val)

    out = {}
    for val in sorted(s.unique(), key=str):
        out[key(val)] = round(float(w[s == val].sum() / total), 4)
    return out


def pct(series: pd.Series) -> dict:
    s = series.dropna()
    if len(s) == 0:
        return {}
    vc = s.value_counts(normalize=True).sort_index()
    return {
        str(int(k)) if float(k).is_integer() else str(k): round(float(v), 4)
        for k, v in vc.items()
    }


def main() -> None:
    df = pd.read_stata(RAW, columns=COLS, convert_categoricals=False)

    # ---------- 2018 加权截面：60+ 独居 ----------
    w4 = df[(df["r4agey"] >= 60) & (df["h4hhres"] == 1)].copy()
    wt = w4["r4wtrespb"]
    age_band = pd.cut(
        w4["r4agey"], bins=[60, 65, 70, 75, 80, 85, 120], right=False,
        labels=["60-64", "65-69", "70-74", "75-79", "80-84", "85+"],
    )
    n_children = w4["h4child"].clip(upper=6)

    cross = {
        "n_unweighted": int(len(w4)),
        "age_band": wpct(age_band.cat.codes.replace(-1, np.nan).map(
            dict(enumerate(age_band.cat.categories))
        ).astype(object).where(age_band.notna()), wt) if len(w4) else {},
        "gender": wpct(w4["ragender"], wt),  # 1男 2女
        "rural": wpct(w4["h4rural"], wt),  # 0城市 1农村
        "cesd_lonely_r4flonel": wpct(w4["r4flonel"], wt),
        "self_health_r4shlta": wpct(w4["r4shlta"], wt),
        "marital_r4mstat": wpct(w4["r4mstat"], wt),
        "n_children": wpct(n_children, wt),
        "weekly_contact_children_any": wpct(w4["h4kcnt"], wt),  # 0否 1是
        "weekly_contact_in_person": wpct(w4["h4kcntf"], wt),
        "children_live_near": wpct(w4["h4lvnear"], wt),
    }

    # ---------- 2015→2018 纵向转移（60+，两轮都有数据）----------
    panel = df[
        (df["r3agey"] >= 60)
        & df["r3flonel"].notna()
        & df["r4flonel"].notna()
    ].copy()
    # 孤独定义：CES-D flonel >= 3（相当一部分时间感到孤独）
    panel["lonely3"] = panel["r3flonel"] >= 3
    panel["lonely4"] = panel["r4flonel"] >= 3
    alone3 = panel["h3hhres"] == 1

    def rate(mask) -> tuple[float, int]:
        sub = panel[mask]
        return (round(float(sub["lonely4"].mean()), 4), int(len(sub))) if len(sub) else (None, 0)

    onset_alone, n_oa = rate(alone3 & ~panel["lonely3"])
    onset_not_alone, n_on = rate(~alone3 & ~panel["lonely3"])
    persist_alone, n_pa = rate(alone3 & panel["lonely3"])
    recover_pool = panel[panel["lonely3"]]

    # 丧偶冲击：w3 已婚(1,3) → w4 丧偶(7)
    married3 = panel["r3mstat"].isin([1, 3])
    widowed4 = panel["r4mstat"] == 7
    shock = panel[married3 & widowed4]
    stable = panel[married3 & panel["r4mstat"].isin([1, 3])]
    longit = {
        "note": "60+ 两轮均有 CES-D 者；孤独=flonel>=3；未加权",
        "n_panel": int(len(panel)),
        "lonely_onset_3y": {
            "living_alone_w3": {"rate": onset_alone, "n": n_oa},
            "not_alone_w3": {"rate": onset_not_alone, "n": n_on},
        },
        "lonely_persistence_3y_alone": {"rate": persist_alone, "n": n_pa},
        "lonely_recovery_3y_all": {
            "rate": round(float((~recover_pool["lonely4"]).mean()), 4),
            "n": int(len(recover_pool)),
        },
        "widowhood_shock": {
            "widowed_w3to4_lonely_w4_rate": round(float(shock["lonely4"].mean()), 4)
            if len(shock) else None,
            "n_widowed": int(len(shock)),
            "stayed_married_lonely_w4_rate": round(float(stable["lonely4"].mean()), 4)
            if len(stable) else None,
            "n_stayed_married": int(len(stable)),
        },
        "alone_entry_3y": {
            "rate": round(
                float((df.loc[(df["r3agey"] >= 60) & (df["h3hhres"] > 1), "h4hhres"] == 1)
                      .mean()), 4
            ),
        },
    }

    result = {
        "_meta": {
            "source": "Harmonized CHARLS Version D (waves 2011/2013/2015/2018)",
            "cross_section": "W4 2018, age>=60, living alone (h4hhres==1), weighted r4wtrespb",
            "codebook": {
                "gender": {"1": "男", "2": "女"},
                "rural": {"0": "城市", "1": "农村"},
                "cesd_lonely": {
                    "1": "很少或没有(<1天/周)", "2": "有些天(1-2天)",
                    "3": "经常(3-4天)", "4": "大多数时间(5-7天)",
                },
                "self_health": {"1": "很好", "2": "好", "3": "一般", "4": "差", "5": "很差"},
                "mstat": {"1": "已婚同住", "3": "已婚分居", "4": "分居", "5": "离异",
                          "7": "丧偶", "8": "未婚"},
                "binary": {"0": "否", "1": "是"},
            },
        },
        "cross_section_2018": cross,
        "longitudinal_2015_2018": longit,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "harmonized_charls.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["longitudinal_2015_2018"], ensure_ascii=False, indent=2))
    print(f"\ncross-section n={cross['n_unweighted']}")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
