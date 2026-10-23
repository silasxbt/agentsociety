"""Strict public status protocol for the remote elder-support cohort."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = 1
COHORT = "astra_router_v1"
SOURCE_REGION = "kr"
CONDITION_ORDER = ("none_s1", "casework_s1", "timebank_s1", "platform_s1")
EXPECTED_MONTHS = 25


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConditionState(StrEnum):
    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    STALLED = "stalled"
    COMPLETED = "completed"
    FAILED = "failed"
    UNKNOWN = "unknown"


class QueueState(StrEnum):
    ACTIVE = "active"
    QUEUED = "queued"
    COMPLETED = "completed"
    FAILED = "failed"
    UNKNOWN = "unknown"


class WarningCode(StrEnum):
    EMBEDDING_PROTOCOL_DEGRADED = "embedding_protocol_degraded"
    COMPLETION_EVIDENCE_MISSING = "completion_evidence_missing"
    PROCESS_EXITED_INCOMPLETE = "process_exited_incomplete"
    PROGRESS_STALLED = "progress_stalled"
    NOT_STARTED = "not_started"


class ConditionStatus(StrictModel):
    name: Literal["none_s1", "casework_s1", "timebank_s1", "platform_s1"]
    seed: Literal[1] = 1
    state: ConditionState
    observed_months: int = Field(ge=0, le=EXPECTED_MONTHS)
    latest_month: int | None = Field(default=None, ge=0, le=24)
    last_progress_at: datetime | None = None
    completion_evidence: Literal["verified", "incomplete"] = "incomplete"
    warnings: list[WarningCode] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_progress(self) -> "ConditionStatus":
        expected_latest = self.observed_months - 1 if self.observed_months else None
        if self.latest_month != expected_latest:
            raise ValueError("latest_month must match contiguous observed_months")
        if self.state == ConditionState.COMPLETED:
            if self.observed_months != EXPECTED_MONTHS or self.completion_evidence != "verified":
                raise ValueError("completed requires 25 months and verified evidence")
        elif self.completion_evidence == "verified":
            raise ValueError("verified evidence is only valid for completed conditions")
        if self.state in {ConditionState.QUEUED, ConditionState.STARTING} and self.observed_months:
            raise ValueError("queued/starting conditions cannot contain metrics")
        return self


class QueueStatus(StrictModel):
    state: QueueState
    active_condition: Literal["none_s1", "casework_s1", "timebank_s1", "platform_s1"] | None = None
    remaining_conditions: list[
        Literal["none_s1", "casework_s1", "timebank_s1", "platform_s1"]
    ] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_queue(self) -> "QueueStatus":
        if self.state == QueueState.ACTIVE and self.active_condition is None:
            raise ValueError("active queue requires active_condition")
        if self.state != QueueState.ACTIVE and self.active_condition is not None:
            raise ValueError("inactive queue cannot have active_condition")
        if len(set(self.remaining_conditions)) != len(self.remaining_conditions):
            raise ValueError("remaining_conditions contains duplicates")
        return self


class RemoteStatusSnapshot(StrictModel):
    schema_version: Literal[1] = SCHEMA_VERSION
    cohort: Literal["astra_router_v1"] = COHORT
    source_region: Literal["kr"] = SOURCE_REGION
    collected_at: datetime
    queue: QueueStatus
    conditions: list[ConditionStatus]

    @model_validator(mode="after")
    def validate_snapshot(self) -> "RemoteStatusSnapshot":
        if self.collected_at.tzinfo is None:
            raise ValueError("collected_at must be timezone-aware")
        if [condition.name for condition in self.conditions] != list(CONDITION_ORDER):
            raise ValueError("conditions must use the fixed allowlist and order")
        names = set(CONDITION_ORDER)
        if self.queue.active_condition and self.queue.active_condition not in names:
            raise ValueError("unknown active condition")
        if any(name not in names for name in self.queue.remaining_conditions):
            raise ValueError("unknown queued condition")
        return self

    def canonical_json(self) -> str:
        return self.model_dump_json(indent=2) + "\n"


def parse_snapshot(data: bytes | str) -> RemoteStatusSnapshot:
    return RemoteStatusSnapshot.model_validate_json(data)


def utc_now() -> datetime:
    return datetime.now(UTC)
