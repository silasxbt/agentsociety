#!/usr/bin/env python3
"""实测模型的关系存活曲线，用于与 Burt (2000) Table 1 / Figure 1A 对标。

背景：Burt 报告的是"T0 时观察到的关系中，有多少比例在 T 年后仍被提及"的
**群体存活率**；而我们模型里的 decay_rate=0.06 衰减的是**单条关系的强度**
（跌破 0.05 才删除）。两者不是同一个量，不能直接对标。

本脚本以 Burt 的口径实测模型输出：记录 T0 时刻每位老人的全部 ties，
逐年检查其中仍存在的比例，得到可与 Burt Table 1 直接比较的存活率。

不消耗 LLM（纯规则层）。
"""

from __future__ import annotations

import asyncio
import json
import math
import random
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

# Burt (2000) Figure 1A 拟合方程 Y=(T+1)^(γ+κ·KIN+λ·WORK) 的 OLS 系数
BURT_G, BURT_K, BURT_L = -0.716, 0.250, -1.126


def burt_survival(years: float, kin: float = 0.0, work: float = 0.0) -> float:
    """Burt 幂函数预测的 T 年后存活比例。"""
    return (years + 1.0) ** (BURT_G + BURT_K * kin + BURT_L * work)


def snapshot_ties(env: ElderSupportEnv) -> set[tuple[int, str]]:
    """当前所有 (老人id, 关系人名) 组合。"""
    out = set()
    for e in env._elders.values():
        for name in e["ties"]:
            out.add((e["id"], name))
    return out


def kin_share(env: ElderSupportEnv, keys: set[tuple[int, str]]) -> float:
    """给定关系集合中家庭关系的占比（Burt 方程的 KIN 变量）。"""
    by_id = env._elders
    fam = sum(
        1 for (aid, n) in keys
        if by_id[aid]["ties"].get(n, {}).get("kind") == "family"
    )
    return fam / len(keys) if keys else 0.0


async def measure(num: int, months: int, seed: int, decay: float) -> dict:
    rng = random.Random(seed)  # 必须复用同一 rng，否则 num 个老人完全相同
    elders = [gen_elder(rng, i + 1, focal=False) for i in range(num)]
    with tempfile.TemporaryDirectory() as td:
        env = ElderSupportEnv(elders=elders, seed=seed, decay_rate=decay)
        env._bind_workspace(Path(td) / "ws")
        t = datetime(2026, 1, 1, 8)

        await env.step(0, t)  # T0：初始关系成型
        t += timedelta(days=30)
        t0 = snapshot_ties(env)
        kin = kin_share(env, t0)

        curve = []
        for tick in range(1, months + 1):
            await env.step(tick, t)
            t += timedelta(days=30)
            alive = len(t0 & snapshot_ties(env))
            curve.append((tick, alive / len(t0) if t0 else 0.0))

    return {"n_ties_t0": len(t0), "kin_share": kin, "curve": curve, "decay": decay}


async def main() -> int:
    MONTHS = 48
    res = await measure(num=50, months=MONTHS, seed=7, decay=0.06)
    curve = dict(res["curve"])
    kin = res["kin_share"]

    print(f"T0 关系数 {res['n_ties_t0']}，家庭关系占比 {kin:.1%}，decay_rate={res['decay']}")
    print()
    print(f"{'年':>3} {'模型存活率':>10} {'Burt家庭':>9} {'Burt非家庭':>10} {'Burt同口径':>10}")
    for yr in range(1, MONTHS // 12 + 1):
        m = curve.get(yr * 12)
        if m is None:
            continue
        print(f"{yr:>3} {m:>10.1%} {burt_survival(yr, kin=1):>9.1%} "
              f"{burt_survival(yr, kin=0):>10.1%} {burt_survival(yr, kin=kin):>10.1%}")

    # 模型的群体半衰期
    half = next((mo for mo, s in res["curve"] if s <= 0.5), None)
    print()
    if half:
        print(f"模型群体半衰期：{half} 个月（{half/12:.2f} 年）")
    else:
        last_m, last_s = res["curve"][-1]
        print(f"模型在 {MONTHS} 个月内未跌破 50%（月{last_m} 存活 {last_s:.1%}）")

    for lab, k, w in [("家庭", 1, 0), ("家庭以外", 0, 0), ("同事(银行家)", 0, 1)]:
        e = BURT_G + BURT_K * k + BURT_L * w
        T = 0.5 ** (1 / e) - 1
        print(f"Burt {lab:<12} 半衰期 {T:.2f} 年")

    Path(__file__).with_name("tie_survival_result.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
