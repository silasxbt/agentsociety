#!/usr/bin/env python3
"""规则层 post_persist 扫描：时间银行撤出后结对延续概率 → 撤出反弹（不耗 LLM）。

目的：为论文中「post_persist 扫描 0.3–0.7 方向不变」提供实际证据文件，
并加入 post_persist=0（完全不延续）与 1.0（完全延续）两个端点作为对照：
若 0 时 timebank 的反弹与 casework 同量级，则「结构性互助更可持续」
在规则层完全由该参数决定。

用法：
  AGENTSOCIETY_LLM_API_KEY=dummy AGENTSOCIETY_LLM_API_BASE=https://tokenflux.dev/v1 \
    <runtime-venv-python> tests/scan_post_persist.py
输出：tests/scan_post_persist_result.json
"""
from __future__ import annotations
import asyncio, json, statistics, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scan_decay_outcomes import run_once, summarize, IV_START, IV_END, MONTHS, N_ELDERS  # noqa: E402

SEEDS = list(range(1, 21))
PP_VALUES = [0.0, 0.3, 0.5, 0.7, 1.0]
DECAY = 0.06

async def main() -> int:
    base, cw = {}, {}
    for s in SEEDS:
        base[s] = summarize(await run_once(s, DECAY, "none", params={}))
        cw[s] = summarize(await run_once(s, DECAY, "casework", params={}))
    def reb(x): return x["post_isolation_rate"] - x["iv_isolation_rate"]
    def agg(vals): return {"mean": round(statistics.mean(vals), 4),
                           "sd": round(statistics.stdev(vals), 4)}
    out = {"months": MONTHS, "iv_window": [IV_START, IV_END], "n_elders": N_ELDERS,
           "seeds": SEEDS, "decay": DECAY,
           "note": "全部老人为规则层（无 LLM）；反弹=撤出期−干预期孤立率；配对=同 seed 减 none",
           "none": {"iv": agg([base[s]["iv_isolation_rate"] for s in SEEDS]),
                    "post": agg([base[s]["post_isolation_rate"] for s in SEEDS]),
                    "reb": agg([reb(base[s]) for s in SEEDS])},
           "casework": {"iv": agg([cw[s]["iv_isolation_rate"] for s in SEEDS]),
                        "post": agg([cw[s]["post_isolation_rate"] for s in SEEDS]),
                        "reb": agg([reb(cw[s]) for s in SEEDS]),
                        "paired_reb": agg([reb(cw[s]) - reb(base[s]) for s in SEEDS])},
           "timebank": {}}
    for pp in PP_VALUES:
        tb = {}
        for s in SEEDS:
            tb[s] = summarize(await run_once(s, DECAY, "timebank", params={"post_persist": pp}))
        out["timebank"][f"pp{pp}"] = {
            "post_persist": pp,
            "iv": agg([tb[s]["iv_isolation_rate"] for s in SEEDS]),
            "post": agg([tb[s]["post_isolation_rate"] for s in SEEDS]),
            "reb": agg([reb(tb[s]) for s in SEEDS]),
            "paired_reb": agg([reb(tb[s]) - reb(base[s]) for s in SEEDS]),
            "n_reb_lt_casework": sum(1 for s in SEEDS if reb(tb[s]) < reb(cw[s])),
        }
        print(f"post_persist={pp}: iv {out['timebank'][f'pp{pp}']['iv']['mean']:.3f}  "
              f"post {out['timebank'][f'pp{pp}']['post']['mean']:.3f}  "
              f"reb {out['timebank'][f'pp{pp}']['reb']['mean']:+.4f}±{out['timebank'][f'pp{pp}']['reb']['sd']:.4f}  "
              f"paired {out['timebank'][f'pp{pp}']['paired_reb']['mean']:+.4f}  "
              f"reb<casework in {out['timebank'][f'pp{pp}']['n_reb_lt_casework']}/{len(SEEDS)} seeds")
    print(f"none: iv {out['none']['iv']['mean']:.3f} post {out['none']['post']['mean']:.3f} reb {out['none']['reb']['mean']:+.4f}")
    print(f"casework: iv {out['casework']['iv']['mean']:.3f} post {out['casework']['post']['mean']:.3f} "
          f"reb {out['casework']['reb']['mean']:+.4f}±{out['casework']['reb']['sd']:.4f} paired {out['casework']['paired_reb']['mean']:+.4f}")
    dest = Path(__file__).with_name("scan_post_persist_result.json")
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"结果已写入 {dest}")
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
