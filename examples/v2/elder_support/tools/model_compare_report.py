#!/usr/bin/env python3
"""双模型（gpt-5.6-sol vs gpt-6-astra）敏感性对比报告（MODEL_COMPARE.md 的分析步骤）。

sol 臂读主批次 tmp/batch/{none,casework}_s1；新模型臂读
tmp/model_compare/<slug>/{none,casework}_s1（须有 DONE 且无 INVALID）。
输出：每模型 casework−none 配对差（iso_iv / iso_post / iso_rebound）
+ 每月孤立率轨迹，写 tests/model_compare_report.json 并打印表格。
窗口与主批次 compare_conditions.py 一致：iv=7–18，post=19–月末。
单 seed，仅描述性比较；不做显著性 / 排名声称。
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_conditions import validate  # 复用主批次静默率/效度判定

ROOT = Path(__file__).resolve().parent.parent
IV_START, IV_END = 7, 18
MONTHS = 24
CONDITIONS = ["none", "casework"]


def load_metrics(run_dir: Path) -> list[dict] | None:
    f = run_dir / "env" / "ElderSupportEnv" / "state" / "metrics.jsonl"
    if not f.is_file():
        return None
    rows = [json.loads(x) for x in f.read_text().splitlines() if x.strip()]
    return rows or None


def avg(rows: list[dict], key: str, lo: int, hi: int) -> float | None:
    vals = [r[key] for r in rows if lo <= r["month"] <= hi and key in r]
    return round(sum(vals) / len(vals), 6) if vals else None


def arm_stats(run_dir: Path) -> dict | None:
    rows = load_metrics(run_dir)
    if not rows:
        return None
    iso_iv = avg(rows, "isolation_rate", IV_START, IV_END)
    iso_post = avg(rows, "isolation_rate", 19, MONTHS)
    v = validate(run_dir)
    return {
        "silence_rate": v["silence_rate"],
        "valid": v["valid"],
        "invalid_reasons": v["reasons"],
        "run": str(run_dir.relative_to(ROOT)),
        "months": len(rows),
        "iso_iv": iso_iv,
        "iso_post": iso_post,
        "iso_rebound": round(iso_post - iso_iv, 6)
        if iso_iv is not None and iso_post is not None
        else None,
        "trajectory": {r["month"]: round(r["isolation_rate"], 4) for r in rows},
    }


def collect_model(label: str, base: Path, *, require_done: bool) -> dict | None:
    arms = {}
    for cond in CONDITIONS:
        d = base / f"{cond}_s1"
        if require_done and not (d / "DONE").is_file():
            return None
        s = arm_stats(d)
        if not s:
            return None
        arms[cond] = s
    paired = {
        k: round(arms["casework"][k] - arms["none"][k], 6)
        for k in ("iso_iv", "iso_post", "iso_rebound")
        if arms["casework"][k] is not None and arms["none"][k] is not None
    }
    manifest = {}
    mf = base / "casework_s1" / "manifest.json"
    if mf.is_file():
        m = json.loads(mf.read_text())
        manifest = {k: m.get(k) for k in ("model", "api_base", "provider", "reasoning_effort")}
    return {"label": label, "arms": arms, "paired_casework_minus_none": paired, "manifest": manifest}


def main() -> None:
    models: list[dict] = []
    sol = collect_model("gpt-5.6-sol (主批次)", ROOT / "tmp" / "batch", require_done=True)
    if sol:
        models.append(sol)
    mc_root = ROOT / "tmp" / "model_compare"
    if mc_root.is_dir():
        for d in sorted(mc_root.iterdir()):
            if d.is_dir():
                m = collect_model(d.name, d, require_done=True)
                if m:
                    models.append(m)
                else:
                    print(f"（跳过 {d.name}：run 未完成 / INVALID / 缺指标）")

    out = {
        "windows": {"intervention": [IV_START, IV_END], "post": [19, MONTHS]},
        "note": "单 seed 描述性比较；判读标准=两模型下 casework 是否同向呈现「干预期压低 + 撤出后反弹」；silence_rate 为焦点老人无决策 agent-月占比（门槛 10%）",
        "models": models,
    }
    dest = ROOT / "tests" / "model_compare_report.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"已写 {dest}\n")

    hdr = f"{'模型':<28}{'Δiso_iv':>10}{'Δiso_post':>11}{'Δiso_reb':>10}  同向?"
    print(hdr)
    print("-" * len(hdr))
    for m in models:
        p = m["paired_casework_minus_none"]
        same = "✓" if p.get("iso_iv", 0) < 0 and p.get("iso_rebound", 0) > 0 else "✗"
        sil = " / ".join(f"{c}:{m['arms'][c]['silence_rate']:.1%}{'' if m['arms'][c]['valid'] else '(INVALID)'}" for c in CONDITIONS)
        print(
            f"{m['label']:<28}{p.get('iso_iv', float('nan')):>10.4f}"
            f"{p.get('iso_post', float('nan')):>11.4f}"
            f"{p.get('iso_rebound', float('nan')):>10.4f}  {same}"
        )
        print(f"  静默率 {sil}")
    print("\n同向判据：Δiso_iv < 0（干预期 casework 压低孤立）且 Δiso_reb > 0（撤出后反弹更大）。")


if __name__ == "__main__":
    main()
