#!/usr/bin/env python3
"""聚合各条件的行为签名（求助请求量 / 成功率），供 §5.3 脚注冻结时取精确数值。

数据源：tmp/batch/<cond>_s<seed>/env/ElderSupportEnv/state/metrics.jsonl
仅统计带 DONE 标记的有效 run。输出到 stdout + tests/behavior_signature.json。
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BATCH = ROOT / "tmp" / "batch"
CONDITIONS = ["none", "timebank", "casework", "platform"]


def load_run(run_dir: Path) -> dict | None:
    f = run_dir / "env" / "ElderSupportEnv" / "state" / "metrics.jsonl"
    if not f.is_file():
        return None
    req = ok = 0
    months = 0
    for line in f.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        m = json.loads(line)
        req += m.get("help_requests", 0)
        ok += m.get("help_success", 0)
        months += 1
    return {"requests": req, "success": ok, "months": months}


def main() -> None:
    out: dict[str, dict] = {}
    for cond in CONDITIONS:
        runs = []
        for d in sorted(BATCH.glob(f"{cond}_s[0-9]")):
            if not (d / "DONE").is_file():
                continue
            r = load_run(d)
            if r:
                r["run"] = d.name
                runs.append(r)
        if not runs:
            out[cond] = {"n": 0}
            continue
        total_req = sum(r["requests"] for r in runs)
        total_ok = sum(r["success"] for r in runs)
        out[cond] = {
            "n": len(runs),
            "runs": [r["run"] for r in runs],
            "total_requests": total_req,
            "total_success": total_ok,
            "success_rate": round(total_ok / total_req, 4) if total_req else None,
            "avg_requests_per_run": round(total_req / len(runs), 1),
            "per_run": runs,
        }

    dest = ROOT / "tests" / "behavior_signature.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"已写 {dest}")
    print(f"{'条件':<10}{'runs':>5}{'请求总量':>10}{'成功':>8}{'成功率':>9}{'均请求/run':>12}")
    for cond, v in out.items():
        if v.get("n"):
            sr = f"{v['success_rate']:.1%}" if v["success_rate"] is not None else "-"
            print(
                f"{cond:<10}{v['n']:>5}{v['total_requests']:>10}"
                f"{v['total_success']:>8}{sr:>9}{v['avg_requests_per_run']:>12}"
            )
        else:
            print(f"{cond:<10}{0:>5}  （无有效 run）")


if __name__ == "__main__":
    main()
