"""规模预设与面板运行时设置（独居老人实验台专用）。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# 文献 / 官方案例锚点：
# - small: Axelrod(~20)、公共品(~24) 机制冒烟尺度
# - medium: 街道/中型社区验证（~400 人，20% 焦点层）
# - large: 研究计划混合分层（~2500 规则 + ~400 LLM 焦点，对齐信息茧房万人案例的分层思路）

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
        "max_retries": 6,
        "rationale": "对齐官方 Axelrod(~20) 与公共品(~24)；用于机制校准与全链路验证。",
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
        "max_retries": 8,
        "rationale": "街道/中型社区量级；足够做效度与单组干预，API 成本仍可控。",
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
        "max_retries": 10,
        "rationale": "研究计划正式档：混合分层 + 多 seed，支撑竞赛与论文级结果。",
    },
}

MODEL_OPTIONS: list[dict[str, str]] = []  # 由 /api/models 实时从网关抓取

REASONING_DEPTHS: list[dict[str, str]] = [
    {"id": "none", "label": "关闭", "hint": "不传 reasoning_effort，适合普通 chat 模型"},
    {"id": "low", "label": "低", "hint": "冒烟 / 小规模：更快更省"},
    {"id": "medium", "label": "中", "hint": "社区验证默认档"},
    {"id": "high", "label": "高", "hint": "大规模焦点层深度推理"},
]

DEFAULT_SETTINGS: dict[str, Any] = {
    "active_scale": "small",
    "model": os.getenv("AGENTSOCIETY_LLM_MODEL", "gpt-5.6-sol"),
    "api_base": os.getenv("AGENTSOCIETY_LLM_API_BASE", "https://tokenflux.dev/v1"),
    "reasoning_depth": "none",
    "max_retries": int(os.getenv("AGENTSOCIETY_LLM_MAX_RETRIES", "6")),
    "request_timeout": int(os.getenv("AGENTSOCIETY_LLM_REQUEST_TIMEOUT", "180")),
}


def settings_path(exp_dir: Path) -> Path:
    return exp_dir / "panel" / "settings.json"


def load_settings(exp_dir: Path) -> dict[str, Any]:
    path = settings_path(exp_dir)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            merged = {**DEFAULT_SETTINGS, **data}
            if merged.get("active_scale") not in SCALE_PRESETS:
                merged["active_scale"] = "small"
            return merged
        except (OSError, json.JSONDecodeError):
            pass
    return dict(DEFAULT_SETTINGS)


def save_settings(exp_dir: Path, data: dict[str, Any]) -> dict[str, Any]:
    path = settings_path(exp_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    current = load_settings(exp_dir)
    current.update({k: v for k, v in data.items() if v is not None})
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return current


def apply_scale(exp_dir: Path, scale_id: str) -> dict[str, Any]:
    if scale_id not in SCALE_PRESETS:
        raise ValueError(f"unknown scale: {scale_id}")
    preset = SCALE_PRESETS[scale_id]
    return save_settings(
        exp_dir,
        {
            "active_scale": scale_id,
            "reasoning_depth": preset["reasoning_depth"],
            "max_retries": preset["max_retries"],
        },
    )


def read_codex_info() -> dict[str, Any]:
    """读取 ~/.codex/config.toml，展示第三方 Codex 路由（非 AGENTSOCIETY_CODER）。"""
    import re

    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    cfg_path = codex_home / "config.toml"
    if not cfg_path.is_file():
        return {
            "configured": False,
            "path": str(cfg_path),
            "note": "未找到 Codex 配置；模拟 LLM 仍走下方 tokenflux 设置",
        }
    try:
        text = cfg_path.read_text(encoding="utf-8")
    except OSError:
        return {"configured": False, "path": str(cfg_path), "note": "无法读取 Codex 配置"}

    def _field(name: str) -> str:
        m = re.search(rf'^{re.escape(name)}\s*=\s*"([^"]*)"', text, re.M)
        return m.group(1) if m else ""

    provider = _field("model_provider")
    model = _field("model")
    base_url = ""
    if provider:
        block = re.search(
            rf'\[model_providers\.{re.escape(provider)}\](.*?)(?=\n\[|\Z)',
            text,
            re.S,
        )
        if block:
            m = re.search(r'base_url\s*=\s*"([^"]*)"', block.group(1))
            base_url = m.group(1) if m else ""

    return {
        "configured": True,
        "path": str(cfg_path),
        "model_provider": provider or "（默认）",
        "model": model or "（未指定）",
        "base_url": base_url or "（见 provider 块）",
        "note": "开发/编排走第三方 Codex；本实验台模拟 LLM 使用 tokenflux 模型设置，不用 coder 角色",
    }


def catalog() -> dict[str, Any]:
    return {
        "scales": list(SCALE_PRESETS.values()),
        "models": [],  # 前端通过 GET /api/models 实时拉取
        "reasoning_depths": REASONING_DEPTHS,
        "models_source": "live",
    }
