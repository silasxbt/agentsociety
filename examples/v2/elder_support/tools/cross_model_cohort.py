#!/usr/bin/env python3
"""Prepare an immutable eight-run cohort; report descriptive paired sensitivity.

Standard library only. Never calls a model API or overwrites run directories.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from compare_conditions import validate, trace_stats

CONDITIONS = ("none", "casework", "timebank", "platform")
SEEDS = (1, 2)
METRICS = ("isolation_rate", "avg_loneliness", "deep_isolation_rate", "avg_active_ties")
DEFAULT_MODEL = "gpt-6-astra"
DEFAULT_EFFORT = "medium"
DEFAULT_PROVIDER = "openai"
DEFAULT_API_BASE = "https://tokenflux.dev/v1"
DEFAULT_COHORT = "astra6_medium_20261019"


def read_lines(path):
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(baseline, output, *, model=DEFAULT_MODEL, reasoning_effort=DEFAULT_EFFORT,
            provider=DEFAULT_PROVIDER, api_base=DEFAULT_API_BASE,
            cohort=DEFAULT_COHORT, seeds=SEEDS):
    # Preflight all inputs before creating anything. Never reuse an old pilot.
    if output.exists():
        raise ValueError(f"Refusing to overwrite existing cohort: {output}")
    for condition in CONDITIONS:
        for seed in seeds:
            for name in ("init_config.json", "steps.yaml"):
                if not (baseline / f"{condition}_s{seed}" / name).is_file():
                    raise ValueError(f"Missing source: {condition}_s{seed}/{name}")
    output.mkdir(parents=True)
    for condition in CONDITIONS:
        for seed in seeds:
            source = baseline / f"{condition}_s{seed}"
            target = output / source.name
            target.mkdir()
            hashes = {}
            for name in ("init_config.json", "steps.yaml"):
                (target / name).write_bytes((source / name).read_bytes())
                hashes[name] = digest(target / name)
            manifest = dict(cohort=cohort, condition=condition,
                            seed=seed, model=model, reasoning_effort=reasoning_effort,
                            provider=provider, api_base=api_base, months=24,
                            config_hashes=hashes, baseline_source=str(source.resolve()),
                            prepared_at=datetime.now(timezone.utc).isoformat(),
                            status="prepared_not_started")
            (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def summarize(run):
    if not run.is_dir():
        return {"valid": False, "reasons": ["missing run"], "outcomes": {}}
    try:
        metrics = read_lines(run / "env/ElderSupportEnv/state/metrics.jsonl")
        decisions = read_lines(run / "env/ElderSupportEnv/state/decisions.jsonl")
        for trace in (run / "trace").glob("trace_*.jsonl"):
            read_lines(trace)  # fail closed on corruption; legacy reader skips it
        gate = validate(run)
        traces = trace_stats(run)
        reasons = list(gate["reasons"])
        if (run / "INVALID").exists():
            reasons.append("explicit INVALID marker")
        if traces["error_rate"] is not None and traces["error_rate"] > .05:
            reasons.append("completion error rate >5%")
        if not traces["calls"]:
            reasons.append("missing completion traces")
        config = json.loads((run / "init_config.json").read_text())
        elders = config["env_modules"][0]["kwargs"]["elders"]
        focal = {e["id"] for e in elders if e.get("focal")}
        expected = {(a, m) for a in focal for m in range(25)}
        observed = {(r.get("agent_id"), r.get("month")) for r in decisions}
        missing = expected - observed
        fixed_silence = len(missing) / len(expected) if expected else None
        if fixed_silence is None or fixed_silence > .10:
            reasons.append("fixed-roster silence >10% or missing roster")
        if any(not math.isfinite(float(row[k])) for row in metrics for k in METRICS):
            reasons.append("non-finite metric")
        outcomes = {}
        for metric in METRICS:
            for phase, lo, hi in (("pre", 0, 6), ("iv", 7, 18), ("post", 19, 24)):
                values = [r[metric] for r in metrics if lo <= r["month"] <= hi]
                outcomes[f"{metric}_{phase}"] = sum(values) / len(values) if values else None
            a, b = outcomes[f"{metric}_iv"], outcomes[f"{metric}_post"]
            outcomes[f"{metric}_rebound"] = b - a if a is not None and b is not None else None
        return dict(valid=not reasons, legacy_valid=gate["valid"], reasons=reasons,
                    legacy_silence=gate["silence_rate"], fixed_roster_silence=fixed_silence,
                    missing_agent_months=sorted(missing), traces=traces,
                    config_hashes={n: digest(run / n) for n in ("init_config.json", "steps.yaml")},
                    outcomes=outcomes, monthly_metrics=metrics, decisions=decisions)
    except (ValueError, KeyError, TypeError, OSError) as error:
        return dict(valid=False, reasons=[f"data integrity: {error}"], outcomes={})


def _vs_none(runs_one_model, condition, seed, key):
    treat = runs_one_model[f"{condition}_s{seed}"]["outcomes"][key]
    none = runs_one_model[f"none_s{seed}"]["outcomes"][key]
    if treat is None or none is None:
        return None
    return treat - none


def report(baseline, cohort, extra_cohorts=None, seeds=SEEDS):
    """sol 读 baseline；其余模型读 cohort / extra_cohorts（label -> 目录）。

    默认仍产出 sol vs astra_medium 的差之差，以保持既有测试。额外模型写入
    runs 与 paired_contrasts[*].outcomes[<label>_vs_none]。
    """
    extra_cohorts = extra_cohorts or {}
    labeled = [("sol", baseline), ("astra_medium", cohort)]
    labeled.extend(extra_cohorts.items())
    runs = {label: {f"{c}_s{s}": summarize(root / f"{c}_s{s}")
                    for c in CONDITIONS for s in seeds}
            for label, root in labeled}
    contrasts = []
    for condition in CONDITIONS[1:]:
        for seed in seeds:
            selected = [runs[m][f"{c}_s{seed}"] for m, _ in labeled for c in (condition, "none")]
            matching = all(
                runs["sol"][f"{c}_s{seed}"].get("config_hashes")
                == runs[label][f"{c}_s{seed}"].get("config_hashes")
                for label, _ in labeled[1:]
                for c in (condition, "none")
            )
            row = dict(condition=condition, seed=seed,
                       eligible=all(r["valid"] for r in selected) and matching,
                       matching_configs=matching)
            if row["eligible"]:
                row["outcomes"] = {}
                for key in selected[0]["outcomes"]:
                    sol = _vs_none(runs["sol"], condition, seed, key)
                    astra = _vs_none(runs["astra_medium"], condition, seed, key)
                    entry = dict(sol_vs_none=sol, astra_vs_none=astra,
                                 difference_in_differences=(
                                     None if sol is None or astra is None else astra - sol
                                 ))
                    for label, _ in labeled[2:]:
                        entry[f"{label}_vs_none"] = _vs_none(runs[label], condition, seed, key)
                    row["outcomes"][key] = entry
            contrasts.append(row)
    return dict(runs=runs, paired_contrasts=contrasts,
                request_audit_status="NOT_VERIFIED: outcome eligibility is not proof of model identity or medium effort; review request audit before publication",
                note="Descriptive sensitivity; model plus reasoning configuration, not pure model causality. No significance test. Raw invalid data retained.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--baseline-dir", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--reasoning-effort", default=DEFAULT_EFFORT)
    p.add_argument("--provider", default=DEFAULT_PROVIDER, choices=("openai", "anthropic"))
    p.add_argument("--api-base", default=DEFAULT_API_BASE)
    p.add_argument("--cohort", default=DEFAULT_COHORT)
    p.add_argument("--seeds", default="1,2", help="逗号分隔的种子，例如 1,2,3")
    p = sub.add_parser("report")
    p.add_argument("--baseline-dir", type=Path, required=True)
    p.add_argument("--cohort-dir", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--extra-cohort", action="append", default=[],
                   metavar="LABEL=DIR", help="额外模型，可重复，如 label=/path")
    p.add_argument("--seeds", default="1,2")
    args = parser.parse_args()
    seeds = tuple(int(x) for x in args.seeds.split(",") if x.strip())
    if args.command == "prepare":
        prepare(args.baseline_dir, args.output_dir, model=args.model,
                reasoning_effort=args.reasoning_effort, provider=args.provider,
                api_base=args.api_base, cohort=args.cohort, seeds=seeds)
    else:
        extras = {}
        for item in args.extra_cohort:
            if "=" not in item:
                raise SystemExit("--extra-cohort 需要 LABEL=DIR")
            label, path = item.split("=", 1)
            extras[label] = Path(path)
        # Exclusive creation prevents accidentally replacing old evidence.
        with args.output.open("x") as handle:
            json.dump(report(args.baseline_dir, args.cohort_dir, extras, seeds), handle,
                      ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")


if __name__ == "__main__":
    main()
