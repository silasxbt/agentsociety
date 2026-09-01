"""Tests for panel settings / scale presets."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def panel_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENTSOCIETY_LLM_API_KEY", "sk-test-panel")
    monkeypatch.setenv("AGENTSOCIETY_LLM_API_BASE", "https://example.test/v1")
    monkeypatch.setenv("AGENTSOCIETY_LLM_MODEL", "gpt-5.6-sol")
    monkeypatch.setenv("WORKSPACE_PATH", str(tmp_path))
    monkeypatch.setenv("AGENTSOCIETY_HOME_DIR", str(tmp_path / "home"))
    # Ensure settings module starts clean for each test.
    from agentsociety2.backend import panel_settings as ps

    ps.clear_settings_cache()
    yield tmp_path
    ps.clear_settings_cache()


def test_scale_presets_have_monotonic_sizes():
    from agentsociety2.backend.panel_settings import SCALE_PRESETS

    small = SCALE_PRESETS["small"]
    medium = SCALE_PRESETS["medium"]
    large = SCALE_PRESETS["large"]
    assert small["total_agents"] < medium["total_agents"] < large["total_agents"]
    assert small["focal_agents"] < medium["focal_agents"] < large["focal_agents"]
    assert small["focal_agents"] <= small["total_agents"]
    assert medium["focal_agents"] <= medium["total_agents"]
    assert large["focal_agents"] <= large["total_agents"]


def test_apply_llm_and_scale_via_api(panel_env: Path):
    # Import app after env is set so Config sees the test key.
    from agentsociety2.backend.app import app

    client = TestClient(app)
    presets = client.get("/api/v1/dashboard/presets")
    assert presets.status_code == 200
    body = presets.json()
    assert {item["id"] for item in body["scales"]} == {"small", "medium", "large"}
    assert any(item["id"] == "high" for item in body["reasoning_depths"])

    updated = client.put(
        "/api/v1/dashboard/settings",
        json={
            "model": "gpt-4o",
            "coder_model": "gpt-4.1",
            "api_base": "https://tokenflux.dev/v1",
            "reasoning_depth": "medium",
            "max_retries": 5,
            "temperature": 0.2,
        },
    )
    assert updated.status_code == 200, updated.text
    assert os.environ["AGENTSOCIETY_LLM_MODEL"] == "gpt-4o"
    assert os.environ["AGENTSOCIETY_LLM_REASONING_EFFORT"] == "medium"
    assert os.environ["AGENTSOCIETY_LLM_MAX_RETRIES"] == "5"

    scaled = client.post("/api/v1/dashboard/settings/scale", json={"scale": "medium"})
    assert scaled.status_code == 200, scaled.text
    payload = scaled.json()
    assert payload["preset"]["total_agents"] == 400
    assert payload["preset"]["focal_agents"] == 80
    assert Path(payload["written_to"]).is_file()
    assert os.environ["AGENTSOCIETY_LLM_REASONING_EFFORT"] == "medium"

    status = client.get("/api/v1/dashboard/status")
    assert status.status_code == 200
    data = status.json()
    assert data["llm"]["model"] == "gpt-4o"
    assert data["scale"]["active"] == "medium"
    assert data["scale"]["preset"]["total_agents"] == 400


def test_llm_call_overrides_reads_env(monkeypatch: pytest.MonkeyPatch):
    from agentsociety2.backend.panel_settings import llm_call_overrides

    monkeypatch.setenv("AGENTSOCIETY_LLM_REASONING_EFFORT", "high")
    monkeypatch.setenv("AGENTSOCIETY_LLM_TEMPERATURE", "0.4")
    assert llm_call_overrides() == {
        "reasoning_effort": "high",
        "temperature": 0.4,
    }
    monkeypatch.delenv("AGENTSOCIETY_LLM_REASONING_EFFORT", raising=False)
    monkeypatch.delenv("AGENTSOCIETY_LLM_TEMPERATURE", raising=False)
    assert llm_call_overrides() == {}
