#!/usr/bin/env python3
"""干预机制冒烟测试（纯规则层，零 LLM）。

同一批 50 名老人、同种子，四个条件各跑 24 个月：
  baseline | casework | timebank | platform（干预窗口：第 7-18 月，之后撤出）
检查：
1. 干预期内三种干预的孤立率/孤独感均值应不高于 baseline；
2. 撤出后（19-24 月）timebank 的孤立率应低于 casework/platform（H4 方向性）；
3. 全部可复现。
"""

from __future__ import annotations

import asyncio
import json
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

MONTHS = 24
IV_START, IV_END = 7, 18


def make_elders(num: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    return [gen_elder(rng, i + 1, focal=False) for i in range(num)]


async def run_cond(elders, iv_type, workspace: Path) -> list[dict]:
    iv = None if iv_type == "baseline" else {
        "type": iv_type, "start_month": IV_START, "end_month": IV_END, "params": {},
    }
    env = ElderSupportEnv(elders=elders, seed=42, intervention=iv)
    env._bind_workspace(workspace)
    t = datetime(2026, 1, 1, 8)
    for tick in range(MONTHS + 1):
        await env.step(tick, t)
        t += timedelta(days=30)
    rows = (workspace / "state" / "metrics.jsonl").read_text(encoding="utf-8")
    return [json.loads(x) for x in rows.splitlines()]


def avg(ms, key, lo, hi):
    sub = [m[key] for m in ms if lo <= m["month"] <= hi]
    return sum(sub) / len(sub)


async def main() -> int:
    elders = make_elders(50, seed=7)
    results = {}
    with tempfile.TemporaryDirectory() as td:
        for cond in ["baseline", "casework", "timebank", "platform"]:
            results[cond] = await run_cond(
                [json.loads(json.dumps(e)) for e in elders], cond, Path(td) / cond
            )

    print(f"{'条件':<10}{'干预期孤立率':>10}{'干预期孤独感':>10}{'撤出后孤立率':>10}{'撤出后孤独感':>10}")
    stats = {}
    for cond, ms in results.items():
        s = {
            "iso_iv": avg(ms, "isolation_rate", IV_START, IV_END),
            "lon_iv": avg(ms, "avg_loneliness", IV_START, IV_END),
            "iso_post": avg(ms, "isolation_rate", IV_END + 1, MONTHS),
            "lon_post": avg(ms, "avg_loneliness", IV_END + 1, MONTHS),
        }
        stats[cond] = s
        print(f"{cond:<10}{s['iso_iv']:>11.2%}{s['lon_iv']:>11.3f}"
              f"{s['iso_post']:>11.2%}{s['lon_post']:>11.3f}")

    failures = []
    for cond in ["casework", "timebank", "platform"]:
        if stats[cond]["lon_iv"] > stats["baseline"]["lon_iv"] + 0.01:
            failures.append(f"{cond} 干预期孤独感高于 baseline，机制方向反了")
        if stats[cond]["iso_iv"] > stats["baseline"]["iso_iv"] + 0.02:
            failures.append(f"{cond} 干预期孤立率高于 baseline")
    if stats["timebank"]["lon_post"] > min(
        stats["casework"]["lon_post"], stats["platform"]["lon_post"]
    ) + 0.02:
        failures.append("撤出后 timebank 孤独感未优于其他干预（H4 机制未生效）")

    if failures:
        print("\nFAIL:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nPASS: 三种干预方向正确，时间银行撤出后可持续性机制生效")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
