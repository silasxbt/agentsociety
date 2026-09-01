"""Panel runtime settings and elder-support scale presets.

Scale sizes are grounded in:
- Official AgentSociety cases: Axelrod (~20), public-goods (~24),
  information-cocoon (10k mostly rule-driven).
- Our research plan hybrid design: ~2,500 rule + 300–500 LLM focal agents.
- Social-work practice: street/community caseload scales for mid size.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock
from typing import Any

from pydantic import BaseModel, Field, field_validator


_SETTINGS_LOCK = Lock()
_SETTINGS_CACHE: dict[str, Any] | None = None

# Curated model ids for the panel dropdown. Users can still type a custom id.
MODEL_OPTIONS: list[dict[str, str]] = [
    {"id": "gpt-5.6-sol", "label": "gpt-5.6-sol（当前常用）"},
    {"id": "gpt-5.5", "label": "gpt-5.5（默认回退）"},
    {"id": "gpt-4.1", "label": "gpt-4.1"},
    {"id": "gpt-4o", "label": "gpt-4o"},
    {"id": "o3-mini", "label": "o3-mini"},
    {"id": "deepseek-chat", "label": "deepseek-chat"},
    {"id": "claude-sonnet-4-20250514", "label": "claude-sonnet-4"},
]

REASONING_DEPTH_OPTIONS: list[dict[str, str]] = [
    {
        "id": "none",
        "label": "关闭",
        "hint": "不传 reasoning 参数，适合普通 chat 模型",
    },
    {
        "id": "low",
        "label": "低",
        "hint": "冒烟/小规模：更快更便宜",
    },
    {
        "id": "medium",
        "label": "中",
        "hint": "正式验证默认档",
    },
    {
        "id": "high",
        "label": "高",
        "hint": "大规模焦点层深度推理",
    },
]

# --- Scale presets ---------------------------------------------------------
# Numbers chosen so each tier has a distinct scientific job, not just "bigger".
SCALE_PRESETS: dict[str, dict[str, Any]] = {
    "small": {
        "id": "small",
        "label": "小规模",
        "badge": "冒烟 / 链路",
        "total_agents": 40,
        "focal_agents": 8,
        "focal_ratio": 0.20,
        "months": 12,
        "seeds": 1,
        "reasoning_depth": "low",
        "max_tool_rounds": 3,
        "batch_hint": 32,
        "estimated_llm_calls_per_run": 8 * 12 * 2,  # focal × months × ~2 calls
        "rationale": (
            "对齐官方 Axelrod(~20) 与公共品(~24) 机制复现尺度；"
            "用于冒烟测试、机制校准和全链路验证，不追求统计功效。"
        ),
    },
    "medium": {
        "id": "medium",
        "label": "中规模",
        "badge": "社区验证",
        "total_agents": 400,
        "focal_agents": 80,
        "focal_ratio": 0.20,
        "months": 24,
        "seeds": 5,
        "reasoning_depth": "medium",
        "max_tool_rounds": 5,
        "batch_hint": 64,
        "estimated_llm_calls_per_run": 80 * 24 * 2,
        "rationale": (
            "约等于一个街道/中型社区服务对象量级；"
            "规则层提供宏观结构，焦点层足够做行为效度与单组干预对照，"
            "API 成本仍可控。"
        ),
    },
    "large": {
        "id": "large",
        "label": "大规模",
        "badge": "正式实验",
        "total_agents": 2500,
        "focal_agents": 400,
        "focal_ratio": 0.16,
        "months": 24,
        "seeds": 10,
        "reasoning_depth": "high",
        "max_tool_rounds": 6,
        "batch_hint": 128,
        "estimated_llm_calls_per_run": 400 * 24 * 2,
        "rationale": (
            "对齐研究计划混合分层设计（约 2500 规则层 + 300–500 焦点层）；"
            "多 seed 重复支撑置信区间，满足竞赛规模展示与论文级结果。"
        ),
    },
}


class LlmControlSettings(BaseModel):
    """Runtime LLM controls exposed by the local panel."""

    model: str = Field(default="", description="Default LLM model id")
    coder_model: str = Field(default="", description="Coder-role model id")
    api_base: str = Field(default="", description="API base URL")
    max_retries: int = Field(default=3, ge=1, le=20)
    reasoning_depth: str = Field(default="none")
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)

    @field_validator("reasoning_depth")
    @classmethod
    def _validate_depth(cls, value: str) -> str:
        allowed = {item["id"] for item in REASONING_DEPTH_OPTIONS}
        if value not in allowed:
            raise ValueError(f"reasoning_depth must be one of {sorted(allowed)}")
        return value

    @field_validator("model", "coder_model", "api_base")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class PanelSettings(BaseModel):
    """Persisted panel settings (LLM + active scale)."""

    llm: LlmControlSettings = Field(default_factory=LlmControlSettings)
    active_scale: str = Field(default="small")

    @field_validator("active_scale")
    @classmethod
    def _validate_scale(cls, value: str) -> str:
        if value not in SCALE_PRESETS:
            raise ValueError(f"active_scale must be one of {sorted(SCALE_PRESETS)}")
        return value


def _settings_path() -> Path:
    workspace = os.getenv("WORKSPACE_PATH", "").strip()
    if workspace:
        root = Path(os.path.expanduser(workspace)).resolve()
        target = root / ".agentsociety" / "panel_settings.json"
        return target
    home = Path(os.getenv("AGENTSOCIETY_HOME_DIR", "./agentsociety_data")).expanduser()
    return (home / "panel_settings.json").resolve()


def _default_settings() -> PanelSettings:
    return PanelSettings(
        llm=LlmControlSettings(
            model=os.getenv("AGENTSOCIETY_LLM_MODEL", "gpt-5.5"),
            coder_model=os.getenv("AGENTSOCIETY_CODER_LLM_MODEL", "")
            or os.getenv("AGENTSOCIETY_LLM_MODEL", "gpt-5.5"),
            api_base=os.getenv(
                "AGENTSOCIETY_LLM_API_BASE", "https://api.openai.com/v1"
            ),
            max_retries=int(os.getenv("AGENTSOCIETY_LLM_MAX_RETRIES", "3")),
            reasoning_depth=os.getenv("AGENTSOCIETY_LLM_REASONING_EFFORT", "none")
            or "none",
        ),
        active_scale="small",
    )


def load_settings() -> PanelSettings:
    global _SETTINGS_CACHE
    with _SETTINGS_LOCK:
        if _SETTINGS_CACHE is not None:
            return PanelSettings.model_validate(_SETTINGS_CACHE)
        path = _settings_path()
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                settings = PanelSettings.model_validate(raw)
            except (OSError, json.JSONDecodeError, ValueError):
                settings = _default_settings()
        else:
            settings = _default_settings()
        _SETTINGS_CACHE = settings.model_dump()
        return settings


def save_settings(settings: PanelSettings) -> PanelSettings:
    global _SETTINGS_CACHE
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = settings.model_dump()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    with _SETTINGS_LOCK:
        _SETTINGS_CACHE = payload
    return settings


def clear_settings_cache() -> None:
    global _SETTINGS_CACHE
    with _SETTINGS_LOCK:
        _SETTINGS_CACHE = None


def apply_llm_runtime(settings: LlmControlSettings) -> dict[str, Any]:
    """Push LLM controls into process env + Config class attrs; clear routers."""

    from agentsociety2.config import config as config_mod
    from agentsociety2.config.config import Config

    updates: dict[str, str] = {}
    if settings.model:
        updates["AGENTSOCIETY_LLM_MODEL"] = settings.model
        Config.LLM_MODEL = settings.model
    if settings.coder_model:
        updates["AGENTSOCIETY_CODER_LLM_MODEL"] = settings.coder_model
        Config.CODER_LLM_MODEL = settings.coder_model
    elif settings.model:
        # Keep coder in sync when only default model is set.
        updates["AGENTSOCIETY_CODER_LLM_MODEL"] = settings.model
        Config.CODER_LLM_MODEL = settings.model
    if settings.api_base:
        updates["AGENTSOCIETY_LLM_API_BASE"] = settings.api_base
        Config.LLM_API_BASE = settings.api_base
        if not os.getenv("AGENTSOCIETY_CODER_LLM_API_BASE"):
            Config.CODER_LLM_API_BASE = settings.api_base
    updates["AGENTSOCIETY_LLM_MAX_RETRIES"] = str(settings.max_retries)
    if settings.reasoning_depth and settings.reasoning_depth != "none":
        updates["AGENTSOCIETY_LLM_REASONING_EFFORT"] = settings.reasoning_depth
    else:
        os.environ.pop("AGENTSOCIETY_LLM_REASONING_EFFORT", None)
        updates.pop("AGENTSOCIETY_LLM_REASONING_EFFORT", None)
    if settings.temperature is not None:
        updates["AGENTSOCIETY_LLM_TEMPERATURE"] = str(settings.temperature)
    else:
        os.environ.pop("AGENTSOCIETY_LLM_TEMPERATURE", None)

    for key, value in updates.items():
        os.environ[key] = value

    # Drop cached litellm routers so next build picks up new model/base.
    config_mod._default_router = None
    config_mod._coder_router = None
    return {
        "applied": updates,
        "reasoning_depth": settings.reasoning_depth,
        "temperature": settings.temperature,
    }


def apply_scale_preset(scale_id: str, *, write_workspace: bool = True) -> dict[str, Any]:
    """Activate a scale preset and optionally write workspace scale_config.json."""

    if scale_id not in SCALE_PRESETS:
        raise ValueError(f"unknown scale preset: {scale_id}")
    preset = dict(SCALE_PRESETS[scale_id])
    settings = load_settings()
    settings.active_scale = scale_id
    # Align reasoning depth with the preset unless user locked something else
    # via an explicit later LLM edit; applying a scale intentionally sets depth.
    settings.llm.reasoning_depth = str(preset["reasoning_depth"])
    apply_llm_runtime(settings.llm)
    save_settings(settings)

    written: str | None = None
    if write_workspace:
        workspace = os.getenv("WORKSPACE_PATH", "").strip()
        if workspace:
            out = Path(os.path.expanduser(workspace)).resolve() / "scale_config.json"
            out.write_text(
                json.dumps(preset, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            written = str(out)
    return {"preset": preset, "written_to": written}


def catalog_payload() -> dict[str, Any]:
    return {
        "models": MODEL_OPTIONS,
        "reasoning_depths": REASONING_DEPTH_OPTIONS,
        "scales": list(SCALE_PRESETS.values()),
    }


def llm_call_overrides() -> dict[str, Any]:
    """Extra kwargs for litellm completion from current env controls."""

    kwargs: dict[str, Any] = {}
    depth = os.getenv("AGENTSOCIETY_LLM_REASONING_EFFORT", "").strip().lower()
    if depth in {"low", "medium", "high"}:
        kwargs["reasoning_effort"] = depth
    temp = os.getenv("AGENTSOCIETY_LLM_TEMPERATURE", "").strip()
    if temp:
        try:
            kwargs["temperature"] = float(temp)
        except ValueError:
            pass
    return kwargs
