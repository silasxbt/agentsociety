#!/usr/bin/env python3
"""从 CLHLS 2021 抽出独居老人（65+）的个体记录，供画像整条重抽（gen_profiles resample）。

输入：data/raw/clhls2021/CLHLS2021_released.tab
输出：data/restricted/clhls2021_alone_records.json —— **受限数据，不入 git、不上面板**。
只保留重抽需要的字段：age, sex, b12, b38, n_children, visits（逐子女 f103x5 是否常探望）。
剔除 b12/b38/sex 缺失或不在 1–5 / 1–2 的记录；口径与 extract_clhls2021.py 一致。
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[4]
RAW = REPO / "data" / "raw" / "clhls2021" / "CLHLS2021_released.tab"
OUT = REPO / "data" / "restricted" / "clhls2021_alone_records.json"
CHILD_LETTERS = "abcdefghijkl"


def main() -> None:
    df = pd.read_csv(RAW, sep="\t", low_memory=False)
    cols = ["age", "sex", "b12", "b38", "a51"] + [
        f"f103{c}{k}" for c in CHILD_LETTERS for k in (4, 5) if f"f103{c}{k}" in df.columns
    ]
    df = df[[c for c in cols if c in df.columns]].apply(pd.to_numeric, errors="coerce")
    alone = df[(df["a51"] == 2) & (df["age"] >= 65)]
    records = []
    for _, row in alone.iterrows():
        if not (row["sex"] in (1, 2) and row["b12"] in range(1, 6) and row["b38"] in range(1, 6)):
            continue
        visits = []
        for c in CHILD_LETTERS:
            a = row.get(f"f103{c}4")
            if pd.notna(a) and 0 < a < 120:
                v = row.get(f"f103{c}5")
                visits.append(1 if v == 1 else 0 if v == 2 else None)
        known = [v for v in visits if v is not None]
        records.append({
            "age": int(min(row["age"], 99)), "sex": int(row["sex"]),
            "b12": int(row["b12"]), "b38": int(row["b38"]),
            "n_children": len(visits), "visits": known,
        })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    OUT.chmod(0o600)
    print(f"独居 65+ {len(alone)} 人，可用记录 {len(records)} 条 -> {OUT}")


if __name__ == "__main__":
    main()
