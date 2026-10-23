#!/usr/bin/env python3
"""Export a sanitized status snapshot for the fixed Korean Astra cohort."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parents[1]
PANEL_DIR = EXP_DIR / "panel"
sys.path.insert(0, str(PANEL_DIR))
from remote_status import (  # noqa: E402
    CONDITION_ORDER,
    EXPECTED_MONTHS,
    ConditionState,
    ConditionStatus,
    QueueState,
    QueueStatus,
    RemoteStatusSnapshot,
    WarningCode,
    parse_snapshot,
    utc_now,
)

DEFAULT_COHORT_ROOT = Path(
    "/srv/agentsociety/examples/v2/elder_support/"
    "supplements/20261021/astra_router_v1"
)
DEFAULT_OUTPUT = Path("/var/lib/elder-support-remote-status/status.json")
METRICS_REL = Path("env/ElderSupportEnv/state/metrics.jsonl")
SUCCESS_RE = re.compile(
    r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] INFO\s+Experiment completed successfully$"
)
CHAIN_EVENT_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z "
    r"(?:(start|done|FAILED) (none_s1|casework_s1|timebank_s1|platform_s1)\b|"
    r"(chain finished)\b)"
)
EMBEDDING_WARNING = "protocol_not_allowed"


class CollectionError(RuntimeError):
    pass


def _read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise CollectionError(f"non-UTF-8 input: {path.name}") from exc
    except OSError as exc:
        raise CollectionError(f"cannot read {path.name}") from exc


def read_metrics(path: Path) -> tuple[int, int | None, datetime | None]:
    if not path.is_file():
        return 0, None, None
    months: list[int] = []
    for line_number, raw in enumerate(_read_lines(path), 1):
        if not raw.strip():
            raise CollectionError(f"blank metrics line {line_number}")
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CollectionError(f"invalid metrics JSON line {line_number}") from exc
        if not isinstance(row, dict) or type(row.get("month")) is not int:
            raise CollectionError(f"missing integer month on metrics line {line_number}")
        month = row["month"]
        if not 0 <= month <= 24:
            raise CollectionError(f"out-of-range month {month}")
        months.append(month)
    expected = list(range(len(months)))
    if months != expected:
        raise CollectionError(f"metrics months must be contiguous from zero: {months}")
    if len(months) > EXPECTED_MONTHS:
        raise CollectionError("too many metrics rows")
    mtime = datetime.fromtimestamp(path.stat().st_mtime, UTC) if months else None
    return len(months), months[-1] if months else None, mtime


def read_proc_argv(proc_root: Path) -> list[list[str]]:
    rows: list[list[str]] = []
    try:
        entries = list(proc_root.iterdir())
    except OSError as exc:
        raise CollectionError("cannot inspect process table") from exc
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            raw = (entry / "cmdline").read_bytes()
        except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
            continue
        if not raw:
            continue
        rows.append([part.decode("utf-8", errors="surrogateescape") for part in raw.split(b"\0") if part])
    return rows


def _run_dir_arg(argv: list[str]) -> str | None:
    if "-m" not in argv:
        return None
    module_index = argv.index("-m")
    if module_index + 1 >= len(argv) or argv[module_index + 1] != "agentsociety2.society.cli":
        return None
    indices = [i for i, value in enumerate(argv) if value == "--run-dir"]
    if len(indices) != 1 or indices[0] + 1 >= len(argv):
        return None
    return argv[indices[0] + 1]


def inspect_processes(proc_root: Path, cohort_root: Path) -> tuple[dict[str, bool], bool]:
    matches = {name: 0 for name in CONDITION_ORDER}
    chain_matches = 0
    resolved_root = cohort_root.resolve()
    expected_chain = str(resolved_root / "chain.sh")
    for argv in read_proc_argv(proc_root):
        run_arg = _run_dir_arg(argv)
        if run_arg is not None:
            try:
                run_dir = Path(run_arg).resolve(strict=False)
            except OSError:
                continue
            for name in CONDITION_ORDER:
                if run_dir == resolved_root / name:
                    matches[name] += 1
        if any(value == expected_chain for value in argv):
            chain_matches += 1
    conflicts = [name for name, count in matches.items() if count > 1]
    if conflicts:
        raise CollectionError(f"multiple CLI processes for {', '.join(conflicts)}")
    if chain_matches > 1:
        raise CollectionError("multiple queue controller processes")
    return {name: count == 1 for name, count in matches.items()}, chain_matches == 1


def read_chain(path: Path) -> tuple[dict[str, str], bool]:
    latest: dict[str, str] = {}
    finished = False
    if not path.is_file():
        return latest, finished
    for raw in _read_lines(path):
        match = CHAIN_EVENT_RE.match(raw)
        if not match:
            continue
        event, name, chain_finished = match.groups()
        if chain_finished:
            finished = True
        elif name and event:
            latest[name] = event.lower()
    return latest, finished


def _has_success_log(lines: list[str]) -> bool:
    return any(SUCCESS_RE.fullmatch(line) for line in lines)


def collect_snapshot(
    cohort_root: Path,
    proc_root: Path = Path("/proc"),
    *,
    now: datetime | None = None,
    stall_seconds: int = 20 * 60,
) -> RemoteStatusSnapshot:
    root = cohort_root.resolve()
    if not root.is_dir():
        raise CollectionError("cohort root is missing")
    now = now or utc_now()
    if now.tzinfo is None:
        raise CollectionError("collection time must be timezone-aware")
    processes, chain_alive = inspect_processes(proc_root, root)
    chain_events, chain_finished = read_chain(root / "chain.log")
    conditions: list[ConditionStatus] = []
    active_names = [name for name, running in processes.items() if running]
    if len(active_names) > 1:
        raise CollectionError("multiple cohort conditions are active")
    active = active_names[0] if active_names else None
    active_index = CONDITION_ORDER.index(active) if active else None

    for index, name in enumerate(CONDITION_ORDER):
        run_dir = root / name
        observed, latest, progressed_at = read_metrics(run_dir / METRICS_REL)
        output_lines = _read_lines(run_dir / "output.log") if (run_dir / "output.log").is_file() else []
        success = _has_success_log(output_lines)
        chain_event = chain_events.get(name)
        complete = not processes[name] and observed == EXPECTED_MONTHS and success and chain_event == "done"
        warnings: list[WarningCode] = []
        if any(EMBEDDING_WARNING in line for line in output_lines):
            warnings.append(WarningCode.EMBEDDING_PROTOCOL_DEGRADED)

        if complete:
            state = ConditionState.COMPLETED
            evidence = "verified"
        elif processes[name]:
            evidence = "incomplete"
            if observed == 0:
                state = ConditionState.STARTING
            elif progressed_at and (now - progressed_at).total_seconds() > stall_seconds:
                state = ConditionState.STALLED
                warnings.append(WarningCode.PROGRESS_STALLED)
            else:
                state = ConditionState.RUNNING
        elif chain_event == "failed":
            state = ConditionState.FAILED
            evidence = "incomplete"
            if observed < EXPECTED_MONTHS:
                warnings.append(WarningCode.PROCESS_EXITED_INCOMPLETE)
        elif observed == EXPECTED_MONTHS and success:
            state = ConditionState.UNKNOWN
            evidence = "incomplete"
            warnings.append(WarningCode.COMPLETION_EVIDENCE_MISSING)
        elif chain_alive and active_index is not None and index > active_index and observed == 0:
            state = ConditionState.QUEUED
            evidence = "incomplete"
            warnings.append(WarningCode.NOT_STARTED)
        else:
            state = ConditionState.UNKNOWN
            evidence = "incomplete"
            if observed and observed < EXPECTED_MONTHS:
                warnings.append(WarningCode.PROCESS_EXITED_INCOMPLETE)
            elif observed == 0:
                warnings.append(WarningCode.NOT_STARTED)

        conditions.append(
            ConditionStatus(
                name=name,
                state=state,
                observed_months=observed,
                latest_month=latest,
                last_progress_at=progressed_at,
                completion_evidence=evidence,
                warnings=list(dict.fromkeys(warnings)),
            )
        )

    remaining = [
        item.name
        for item in conditions
        if item.state in {ConditionState.QUEUED, ConditionState.STARTING}
    ]
    if active:
        queue_state = QueueState.ACTIVE
    elif chain_finished and all(item.state == ConditionState.COMPLETED for item in conditions):
        queue_state = QueueState.COMPLETED
    elif any(item.state == ConditionState.FAILED for item in conditions):
        queue_state = QueueState.FAILED
    elif remaining:
        queue_state = QueueState.QUEUED
    else:
        queue_state = QueueState.UNKNOWN
    return RemoteStatusSnapshot(
        collected_at=now,
        queue=QueueStatus(
            state=queue_state,
            active_condition=active,
            remaining_conditions=remaining,
        ),
        conditions=conditions,
    )


def atomic_write_snapshot(snapshot: RemoteStatusSnapshot, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = snapshot.canonical_json().encode("utf-8")
    parse_snapshot(payload)
    fd, temporary = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    temp_path = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        parse_snapshot(temp_path.read_bytes())
        os.replace(temp_path, output)
        os.chmod(output, 0o644)
        directory_fd = os.open(output.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort-root", type=Path, default=DEFAULT_COHORT_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--proc-root", type=Path, default=Path("/proc"), help=argparse.SUPPRESS)
    parser.add_argument("--stall-seconds", type=int, default=20 * 60)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.stall_seconds < 1:
        raise SystemExit("--stall-seconds must be positive")
    snapshot = collect_snapshot(
        args.cohort_root,
        args.proc_root,
        stall_seconds=args.stall_seconds,
    )
    atomic_write_snapshot(snapshot, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
