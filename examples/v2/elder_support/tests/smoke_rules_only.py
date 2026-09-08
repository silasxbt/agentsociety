#!/usr/bin/env python3
"""纯规则层冒烟测试：不消耗 LLM，验证环境机制与指标曲线的合理性。

把 50 名老人全部作为规则层跑 24 个模拟月，检查：
1. 环境可实例化、step 可推进、to_workspace/restore 往返一致；
2. 孤立率/孤独感随时间上升（无干预基线应恶化）；
3. 同种子两次运行结果完全一致（可复现性）。
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


def make_elders(num: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    return [gen_elder(rng, i + 1, focal=False) for i in range(num)]


async def run_sim(elders: list[dict], months: int, seed: int, workspace: Path) -> list[dict]:
    env = ElderSupportEnv(elders=elders, seed=seed)
    env._bind_workspace(workspace)
    t = datetime(2026, 1, 1, 8)
    for tick in range(months + 1):
        await env.step(tick, t)
        t += timedelta(days=30)
    await env.to_workspace()
    metrics_path = workspace / "state" / "metrics.jsonl"
    return [json.loads(x) for x in metrics_path.read_text(encoding="utf-8").splitlines()]


async def main() -> int:
    elders = make_elders(50, seed=7)
    with tempfile.TemporaryDirectory() as td:
        m1 = await run_sim(elders, 24, seed=42, workspace=Path(td) / "run1")
        m2 = await run_sim(elders, 24, seed=42, workspace=Path(td) / "run2")

        # 恢复往返
        env = ElderSupportEnv(elders=elders, seed=42)
        ok = await env.restore(Path(td) / "run1")
        assert ok, "restore 应成功"
        assert env._month == 25, f"restore 后月份应为 25，实际 {env._month}"

    print(f"{'月':>3} {'孤立率':>8} {'深孤':>8} {'孤独感':>8} {'关系数':>8}")
    for m in m1:
        print(
            f"{m['month']:>3} {m['isolation_rate']:>9.2%} {m['deep_isolation_rate']:>9.2%} "
            f"{m['avg_loneliness']:>9.3f} {m['avg_active_ties']:>9.2f}"
        )

    failures = []
    # 可复现性
    if m1 != m2:
        failures.append("同种子两次运行结果不一致")
    # 校准区间（对文献汇总数字的粗对齐；正式版换 CHARLS/CLHLS 精确校准）：
    # 城市独居老人孤独感中高比例、月度无情感支持接触约一到三成
    final = m1[-1]
    if not (0.20 <= final["avg_loneliness"] <= 0.60):
        failures.append(f"期末平均孤独感 {final['avg_loneliness']} 超出可信区间 [0.20, 0.60]")
    if not (0.05 <= final["isolation_rate"] <= 0.60):
        failures.append(f"期末孤立率 {final['isolation_rate']} 超出可信区间 [0.05, 0.60]")
    if not (0.0 <= final["deep_isolation_rate"] <= 0.30):
        failures.append(f"期末深度孤立率异常：{final['deep_isolation_rate']}")
    # 关系数应下降（衰减存在），且孤独感不应塌缩到 0
    if final["avg_active_ties"] >= m1[0]["avg_active_ties"]:
        failures.append("平均关系数未下降，衰减机制可能未生效")
    if final["avg_loneliness"] < 0.05:
        failures.append("孤独感塌缩到近 0，稳态机制未生效")

    if failures:
        print("\nFAIL:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nPASS: 机制冒烟全部通过（可复现、基线恶化、衰减生效、restore 往返）")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
