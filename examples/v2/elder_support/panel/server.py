#!/usr/bin/env python3
"""ElderSupport 实验面板：一键启停模拟 + 实时观察 + 历史轮次浏览。

启动：
  /Users/silas/Documents/Codex/2026-08-21/ba/work/agentsociety-runtime/.venv/bin/python \
    examples/v2/elder_support/panel/server.py
然后浏览器打开 http://127.0.0.1:8722

只读 run 产物文件（metrics/decisions/replay/trace/log），不改动任何实验代码。
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import time
from datetime import datetime
from pathlib import Path

import sys
import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from presets import (
    REASONING_DEPTHS,
    SCALE_PRESETS,
    apply_scale,
    catalog,
    load_settings,
    read_codex_info,
    save_settings,
)
from llm_probe import fetch_models, resolve_api_key, test_connection

EXP = Path(os.environ.get("PANEL_EXP_DIR", HERE.parent))   # examples/v2/elder_support
REPO = Path(os.environ.get("PANEL_REPO_DIR", EXP.parent.parent.parent))  # AgentSociety 仓库根
PY = os.environ.get(
    "PANEL_PYTHON",
    "/Users/silas/Documents/Codex/2026-08-21/ba/work/agentsociety-runtime/.venv/bin/python",
)
TMP = EXP / "tmp"
PANEL_RUNS = TMP / "panel"
# 只读模式（用于云端只读展示部署）：不接受 /api/start /api/stop，仅浏览已同步的 run 数据
READONLY = os.environ.get("PANEL_READONLY", "0") == "1"

DEFAULT_ENV = {
    "AGENTSOCIETY_LLM_API_BASE": "https://tokenflux.dev/v1",
    "AGENTSOCIETY_LLM_MODEL": "gpt-5.6-sol",
    "AGENTSOCIETY_LLM_REQUEST_TIMEOUT": "180",
    "AGENTSOCIETY_LLM_MAX_RETRIES": "6",
    "WORKSPACE_PATH": str(REPO),
}
FALLBACK_KEY = ""
FORMAL_RUN = re.compile(r"^(none|casework|timebank|platform)_s(\d+)$")

app = FastAPI()
_proc: subprocess.Popen | None = None
_proc_run: str | None = None  # 当前面板启动的 run 名


# ---------------- 工具 ----------------

def load_jsonl(path: Path, limit: int | None = None) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except OSError:
        return []
    return rows[-limit:] if limit else rows


def all_run_dirs() -> list[Path]:
    dirs = []
    for base in [TMP, TMP / "batch", PANEL_RUNS]:
        if base.is_dir():
            for d in sorted(base.iterdir()):
                if d.is_dir() and (d / "env" / "ElderSupportEnv").is_dir():
                    dirs.append(d)
    return dirs


def run_mtime(d: Path) -> float:
    # 目录 mtime 不随内部文件更新；用 metrics.jsonl 的时间挑最新 run（同步到远端后依然正确）
    mp = d / "env/ElderSupportEnv/state/metrics.jsonl"
    try:
        return mp.stat().st_mtime
    except OSError:
        return (d / "env").stat().st_mtime


def find_run(name: str | None) -> Path | None:
    dirs = all_run_dirs()
    if not dirs:
        return None
    if name:
        for d in dirs:
            if d.name == name:
                return d
    # 默认：面板当前 run > 外部 CLI 正在跑的正式 run > 最近修改
    if _proc_run:
        for d in dirs:
            if d.name == _proc_run:
                return d
    for d in formal_run_dirs():
        if is_running(d):
            return d
    return max(dirs, key=run_mtime)


def run_meta(d: Path) -> dict:
    meta_p = d / "panel_meta.json"
    meta = {}
    if meta_p.is_file():
        try:
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    # 从 steps.yaml 推断总月数（run 类型 step 数）
    if "months" not in meta:
        sy = d / "steps.yaml"
        if not sy.is_file():
            sy = TMP / "init" / "steps.yaml"
        try:
            # steps.yaml 的 run 步数含 1 个期末结算 step，显示月数需减 1
            meta["months"] = max(1, sy.read_text(encoding="utf-8").count("type: run") - 1)
        except OSError:
            meta["months"] = None
    m = FORMAL_RUN.match(d.name)
    if m:
        meta.setdefault("condition", m.group(1))
        if meta.get("seed") is None:
            meta["seed"] = int(m.group(2))
    return meta


def run_seed(d: Path, meta: dict) -> int | None:
    """Preserve the seed in older runs that predate panel_meta.json."""
    if meta.get("seed") is not None:
        return meta["seed"]
    suffix = d.name.rsplit("_s", 1)
    if len(suffix) == 2 and suffix[1].isdigit():
        return int(suffix[1])
    return None


def env_state(d: Path) -> dict:
    p = d / "env" / "ElderSupportEnv" / "state" / "ENV_STATE.json"
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def profiles_for(d: Path) -> list[dict]:
    """优先 run 内 init_config 中注入的 elders；退回共享 profiles 文件。"""
    st = env_state(d)
    elders = st.get("elders")
    if isinstance(elders, dict):
        elders = list(elders.values())
    if isinstance(elders, list) and elders and isinstance(elders[0], dict):
        return elders
    meta = run_meta(d)
    for cand in [meta.get("profiles"), TMP / "init" / "profiles.json"]:
        if cand and Path(cand).is_file():
            try:
                return json.loads(Path(cand).read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
    return []


def llm_call_stats(d: Path) -> dict:
    n, dur = 0, 0.0
    tdir = d / "trace"
    if tdir.is_dir():
        for f in tdir.glob("trace_*.jsonl"):
            for r in load_jsonl(f):
                if r.get("name") == "llm.completion":
                    n += 1
                    dur += (r.get("end_time_unix_nano", 0) - r.get("start_time_unix_nano", 0)) / 1e9
    return {"calls": n, "avg_latency_s": round(dur / n, 1) if n else 0}


# trace 目录按文件总大小做缓存签名，避免每次轮询全量重扫 12 个 run 的 trace
_calls_cache: dict[str, tuple[float, dict]] = {}


def cached_call_stats(d: Path) -> dict:
    sig = 0.0
    tdir = d / "trace"
    if tdir.is_dir():
        for f in tdir.glob("trace_*.jsonl"):
            try:
                sig += f.stat().st_size
            except OSError:
                pass
    hit = _calls_cache.get(str(d))
    if hit and hit[0] == sig:
        return hit[1]
    st = llm_call_stats(d)
    _calls_cache[str(d)] = (sig, st)
    return st


def formal_run_dirs() -> list[Path]:
    """Only the 12 official condition×seed directories, never archived invalid copies."""
    batch = TMP / "batch"
    if not batch.is_dir():
        return []
    out = []
    for d in sorted(batch.iterdir()):
        if d.is_dir() and FORMAL_RUN.match(d.name) and (d / "env" / "ElderSupportEnv").is_dir():
            out.append(d)
    return out


def scientific_valid(d: Path) -> bool:
    if not (d / "DONE").is_file():
        return False
    summary_p = d / "analysis" / "summary.json"
    if not summary_p.is_file():
        return False
    try:
        summary = json.loads(summary_p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    silence = summary.get("silence_rate")
    llm_error_rate = summary.get("llm_error_rate")
    return bool(summary.get("num_decisions", 0) > 0
                and silence is not None and silence <= 0.10
                and (llm_error_rate is None or llm_error_rate <= 0.05))


def _cli_procs() -> list[tuple[int, str]]:
    """macOS pgrep -af often returns only PIDs; read full command lines from ps."""
    try:
        out = subprocess.run(
            ["ps", "-ax", "-o", "pid=,command="],
            capture_output=True, text=True,
        ).stdout
    except OSError:
        return []
    rows = []
    for line in out.splitlines():
        line = line.strip()
        if "agentsociety2.society.cli" not in line:
            continue
        try:
            pid_s, cmd = line.split(None, 1)
            rows.append((int(pid_s), cmd))
        except ValueError:
            continue
    return rows


def _cli_running_for(d: Path) -> bool:
    """Detect a terminal-launched agentsociety CLI for this exact run directory."""
    token = f"--run-dir {d}"
    return any(token in cmd for _, cmd in _cli_procs())


def batch_totals() -> dict:
    """跨正式 12 个 run 的累计调用数 + 批次计划进度（顶部 ETA / 累积 tokens / 预算）。

    批次计划从 tmp/batch/PLAN.json 读（runs/months/started_at）。
    只统计 none|casework|timebank|platform_sN，不含归档无效目录。
    科学有效的 DONE 计满月；正在跑的计当前月；无效完成不计进度。
    """
    plan = {}
    p = TMP / "batch" / "PLAN.json"
    if p.is_file():
        try:
            plan = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            plan = {}
    planned_runs = int(plan["runs"]) if plan.get("runs") else 12
    planned_months = int(plan["months"]) if plan.get("months") else 24
    total_months = planned_runs * planned_months
    calls = 0
    months_done = 0
    latest_mtime = 0.0
    runs_done = 0
    current_run = None
    current_month = 0
    for d in formal_run_dirs():
        calls += cached_call_stats(d)["calls"]
        m = load_jsonl(d / "env" / "ElderSupportEnv" / "state" / "metrics.jsonl")
        month = m[-1].get("month", 0) if m else 0
        running = is_running(d)
        valid = scientific_valid(d)
        if valid:
            months_done += planned_months
            runs_done += 1
        elif running or run_mtime(d) > time.time() - 3600:
            # 数据一小时内还在更新就计入进度：同步到远端后检测不到本机进程，
            # 用新鲜度代替进程存活判断
            if not (d / "INVALID").is_file():
                months_done += month
                current_run = d.name
                current_month = month
        try:
            latest_mtime = max(latest_mtime, (d / "env").stat().st_mtime)
        except OSError:
            pass
    if current_run is None:
        for d in formal_run_dirs():
            if not scientific_valid(d) and not (d / "INVALID").is_file():
                m = load_jsonl(d / "env" / "ElderSupportEnv" / "state" / "metrics.jsonl")
                current_run = d.name
                current_month = m[-1].get("month", 0) if m else 0
                break
    # 模型对比臂（tmp/model_compare/<model>/<cond>_s1[.invalid-*]）的调用计入累计成本，不计入批次进度
    calls_mc = 0
    mc_root = TMP / "model_compare"
    if mc_root.is_dir():
        for md in sorted(mc_root.iterdir()):
            if not md.is_dir():
                continue
            for d in md.iterdir():
                if d.is_dir() and (d / "trace").is_dir():
                    calls_mc += cached_call_stats(d)["calls"]
    # 归档目录（*.invalid-* / *.stale-* 等非正式命名）的调用也计入累计成本：真实成本必须含沉没部分
    calls_archived = 0
    bdir = TMP / "batch"
    if bdir.is_dir():
        for d in bdir.iterdir():
            if d.is_dir() and not FORMAL_RUN.match(d.name) and (d / "trace").is_dir():
                calls_archived += cached_call_stats(d)["calls"]
    calls += calls_mc + calls_archived
    current_steps = None
    total_steps = None
    if current_run:
        sf = TMP / "batch" / current_run / "SOCIETY_STEP.json"
        if sf.is_file():
            try:
                sd = json.loads(sf.read_text(encoding="utf-8"))
                current_steps = sd.get("completed_step_count")
                total_steps = planned_months + 9  # 25 tick + 8 问卷/初始化步，与主批次 33 步一致
            except (json.JSONDecodeError, OSError):
                pass
    eta_ts = None
    elapsed_s = None
    started_at = plan.get("started_at")
    if started_at:
        elapsed_s = max(1.0, time.time() - float(started_at))
        remaining = max(0, total_months - months_done)
        if remaining == 0:
            eta_ts = latest_mtime or time.time()
            elapsed_s = max(1.0, float(latest_mtime or time.time()) - float(started_at))
        else:
            pace = months_done / elapsed_s
            if pace > 0:
                eta_ts = time.time() + remaining / pace
    return {
        "calls_all_runs": calls,
        "calls_model_compare": calls_mc,
        "calls_archived_invalid": calls_archived,
        "batch_months_done": months_done,
        "batch_total_months": total_months,
        "batch_runs_planned": planned_runs,
        "batch_runs_done": runs_done,
        "current_run": current_run,
        "current_month": current_month,
        "current_steps": current_steps,
        "current_total_steps": total_steps,
        "elapsed_s": elapsed_s,
        "eta_ts": eta_ts,
        "started_at": started_at,
    }


def is_running(d: Path) -> bool:
    global _proc
    if _proc and _proc.poll() is None and _proc_run == d.name:
        return True
    return _cli_running_for(d)


def elapsed_of(d: Path) -> float | None:
    running = is_running(d)
    t0 = None
    pid_p = d / "pid.json"
    if pid_p.is_file():
        try:
            started = json.loads(pid_p.read_text(encoding="utf-8")).get("start_time")
            if started:
                t0 = datetime.fromisoformat(started.replace("Z", "+00:00")).timestamp()
        except (json.JSONDecodeError, OSError, ValueError, TypeError):
            t0 = None
    if t0 is None:
        t0 = run_meta(d).get("started_at")
    log = d / "output.log"
    if not t0:
        if not running:
            return None
        t0 = log.stat().st_ctime if log.is_file() else time.time()
    end = time.time() if running else (log.stat().st_mtime if log.is_file() else time.time())
    return max(0.0, end - float(t0))


def summarize_run(d: Path) -> dict:
    metrics = load_jsonl(d / "env" / "ElderSupportEnv" / "state" / "metrics.jsonl")
    meta = run_meta(d)
    last = metrics[-1] if metrics else {}
    done = (d / "DONE").is_file() or "Experiment completed" in tail_log(d, 40)
    valid = None
    invalid_reasons = []
    summary_p = d / "analysis" / "summary.json"
    if summary_p.is_file():
        try:
            summary = json.loads(summary_p.read_text(encoding="utf-8"))
            silence = summary.get("silence_rate")
            llm_error_rate = summary.get("llm_error_rate")
            invalid_reasons = [
                reason for reason in summary.get("anomalies", [])
                if "决策记录为空" in reason or "整体静默率" in reason or "LLM completion 错误率" in reason
            ]
            valid = bool(done and summary.get("num_decisions", 0) > 0
                         and silence is not None and silence <= 0.10
                         and (llm_error_rate is None or llm_error_rate <= 0.05))
        except (json.JSONDecodeError, OSError):
            valid = False
            invalid_reasons = ["分析摘要无法读取"]
    return {
        "name": d.name,
        "condition": meta.get("condition", ("none" if "baseline" in d.name or d.name.startswith("run") else d.name.split("_s")[0])),
        "seed": run_seed(d, meta),
        "months_done": last.get("month", 0),
        "months_total": meta.get("months"),
        "done": done,
        "valid": valid,
        "invalid_reasons": invalid_reasons,
        "running": is_running(d),
        "final_loneliness": last.get("avg_loneliness"),
        "final_isolation": last.get("isolation_rate"),
        "final_deep": last.get("deep_isolation_rate"),
        "mtime": (d / "env").stat().st_mtime,
    }


def tail_log(d: Path, n: int = 15) -> str:
    log = d / "output.log"
    if not log.is_file():
        return ""
    try:
        return "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-n:])
    except OSError:
        return ""


def calibration_of(metrics_last_agents: list[dict]) -> dict:
    n = len(metrics_last_agents)
    if not n:
        return {}
    often = sum(1 for r in metrics_last_agents if r.get("loneliness", 0) >= 0.6) / n
    some = sum(1 for r in metrics_last_agents if r.get("loneliness", 0) >= 0.45) / n
    return {
        "lonely_often": {"sim": round(often, 3), "target": 0.15, "label": "常常+总是孤独", "source": "CLHLS 2021 b38 15.4%"},
        "lonely_some": {"sim": round(some, 3), "target": 0.40, "label": "有时及以上孤独", "source": "CLHLS 2021 b38 40.3%"},
    }


def final_agent_rows(d: Path) -> list[dict]:
    rows = []
    for f in (d / "replay").glob("elder_support_agent_state.*.jsonl"):
        rows += load_jsonl(f)
    if not rows:
        return []
    last_t = max(r["t"] for r in rows)
    return [r for r in rows if r["t"] == last_t]


def latest_agent_rows(d: Path) -> dict[int, dict]:
    """每个 agent 最近一条 replay 状态。"""
    latest: dict[int, dict] = {}
    for f in (d / "replay").glob("elder_support_agent_state.*.jsonl"):
        for r in load_jsonl(f):
            aid = r.get("agent_id")
            if aid is None:
                continue
            if aid not in latest or r["t"] > latest[aid]["t"]:
                latest[aid] = r
    return latest


class StartReq(BaseModel):
    months: int = 12
    seed: int = 42
    condition: str = "none"
    iv_start: int = 7
    iv_end: int = 18
    num: int = 20
    focal: int = 6
    note: str = ""
    model: str | None = None
    api_base: str | None = None
    reasoning_depth: str = "none"
    max_retries: int | None = None
    scale: str | None = None


class SettingsUpdate(BaseModel):
    model: str | None = None
    api_base: str | None = None
    reasoning_depth: str | None = None
    max_retries: int | None = Field(default=None, ge=1, le=20)
    request_timeout: int | None = Field(default=None, ge=30, le=600)
    active_scale: str | None = None


class ScaleReq(BaseModel):
    scale: str


class ModelTestReq(BaseModel):
    model: str
    api_base: str | None = None
    reasoning_depth: str = "none"


def _llm_base_and_key(api_base: str | None = None) -> tuple[str, str]:
    settings = load_settings(EXP)
    base = (api_base or settings.get("api_base") or DEFAULT_ENV["AGENTSOCIETY_LLM_API_BASE"]).strip()
    key = resolve_api_key(FALLBACK_KEY)
    return base, key


def load_qa() -> dict:
    path = HERE / "qa.json"
    if not path.is_file():
        return {"principle": "", "items": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"principle": "", "items": []}


# ---------------- API ----------------

@app.get("/")
def index():
    return FileResponse(HERE / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/api/runs")
def api_runs():
    return [summarize_run(d) for d in sorted(all_run_dirs(), key=lambda d: (d / "env").stat().st_mtime, reverse=True)]


@app.get("/api/qa")
def api_qa():
    return load_qa()


@app.get("/api/config")
def api_config():
    settings = load_settings(EXP)
    preset = SCALE_PRESETS.get(settings.get("active_scale", "small"))
    return {
        "readonly": READONLY,
        "settings": settings,
        "preset": preset,
        "catalog": catalog(),
        "codex": read_codex_info(),
        "sim_llm": {
            "model": settings.get("model") or DEFAULT_ENV["AGENTSOCIETY_LLM_MODEL"],
            "api_base": settings.get("api_base") or DEFAULT_ENV["AGENTSOCIETY_LLM_API_BASE"],
            "reasoning_depth": settings.get("reasoning_depth", "none"),
            "max_retries": settings.get("max_retries", 6),
            "note": "模拟焦点老人 LLM；不使用 AGENTSOCIETY_CODER 角色",
        },
    }


@app.get("/api/settings")
def api_settings_get():
    settings = load_settings(EXP)
    return {
        "settings": settings,
        "catalog": catalog(),
        "codex": read_codex_info(),
        "effective": {
            **settings,
            "preset": SCALE_PRESETS.get(settings.get("active_scale", "small")),
        },
    }


@app.put("/api/settings")
def api_settings_put(body: SettingsUpdate):
    data = body.model_dump(exclude_unset=True)
    if data.get("reasoning_depth") and data["reasoning_depth"] not in {
        x["id"] for x in REASONING_DEPTHS
    }:
        return JSONResponse({"error": "无效的推理深度"}, status_code=400)
    if data.get("active_scale") and data["active_scale"] not in SCALE_PRESETS:
        return JSONResponse({"error": "无效的规模预设"}, status_code=400)
    settings = save_settings(EXP, data)
    return {"ok": True, "settings": settings}


@app.post("/api/settings/scale")
def api_settings_scale(body: ScaleReq):
    try:
        settings = apply_scale(EXP, body.scale)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    preset = SCALE_PRESETS[body.scale]
    return {"ok": True, "settings": settings, "preset": preset}


@app.get("/api/models")
def api_models(api_base: str | None = None):
    base, key = _llm_base_and_key(api_base)
    result = fetch_models(base, key)
    settings = load_settings(EXP)
    current = settings.get("model") or DEFAULT_ENV["AGENTSOCIETY_LLM_MODEL"]
    if current and result.get("ok"):
        ids = {m["id"] for m in result.get("models", [])}
        if current not in ids:
            result["models"] = [{"id": current, "label": f"{current}（当前，未在列表中）"}] + result["models"]
    result["api_base"] = base
    result["has_api_key"] = bool(key)
    return result


@app.post("/api/models/test")
def api_models_test(body: ModelTestReq):
    base, key = _llm_base_and_key(body.api_base)
    result = test_connection(base, key, body.model, reasoning_depth=body.reasoning_depth)
    result["api_base"] = base
    result["has_api_key"] = bool(key)
    if not result.get("ok"):
        return JSONResponse(result, status_code=502)
    return result


@app.get("/api/state")
def api_state(run: str | None = None):
    d = find_run(run)
    if not d:
        return JSONResponse(
            {"error": "没有任何运行记录"},
            status_code=404,
            headers={"Cache-Control": "no-store"},
        )
    meta = run_meta(d)
    metrics = load_jsonl(d / "env" / "ElderSupportEnv" / "state" / "metrics.jsonl")
    decisions = load_jsonl(d / "env" / "ElderSupportEnv" / "state" / "decisions.jsonl")
    profiles = profiles_for(d)
    live = latest_agent_rows(d)
    st = env_state(d)

    # agent 卡片：画像 + 最新状态 + 最近发言
    last_words: dict[int, dict] = {}
    for dec in decisions:
        if dec.get("reason"):
            last_words[dec["agent_id"]] = dec
    agents = []
    for p in profiles:
        aid = p.get("id")
        lv = live.get(aid, {})
        w = last_words.get(aid)
        agents.append({
            "id": aid, "name": p.get("name"), "age": p.get("age"), "gender": p.get("gender"),
            "focal": p.get("focal", False),
            "extroversion": p.get("extroversion"), "health": lv.get("health", p.get("health")),
            "loneliness": lv.get("loneliness", p.get("loneliness")),
            "active_ties": lv.get("active_ties", len(p.get("ties", []) or []) + len(p.get("children", []) or [])),
            "deep_isolation": bool(lv.get("deep_isolation")),
            "last_event": lv.get("events") or "",
            "last_action": (w or {}).get("action"), "last_target": (w or {}).get("target"),
            "last_reason": (w or {}).get("reason"), "last_month": (w or {}).get("month"),
        })

    running = is_running(d)
    payload = {
        "run": d.name,
        "running": running,
        "external_hint": _external_running() and not running,
        "condition": meta.get("condition", "none"),
        "seed": run_seed(d, meta),
        "iv_start": meta.get("iv_start"),
        "iv_end": meta.get("iv_end"),
        "scale": meta.get("scale"),
        "model": meta.get("model"),
        "reasoning_depth": meta.get("reasoning_depth"),
        "num": meta.get("num", len(profiles)),
        "focal": meta.get("focal", sum(1 for p in profiles if p.get("focal"))),
        "note": meta.get("note", ""),
        "month": (metrics[-1]["month"] if metrics else st.get("month", 0)),
        "months_total": meta.get("months"),
        "elapsed_s": elapsed_of(d),
        "metrics": metrics,
        "cost": cached_call_stats(d),
        "totals": batch_totals(),
        "agents": agents,
        "feed": [dd for dd in decisions if dd.get("reason")][-40:][::-1],
        # 决策视图用全量记录：含焦点老人决策与规则层干预（agent_id=-1）
        "feed_full": [{"month": dd.get("month"), "agent_id": dd.get("agent_id"),
                       "action": dd.get("action"),
                       "target": dd.get("target") or dd.get("activity"),
                       "elder": dd.get("elder"), "outcome": dd.get("outcome"),
                       "reason": dd.get("reason")} for dd in decisions],
        "calibration": calibration_of(final_agent_rows(d)),
        "log_tail": tail_log(d, 8),
        "done": (d / "DONE").is_file() or "Experiment completed" in tail_log(d, 40),
    }
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})



@app.get("/api/conclusions")
def api_conclusions(run: str | None = None):
    d = find_run(run)
    comparison = None
    cmp_p = TMP / "batch" / "comparison.json"
    if cmp_p.is_file():
        try:
            comparison = json.loads(cmp_p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    # 规则层干预冒烟结果（tests/smoke_interventions.py 实测，作为批量实验前的占位）
    smoke = {
        "iv_loneliness": {"none": 0.321, "casework": 0.245, "timebank": 0.235, "platform": 0.303},
        "post_isolation": {"none": 0.1067, "casework": 0.0933, "timebank": 0.0567, "platform": 0.0833},
        "label": "规则层冒烟（50人×24月，非正式结果）",
    }
    calib = calibration_of(final_agent_rows(d)) if d else {}
    quotes = []
    if d:
        for dec in load_jsonl(d / "env" / "ElderSupportEnv" / "state" / "decisions.jsonl"):
            r = dec.get("reason", "")
            if r and any(k in r for k in ["麻烦", "欠", "打扰", "面子"]):
                quotes.append({"month": dec["month"], "agent_id": dec["agent_id"],
                               "action": dec["action"], "reason": r})
    mechanism = None
    mech_p = HERE / "mechanism.json"
    if mech_p.is_file():
        try:
            mechanism = json.loads(mech_p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"run": d.name if d else None, "calibration": calib,
            "smoke": smoke, "batch_comparison": comparison,
            "mechanism": mechanism, "quotes": quotes[:8]}


@app.post("/api/start")
def api_start(req: StartReq):
    global _proc, _proc_run
    if READONLY:
        return JSONResponse({"error": "只读展示实例：不支持从此处启动模拟，请在本地面板启动"}, status_code=403)
    if _proc and _proc.poll() is None:
        return JSONResponse({"error": f"已有运行中的模拟（{_proc_run}），请先停止"}, status_code=409)
    if _external_running():
        return JSONResponse({"error": "检测到面板之外启动的模拟进程仍在运行，请先处理"}, status_code=409)
    if req.condition not in ("none", "casework", "timebank", "platform"):
        return JSONResponse({"error": "未知干预条件"}, status_code=400)

    panel_settings = load_settings(EXP)
    if req.scale and req.scale in SCALE_PRESETS:
        panel_settings = apply_scale(EXP, req.scale)
    preset = SCALE_PRESETS.get(req.scale or panel_settings.get("active_scale", "small"))

    months = req.months
    num = req.num
    focal = req.focal
    if req.scale and preset:
        months = preset["months"]
        num = preset["total_agents"]
        focal = preset["focal_agents"]

    model = (req.model or panel_settings.get("model") or DEFAULT_ENV["AGENTSOCIETY_LLM_MODEL"]).strip()
    api_base = (
        req.api_base or panel_settings.get("api_base") or DEFAULT_ENV["AGENTSOCIETY_LLM_API_BASE"]
    ).strip()
    reasoning = req.reasoning_depth or panel_settings.get("reasoning_depth") or "none"
    max_retries = req.max_retries or panel_settings.get("max_retries") or 6
    request_timeout = panel_settings.get("request_timeout") or 180

    env = {**os.environ, **DEFAULT_ENV}
    env["AGENTSOCIETY_LLM_MODEL"] = model
    env["AGENTSOCIETY_LLM_API_BASE"] = api_base
    env["AGENTSOCIETY_LLM_MAX_RETRIES"] = str(max_retries)
    # API keys must come from the environment, never from source code.
    if not env.get("AGENTSOCIETY_LLM_API_KEY"):
        return JSONResponse({"error": "未设置 AGENTSOCIETY_LLM_API_KEY"}, status_code=400)
    env["AGENTSOCIETY_LLM_REQUEST_TIMEOUT"] = str(request_timeout)
    if reasoning and reasoning != "none":
        env["AGENTSOCIETY_LLM_REASONING_EFFORT"] = reasoning
    else:
        env.pop("AGENTSOCIETY_LLM_REASONING_EFFORT", None)

    save_settings(
        EXP,
        {
            "model": model,
            "api_base": api_base,
            "reasoning_depth": reasoning,
            "max_retries": max_retries,
            "request_timeout": request_timeout,
            "active_scale": req.scale or panel_settings.get("active_scale", "small"),
        },
    )

    profiles = TMP / "init" / f"profiles_s{req.seed}.json"
    if not profiles.is_file():
        r = subprocess.run([PY, str(EXP / "init" / "gen_profiles.py"), "--num", str(num),
                            "--focal", str(focal), "--seed", str(req.seed),
                            "--out", str(profiles)], capture_output=True, text=True, cwd=REPO)
        if r.returncode != 0:
            return JSONResponse({"error": f"画像生成失败: {r.stderr[-800:]}"}, status_code=500)

    cfg_cmd = [PY, str(EXP / "init" / "config_params.py"), "--months", str(months),
               "--seed", str(req.seed), "--profiles", str(profiles)]
    if req.condition != "none":
        cfg_cmd += ["--intervention", req.condition, "--iv-start", str(req.iv_start),
                    "--iv-end", str(req.iv_end)]
    r = subprocess.run(cfg_cmd, capture_output=True, text=True, cwd=REPO)
    if r.returncode != 0:
        return JSONResponse({"error": f"配置生成失败: {r.stderr[-800:]}"}, status_code=500)

    tag = f"{req.condition}_s{req.seed}_{datetime.now():%m%d_%H%M%S}"
    run_dir = PANEL_RUNS / tag
    run_dir.mkdir(parents=True, exist_ok=True)
    for f in ["init_config.json", "steps.yaml"]:
        (run_dir / f).write_bytes((TMP / "init" / f).read_bytes())
    (run_dir / "panel_meta.json").write_text(json.dumps({
        "condition": req.condition, "seed": req.seed, "months": months,
        "iv_start": req.iv_start, "iv_end": req.iv_end, "note": req.note,
        "profiles": str(profiles), "started_at": time.time(),
        "num": num, "focal": focal, "scale": req.scale or panel_settings.get("active_scale"),
        "model": model, "api_base": api_base, "reasoning_depth": reasoning,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    _proc = subprocess.Popen(
        ["caffeinate", "-is", PY, "-m", "agentsociety2.society.cli",
         "--config", str(run_dir / "init_config.json"),
         "--steps", str(run_dir / "steps.yaml"),
         "--run-dir", str(run_dir),
         "--experiment-id", f"elder_support_panel_{tag}",
         "--log-file", str(run_dir / "output.log")],
        cwd=REPO, env=env, start_new_session=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _proc_run = tag
    return {"ok": True, "run": tag}


@app.post("/api/stop")
def api_stop():
    global _proc
    if READONLY:
        return JSONResponse({"error": "只读展示实例：不支持从此处停止模拟"}, status_code=403)
    if not (_proc and _proc.poll() is None):
        return JSONResponse({"error": "面板没有在运行的模拟（面板外启动的进程请在终端处理）"}, status_code=409)
    try:
        os.killpg(os.getpgid(_proc.pid), signal.SIGTERM)
    except ProcessLookupError:
        pass
    for _ in range(20):
        if _proc.poll() is not None:
            break
        time.sleep(0.5)
    if _proc.poll() is None:
        os.killpg(os.getpgid(_proc.pid), signal.SIGKILL)
    return {"ok": True, "note": "已停止；该 run 目录保留，可用 --resume 续跑"}


def _external_running() -> bool:
    rows = _cli_procs()
    if not rows:
        return False
    skip = set()
    if _proc and _proc.poll() is None:
        skip.add(_proc.pid)
        try:
            pgid = os.getpgid(_proc.pid)
            skip.update(pid for pid, _ in rows if pid == pgid)
            # also drop children whose command still points at the panel run dir
            if _proc_run:
                token = f"--run-dir {PANEL_RUNS / _proc_run}"
                skip.update(pid for pid, cmd in rows if token in cmd)
        except ProcessLookupError:
            pass
    return any(pid not in skip for pid, _ in rows)


if __name__ == "__main__":
    PANEL_RUNS.mkdir(parents=True, exist_ok=True)
    port = int(os.environ.get("PANEL_PORT", "8722"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
