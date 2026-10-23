"""Contract tests for the sanitized remote cohort status channel."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

EXP = Path(__file__).resolve().parents[1]
PANEL = EXP / "panel"
TOOLS = EXP / "tools"
sys.path.insert(0, str(PANEL))

from remote_status import (  # noqa: E402
    CONDITION_ORDER,
    ConditionState,
    QueueState,
    parse_snapshot,
)


def _load_exporter():
    spec = importlib.util.spec_from_file_location("export_remote_status", TOOLS / "export_remote_status.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


EXPORTER = _load_exporter()


def _write_metrics(root: Path, name: str, months: int, *, mtime: datetime | None = None) -> Path:
    path = root / name / EXPORTER.METRICS_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps({"month": month}) + "\n" for month in range(months)))
    if mtime:
        stamp = mtime.timestamp()
        os.utime(path, (stamp, stamp))
    return path


def _write_output(root: Path, name: str, *lines: str) -> None:
    path = root / name / "output.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _make_proc(proc_root: Path, pid: int, argv: list[str]) -> None:
    path = proc_root / str(pid)
    path.mkdir(parents=True)
    (path / "cmdline").write_bytes(b"\0".join(item.encode() for item in argv) + b"\0")


def _cli_argv(run_dir: Path) -> list[str]:
    return [
        "/venv/bin/python",
        "-m",
        "agentsociety2.society.cli",
        "--config",
        str(run_dir / "init_config.json"),
        "--run-dir",
        str(run_dir),
    ]


@pytest.fixture()
def cohort(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "astra_router_v1"
    proc = tmp_path / "proc"
    root.mkdir()
    proc.mkdir()
    for name in CONDITION_ORDER:
        (root / name).mkdir()
    return root, proc


def test_complete_requires_all_three_artifact_proofs(cohort: tuple[Path, Path]):
    root, proc = cohort
    _write_metrics(root, "casework_s1", 25)
    _write_output(root, "casework_s1", "[2026-10-22 07:36:38] INFO    Experiment completed successfully")
    (root / "chain.log").write_text("2026-10-22T07:38:26Z done casework_s1 rc=0\n")
    snapshot = EXPORTER.collect_snapshot(root, proc)
    item = snapshot.conditions[1]
    assert item.state == ConditionState.COMPLETED
    assert item.completion_evidence == "verified"


def test_full_metrics_without_chain_proof_stays_unknown(cohort: tuple[Path, Path]):
    root, proc = cohort
    _write_metrics(root, "none_s1", 25)
    _write_output(root, "none_s1", "[2026-10-21 09:32:20] INFO    Experiment completed successfully")
    snapshot = EXPORTER.collect_snapshot(root, proc)
    item = snapshot.conditions[0]
    assert item.state == ConditionState.UNKNOWN
    assert "completion_evidence_missing" in item.warnings


def test_live_process_and_queue_are_derived_from_exact_argv(cohort: tuple[Path, Path]):
    root, proc = cohort
    now = datetime(2026, 10, 22, 10, tzinfo=UTC)
    _write_metrics(root, "timebank_s1", 14, mtime=now - timedelta(minutes=2))
    _make_proc(proc, 101, _cli_argv(root / "timebank_s1"))
    _make_proc(proc, 102, ["/bin/bash", str(root / "chain.sh")])
    snapshot = EXPORTER.collect_snapshot(root, proc, now=now)
    assert snapshot.conditions[2].state == ConditionState.RUNNING
    assert snapshot.conditions[3].state == ConditionState.QUEUED
    assert snapshot.queue.state == QueueState.ACTIVE
    assert snapshot.queue.active_condition == "timebank_s1"


def test_stalled_process_is_not_reported_as_healthy_running(cohort: tuple[Path, Path]):
    root, proc = cohort
    now = datetime(2026, 10, 22, 10, tzinfo=UTC)
    _write_metrics(root, "timebank_s1", 14, mtime=now - timedelta(hours=1))
    _make_proc(proc, 101, _cli_argv(root / "timebank_s1"))
    snapshot = EXPORTER.collect_snapshot(root, proc, now=now, stall_seconds=1200)
    assert snapshot.conditions[2].state == ConditionState.STALLED


def test_embedding_403_is_warning_not_failure(cohort: tuple[Path, Path]):
    root, proc = cohort
    now = datetime(2026, 10, 22, 10, tzinfo=UTC)
    _write_metrics(root, "timebank_s1", 4, mtime=now)
    _write_output(root, "timebank_s1", "403 protocol_not_allowed")
    _make_proc(proc, 101, _cli_argv(root / "timebank_s1"))
    snapshot = EXPORTER.collect_snapshot(root, proc, now=now)
    item = snapshot.conditions[2]
    assert item.state == ConditionState.RUNNING
    assert "embedding_protocol_degraded" in item.warnings


@pytest.mark.parametrize(
    "content",
    [
        '{"month": 0}\nnot-json\n',
        '{"month": 0}\n{"month": 0}\n',
        '{"month": 0}\n{"month": 2}\n',
        '{"month": 25}\n',
    ],
)
def test_malformed_noncontiguous_or_out_of_range_metrics_fail_closed(
    cohort: tuple[Path, Path], content: str
):
    root, proc = cohort
    path = root / "none_s1" / EXPORTER.METRICS_REL
    path.parent.mkdir(parents=True)
    path.write_text(content)
    with pytest.raises(EXPORTER.CollectionError):
        EXPORTER.collect_snapshot(root, proc)


def test_multiple_processes_fail_closed_and_near_match_is_ignored(cohort: tuple[Path, Path]):
    root, proc = cohort
    _make_proc(proc, 100, _cli_argv(root / "none_s1-copy"))
    snapshot = EXPORTER.collect_snapshot(root, proc)
    assert snapshot.conditions[0].state == ConditionState.UNKNOWN
    _make_proc(proc, 101, _cli_argv(root / "none_s1"))
    _make_proc(proc, 102, _cli_argv(root / "none_s1"))
    with pytest.raises(EXPORTER.CollectionError, match="multiple CLI"):
        EXPORTER.collect_snapshot(root, proc)


def test_atomic_failure_retains_previous_snapshot(cohort: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch):
    root, proc = cohort
    output = root.parent / "public" / "status.json"
    snapshot = EXPORTER.collect_snapshot(root, proc)
    EXPORTER.atomic_write_snapshot(snapshot, output)
    previous = output.read_bytes()
    assert output.stat().st_mode & 0o777 == 0o644

    def fail_replace(source, destination):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(EXPORTER.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated"):
        EXPORTER.atomic_write_snapshot(snapshot, output)
    assert output.read_bytes() == previous


def test_snapshot_is_strict_and_contains_no_sensitive_runtime_data(cohort: tuple[Path, Path]):
    root, proc = cohort
    _write_metrics(root, "timebank_s1", 1)
    _make_proc(proc, 101, _cli_argv(root / "timebank_s1") + ["--api-key", "secret"])
    snapshot = EXPORTER.collect_snapshot(root, proc)
    payload = snapshot.canonical_json()
    parse_snapshot(payload)
    for forbidden in (str(root), '"pid"', "secret", '"command"', '"log"', '"prompt"', '"key"'):
        assert forbidden not in payload
    raw = json.loads(payload)
    raw["unexpected"] = True
    with pytest.raises(ValueError):
        parse_snapshot(json.dumps(raw))


def _load_server(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, payload: str | None):
    status_file = tmp_path / "status.json"
    if payload is not None:
        status_file.write_text(payload)
    monkeypatch.setenv("PANEL_EXP_DIR", str(tmp_path / "exp"))
    monkeypatch.setenv("PANEL_REPO_DIR", str(tmp_path))
    monkeypatch.setenv("PANEL_READONLY", "1")
    monkeypatch.setenv("PANEL_REMOTE_STATUS_FILE", str(status_file))
    monkeypatch.setenv("PANEL_REMOTE_FRESH_SECONDS", "600")
    monkeypatch.setenv("PANEL_REMOTE_STALE_SECONDS", "1800")
    module_name = f"elder_panel_server_{id(tmp_path)}"
    spec = importlib.util.spec_from_file_location(module_name, PANEL / "server.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_remote_status_api_fresh_stale_and_no_local_fallback(
    cohort: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    root, proc = cohort
    snapshot = EXPORTER.collect_snapshot(root, proc)
    server = _load_server(monkeypatch, tmp_path, snapshot.canonical_json())
    client = TestClient(server.app)
    response = client.get("/api/remote-status")
    assert response.status_code == 200
    assert response.json()["freshness"] == "fresh"

    old = snapshot.model_copy(update={"collected_at": datetime.now(UTC) - timedelta(hours=1)})
    Path(server.REMOTE_STATUS_FILE).write_text(old.canonical_json())
    response = client.get("/api/remote-status")
    assert response.status_code == 200
    assert response.json()["freshness"] == "stale"
    assert response.json()["display_state"] == "unavailable"

    Path(server.REMOTE_STATUS_FILE).unlink()
    response = client.get("/api/remote-status")
    assert response.status_code == 503
    assert response.json()["display_state"] == "unavailable"


def test_remote_status_rejects_malformed_and_future_snapshot(
    cohort: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    root, proc = cohort
    server = _load_server(monkeypatch, tmp_path, "{}")
    client = TestClient(server.app)
    assert client.get("/api/remote-status").status_code == 503
    future = EXPORTER.collect_snapshot(root, proc, now=datetime.now(UTC) + timedelta(minutes=10))
    Path(server.REMOTE_STATUS_FILE).write_text(future.canonical_json())
    assert client.get("/api/remote-status").status_code == 503


def test_readonly_blocks_all_mutations_and_model_probe(
    cohort: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    root, proc = cohort
    snapshot = EXPORTER.collect_snapshot(root, proc)
    server = _load_server(monkeypatch, tmp_path, snapshot.canonical_json())
    monkeypatch.setattr(server, "fetch_models", lambda *args: pytest.fail("upstream called"))
    client = TestClient(server.app)
    assert client.get("/api/models").status_code == 403
    assert client.put("/api/settings", json={"model": "x"}).status_code == 403
    assert client.post("/api/settings/scale", json={"scale": "small"}).status_code == 403
    assert client.post("/api/models/test", json={"model": "x"}).status_code == 403
    assert client.post("/api/start", json={}).status_code == 403
    assert client.post("/api/stop").status_code == 403


def test_html_uses_remote_status_without_local_running_fallback():
    html = (PANEL / "index.html").read_text(encoding="utf-8")
    assert "fetch('/api/remote-status'" in html
    assert "if(panelCfg?.readonly){ renderRemoteRunRecord(); return; }" in html
    assert "id=\"remoteConditionProgress\"" in html
    assert "if(panelCfg === null) return;" in html
    assert "await loadPanelConfig();\n  await poll();" in html
    assert "setInterval(poll, 5000); poll();" not in html
    assert "escapeHtml(labels[item.name]||item.name)" in html
