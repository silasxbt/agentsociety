#!/usr/bin/env python3
"""Harness 自主闭环：LLM 设计师在预注册空间内迭代提出干预配置，
规则层运行器评估，全过程落盘可审计（不动正式批次）。

== 预注册（运行前写定）=====================================================
目标函数：最小化 overall_isolation_rate（第 1–24 月均值，20 种子平均）。
约束（资源帽，实践对应"预算固定时如何排期"）：duration ≤ 12 个月。
搜索空间：condition ∈ {casework, timebank, platform}；
  iv_start ∈ [3, 12]（整数）；duration ∈ [6, 12]（整数）；iv_end ≤ 24。
迭代预算：6 轮；连续 3 轮无改进提前停止。
证据供给：设计师每轮可见 scan_timing 网格结果 + 此前所有闭环轮次
  （候选、理由、得分），不可见未来。
诚实性规则：所有轮次全量落盘并报告（harness_loop_log.jsonl），
  不允许只报告最优；重复候选按确定性规则处理（重询一次，仍重复则
  记 duplicate 并跳过评估）。
角色边界：LLM 只做"提案"，评估由确定性规则层完成；这展示 harness
  能闭环执行"设计→运行→评估→修订"，不宣称发现超越网格的新科学。

科学定位：机制层探索（规则层，无 LLM agent），结果只进机制/自动化
科研章节，不进主结果；绝对水平不与正式 LLM 批次比较。

用法：
  AGENTSOCIETY_LLM_API_KEY=... AGENTSOCIETY_LLM_API_BASE=https://tokenflux.dev/v1 \
    <runtime-venv-python> tools/harness_loop.py

输出：tests/harness_loop_log.jsonl（逐轮）+ tests/harness_loop_result.json
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXP_DIR / "tests"))

import scan_timing as st  # noqa: E402  复用规则层 runner 与摘要口径

SPACE = {"conditions": ["casework", "timebank", "platform"],
         "iv_start": [3, 12], "duration": [6, 12], "iv_end_max": 24}
MAX_ITER = 6
PATIENCE = 3
SEEDS = st.SEEDS            # 与 scan_timing 相同的 20 个预注册种子
MODEL = os.environ.get("AGENTSOCIETY_LLM_MODEL", "gpt-5.6-sol")
API_BASE = os.environ.get("AGENTSOCIETY_LLM_API_BASE", "https://tokenflux.dev/v1")
LOG_PATH = EXP_DIR / "tests" / "harness_loop_log.jsonl"
RESULT_PATH = EXP_DIR / "tests" / "harness_loop_result.json"


def llm(prompt: str) -> str:
    key = os.environ.get("AGENTSOCIETY_LLM_API_KEY", "")
    if not key:
        raise SystemExit("需要 AGENTSOCIETY_LLM_API_KEY")
    body = json.dumps({"model": MODEL, "messages": [
        {"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(
        f"{API_BASE}/chat/completions", data=body,
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"})
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
    except json.JSONDecodeError:
        return None
    try:
        cand = {"condition": str(p["condition"]),
                "iv_start": int(p["iv_start"]), "duration": int(p["duration"]),
                "rationale": str(p.get("rationale", ""))[:1200]}
    except (KeyError, TypeError, ValueError):
        return None
    lo_s, hi_s = SPACE["iv_start"]
    lo_d, hi_d = SPACE["duration"]
    if (cand["condition"] not in SPACE["conditions"]
            or not lo_s <= cand["iv_start"] <= hi_s
            or not lo_d <= cand["duration"] <= hi_d
            or cand["iv_start"] + cand["duration"] - 1 > SPACE["iv_end_max"]):
        return None
    return cand


async def evaluate(cand: dict) -> dict:
    start = cand["iv_start"]
    end = start + cand["duration"] - 1
    per_seed = []
    for seed in SEEDS:
        rows = await st.run_once(seed, cand["condition"], start, end)
        per_seed.append(st.summarize(rows, start, end))
    a = st.agg(per_seed)
    return {"overall_isolation_rate": a["overall_isolation_rate"],
            "iv_isolation_rate": a["iv_isolation_rate"],
            "post_isolation_rate": a["post_isolation_rate"],
            "rebound_isolation_rate": a["rebound_isolation_rate"],
            "iv_window": [start, end]}


def evidence_block(history: list[dict]) -> str:
    grid = json.loads((EXP_DIR / "tests" / "scan_timing_result.json")
                      .read_text(encoding="utf-8"))
    lines = ["已评估网格（scan_timing，20 种子，overall=第1–24月平均孤立率，越低越好）："]
    for name, v in {**grid["timing_scan"], **grid["duration_scan"]}.items():
        lines.append(f"  {name}: overall={v['overall_isolation_rate']['mean']:.4f} "
                     f"rebound={v['rebound_isolation_rate']['mean']:+.4f} "
                     f"window={v['iv_window']}")
    lines.append(f"none 基线 overall={grid['baseline']['none']['overall_isolation_rate']['mean']:.4f}")
    if history:
        lines.append("闭环已试过的候选：")
        for h in history:
            sc = h.get("score")
            lines.append(f"  第{h['iter']}轮 {h['candidate']} -> "
                         f"{'重复，未评估' if sc is None else f'overall={sc:.4f}'}")
    return "\n".join(lines)


def key_of(c: dict) -> tuple:
    return (c["condition"], c["iv_start"], c["duration"])


async def main() -> int:
    history: list[dict] = []
    tried: set[tuple] = set()
    # 网格里 duration 12 或 start 7 的组合视为已试，逼设计师探索网格之外
    grid_tried = {(c, s, 12) for c in SPACE["conditions"] for s in st.STARTS}
    grid_tried |= {(c, 7, d) for c in SPACE["conditions"] for d in st.DURATIONS if d <= 12}
    best: dict | None = None
    no_improve = 0
    log_f = LOG_PATH.open("a", encoding="utf-8")

    for it in range(1, MAX_ITER + 1):
        prompt = f"""你是模拟实验设计师。任务：在约束内提出下一个值得评估的干预配置，
