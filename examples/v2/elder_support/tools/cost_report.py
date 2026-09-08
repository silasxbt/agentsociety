#!/usr/bin/env python3
"""真实成本说明：从 trace 逐 run 统计实测 LLM 调用数与错误数，
按公开定价与文档化的 token 假设估算成本。

口径（写死并随表输出，不得事后调整）：
- 调用数：trace llm.completion span 实测（含失败重试后放弃的 span）。
- token/调用：3500 输入 + 450 输出（baseline12 实测均值，见部署备忘）。
  trace 未记录逐调用 token，故这是文档化假设而非实测。
- 单价：GPT 5.6 SOL 官方 $4/M 输入、$20/M 输出（标准档 ≤272K）。

输出：tests/cost_report.json + 终端表。含无效 run 的沉没成本——真实成本
说明必须包含失败的钱，不只报有效 run。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]
IN_TOK, OUT_TOK = 3500, 450
IN_PRICE, OUT_PRICE = 4.0, 20.0  # $/M tokens
COST_PER_CALL = (IN_TOK * IN_PRICE + OUT_TOK * OUT_PRICE) / 1e6


def run_stats(d: Path) -> dict | None:
    tdir = d / "trace"
    if not tdir.is_dir():
        return None
    tot = err = 0
    for f in tdir.glob("trace_*.jsonl"):
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                s = json.loads(line)
            except json.JSONDecodeError:
                continue
            if s.get("name") != "llm.completion":
                continue
            tot += 1
            if s.get("status", {}).get("code") == "error":
                err += 1
    if tot == 0:
        return None
    status = "valid" if (d / "DONE").is_file() else (
        "invalid" if (d / "INVALID").is_file() else "pending")
    return {"run": d.name, "status": status, "llm_calls": tot, "llm_errors": err,
            "est_cost_usd": round(tot * COST_PER_CALL, 2)}


def main() -> int:
    batch = EXP / "tmp" / "batch"
    rows = []
    for d in sorted(batch.iterdir()):
        if not d.is_dir():
            continue
        r = run_stats(d)
        if r:
            rows.append(r)
    by = {"valid": 0.0, "invalid": 0.0, "pending": 0.0}
    calls = {"valid": 0, "invalid": 0, "pending": 0}
    for r in rows:
        key = "invalid" if ".invalid-" in r["run"] else r["status"]
        r["bucket"] = key
        by[key] += r["est_cost_usd"]
        calls[key] += r["llm_calls"]
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "assumptions": {"tokens_per_call": [IN_TOK, OUT_TOK],
                        "price_per_mtok": [IN_PRICE, OUT_PRICE],
                        "cost_per_call_usd": round(COST_PER_CALL, 5),
                        "note": "调用数为 trace 实测；token 为文档化假设（trace 未记录逐调用用量）"},
        "runs": rows,
        "totals": {k: {"est_cost_usd": round(by[k], 2), "llm_calls": calls[k]}
                   for k in by},
        "grand_total_usd": round(sum(by.values()), 2),
        "waste_share": round(by["invalid"] / max(sum(by.values()), 1e-9), 3),
    }
    p = EXP / "tests" / "cost_report.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{'run':<42}{'状态':<10}{'调用':>7}{'错误':>6}{'估算$':>8}")
    for r in rows:
        print(f"{r['run']:<42}{r['bucket']:<10}{r['llm_calls']:>7}{r['llm_errors']:>6}"
              f"{r['est_cost_usd']:>8.2f}")
    print(f"\n合计 ${out['grand_total_usd']}（有效 ${by['valid']:.2f} / "
          f"无效沉没 ${by['invalid']:.2f} / 进行中 ${by['pending']:.2f}；"
          f"沉没占比 {out['waste_share']*100:.1f}%）")
    print(f"已写 {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
