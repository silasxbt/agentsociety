#!/usr/bin/env python3
"""从 CLHLS 2021 截面数据提取独居老人校准分布。

输入：data/raw/clhls2021/CLHLS2021_released.tab（微观数据，不入 git）
输出：examples/v2/elder_support/data_pipeline/out/clhls2021_dist.json（汇总分布，可入 git）
     以及同名 .md 人类可读摘要

样本筛选：a51 == 2（独居）且 age >= 65。
变量对照（见 DDI 元数据）：
  age 验证年龄 | sex 性别(1男2女) | residenc 城乡(1城市2镇3农村)
  b38 孤独感(1总是..5从不) | b12 自评健康(1很好..5很差)
  f41 婚姻(4丧偶) | f10 曾生育子女数 | a58 独居原因
  f103{a-l}4 子女在世年龄 | f103{a-l}5 是否常来探望 | f103{a-l}6 是否有联系
  f103{a-l}7 子女居住距离（编码，用于本地/同城/外地近似）

用法：
  python extract_clhls2021.py
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[4]
RAW = REPO / "data" / "raw" / "clhls2021" / "CLHLS2021_released.tab"
OUT_DIR = Path(__file__).resolve().parent / "out"

CHILD_LETTERS = "abcdefghijkl"


def pct(counter: Counter, valid_keys=None) -> dict:
    """把计数变成百分比分布（剔除缺失/不知道）。"""
    items = {
        k: v for k, v in counter.items() if valid_keys is None or k in valid_keys
    }
    total = sum(items.values())
    if total == 0:
        return {}
    return {str(k): round(v / total, 4) for k, v in sorted(items.items())}


def main() -> None:
    usecols = ["age", "sex", "residenc", "b38", "b12", "f41", "f10", "a58", "a51"]
    child_cols = []
    for c in CHILD_LETTERS:
        child_cols += [f"f103{c}4", f"f103{c}5", f"f103{c}6", f"f103{c}7"]
    df = pd.read_csv(RAW, sep="\t", low_memory=False)
    have = [c for c in usecols + child_cols if c in df.columns]
    missing = [c for c in usecols if c not in df.columns]
    df = df[have]

    for col in have:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    total_n = len(df)
    alone = df[(df["a51"] == 2) & (df["age"] >= 65)].copy()
    n = len(alone)

    # 子女在世数量：有年龄记录的子女数（f103x4 > 0 且非缺失码）
    def alive_children(row) -> int:
        cnt = 0
        for c in CHILD_LETTERS:
            v = row.get(f"f103{c}4")
            if pd.notna(v) and 0 < v < 120:
                cnt += 1
        return cnt

    alone["alive_children"] = alone.apply(alive_children, axis=1)

    # 子女探望/联系（对每个在世子女汇总）
    visit_counter: Counter = Counter()
    contact_counter: Counter = Counter()
    dist_counter: Counter = Counter()
    for c in CHILD_LETTERS:
        age_col, v_col, ct_col, d_col = (
            f"f103{c}4", f"f103{c}5", f"f103{c}6", f"f103{c}7",
        )
        if age_col not in alone.columns:
            continue
        mask = alone[age_col].notna() & (alone[age_col] > 0) & (alone[age_col] < 120)
        if v_col in alone.columns:
            visit_counter.update(alone.loc[mask, v_col].dropna().astype(int).tolist())
        if ct_col in alone.columns:
            contact_counter.update(alone.loc[mask, ct_col].dropna().astype(int).tolist())
        if d_col in alone.columns:
            dist_counter.update(alone.loc[mask, d_col].dropna().astype(int).tolist())

    age_bins = pd.cut(
        alone["age"],
        bins=[65, 70, 75, 80, 85, 90, 95, 120],
        right=False,
        labels=["65-69", "70-74", "75-79", "80-84", "85-89", "90-94", "95+"],
    )

    dist = {
        "_meta": {
            "source": "CLHLS 2021 cross-sectional (PKU Open Research Data, DVN/UNYEL1 V3)",
            "filter": "a51==2 (living alone) & age>=65",
            "n_total_sample": int(total_n),
            "n_living_alone_65plus": int(n),
            "missing_expected_cols": missing,
            "note": "百分比分布已剔除缺失/不知道；仅汇总统计，无微观个体数据",
        },
        "age_band": pct(Counter(age_bins.dropna().tolist())),
        "sex": pct(Counter(alone["sex"].dropna().astype(int)), {1, 2}),
        "residence": pct(Counter(alone["residenc"].dropna().astype(int)), {1, 2, 3}),
        "loneliness_b38": pct(
            Counter(alone["b38"].dropna().astype(int)), {1, 2, 3, 4, 5}
        ),
        "self_rated_health_b12": pct(
            Counter(alone["b12"].dropna().astype(int)), {1, 2, 3, 4, 5}
        ),
        "marital_f41": pct(
            Counter(alone["f41"].dropna().astype(int)), {1, 2, 3, 4, 5}
        ),
        "reason_live_alone_a58": pct(
            Counter(alone["a58"].dropna().astype(int)), {1, 2, 3, 4}
        ),
        "alive_children_count": pct(Counter(alone["alive_children"].astype(int))),
        "child_frequent_visits_f103x5": pct(visit_counter, {1, 2}),
        "child_contact_f103x6": pct(contact_counter, {1, 2}),
        "child_residence_distance_f103x7_raw": pct(dist_counter),
        "codebook": {
            "sex": {"1": "男", "2": "女"},
            "residence": {"1": "城市", "2": "镇", "3": "农村"},
            "loneliness_b38": {
                "1": "总是", "2": "经常", "3": "有时", "4": "很少", "5": "从不",
            },
            "self_rated_health_b12": {
                "1": "很好", "2": "好", "3": "一般", "4": "差", "5": "很差",
            },
            "marital_f41": {
                "1": "已婚同住", "2": "分居", "3": "离异", "4": "丧偶", "5": "未婚",
            },
            "reason_live_alone_a58": {
                "1": "无子女", "2": "子女无法照料", "3": "不想麻烦子女", "4": "其他",
            },
            "child_visits/contact": {"1": "是", "2": "否"},
        },
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / "clhls2021_dist.json"
    out_json.write_text(json.dumps(dist, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# CLHLS 2021 独居老人（65+）校准分布",
        f"\n全样本 {total_n} 人，其中 65+ 独居 **{n}** 人。\n",
    ]
    for key in [
        "age_band", "sex", "residence", "loneliness_b38",
        "self_rated_health_b12", "marital_f41", "reason_live_alone_a58",
        "alive_children_count", "child_frequent_visits_f103x5",
        "child_contact_f103x6",
    ]:
        lines.append(f"## {key}")
        code = dist["codebook"].get(key, {})
        for k, v in dist[key].items():
            label = code.get(k, k)
            lines.append(f"- {label}: {v:.1%}")
        lines.append("")
    (OUT_DIR / "clhls2021_dist.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"n_living_alone_65plus = {n} / {total_n}")
    print(f"Wrote {out_json}")
    print(f"Wrote {OUT_DIR / 'clhls2021_dist.md'}")


if __name__ == "__main__":
    main()