目标是最小化 overall_isolation_rate（第1-24月平均孤立率，规则层老人支持网络模型）。

搜索空间（硬约束）：condition ∈ {SPACE['conditions']}；iv_start 3-12 整数；
duration 6-12 整数；iv_start+duration-1 ≤ 24。总迭代 {MAX_ITER} 轮，现在是第 {it} 轮。

{evidence_block(history)}

要求：
1. 不要重复上面已评估过的 (condition, iv_start, duration) 组合。
2. 用一句话说明提案的机制理由（基于关系衰减与反弹证据）。
3. 只输出一个 JSON：{{"condition": "...", "iv_start": N, "duration": N, "rationale": "..."}}"""
        cand = parse_proposal(llm(prompt))
        if cand is None:
            rec = {"iter": it, "ts": datetime.now(timezone.utc).isoformat(),
                   "candidate": None, "score": None, "note": "解析失败/越界，跳过"}
            history.append(rec)
            log_f.write(json.dumps(rec, ensure_ascii=False) + "\n"); log_f.flush()
            continue
        if key_of(cand) in tried or key_of(cand) in grid_tried:
            cand2 = parse_proposal(llm(prompt + "\n\n注意：你刚才的提案与已评估组合重复，请换一个。"))
            if cand2 is None or key_of(cand2) in tried or key_of(cand2) in grid_tried:
                rec = {"iter": it, "ts": datetime.now(timezone.utc).isoformat(),
                       "candidate": cand, "score": None, "note": "duplicate，按预注册规则跳过评估"}
                history.append(rec)
                log_f.write(json.dumps(rec, ensure_ascii=False) + "\n"); log_f.flush()
                no_improve += 1
                if no_improve >= PATIENCE:
                    break
                continue
            cand = cand2
        tried.add(key_of(cand))
        res = await evaluate(cand)
        score = res["overall_isolation_rate"]["mean"]
        rec = {"iter": it, "ts": datetime.now(timezone.utc).isoformat(),
               "candidate": {k: cand[k] for k in ("condition", "iv_start", "duration")},
               "rationale": cand["rationale"], "result": res, "score": score}
        improved = best is None or score < best["score"]
        if improved:
            best = rec
            no_improve = 0
        else:
            no_improve += 1
        rec["best_so_far"] = best["candidate"]
        history.append(rec)
        log_f.write(json.dumps(rec, ensure_ascii=False) + "\n"); log_f.flush()
        print(f"第{it}轮 {rec['candidate']} overall={score:.4f} "
              f"{'← 新最优' if improved else ''}")
        if no_improve >= PATIENCE:
            print("连续无改进，按预注册规则提前停止")
            break
    log_f.close()

    grid = json.loads((EXP_DIR / "tests" / "scan_timing_result.json")
                      .read_text(encoding="utf-8"))
    grid_best = min(
        ({"name": k, "overall": v["overall_isolation_rate"]["mean"]}
         for k, v in {**grid["timing_scan"], **grid["duration_scan"]}.items()),
        key=lambda x: x["overall"])
    out = {
        "preregistered": {"objective": "min overall_isolation_rate (months 1-24, 20 seeds)",
                          "space": SPACE, "max_iter": MAX_ITER, "patience": PATIENCE,
                          "seeds": SEEDS, "designer_model": MODEL},
        "iterations": history,
        "best": best,
        "grid_best_for_reference": grid_best,
        "caveats": ["规则层机制探索，不进主结果",
                     "LLM 仅提案，评估为确定性规则层",
                     "全部轮次已落盘（harness_loop_log.jsonl），无选择性报告"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    RESULT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(f"\n闭环最优：{best['candidate'] if best else None} "
          f"overall={best['score']:.4f}" if best else "无有效评估")
    print(f"网格参照最优：{grid_best['name']} overall={grid_best['overall']:.4f}")
    print(f"结果已写入 {RESULT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
