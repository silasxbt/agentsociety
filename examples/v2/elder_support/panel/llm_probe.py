"""从 OpenAI 兼容网关拉取模型列表并测试连通性。"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any


def resolve_api_key(fallback: str = "") -> str:
    return (os.environ.get("AGENTSOCIETY_LLM_API_KEY") or fallback or "").strip()


def _normalize_base(api_base: str) -> str:
    return api_base.rstrip("/")


def _request_json(
    method: str,
    url: str,
    api_key: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> tuple[int, Any, float]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            elapsed_ms = round((time.monotonic() - t0) * 1000, 1)
            return resp.status, json.loads(body) if body else {}, elapsed_ms
    except urllib.error.HTTPError as exc:
        elapsed_ms = round((time.monotonic() - t0) * 1000, 1)
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"message": raw[:500] or str(exc)}
        return exc.code, parsed, elapsed_ms
    except urllib.error.URLError as exc:
        elapsed_ms = round((time.monotonic() - t0) * 1000, 1)
        return 0, {"message": str(exc.reason or exc)}, elapsed_ms


def fetch_models(api_base: str, api_key: str, *, timeout: float = 30.0) -> dict[str, Any]:
    if not api_key:
        return {"ok": False, "models": [], "error": "未配置 API Key（请设置 AGENTSOCIETY_LLM_API_KEY）"}
    base = _normalize_base(api_base)
    status, body, elapsed_ms = _request_json(
        "GET", f"{base}/models", api_key, timeout=timeout
    )
    if status != 200:
        msg = body.get("error", {}).get("message") if isinstance(body.get("error"), dict) else body.get("message")
        return {
            "ok": False,
            "models": [],
            "error": msg or f"HTTP {status}",
            "latency_ms": elapsed_ms,
            "status": status,
        }
    rows = body.get("data") if isinstance(body, dict) else None
    if not isinstance(rows, list):
        return {
            "ok": False,
            "models": [],
            "error": "响应格式异常（缺少 data 数组）",
            "latency_ms": elapsed_ms,
        }
    models: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in rows:
        if not isinstance(item, dict):
            continue
        mid = str(item.get("id") or item.get("model") or "").strip()
        if not mid or mid in seen:
            continue
        seen.add(mid)
        owned = item.get("owned_by")
        label = f"{mid}" + (f" · {owned}" if owned else "")
        models.append({"id": mid, "label": label})
    models.sort(key=lambda x: x["id"].lower())
    return {
        "ok": True,
        "models": models,
        "count": len(models),
        "latency_ms": elapsed_ms,
        "fetched_at": time.time(),
    }


def test_connection(
    api_base: str,
    api_key: str,
    model: str,
    *,
    reasoning_depth: str = "none",
    timeout: float = 45.0,
) -> dict[str, Any]:
    if not api_key:
        return {"ok": False, "error": "未配置 API Key（请设置 AGENTSOCIETY_LLM_API_KEY）"}
    if not model.strip():
        return {"ok": False, "error": "请选择或填写模型名称"}
    base = _normalize_base(api_base)
    payload: dict[str, Any] = {
        "model": model.strip(),
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 8,
    }
    if reasoning_depth and reasoning_depth != "none":
        payload["reasoning_effort"] = reasoning_depth
    status, body, elapsed_ms = _request_json(
        "POST",
        f"{base}/chat/completions",
        api_key,
        payload=payload,
        timeout=timeout,
    )
    if status != 200:
        msg = body.get("error", {}).get("message") if isinstance(body.get("error"), dict) else body.get("message")
        return {
            "ok": False,
            "error": msg or f"HTTP {status}",
            "latency_ms": elapsed_ms,
            "status": status,
        }
    content = ""
    try:
        content = body["choices"][0]["message"].get("content") or ""
    except (KeyError, IndexError, TypeError):
        content = ""
    return {
        "ok": True,
        "latency_ms": elapsed_ms,
        "model": model.strip(),
        "reply_preview": str(content)[:120],
        "usage": body.get("usage"),
    }
