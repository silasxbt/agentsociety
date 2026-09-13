# -*- coding: utf-8 -*-
"""把宏观孤立率/孤独感拆成 LLM 焦点老人（6 名）与规则层老人（14 名）两部分。

数据源：每个有效 run 的 replay/elder_support_agent_state.*.jsonl（逐老人月度状态，
由环境模块每 step 落盘），focal 标记取自 init_config.json。
输出 tests/layer_decomposition.json，供 gen_paper_numbers.py 与论文引用。
只做描述性拆分，不做检验。
"""
from __future__ import annotations
import json, re, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "tmp" / "batch"
FORMAL = re.compile(r"^(none|casework|timebank|platform)_s(\d+)$")
IV = (7, 18); POST = (19, 24)

def load_run(d: Path):
    cfg = json.loads((d / "init_config.json").read_text(encoding="utf-8"))
    elders = cfg["env_modules"][0]["kwargs"]["elders"]
    focal = {e["id"] for e in elders if e.get("focal")}
    rows = []
    for f in sorted((d / "replay").glob("elder_support_agent_state.*.jsonl")):
        rows += [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    ts = sorted({r["t"] for r in rows})
    month_of = {t: i for i, t in enumerate(ts)}  # 第 0 个快照 = 月 0
    by_month = defaultdict(list)
    for r in rows:
        by_month[month_of[r["t"]]].append(r)
    traj = {}
    for m, rs in sorted(by_month.items()):
        g = {"focal": [r for r in rs if r["agent_id"] in focal],
             "rule": [r for r in rs if r["agent_id"] not in focal],
             "all": rs}
        traj[m] = {k: {"iso": sum(1 for r in v if r["months_no_emotional"] >= 1) / len(v),
                       "lon": sum(r["loneliness"] for r in v) / len(v),
                       "n": len(v)} for k, v in g.items() if v}
    return traj, len(focal), len(elders) - len(focal)

def win(traj, key, metric, lo, hi):
    v = [traj[m][key][metric] for m in traj if lo <= m <= hi and key in traj[m]]
    return sum(v) / len(v) if v else None

def main():
    out = {"windows": {"iv": IV, "post": POST}, "runs": {}, "by_condition": {}}
    per_cond = defaultdict(list)
    for d in sorted(BATCH.iterdir()):
        if not (d.is_dir() and FORMAL.match(d.name) and (d / "DONE").is_file() and not (d / "INVALID").exists()):
            continue
        traj, nf, nr = load_run(d)
        cond = FORMAL.match(d.name).group(1)
        rec = {"n_focal": nf, "n_rule": nr}
        for key in ("focal", "rule", "all"):
            for metric in ("iso", "lon"):
                rec[f"{key}_{metric}_iv"] = win(traj, key, metric, *IV)
                rec[f"{key}_{metric}_post"] = win(traj, key, metric, *POST)
        rec["trajectory_iso"] = {m: {k: round(traj[m][k]["iso"], 4) for k in traj[m]} for m in traj}
        out["runs"][d.name] = rec
        per_cond[cond].append(rec)
    for cond, recs in per_cond.items():
        agg = {"n_runs": len(recs)}
        for k in recs[0]:
            if k.startswith(("focal_", "rule_", "all_")) and not k.startswith("trajectory"):
                vals = [r[k] for r in recs if r[k] is not None]
                agg[k] = round(sum(vals) / len(vals), 4) if vals else None
        # 焦点层在宏观孤立率中的份额：focal 贡献 = 6/20 * focal_iso
        nf, nr = recs[0]["n_focal"], recs[0]["n_rule"]
        for w in ("iv", "post"):
            fi, ri = agg[f"focal_iso_{w}"], agg[f"rule_iso_{w}"]
            tot = (nf * fi + nr * ri) / (nf + nr)
            agg[f"focal_share_of_iso_{w}"] = round(nf * fi / (nf + nr) / tot, 4) if tot else None
        out["by_condition"][cond] = agg
    # 配对差（casework - none，按 seed）
    def seed(n): return FORMAL.match(n).group(2)
    for cond in ("casework", "timebank", "platform"):
        diffs = defaultdict(list)
        for n, r in out["runs"].items():
            if FORMAL.match(n).group(1) != cond: continue
            base = out["runs"].get(f"none_s{seed(n)}")
            if not base: continue
            for key in ("focal", "rule"):
                diffs[f"{key}_iso_iv"].append(r[f"{key}_iso_iv"] - base[f"{key}_iso_iv"])
                diffs[f"{key}_iso_reb"].append((r[f"{key}_iso_post"] - r[f"{key}_iso_iv"]) - (base[f"{key}_iso_post"] - base[f"{key}_iso_iv"]))
        out["by_condition"][cond]["paired_vs_none"] = {k: round(sum(v) / len(v), 4) for k, v in diffs.items()}
        out["by_condition"][cond]["paired_n"] = len(diffs["focal_iso_iv"])
    dest = ROOT / "tests" / "layer_decomposition.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已写 {dest}")
    print(f"{'条件':10s} {'n':>2s} | 焦点iso iv/post | 规则iso iv/post | 焦点份额iv | 焦点lon iv/post | 规则lon iv/post")
    for c in ("none", "casework", "timebank", "platform"):
        a = out["by_condition"].get(c)
        if not a: continue
        print(f"{c:10s} {a['n_runs']:>2d} | {a['focal_iso_iv']*100:5.1f}/{a['focal_iso_post']*100:5.1f}   | {a['rule_iso_iv']*100:5.1f}/{a['rule_iso_post']*100:5.1f}   | {a['focal_share_of_iso_iv']*100:5.1f}%   | {a['focal_lon_iv']:.3f}/{a['focal_lon_post']:.3f}   | {a['rule_lon_iv']:.3f}/{a['rule_lon_post']:.3f}")
        if "paired_vs_none" in a: print("           配对 vs none:", a["paired_vs_none"])

if __name__ == "__main__":
    sys.exit(main())
