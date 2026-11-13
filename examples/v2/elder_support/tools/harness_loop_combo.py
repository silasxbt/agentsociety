#!/usr/bin/env python3
"""Harness 闭环（组合与顺序）：LLM 设计师在预注册空间内提出社工探访与互助结对的
排期组合，规则层确定性评估，全轮次落盘（不动正式批次与组合扫描）。

== 预注册（2026-11-13 运行前写定并提交）=========================================
目标函数：最小化 overall_isolation_rate（第 1–30 月均值，20 种子平均），
  与 tests/scan_combo.py 的 overall 窗口一致，可直接与其 A–F 组比较。
搜索空间（硬约束）：
  社工探访 casework：start ∈ [3, 18]，duration ∈ [0, 12]（0 表示不做）；
  互助结对 timebank：start ∈ [3, 18]，duration ∈ [0, 12]；
  每个成分 start + duration − 1 ≤ 24；两者 duration 至少一个 ≥ 1。
资源帽：两种服务的服务月数之和 ≤ 12，与 scan_combo 中 B、C、D、F 的投入相同
  （E 同时做 24 服务月，超出资源帽，不在空间内）。
固定设定：handover_boost = 0（不假设任何“社工开路、互助接续”机制），
  post_persist = 0.5（默认），校准画像，默认动力学，decay = 0.06。
迭代预算：6 轮；连续 3 轮无改进提前停止。
证据供给：设计师每轮可见 scan_combo（校准画像、post_persist = 0.5、b = 0）
  的 A、B、C、D、F 组 overall 结果，以及此前闭环轮次（候选、理由、得分）。
已评估组合：B、C、D、F 的排期视为已试；设计师重复时重询一次，仍重复记 duplicate 跳过。
诚实性规则：全部轮次落盘并报告（harness_loop_combo_log.jsonl），不只报最优。
角色边界：LLM 只提案，评估由确定性规则层完成。b = 0 下任何“顺序优势”只来自
  现有规则（撤出后留下的是哪种服务），不是对接续机制的证据。
成本：设计师调用 ≤ 12 次（6 轮，每轮至多重询一次）；评估零 LLM 调用。

用法：
  AGENTSOCIETY_LLM_API_KEY=... AGENTSOCIETY_LLM_API_BASE=https://tokenflux.dev/v1 \\
    <runtime-venv-python> tools/harness_loop_combo.py
输出：tests/harness_loop_combo_log.jsonl（逐轮）+ tests/harness_loop_combo_result.json
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import statistics
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXP_DIR / "tests"))

import scan_combo as sc  # noqa: E402  复用组合扫描的 runner 与窗口口径
from gen_profiles import set_profile_source  # noqa: E402

SPACE = {"start": [3, 18], "duration": [0, 12], "end_max": 24, "service_months_max": 12}
MAX_ITER = 6
PATIENCE = 3
SEEDS = sc.SEEDS
PROFILES = "calibrated"
POST_PERSIST = 0.5
MODEL = os.environ.get("AGENTSOCIETY_LLM_MODEL", "gpt-5.6-sol")
API_BASE = os.environ.get("AGENTSOCIETY_LLM_API_BASE", "https://tokenflux.dev/v1")
LOG_PATH = EXP_DIR / "tests" / "harness_loop_combo_log.jsonl"
RESULT_PATH = EXP_DIR / "tests" / "harness_loop_combo_result.json"
GRID_PATH = EXP_DIR / "tests" / "scan_combo_result_calibrated.json"
# scan_combo 中满足资源帽的组（b = 0），作为已试排期与参照
GRID_ARMS = {
    "B": {"casework": (7, 12), "timebank": (0, 0)},
    "C": {"casework": (0, 0), "timebank": (7, 12)},
    "D_b0.0": {"casework": (7, 6), "timebank": (13, 6)},
    "F": {"casework": (13, 6), "timebank": (7, 6)},
}


def llm(prompt: str) -> str:
    key = os.environ.get("AGENTSOCIETY_LLM_API_KEY", "")
    if not key:
        raise SystemExit("需要 AGENTSOCIETY_LLM_API_KEY")
    body = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(
        f"{API_BASE}/chat/completions", data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    last_err: Exception | None = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read())["choices"][0]["message"]["content"]
        except Exception as e:  # noqa: BLE001 网关瞬时错误重试
            last_err = e
            time.sleep(5)
    raise RuntimeError(f"LLM 调用失败：{last_err}")


def parse_proposal(text: str) -> dict | None:
    m = re.search(r"\{[^{}]*\}", text, re.S)
    if not m:
        return None
    try:
        p = json.loads(m.group(0))
        cand = {
            "casework_start": int(p["casework_start"]), "casework_duration": int(p["casework_duration"]),
            "timebank_start": int(p["timebank_start"]), "timebank_duration": int(p["timebank_duration"]),
            "rationale": str(p.get("rationale", ""))[:1200],
        }
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None
    lo_s, hi_s = SPACE["start"]
    lo_d, hi_d = SPACE["duration"]
    total = 0
    for kind in ("casework", "timebank"):
        s, d = cand[f"{kind}_start"], cand[f"{kind}_duration"]
        if not lo_d <= d <= hi_d:
            return None
        if d and (not lo_s <= s <= hi_s or s + d - 1 > SPACE["end_max"]):
            return None
        total += d
    if not 1 <= total <= SPACE["service_months_max"]:
        return None
    return cand


def key_of(c: dict) -> tuple:
    def part(kind: str) -> tuple:
        d = c[f"{kind}_duration"]
        return (c[f"{kind}_start"], d) if d else (0, 0)
    return part("casework") + part("timebank")


def to_intervention(c: dict) -> dict:
    comps = []
    for kind in ("casework", "timebank"):
        s, d = c[f"{kind}_start"], c[f"{kind}_duration"]
        if d:
            comps.append(sc._c(kind, s, s + d - 1, POST_PERSIST))
    comps.sort(key=lambda x: (x["start_month"], x["type"] != "casework"))
    return {"type": "combo", "components": comps, "coupling": {"handover_boost": 0.0}}


async def evaluate(c: dict) -> dict:
    iv = to_intervention(c)
    per_seed = [sc.summarize(await sc.run_once(s, iv)) for s in SEEDS]
    out = {}
    for k in ("overall_isolation_rate", "iv_isolation_rate", "post_isolation_rate", "overall_avg_loneliness"):
        vals = [p[k] for p in per_seed]
        out[k] = {"mean": round(statistics.mean(vals), 5), "sd": round(statistics.stdev(vals), 5)}
    out["intervention"] = iv
    return out


def load_grid() -> dict:
    if not GRID_PATH.is_file():
        raise SystemExit(f"缺少 {GRID_PATH}；先运行 tests/scan_combo.py --profiles calibrated")
    return json.loads(GRID_PATH.read_text(encoding="utf-8"))["by_post_persist"][f"pp{POST_PERSIST}"]["arms"]


def evidence_block(history: list[dict]) -> str:
    arms = load_grid()
    desc = {"A": "不干预", "B": "社工 7–18", "C": "互助 7–18", "D_b0.0": "社工 7–12 → 互助 13–18",
            "F": "互助 7–12 → 社工 13–18", "E_b0.0": "社工 + 互助同时 7–18（24 服务月，超资源帽）"}
    lines = ["已评估组（scan_combo，20 种子，overall = 第 1–30 月平均孤立率，越低越好）："]
    for name, text in desc.items():
        a = arms[name]
        lines.append(f"  {name} {text}: overall={a['overall_isolation_rate']['mean']:.4f} "
                     f"干预期={a['iv_isolation_rate']['mean']:.4f} 撤出后={a['post_isolation_rate']['mean']:.4f}")
    if history:
        lines.append("闭环已试过的候选：")
        for h in history:
            sc_ = h.get("score")
            lines.append(f"  第{h['iter']}轮 {h['candidate']} -> "
                         f"{'未评估：' + h.get('note', '') if sc_ is None else f'overall={sc_:.4f}'}")
    return "\n".join(lines)


async def main() -> int:
    set_profile_source(PROFILES)
    load_grid()
    grid_tried = {key_of({f"{k}_{f}": v for k, (s, d) in arm.items() for f, v in (("start", s), ("duration", d))})
                  for arm in GRID_ARMS.values()}
    history: list[dict] = []
    tried: set[tuple] = set()
    best: dict | None = None
    no_improve = 0
    log_f = LOG_PATH.open("a", encoding="utf-8")

    def record(rec: dict) -> None:
        history.append(rec)
        log_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        log_f.flush()

    for it in range(1, MAX_ITER + 1):
        prompt = f"""你是模拟实验设计师。任务：在约束内提出下一个值得评估的服务排期，
