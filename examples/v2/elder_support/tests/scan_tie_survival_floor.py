#!/usr/bin/env python3
"""decay_rate 扫描下的关系存活率地板（规则层，无 LLM）。

复现 data_pipeline/out/references_verified.md 中"存活率地板 ≈ 46%"的表：
decay 再大，有固定联系频率的关系每月刷新 last_contact_month、永不衰减，
存活率触底后进入平台。输出 tests/tie_survival_floor_result.json。

用法：AGENTSOCIETY_LLM_API_KEY=dummy AGENTSOCIETY_LLM_API_BASE=https://tokenflux.dev/v1 \
  <runtime-venv-python> tests/scan_tie_survival_floor.py
"""
from __future__ import annotations
import asyncio, json
from pathlib import Path
from measure_tie_survival import measure

DECAYS = [0.06, 0.10, 0.15, 0.20, 0.30, 0.40]
MONTHS = 48

async def main() -> int:
    out = {"months": MONTHS, "num_elders": 50, "seed": 7, "rows": {}}
    for d in DECAYS:
        r = await measure(num=50, months=MONTHS, seed=7, decay=d)
        c = dict(r["curve"])
        out["rows"][str(d)] = {f"y{y}": c[y * 12] for y in range(1, MONTHS // 12 + 1)}
        out["rows"][str(d)]["min"] = min(c.values())
        print(d, {k: round(v, 3) for k, v in out["rows"][str(d)].items()})
    out["floor"] = min(v["min"] for v in out["rows"].values())
    out["floor_decay"] = str(DECAYS[-1])
    Path(__file__).with_name("tie_survival_floor_result.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("floor", round(out["floor"], 4))
    return 0

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
