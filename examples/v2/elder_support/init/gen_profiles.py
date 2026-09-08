#!/usr/bin/env python3
"""生成独居老人画像（可复现）。

两种模式：
- 校准模式（默认，找得到分布文件时）：从 CLHLS 2021 独居老人（65+，n=1707）
  的真实分布抽样（年龄段、性别、自评健康、孤独感基线、在世子女数、子女探望率），
  由 data_pipeline/extract_clhls2021.py 生成。
  注意：CLHLS 对高龄老人过抽样，原始分布偏老，报告中需说明或做事后分层。
- 占位模式（--placeholder 或分布文件缺失）：文献汇总数字的近似分布。

外向性无调查对应变量，两种模式都用截断正态；子女距离 CLHLS 编码无标签，
暂用 本地/同城/外地 35%/30%/35% 占位，探望频率按 f103x5 常探望比例校准。

用法：
  python gen_profiles.py --num 20 --focal 6 --seed 42 --out profiles.json
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

DIST_PATH = (
    Path(__file__).resolve().parent.parent
    / "data_pipeline" / "out" / "clhls2021_dist.json"
)

# b12 自评健康 -> health 分值中心
_HEALTH_MAP = {"1": 0.88, "2": 0.75, "3": 0.55, "4": 0.35, "5": 0.20}
# b38 孤独感 -> 初始孤独值中心（1=总是 .. 5=从不）
_LONELY_MAP = {"1": 0.85, "2": 0.70, "3": 0.50, "4": 0.30, "5": 0.15}
_AGE_BAND = {
    "65-69": (65, 69), "70-74": (70, 74), "75-79": (75, 79),
    "80-84": (80, 84), "85-89": (85, 89), "90-94": (90, 94), "95+": (95, 99),
}


def _sample_cat(rng: random.Random, dist: dict) -> str:
    keys = list(dist.keys())
    return rng.choices(keys, weights=[dist[k] for k in keys])[0]

SURNAMES = "王李张刘陈杨黄赵周吴徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭"
NEIGHBOR_GIVEN = ["大爷", "大妈", "叔", "婶", "伯", "姨", "老师", "师傅"]


def _trunc_gauss(rng: random.Random, mu: float, sigma: float, lo: float, hi: float) -> float:
    for _ in range(20):
        x = rng.gauss(mu, sigma)
        if lo <= x <= hi:
            return round(x, 3)
    return round(min(hi, max(lo, mu)), 3)


def gen_elder(rng: random.Random, idx: int, focal: bool) -> dict:
    age = min(90, 65 + int(rng.expovariate(1 / 8.0)))
    gender = rng.choice(["女", "女", "女", "男", "男"])  # 独居老人中女性偏多
    surname = rng.choice(SURNAMES)
    name = f"{surname}{'奶奶' if gender == '女' else '爷爷'}（{idx}号）"
    # 健康随年龄下降
    health = _trunc_gauss(rng, 0.72 - (age - 65) * 0.012, 0.15, 0.15, 0.95)
    extroversion = _trunc_gauss(rng, 0.5, 0.2, 0.05, 0.95)

    n_children = rng.choices([0, 1, 2, 3], weights=[8, 30, 42, 20])[0]
    children = []
    for c in range(n_children):
        distance = rng.choices(
            ["local", "same_city", "other_province"], weights=[35, 30, 35]
        )[0]
        base_freq = {"local": 5.0, "same_city": 3.0, "other_province": 1.5}[distance]
        children.append(
            {
                "name": f"{'儿子' if rng.random() < 0.5 else '女儿'}{surname}{c + 1}",
                "distance": distance,
                "contact_per_month": round(base_freq * rng.uniform(0.5, 1.5), 1),
            }
        )

    n_ties = rng.choices([0, 1, 2, 3, 4], weights=[10, 25, 35, 20, 10])[0]
    # 外向的人初始关系更多
    n_ties = min(4, n_ties + (1 if extroversion > 0.7 else 0))
    ties = []
    for _ in range(n_ties):
        ties.append(
            {
                "name": f"{rng.choice(SURNAMES)}{rng.choice(NEIGHBOR_GIVEN)}",
                "kind": rng.choice(["neighbor", "neighbor", "friend"]),
                "strength": _trunc_gauss(rng, 0.5, 0.18, 0.1, 0.9),
            }
        )

    return {
        "id": idx,
        "name": name,
        "age": age,
        "gender": gender,
        "health": health,
        "extroversion": extroversion,
        "focal": focal,
        "children": children,
        "ties": ties,
        "loneliness": _trunc_gauss(rng, 0.35, 0.15, 0.05, 0.8),
    }


def gen_elder_calibrated(
    rng: random.Random, idx: int, focal: bool, dist: dict
) -> dict:
    """按 CLHLS 2021 独居老人分布抽样一位老人。"""
    band = _sample_cat(rng, dist["age_band"])
    lo, hi = _AGE_BAND[band]
    age = rng.randint(lo, hi)
    gender = "男" if _sample_cat(rng, dist["sex"]) == "1" else "女"
    surname = rng.choice(SURNAMES)
    name = f"{surname}{'奶奶' if gender == '女' else '爷爷'}（{idx}号）"

    health = _trunc_gauss(
        rng, _HEALTH_MAP[_sample_cat(rng, dist["self_rated_health_b12"])], 0.06,
        0.10, 0.95,
    )
    loneliness = _trunc_gauss(
        rng, _LONELY_MAP[_sample_cat(rng, dist["loneliness_b38"])], 0.06, 0.05, 0.9
    )
    extroversion = _trunc_gauss(rng, 0.5, 0.2, 0.05, 0.95)

    n_children = int(_sample_cat(rng, dist["alive_children_count"]))
    n_children = min(n_children, 6)  # 模拟中超过 6 个子女合并意义不大
    freq_visit_share = dist["child_frequent_visits_f103x5"].get("1", 0.79)
    children = []
    for c in range(n_children):
        # CHARLS 2015 Child.dta cb053（非同住子女，n≈22k）：
        # 同村/同院 27.6% | 同县市 35.6% | 更远 36.7%
        distance = rng.choices(
            ["local", "same_city", "other_province"], weights=[28, 36, 36]
        )[0]
        # 常探望子女联系频率高；不常探望的明显稀疏
        if rng.random() < freq_visit_share:
            base = {"local": 5.0, "same_city": 3.0, "other_province": 1.8}[distance]
        else:
            base = {"local": 1.5, "same_city": 0.8, "other_province": 0.4}[distance]
        children.append(
            {
                "name": f"{'儿子' if rng.random() < 0.5 else '女儿'}{surname}{c + 1}",
                "distance": distance,
                "contact_per_month": round(base * rng.uniform(0.7, 1.3), 1),
            }
        )

    n_ties = rng.choices([0, 1, 2, 3, 4], weights=[10, 25, 35, 20, 10])[0]
    n_ties = min(4, n_ties + (1 if extroversion > 0.7 else 0))
    ties = [
        {
            "name": f"{rng.choice(SURNAMES)}{rng.choice(NEIGHBOR_GIVEN)}",
            "kind": rng.choice(["neighbor", "neighbor", "friend"]),
            "strength": _trunc_gauss(rng, 0.5, 0.18, 0.1, 0.9),
        }
        for _ in range(n_ties)
    ]

    return {
        "id": idx,
        "name": name,
        "age": age,
        "gender": gender,
        "health": health,
        "extroversion": extroversion,
        "focal": focal,
        "children": children,
        "ties": ties,
        "loneliness": loneliness,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--num", type=int, default=20)
    ap.add_argument("--focal", type=int, default=6)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--placeholder", action="store_true", help="强制用占位分布")
    ap.add_argument("--out", default=str(Path(__file__).parent / "../tmp/init/profiles.json"))
    args = ap.parse_args()

    rng = random.Random(args.seed)
    if not args.placeholder and DIST_PATH.is_file():
        dist = json.loads(DIST_PATH.read_text(encoding="utf-8"))
        elders = [
            gen_elder_calibrated(rng, i + 1, i < args.focal, dist)
            for i in range(args.num)
        ]
        mode = f"calibrated(CLHLS2021, n={dist['_meta']['n_living_alone_65plus']})"
    else:
        elders = [gen_elder(rng, i + 1, i < args.focal) for i in range(args.num)]
        mode = "placeholder"
    print(f"mode={mode}")
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(elders, ensure_ascii=False, indent=2), encoding="utf-8")
    n_focal = sum(1 for e in elders if e["focal"])
    print(f"Wrote {out} (elders={len(elders)}, focal={n_focal}, seed={args.seed})")


if __name__ == "__main__":
    main()
