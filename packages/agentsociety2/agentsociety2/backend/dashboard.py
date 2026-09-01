"""Browser dashboard for the AgentSociety v2 backend (status + local controls)."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
from threading import Lock
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from agentsociety2 import __version__
from agentsociety2.backend import panel_settings as panel_cfg
from agentsociety2.backend.path_security import (
    require_safe_segment,
    resolve_experiment_dir,
    resolve_under_root,
    resolve_workspace_root,
)


router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])

_WEB_ROOT = Path(__file__).resolve().parent / "web"
_STARTED_AT = time.time()
_MAX_LOG_ENTRIES = 500
_MAX_REQUEST_ENTRIES = 300
_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)((?:api[_-]?key|token)\s*[:=]\s*)[^\s,;]+"),
)
_HYPOTHESIS_RE = re.compile(r"^hypothesis_([A-Za-z0-9_-]+)$")
_EXPERIMENT_RE = re.compile(r"^experiment_([A-Za-z0-9_-]+)$")
_INTERNAL_REQUEST_PATHS = {
    "/health",
    "/panel",
    "/panel/",
    "/api/v1/dashboard/status",
    "/api/v1/dashboard/experiments",
    "/api/v1/dashboard/logs",
    "/api/v1/dashboard/requests",
    "/api/v1/dashboard/settings",
    "/api/v1/dashboard/presets",
}


class LlmSettingsUpdate(BaseModel):
    model: str | None = None
    coder_model: str | None = None
    api_base: str | None = None
    max_retries: int | None = Field(default=None, ge=1, le=20)
    reasoning_depth: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)


class ScaleApplyRequest(BaseModel):
    scale: str = Field(..., description="small | medium | large")

_log_entries: deque[dict[str, Any]] = deque(maxlen=_MAX_LOG_ENTRIES)
_request_entries: deque[dict[str, Any]] = deque(maxlen=_MAX_REQUEST_ENTRIES)
_state_lock = Lock()


def _utc_iso(timestamp: float | None = None) -> str:
    value = time.time() if timestamp is None else timestamp
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def _redact(value: str) -> str:
    result = value
    for pattern in _SECRET_PATTERNS:
        if pattern.groups:
            result = pattern.sub(r"\1[redacted]", result)
        else:
            result = pattern.sub("[redacted]", result)
    return result


class _DashboardLogHandler(logging.Handler):
    """Keep a bounded, redacted copy of backend logs for the local panel."""

    _agentsociety_dashboard_handler = True

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "timestamp": _utc_iso(record.created),
                "level": record.levelname.lower(),
                "source": record.name,
                "message": _redact(record.getMessage()),
            }
            with _state_lock:
                _log_entries.append(entry)
        except Exception:
            self.handleError(record)


def install_log_handler() -> None:
    """Install the in-memory handler once, including across test app imports."""

    root_logger = logging.getLogger()
    if any(
        getattr(handler, "_agentsociety_dashboard_handler", False)
        for handler in root_logger.handlers
    ):
        return
    root_logger.addHandler(_DashboardLogHandler())


def record_request(
    *, method: str, path: str, status: int, duration_ms: float, timestamp: float
) -> None:
    """Record request metadata without query strings or request bodies."""

    if path.startswith("/panel/assets/") or path in _INTERNAL_REQUEST_PATHS:
        return
    entry = {
        "timestamp": _utc_iso(timestamp),
        "method": method,
        "path": path,
        "status": status,
        "duration_ms": round(duration_ms, 1),
    }
    with _state_lock:
        _request_entries.append(entry)


def panel_file(filename: str = "index.html") -> FileResponse:
    path = _WEB_ROOT / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Dashboard asset not found")
    return FileResponse(
        path,
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": (
                "default-src 'self'; connect-src 'self'; img-src 'self' data:; "
                "style-src 'self'; script-src 'self'; frame-ancestors 'none'"
            ),
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
        },
    )


def _workspace_state() -> tuple[str, Path | None, str | None]:
    workspace_path = os.getenv("WORKSPACE_PATH", "").strip()
    if not workspace_path:
        return "", None, "WORKSPACE_PATH is not configured"
    try:
        root = resolve_workspace_root(workspace_path)
    except HTTPException as exc:
        return workspace_path, None, str(exc.detail)
    return workspace_path, root, None


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _process_alive(pid: Any) -> bool | None:
    if not isinstance(pid, int) or pid <= 0:
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _normalise_status(value: Any, process_alive: bool | None) -> str:
    status = str(value or "pending").strip().lower()
    aliases = {
        "success": "completed",
        "complete": "completed",
        "done": "completed",
        "error": "failed",
        "paused": "pending",
        "not_started": "pending",
    }
    status = aliases.get(status, status)
    if status == "running" and process_alive is False:
        return "stale"
    if status not in {"completed", "running", "failed", "pending", "stale"}:
        return "unknown"
    return status


def _document_title(path: Path, fallback: str) -> str:
    if not path.is_file():
        return fallback
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            cleaned = line.strip().lstrip("#").strip()
            if cleaned:
                return cleaned[:160]
    except OSError:
        pass
    return fallback


def _scan_experiments(root: Path) -> list[dict[str, Any]]:
    experiments: list[dict[str, Any]] = []
    for hypothesis_dir in sorted(root.iterdir()):
        if not hypothesis_dir.is_dir():
            continue
        hypothesis_match = _HYPOTHESIS_RE.fullmatch(hypothesis_dir.name)
        if not hypothesis_match:
            continue
        hypothesis_id = hypothesis_match.group(1)
        hypothesis_title = _document_title(
            hypothesis_dir / "HYPOTHESIS.md", f"Hypothesis {hypothesis_id}"
        )
        for experiment_dir in sorted(hypothesis_dir.iterdir()):
            if not experiment_dir.is_dir():
                continue
            experiment_match = _EXPERIMENT_RE.fullmatch(experiment_dir.name)
            if not experiment_match:
                continue
            experiment_id = experiment_match.group(1)
            run_dir = experiment_dir / "run"
            pid_path = run_dir / "pid.json"
            pid_data = _read_json(pid_path) if pid_path.is_file() else {}
            alive = _process_alive(pid_data.get("pid"))
            status = _normalise_status(pid_data.get("status"), alive)
            replay_dir = run_dir / "replay"
            has_replay = replay_dir.is_dir() and (replay_dir / "_schema.json").is_file()
            output_log = run_dir / "output.log"
            artifacts_dir = run_dir / "artifacts"
            try:
                updated_at = _utc_iso(experiment_dir.stat().st_mtime)
            except OSError:
                updated_at = None
            experiments.append(
                {
                    "hypothesis_id": hypothesis_id,
                    "hypothesis_title": hypothesis_title,
                    "experiment_id": experiment_id,
                    "title": _document_title(
                        experiment_dir / "EXPERIMENT.md", f"Experiment {experiment_id}"
                    ),
                    "status": status,
                    "pid": pid_data.get("pid"),
                    "process_alive": alive,
                    "start_time": pid_data.get("start_time"),
                    "end_time": pid_data.get("end_time"),
                    "simulation_time": pid_data.get("simulation_time"),
                    "step_count": int(pid_data.get("step_count") or 0),
                    "has_replay": has_replay,
                    "has_log": output_log.is_file(),
                    "artifact_count": (
                        len(list(artifacts_dir.glob("*.md")))
                        if artifacts_dir.is_dir()
                        else 0
                    ),
                    "updated_at": updated_at,
                }
            )
    experiments.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return experiments


def _experiment_summary(experiments: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "total": len(experiments),
        "running": 0,
        "completed": 0,
        "failed": 0,
        "pending": 0,
        "stale": 0,
        "unknown": 0,
    }
    for experiment in experiments:
        status = experiment["status"]
        summary[status if status in summary else "unknown"] += 1
    return summary


def _tail_lines(path: Path, limit: int) -> list[str]:
    """Read a bounded tail without loading a large experiment log into memory."""

    max_bytes = 256 * 1024
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        handle.seek(max(0, size - max_bytes))
        raw = handle.read(max_bytes)
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if size > max_bytes and lines:
        lines = lines[1:]
    return [_redact(line) for line in lines[-limit:]]


def _line_level(line: str) -> str:
    prefix = line.lstrip().split(":", 1)[0].lower()
    if prefix in {"critical", "error"}:
        return "error"
    if prefix in {"warning", "warn"}:
        return "warning"
    if prefix == "debug":
        return "debug"
    return "info"


def _backend_file_entries(limit: int) -> list[dict[str, Any]]:
    configured = os.getenv("AGENTSOCIETY_BACKEND_LOG_PATH", "").strip()
    if not configured or "\0" in configured:
        return []
    log_path = Path(os.path.realpath(os.path.expanduser(configured)))
    if not log_path.is_file():
        return []
    try:
        lines = _tail_lines(log_path, limit * 2)
    except OSError:
        return []
    filtered = [
        line
        for line in lines
        if '"GET /health HTTP/' not in line
        and '"GET /api/v1/dashboard/' not in line
        and '"GET /panel' not in line
    ]
    return [
        {
            "timestamp": None,
            "level": _line_level(line),
            "source": "backend.log",
            "message": line,
        }
        for line in filtered[-limit:]
    ]


@router.get("/status")
async def get_dashboard_status() -> dict[str, Any]:
    workspace_path, root, workspace_error = _workspace_state()
    experiments = _scan_experiments(root) if root else []
    now = time.time()
    host = os.getenv("BACKEND_HOST", "127.0.0.1")
    port = int(os.getenv("BACKEND_PORT", "8001"))
    with _state_lock:
        log_count = len(_log_entries)
        request_count = len(_request_entries)
    panel_state = panel_cfg.load_settings()
    return {
        "service": "AI Social Scientist Backend",
        "version": __version__,
        "status": "healthy",
        "pid": os.getpid(),
        "started_at": _utc_iso(_STARTED_AT),
        "uptime_seconds": int(now - _STARTED_AT),
        "host": host,
        "port": port,
        "workspace": {
            "configured": root is not None,
            "path": workspace_path,
            "name": root.name if root else "",
            "error": workspace_error,
        },
        "llm": {
            "base_url": os.getenv("AGENTSOCIETY_LLM_API_BASE", ""),
            "model": os.getenv("AGENTSOCIETY_LLM_MODEL", ""),
            "key_configured": bool(os.getenv("AGENTSOCIETY_LLM_API_KEY", "").strip()),
            "coder_model": os.getenv("AGENTSOCIETY_CODER_LLM_MODEL", "")
            or os.getenv("AGENTSOCIETY_LLM_MODEL", ""),
            "embedding_configured": bool(
                os.getenv("AGENTSOCIETY_EMBEDDING_API_KEY", "").strip()
            ),
            "max_retries": int(os.getenv("AGENTSOCIETY_LLM_MAX_RETRIES", "3")),
            "reasoning_depth": os.getenv("AGENTSOCIETY_LLM_REASONING_EFFORT", "none")
            or "none",
            "temperature": (
                float(v)
                if (v := os.getenv("AGENTSOCIETY_LLM_TEMPERATURE", "").strip())
                else None
            ),
        },
        "scale": {
            "active": panel_state.active_scale,
            "preset": panel_cfg.SCALE_PRESETS.get(panel_state.active_scale),
        },
        "experiments": _experiment_summary(experiments),
        "telemetry": {"log_entries": log_count, "request_entries": request_count},
        "links": {"panel": "/panel", "docs": "/docs", "openapi": "/openapi.json"},
    }


@router.get("/presets")
async def get_dashboard_presets() -> dict[str, Any]:
    """Return model / reasoning / scale catalogs for the control panel."""

    return panel_cfg.catalog_payload()


@router.get("/settings")
async def get_dashboard_settings() -> dict[str, Any]:
    settings = panel_cfg.load_settings()
    return {
        "settings": settings.model_dump(),
        "catalog": panel_cfg.catalog_payload(),
        "effective": {
            "model": os.getenv("AGENTSOCIETY_LLM_MODEL", ""),
            "coder_model": os.getenv("AGENTSOCIETY_CODER_LLM_MODEL", "")
            or os.getenv("AGENTSOCIETY_LLM_MODEL", ""),
            "api_base": os.getenv("AGENTSOCIETY_LLM_API_BASE", ""),
            "max_retries": int(os.getenv("AGENTSOCIETY_LLM_MAX_RETRIES", "3")),
            "reasoning_depth": os.getenv("AGENTSOCIETY_LLM_REASONING_EFFORT", "none")
            or "none",
            "temperature": (
                float(v)
                if (v := os.getenv("AGENTSOCIETY_LLM_TEMPERATURE", "").strip())
                else None
            ),
            "active_scale": settings.active_scale,
        },
    }


@router.put("/settings")
async def update_dashboard_settings(body: LlmSettingsUpdate) -> dict[str, Any]:
    """Update runtime LLM controls from the local panel."""

    settings = panel_cfg.load_settings()
    llm = settings.llm
    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(llm, key, value)
    try:
        # Re-validate after partial update.
        settings.llm = panel_cfg.LlmControlSettings.model_validate(llm.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    applied = panel_cfg.apply_llm_runtime(settings.llm)
    panel_cfg.save_settings(settings)
    return {
        "ok": True,
        "settings": settings.model_dump(),
        "applied": applied,
    }


@router.post("/settings/scale")
async def apply_dashboard_scale(body: ScaleApplyRequest) -> dict[str, Any]:
    """Activate small / medium / large agent-scale preset."""

    try:
        result = panel_cfg.apply_scale_preset(body.scale)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **result}


@router.get("/experiments")
async def list_dashboard_experiments() -> dict[str, Any]:
    _, root, workspace_error = _workspace_state()
    if root is None:
        return {"experiments": [], "summary": _experiment_summary([]), "error": workspace_error}
    experiments = _scan_experiments(root)
    return {
        "experiments": experiments,
        "summary": _experiment_summary(experiments),
        "error": None,
    }


@router.get("/logs")
async def get_dashboard_logs(
    source: str = Query("backend", pattern="^(backend|experiment)$"),
    limit: int = Query(200, ge=1, le=500),
    hypothesis_id: str | None = None,
    experiment_id: str | None = None,
) -> dict[str, Any]:
    if source == "backend":
        with _state_lock:
            memory_entries = list(_log_entries)[-limit:]
        file_entries = _backend_file_entries(limit)
        entries = (file_entries + memory_entries)[-limit:]
        return {"source": "backend", "entries": entries}

    if hypothesis_id is None or experiment_id is None:
        raise HTTPException(
            status_code=400,
            detail="hypothesis_id and experiment_id are required for experiment logs",
        )
    require_safe_segment(hypothesis_id, field="hypothesis_id")
    require_safe_segment(experiment_id, field="experiment_id")
    workspace_path, root, _ = _workspace_state()
    if root is None:
        raise HTTPException(status_code=503, detail="Workspace is not configured")
    experiment_dir = resolve_experiment_dir(
        workspace_path, hypothesis_id, experiment_id
    )
    log_path = resolve_under_root(experiment_dir, "run", "output.log")
    if not log_path.is_file():
        return {"source": "experiment", "entries": []}
    try:
        lines = _tail_lines(log_path, limit)
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Unable to read experiment log") from exc
    return {
        "source": "experiment",
        "entries": [
            {
                "timestamp": None,
                "level": "info",
                "source": f"{hypothesis_id}/{experiment_id}",
                "message": line,
            }
            for line in lines
        ],
    }


@router.get("/requests")
async def get_dashboard_requests(
    limit: int = Query(100, ge=1, le=300),
) -> dict[str, Any]:
    with _state_lock:
        entries = list(_request_entries)[-limit:]
    return {"entries": entries}
