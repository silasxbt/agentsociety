"""ElderSupportEnv 参数外置：覆盖生效、未知键报错、旧状态文件可恢复。

用法（examples/v2/elder_support 目录）：
  ../../../.venv/bin/python -m pytest tests/test_env_dynamics.py -q
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

os.environ.setdefault("AGENTSOCIETY_LLM_API_KEY", "test-no-llm")
os.environ.setdefault("AGENTSOCIETY_LLM_API_BASE", "http://127.0.0.1:9")
os.environ.setdefault("MEM0_TELEMETRY", "False")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

EXP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = EXP_DIR.parents[2]
sys.path.insert(0, str(REPO_ROOT / "custom" / "envs"))
sys.path.insert(0, str(EXP_DIR / "init"))

from elder_support_env import DEFAULT_DYNAMICS, ElderSupportEnv  # noqa: E402
from gen_profiles import gen_elder  # noqa: E402


def _elders(seed: int = 1, n: int = 20) -> list[dict]:
    rng = random.Random(seed)
    return [gen_elder(rng, i + 1, focal=i < 6) for i in range(n)]


async def _run(env: ElderSupportEnv, ws: Path, months: int) -> list[dict]:
    env._bind_workspace(ws)
    t = datetime(2026, 1, 1, 8)
    for tick in range(months + 1):
        await env.step(tick, t)
        t += timedelta(days=30)
    await env.to_workspace()
    lines = (ws / "state" / "metrics.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(x) for x in lines if x.strip()]


def test_unknown_dynamics_key_rejected():
    with pytest.raises(ValueError):
        ElderSupportEnv(elders=_elders(), dynamics={"no_such_param": 1.0})


def test_unknown_intervention_param_rejected():
    iv = {"type": "casework", "start_month": 7, "end_month": 18, "params": {"casload": 8}}
    with pytest.raises(ValueError):
        ElderSupportEnv(elders=_elders(), intervention=iv)


def test_dynamics_override_takes_effect(tmp_path):
    base = asyncio.run(_run(ElderSupportEnv(elders=_elders(), seed=1), tmp_path / "a", 12))
    never_isolated = asyncio.run(
        _run(
            ElderSupportEnv(elders=_elders(), seed=1, dynamics={"deep_isolation_months": 10**6}),
            tmp_path / "b",
            12,
        )
    )
    assert max(m["deep_isolation_rate"] for m in base) > 0
    assert all(m["deep_isolation_rate"] == 0 for m in never_isolated)


def test_restore_old_state_without_dynamics(tmp_path):
    ws = tmp_path / "ws"
    env = ElderSupportEnv(elders=_elders(), seed=3)
    asyncio.run(_run(env, ws, 3))
    state_path = ws / "state" / "ENV_STATE.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["dynamics"] == DEFAULT_DYNAMICS
    state.pop("dynamics")
    state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    restored = ElderSupportEnv(elders=_elders(), seed=3, dynamics={"lonely_relaxation": 0.9})
    assert asyncio.run(restored.restore(ws))
    assert restored._dyn == DEFAULT_DYNAMICS


def test_saved_dynamics_survive_restore(tmp_path):
    ws = tmp_path / "ws"
    env = ElderSupportEnv(elders=_elders(), seed=3, dynamics={"help_base": 0.3})
    asyncio.run(_run(env, ws, 2))
    restored = ElderSupportEnv(elders=_elders(), seed=3)
    assert asyncio.run(restored.restore(ws))
    assert restored._dyn["help_base"] == 0.3
