#!/usr/bin/env python3
"""单场 LLM 实验启动器：本地审计代理转发上游，禁止自动续跑或整场重试。

默认值保留 2026-10-19 韩国节点 Astra medium none_s1 那场，使已部署的
systemd 单元不改参数仍可工作。新批次用命令行覆盖模型、推理强度、
provider 与 run 目录：

  python tools/run_astra_single.py --run-dir <prepared_run> \\
      --model gpt-6-astra --reasoning-effort medium --provider openai

  python tools/run_astra_single.py --run-dir <prepared_run> \\
      --model gpt-6-astra --reasoning-effort medium --provider openai

审计代理按 provider 校验请求：openai 走 /chat/completions 且须带
reasoning_effort；anthropic 走 /messages，须带 thinking 或 output_config。
不记录密钥或提示词。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

THIS_FILE = Path(__file__).resolve()
REPO_ROOT = THIS_FILE.parents[4]
EXP_DIR = THIS_FILE.parents[1]

# 韩国节点那场的默认值；命令行可覆盖。测试也读这些模块级常量。
MODEL = "gpt-6-astra"
REASONING_EFFORT = "medium"
PROVIDER = "openai"
UPSTREAM = "https://tokenflux.dev/v1"
DEFAULT_RUN = Path("/srv/agentsociety/examples/v2/elder_support/supplements/20261019/astra6_medium_20261019/none_s1")
DEFAULT_KEYFILE = Path("/home/silas/.config/elder-support/tokenflux.key")
DEFAULT_PYTHON = Path("/srv/agentsociety/.venv/bin/python")


class AuditServer(ThreadingHTTPServer):
    daemon_threads = True


def _effort_ok(payload: dict, provider: str, effort: str) -> bool:
    if not effort:
        return True
    if provider == "anthropic":
        cfg = payload.get("output_config")
        if isinstance(cfg, dict) and cfg.get("effort") == effort:
            return True
        thinking = payload.get("thinking")
        return isinstance(thinking, dict) and thinking.get("type") in {"adaptive", "enabled"}
    return payload.get("reasoning_effort") == effort


def _path_ok(path: str, provider: str) -> bool:
    if provider == "anthropic":
        return path.rstrip("/").endswith("/messages")
    return path.rstrip("/").endswith("/chat/completions")


def _upstream_path(provider: str) -> str:
    return "/messages" if provider == "anthropic" else "/chat/completions"


class AuditHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Never log request headers or bodies.

    def do_POST(self):
        start = time.time()
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            payload = json.loads(raw)
        except ValueError:
            self.send_error(400)
            return
        model = getattr(self.server, "expected_model", MODEL)
        effort = getattr(self.server, "expected_effort", REASONING_EFFORT)
        provider = getattr(self.server, "expected_provider", PROVIDER)
        upstream = getattr(self.server, "upstream", UPSTREAM)
        # Fail closed if runtime silently omits reasoning or changes model.
        if (
            not _path_ok(self.path, provider)
            or payload.get("model") != model
            or not _effort_ok(payload, provider, effort)
            or payload.get("stream")
        ):
            self.send_error(422, "model, effort, or endpoint mismatch")
            self.server.record(
                dict(
                    event="rejected_request",
                    requested_model=payload.get("model"),
                    reasoning_effort=payload.get("reasoning_effort"),
                    output_config=payload.get("output_config"),
                    thinking_type=(
                        payload.get("thinking", {}).get("type")
                        if isinstance(payload.get("thinking"), dict)
                        else None
                    ),
                    path=self.path,
                )
            )
            return
        row = dict(
            event="completion",
            started_at=start,
            requested_model=model,
            provider=provider,
            reasoning_effort=effort,
            request_id=self.server.next_id(),
        )
        try:
            headers = {"Content-Type": "application/json"}
            if provider == "anthropic":
                headers["x-api-key"] = self.server.key
                headers["anthropic-version"] = "2023-06-01"
            else:
                headers["Authorization"] = "Bearer " + self.server.key
            request = Request(upstream.rstrip("/") + _upstream_path(provider), data=raw, headers=headers)
            try:
                with urlopen(request, timeout=185) as response:
                    code, body = response.status, response.read()
            except HTTPError as error:
                code, body = error.code, error.read()
            row["http_status"] = code
            try:
                response_data = json.loads(body)
                row["response_model"] = response_data.get("model")
                row["usage"] = response_data.get("usage")
                if "error" in response_data:
                    e = response_data["error"]
                    row["error_type"] = e.get("type") if isinstance(e, dict) else "upstream_error"
            except ValueError:
                row["error_type"] = "non_json_response"
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as error:
            row["transport_error_type"] = type(error).__name__
            try:
                self.send_error(502, "upstream transport failure")
            except OSError:
                pass
        finally:
            row["elapsed_s"] = round(time.time() - start, 3)
            self.server.record(row)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_key(keyfile: Path) -> str:
    if not keyfile.is_file():
        raise SystemExit(f"缺少凭证文件 {keyfile}")
    if keyfile.stat().st_mode & 0o077:
        raise SystemExit("Credential permissions must be 600")
    key = keyfile.read_text().strip()
    if not key:
        raise SystemExit("Empty credential")
    return key


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", type=Path, default=None, help="已 prepare 的 run 目录（含 manifest.json）")
    ap.add_argument("--model", default=None)
    ap.add_argument("--reasoning-effort", default=None, choices=["low", "medium", "high"])
    ap.add_argument("--provider", default=None, choices=["openai", "anthropic"])
    ap.add_argument("--api-base", default=None, help="上游 OpenAI 兼容或 Anthropic 网关，默认读 manifest 或 tokenflux")
    ap.add_argument("--keyfile", type=Path, default=DEFAULT_KEYFILE)
    ap.add_argument("--python", type=Path, default=None, help="运行 CLI 的解释器")
    ap.add_argument("--experiment-id", default=None)
    ap.add_argument("--restart-infrastructure", action="store_true")
    ap.add_argument("--no-analyze", action="store_true")
    return ap.parse_args(argv)


def resolve_run(args: argparse.Namespace) -> tuple[Path, dict, str, str, str, str]:
    run = args.run_dir.resolve() if args.run_dir else DEFAULT_RUN
    manifest_path = run / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(f"缺少 {manifest_path}")
    manifest = _load_json(manifest_path)
    model = args.model or manifest.get("model") or MODEL
    effort = args.reasoning_effort or manifest.get("reasoning_effort") or REASONING_EFFORT
    provider = args.provider or manifest.get("provider") or PROVIDER
    upstream = args.api_base or manifest.get("api_base") or UPSTREAM
    for name, got, expected in (
        ("model", model, manifest.get("model")),
        ("reasoning_effort", effort, manifest.get("reasoning_effort")),
        ("provider", provider, manifest.get("provider")),
    ):
        if expected and got != expected:
            raise SystemExit(f"命令行 {name}={got} 与 manifest {expected} 不一致")
    return run, manifest, model, effort, provider, upstream


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run, manifest, model, effort, provider, upstream = resolve_run(args)
    if args.restart_infrastructure:
        if (
            (run / "request_audit.jsonl").exists()
            or (run / "SOCIETY.json").exists()
            or (run / "env/ElderSupportEnv/state/metrics.jsonl").exists()
        ):
            raise SystemExit("Cannot use infrastructure restart after requests or simulation data")
        archive = run / "startup_attempts" / str(time.time_ns())
        archive.mkdir(parents=True)
        for name in ("execution.json", "launcher.log", "output.log", "EXECUTION_FAILED"):
            if (run / name).exists():
                (run / name).rename(archive / name)
    if manifest.get("status") != "prepared_not_started" or (run / "execution.json").exists():
        raise SystemExit("Refusing to restart or overwrite a started trial")
    for name, expected in manifest["config_hashes"].items():
        if hashlib.sha256((run / name).read_bytes()).hexdigest() != expected:
            raise SystemExit("Configuration hash mismatch")
    key = _read_key(args.keyfile)
    python = args.python or (
        DEFAULT_PYTHON if DEFAULT_PYTHON.is_file() else REPO_ROOT / ".venv" / "bin" / "python"
    )
    workspace = Path("/srv/agentsociety") if Path("/srv/agentsociety").is_dir() else REPO_ROOT
    audit_file = run / "request_audit.jsonl"
    lock = threading.Lock()
    counter = 0

    def record(row):
        with lock:
            with audit_file.open("a", encoding="utf-8") as output:
                output.write(json.dumps(row, ensure_ascii=False) + "\n")

    def next_id():
        nonlocal counter
        with lock:
            counter += 1
            return counter

    server = AuditServer(("127.0.0.1", 0), AuditHandler)
    server.key = key
    server.record = record
    server.next_id = next_id
    server.expected_model = model
    server.expected_effort = effort
    server.expected_provider = provider
    server.upstream = upstream
    threading.Thread(target=server.serve_forever, daemon=True).start()
    env = dict(os.environ)
    env.update(
        AGENTSOCIETY_LLM_API_KEY=key,
        AGENTSOCIETY_LLM_API_BASE=f"http://127.0.0.1:{server.server_port}/v1",
        AGENTSOCIETY_LLM_MODEL=model,
        AGENTSOCIETY_LLM_PROVIDER=provider,
        AGENTSOCIETY_LLM_REASONING_EFFORT=effort,
        AGENTSOCIETY_LLM_ALLOW_REASONING_ALIAS="1" if provider != "anthropic" else "0",
        AGENTSOCIETY_LLM_REQUEST_TIMEOUT="180",
        AGENTSOCIETY_LLM_MAX_RETRIES="6",
        AGENTSOCIETY_RAY_OBJECT_STORE_BYTES="80000000",
        WORKSPACE_PATH=str(workspace),
        MEM0_TELEMETRY="False",
        ANONYMIZED_TELEMETRY="False",
        AGENTSOCIETY_LLM_RAY_MAX_WORKERS="1",
        OMP_NUM_THREADS="1",
        OPENBLAS_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
        RAY_memory_monitor_refresh_ms="0",
    )
    env.pop("AGENTSOCIETY_LLM_TEMPERATURE", None)
    experiment_id = args.experiment_id or manifest.get("experiment_id") or f"elder_{model}_{effort}_{run.name}"
    execution = dict(
        started_at=time.time(),
        status="running",
        model=model,
        provider=provider,
        reasoning_effort=effort,
        upstream_api_base=upstream,
        local_audit_proxy=True,
        automatic_next_run=False,
        automatic_run_retry=False,
        request_max_retries=6,
        host=os.uname().nodename,
        ray_workers=1,
        object_store_bytes=80000000,
        ray_physical_memory_killer=False,
        runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    )
    (run / "execution.json").write_text(json.dumps(execution, indent=2), encoding="utf-8")
    command = [
        str(python),
        "-m",
        "agentsociety2.society.cli",
        "--config",
        str(run / "init_config.json"),
        "--steps",
        str(run / "steps.yaml"),
        "--run-dir",
        str(run),
        "--experiment-id",
        experiment_id,
        "--log-file",
        str(run / "output.log"),
    ]
    with (run / "launcher.log").open("x") as log:
        result = subprocess.run(command, cwd=str(workspace), env=env, stdout=log, stderr=log)
    server.shutdown()
    execution.update(
        ended_at=time.time(),
        cli_exit_code=result.returncode,
        status="stopped_after_single_trial",
    )
    rows = (
        [json.loads(line) for line in audit_file.read_text(encoding="utf-8").splitlines()]
        if audit_file.exists()
        else []
    )
    usage = [r["usage"] for r in rows if isinstance(r.get("usage"), dict)]
    execution["billing_evidence"] = dict(
        attempts=len(rows),
        responses_with_usage=len(usage),
        prompt_tokens=sum(u.get("prompt_tokens", 0) or u.get("input_tokens", 0) or 0 for u in usage),
        completion_tokens=sum(
            u.get("completion_tokens", 0) or u.get("output_tokens", 0) or 0 for u in usage
        ),
        actual_currency_charge=None,
        note="Token usage is not the provider bill. Verify provider billing before continuing.",
    )
    (run / "execution.json").write_text(json.dumps(execution, indent=2), encoding="utf-8")
    if result.returncode == 0:
        (run / "CLI_FINISHED").touch()
        if not args.no_analyze:
            analyze = subprocess.run(
                [str(python), str(EXP_DIR / "tools/analyze.py"), "--run-dir", str(run)],
                cwd=str(workspace),
                env=env,
                capture_output=True,
            )
            (run / "analysis_exit_code.txt").write_text(str(analyze.returncode) + "\n")
            (run / "analysis_stdout.log").write_bytes(analyze.stdout)
            (run / "analysis_stderr.log").write_bytes(analyze.stderr)
    else:
        (run / "EXECUTION_FAILED").touch()
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