目标是最小化 overall_isolation_rate（第 1-30 月平均孤立率，规则层独居老人支持网络模型，
第 30 月后不再观察）。两种服务：社工探访（专业服务，撤出即停）与互助结对（老人间结对，
撤出后结对以一定概率延续）。

搜索空间（硬约束）：casework_start、timebank_start ∈ 3-18 整数；casework_duration、
timebank_duration ∈ 0-12 整数（0 表示不做该服务）；每种服务 start+duration-1 ≤ 24；
两种服务的 duration 之和为 1-12（资源帽：总共最多 12 个服务月）。
两种服务可以先后、重叠或只做一种。总迭代 {MAX_ITER} 轮，现在是第 {it} 轮。

{evidence_block(history)}

要求：
1. 不要重复上面已评估过的排期。
2. 用一句话说明提案的机制理由。
3. 只输出一个 JSON：{{"casework_start": N, "casework_duration": N, "timebank_start": N, "timebank_duration": N, "rationale": "..."}}"""
        cand = parse_proposal(llm(prompt))
        ts = datetime.now(timezone.utc).isoformat()
        if cand is None:
            record({"iter": it, "ts": ts, "candidate": None, "score": None, "note": "解析失败/越界，跳过"})
            no_improve += 1
            if no_improve >= PATIENCE:
                break
            continue
        if key_of(cand) in tried or key_of(cand) in grid_tried:
            cand2 = parse_proposal(llm(prompt + "\n\n注意：你刚才的提案与已评估排期重复，请换一个。"))
            if cand2 is None or key_of(cand2) in tried or key_of(cand2) in grid_tried:
                record({"iter": it, "ts": ts, "candidate": {k: v for k, v in cand.items() if k != "rationale"},
                        "score": None, "note": "duplicate，按预注册规则跳过评估"})
                no_improve += 1
                if no_improve >= PATIENCE:
                    break
                continue
            cand = cand2
        tried.add(key_of(cand))
        res = await evaluate(cand)
        score = res["overall_isolation_rate"]["mean"]
        rec = {"iter": it, "ts": ts, "candidate": {k: v for k, v in cand.items() if k != "rationale"},
               "rationale": cand["rationale"], "result": res, "score": score}
        improved = best is None or score < best["score"]
        if improved:
            best, no_improve = rec, 0
        else:
            no_improve += 1
        rec["best_so_far"] = best["candidate"]
        record(rec)
        print(f"第{it}轮 {rec['candidate']} overall={score:.4f} {'← 新最优' if improved else ''}")
        if no_improve >= PATIENCE:
            print("连续无改进，按预注册规则提前停止")
            break
    log_f.close()

    arms = load_grid()
    grid_best = min(({"name": n, "overall": arms[n]["overall_isolation_rate"]["mean"]} for n in GRID_ARMS),
                    key=lambda x: x["overall"])
    out = {
        "preregistered": {"objective": "min overall_isolation_rate (months 1-30, 20 seeds)", "space": SPACE,
                          "max_iter": MAX_ITER, "patience": PATIENCE, "seeds": SEEDS, "designer_model": MODEL,
                          "profiles": PROFILES, "post_persist": POST_PERSIST, "handover_boost": 0.0},
        "iterations": history,
        "best": best,
        "grid_best_for_reference": grid_best,
        "designer_calls_upper_bound": 2 * MAX_ITER,
        "caveats": ["规则层机制探索，不进主结果", "LLM 仅提案，评估为确定性规则层",
                    "handover_boost = 0，顺序优势只来自现有规则",
                    f"全部轮次已落盘（{LOG_PATH.name}），无选择性报告"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    RESULT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"闭环最优：{best['candidate'] if best else None} overall={best['score']:.4f}" if best else "无有效评估")
    print(f"资源帽内网格参照最优：{grid_best['name']} overall={grid_best['overall']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
