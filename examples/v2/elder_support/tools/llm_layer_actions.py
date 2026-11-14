#!/usr/bin/env python3
"""LLM 主批次：焦点老人主动联系对象按关系层拆分（只读冻结批次，不调用 LLM）。

== 预注册（2026-11-14 运行前写定并提交）=====================================
数据：tmp/batch 下 comparison.json 判为有效的 11 个 run（旧路由 gpt-5.6-sol 主批次），
  只读 decisions.jsonl、init_config.json、ENV_STATE.json；输出只含聚合数。
主动联系：焦点老人（agent_id > 0）的 call_family、visit_neighbor、seek_help 中带 target 的决策。
关系层判定（按对象名，不按动作名，因为模型会用 call_family 联系邻居）：
  先查该老人在初始配置与最终状态关系账本中的 kind；查不到时按名字前缀：
  “互助伙伴/互助对象”→ timebank，“志愿者”→ volunteer，“社工”→ social_worker，
  “活动认识的”→ activity；仍查不到记 unknown。
  层：family；peer（friend、neighbor）；timebank；volunteer；social_worker；activity；unknown。
指标：每名焦点老人每月主动联系某层的次数，以及其中 deep_talk = True 的次数；
  窗口为干预前 1–6、干预期 7–18、撤出后 19–24；按条件对种子取平均（n = 每条件有效 run 数）。
环境侧：社工联结家庭（casework_link）落在焦点老人身上的次数，按窗口计数。
用途：回答“撤出后 LLM 老人还主动联系哪一层”，尤其是互助结对撤出后是否主动联系伙伴。
解读边界：主批次运行在修复前的路由上；n = 3（platform n = 2），只作描述。

用法（在有完整 tmp/batch 的机器上）：python3 tools/llm_layer_actions.py
输出：tests/llm_layer_actions.json
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]
BATCH = EXP / "tmp" / "batch"
OUT = EXP / "tests" / "llm_layer_actions.json"
WINDOWS = {"pre": (1, 6), "iv": (7, 18), "post": (19, 24)}
LAYERS = ("family", "peer", "timebank", "volunteer", "social_worker", "activity", "unknown")
KIND_TO_LAYER = {"family": "family", "friend": "peer", "neighbor": "peer", "timebank": "timebank",
                 "volunteer": "volunteer", "social_worker": "social_worker"}
PREFIXES = (("互助伙伴", "timebank"), ("互助对象", "timebank"), ("志愿者", "volunteer"),
            ("社工", "social_worker"), ("活动认识的", "activity"))


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def kind_maps(run: Path) -> dict[int, dict[str, str]]:
    maps: dict[int, dict[str, str]] = defaultdict(dict)
    cfg = json.loads((run / "init_config.json").read_text(encoding="utf-8"))
    for e in cfg["env_modules"][0]["kwargs"]["elders"]:
        for c in e.get("children", []):
            maps[int(e["id"])][c["name"]] = "family"
        for t in e.get("ties", []):
            maps[int(e["id"])][t["name"]] = t.get("kind", "neighbor")
    state = run / "env" / "ElderSupportEnv" / "state" / "ENV_STATE.json"
    if state.is_file():
        for eid, e in json.loads(state.read_text(encoding="utf-8"))["elders"].items():
            for name, t in e["ties"].items():
                maps[int(eid)].setdefault(name, t["kind"])
    return maps


def layer_of(name: str, kinds: dict[str, str]) -> str:
    if name in kinds:
        return KIND_TO_LAYER.get(kinds[name], "unknown")
    for prefix, layer in PREFIXES:
        if name.startswith(prefix):
            return layer
    return "unknown"


def window_of(month: int) -> str | None:
    return next((w for w, (lo, hi) in WINDOWS.items() if lo <= month <= hi), None)


def run_summary(run: Path) -> dict:
    kinds = kind_maps(run)
    rows = load_jsonl(run / "env" / "ElderSupportEnv" / "state" / "decisions.jsonl")
    focal = sorted({r["agent_id"] for r in rows if r.get("agent_id", 0) > 0})
    counts = {w: {layer: {"contacts": 0, "deep": 0} for layer in LAYERS} for w in WINDOWS}
    links = {w: 0 for w in WINDOWS}
    for r in rows:
        w = window_of(int(r.get("month", -1)))
        if w is None:
            continue
        if r.get("agent_id", 0) > 0 and r.get("action") in ("call_family", "visit_neighbor", "seek_help") \
                and r.get("target"):
            layer = layer_of(str(r["target"]), kinds.get(int(r["agent_id"]), {}))
            counts[w][layer]["contacts"] += 1
            counts[w][layer]["deep"] += bool(r.get("deep_talk"))
        elif r.get("action") == "casework_link" and r.get("elder") in focal:
            links[w] += 1
    out = {"n_focal": len(focal), "per_elder_month": {}, "casework_link_per_focal_month": {}}
    for w, (lo, hi) in WINDOWS.items():
        denom = len(focal) * (hi - lo + 1)
        out["per_elder_month"][w] = {layer: {k: round(v / denom, 5) for k, v in c.items()}
                                     for layer, c in counts[w].items()}
        out["casework_link_per_focal_month"][w] = round(links[w] / denom, 5)
    return out


def main() -> int:
    comp = json.loads((BATCH / "comparison.json").read_text(encoding="utf-8"))
    invalid = {r["run"] for r in comp.get("invalid_runs", [])}
    runs = sorted(p for p in BATCH.iterdir() if p.is_dir() and p.name.split("_s")[0] in
                  ("none", "casework", "timebank", "platform") and "." not in p.name and p.name not in invalid)
    per_run = {p.name: run_summary(p) for p in runs}
    by_cond: dict = {}
    for cond in ("none", "casework", "timebank", "platform"):
        names = [n for n in per_run if n.startswith(cond + "_s")]
        agg = {}
        for w in WINDOWS:
            agg[w] = {layer: {k: round(sum(per_run[n]["per_elder_month"][w][layer][k] for n in names) / len(names), 5)
                              for k in ("contacts", "deep")} for layer in LAYERS}
        links = {w: round(sum(per_run[n]["casework_link_per_focal_month"][w] for n in names) / len(names), 5)
                 for w in WINDOWS}
        by_cond[cond] = {"runs": names, "per_elder_month": agg, "casework_link_per_focal_month": links}
    OUT.write_text(json.dumps({"preregistered": {"windows": WINDOWS, "layers": LAYERS, "batch": "tmp/batch (old router, Sol)"},
                               "by_condition": by_cond, "per_run": per_run}, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    for cond, v in by_cond.items():
        print(cond, len(v["runs"]), {w: {k: v["per_elder_month"][w][k]["contacts"] for k in ("family", "peer", "timebank", "volunteer", "social_worker", "unknown")} for w in WINDOWS})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
