"""Versioned strategy proposals (docs/ARCHITECTURE.md, schema v1). A proposal is never an order."""

import re
from dataclasses import dataclass
from enum import StrEnum

from drift.data.model import DataError

SCHEMA_VERSION = 1
FAMILIES = ("RULE", "ML", "LLM")
_ID = re.compile(r"[A-Za-z0-9_.:|+-]{1,160}")


class Intent(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"
    NO_TRADE = "NO_TRADE"


@dataclass(frozen=True, slots=True)
class Proposal:
    """Times are UTC nanoseconds. `reasons` carries stable codes for abstentions."""

    proposal_id: str
    agent_id: str
    strategy_id: str
    instrument_id: str
    generated_at: int
    data_asof: int
    valid_until: int
    horizon_seconds: int
    intent: Intent
    rule_version: str
    input_refs: tuple[str, ...]
    rationale: str
    reasons: tuple[str, ...] = ()
    family: str = "RULE"
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION or self.family not in FAMILIES:
            raise DataError("unsupported proposal schema or family")
        for value in (
            self.proposal_id,
            self.agent_id,
            self.strategy_id,
            self.instrument_id,
            self.rule_version,
            *self.input_refs,
        ):
            if not _ID.fullmatch(value):
                raise DataError("invalid proposal identifier")
        if not self.input_refs or not isinstance(self.intent, Intent):
            raise DataError("proposal needs lineage and a known intent")
        if not self.data_asof <= self.generated_at < self.valid_until:
            raise DataError("proposal clocks must satisfy asof <= generated < valid_until")
        if self.horizon_seconds < 0:
            raise DataError("negative horizon")

    def live_at(self, now: int) -> bool:
        return self.generated_at <= now < self.valid_until


def new_proposal(
    *,
    agent_id: str,
    strategy_id: str,
    instrument_id: str,
    version: str,
    generated_at: int,
    valid_seconds: int,
    horizon_seconds: int,
    intent: Intent,
    rationale: str,
    reasons: tuple[str, ...],
    refs: tuple[str, ...],
) -> Proposal:
    """Shared constructor for rules whose decision clock is one candle's availability."""
    return Proposal(
        f"{strategy_id}|{instrument_id}|{generated_at}|{intent}",
        agent_id,
        strategy_id,
        instrument_id,
        generated_at,
        generated_at,
        generated_at + valid_seconds * 1_000_000_000,
        horizon_seconds,
        intent,
        version,
        refs,
        rationale,
        tuple(sorted(set(reasons))),
    )
