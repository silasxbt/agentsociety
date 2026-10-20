#!/usr/bin/env python3
"""环境动力学回归：默认参数下的逐月指标与期末状态必须与基准快照逐位一致。

用途：改动 ElderSupportEnv 的实现（如参数外置）后，确认旧配置的结果不变。
覆盖规则层老人与焦点老人工具中的随机分支（每月按固定顺序调用工具），
四种条件 × 5 个种子 × 24 个月，干预窗 7–18。

用法：
  python tests/regress_dynamics.py --write   # 由当前实现生成基准
  python tests/regress_dynamics.py           # 与基准比对，不一致则退出码 1
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "regression-no-llm")
os.environ.setdefault("AGENTSOCIETY_LLM_API_BASE", "http://127.0.0.1:9")
os.environ.setdefault("MEM0_TELEMETRY", "False")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

EXP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = EXP_DIR.parents[2]
sys.path.insert(0, str(REPO_ROOT / "custom" / "envs"))
sys.path.insert(0, str(EXP_DIR / "init"))

from elder_support_env import ElderSupportEnv  # noqa: E402
from gen_profiles import gen_elder  # noqa: E402

GOLDEN = EXP_DIR / "tests" / "regress_dynamics_golden.json"
SEEDS = [1, 2, 3, 4, 5]
CONDITIONS = ["none", "casework", "timebank", "platform"]
MONTHS = 24
N_ELDERS = 20
N_FOCAL = 6


async def _drive_focal(env: ElderSupportEnv, aid: int, month: int) -> None:
    e = env._elders[aid]
    names = sorted(e["ties"])
    family = sorted(n for n, t in e["ties"].items() if t["kind"] == "family")
    others = sorted(n for n, t in e["ties"].items() if t["kind"] != "family")
    pattern = (aid + month) % 4
    if pattern == 0 and family:
        await env.call_family(aid, family[0], "回归测试")
    elif pattern == 1 and others:
        await env.visit_neighbor(aid, others[0], "回归测试")
    elif pattern == 2 and names:
        help_type = "emotional" if month % 2 else "instrumental"
        await env.seek_help(aid, names[-1], help_type, "回归测试")
    elif pattern == 3:
        await env.join_activity(aid, "棋牌", "回归测试")
    else:
        await env.stay_home(aid, "回归测试")


async def run_once(seed: int, cond: str) -> dict:
    rng = random.Random(seed)
    elders = [gen_elder(rng, i + 1, focal=i < N_FOCAL) for i in range(N_ELDERS)]
    iv = None
    if cond != "none":
        iv = {"type": cond, "start_month": 7, "end_month": 18, "params": {}}
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / "ws"
        env = ElderSupportEnv(elders=elders, seed=seed, decay_rate=0.06, intervention=iv)
        env._bind_workspace(ws)
        t = datetime(2026, 1, 1, 8)
        for tick in range(MONTHS + 1):
            await env.step(tick, t)
            t += timedelta(days=30)
            if tick < MONTHS:
                for aid in range(1, N_FOCAL + 1):
                    await _drive_focal(env, aid, env._month)
        await env.to_workspace()
        metrics = (ws / "state" / "metrics.jsonl").read_text(encoding="utf-8")
        decisions = (ws / "state" / "decisions.jsonl").read_text(encoding="utf-8")
        state = json.loads((ws / "state" / "ENV_STATE.json").read_text(encoding="utf-8"))
    state.pop("dynamics", None)
    canon = json.dumps(
        {"metrics": metrics, "decisions": decisions, "elders": state["elders"],
         "pairs": state["timebank_pairs"], "credits": state["timebank_credits"],
         "rng_state": state["rng_state"]},
        ensure_ascii=False, sort_keys=True,
    )
    last = json.loads(metrics.strip().splitlines()[-1])
    return {"sha256": hashlib.sha256(canon.encode("utf-8")).hexdigest(),
            "final_isolation_rate": last["isolation_rate"],
            "final_avg_loneliness": last["avg_loneliness"]}


async def collect() -> dict:
    return {f"{c}_s{s}": await run_once(s, c) for c in CONDITIONS for s in SEEDS}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="由当前实现生成基准快照")
    args = ap.parse_args()
    result = asyncio.run(collect())
    if args.write:
        GOLDEN.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {GOLDEN} ({len(result)} runs)")
        return 0
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    bad = [k for k in golden if golden[k]["sha256"] != result.get(k, {}).get("sha256")]
    for k in bad:
        print(f"MISMATCH {k}: golden {golden[k]} vs now {result.get(k)}")
    print(f"{len(golden) - len(bad)}/{len(golden)} runs identical")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
