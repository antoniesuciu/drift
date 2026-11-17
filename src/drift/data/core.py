"""Source-neutral normalization, coverage and as-of endpoint references."""

from dataclasses import asdict, replace
from decimal import Decimal, InvalidOperation
from typing import Any

from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.objects import Price, Quantity

from drift.data.model import MINUTE, Config, DataError, Observation, SourceBar, instant, local_ns


def normalize(config: Config, records: list[SourceBar]) -> tuple[list[Observation], int]:
    unique: dict[tuple[str, int], Observation] = {}
    duplicates = 0
    for r in records:
        try:
            prices = tuple(Decimal(p) for p in r.prices)
            if len(prices) != 4 or any(
                not p.is_finite() or p <= 0 or p % Decimal("0.25") for p in prices
            ):
                raise DataError("invalid normalized MES price")
            op, hi, lo, cl = prices
            if not lo <= min(op, cl) <= max(op, cl) <= hi:
                raise DataError("invalid normalized OHLC")
        except (InvalidOperation, TypeError):
            raise DataError("invalid normalized MES price") from None
        if type(r.volume) is not int or not 0 <= r.volume <= 2**63 - 1:
            raise DataError("invalid normalized contract volume")
        if r.contract not in config.contracts or type(r.start) is not int or r.start % MINUTE:
            raise DataError("invalid normalized identity/timestamp")
        end = r.start + MINUTE
        if (
            not config.start <= r.start < end <= config.end
            or not r.contract.activation <= r.start < end <= r.contract.expiration
        ):
            raise DataError("normalized observation outside request/contract bounds")
        session = config.session_for(r.start, end)
        row = Observation(
            r.contract.key,
            r.start,
            end,
            end + config.delay_ns,
            *r.prices,
            r.volume,
            session.day,
            (r.source_ref,),
        )
        key = (row.contract, row.start)
        prior = unique.get(key)
        if prior:
            if replace(prior, source_refs=()) != replace(row, source_refs=()):
                raise DataError("conflicting duplicate/revision; no dataset published")
            duplicates += 1
            unique[key] = replace(
                prior, source_refs=tuple(sorted(set(prior.source_refs + row.source_refs)))
            )
        else:
            unique[key] = row
    return sorted(unique.values(), key=lambda r: (r.available, r.contract, r.start)), duplicates


def native_bar(row: Observation) -> Bar:
    month = row.contract.rsplit(":", 1)[1]
    return Bar(
        BarType.from_str(f"MES-{month}.CME-1-MINUTE-LAST-EXTERNAL"),
        Price.from_str(row.open),
        Price.from_str(row.high),
        Price.from_str(row.low),
        Price.from_str(row.close),
        Quantity.from_int(row.volume),
        row.end,
        row.available,
    )


def snapshot(config: Config, rows: list[Observation], day: str, asof_ns: int) -> dict[str, Any]:
    """Only decision inputs; intentionally excludes future outcome/quality status."""
    session = next((s for s in config.sessions if s.day == day), None)
    if session is None:
        raise DataError("cash date not classified by calendar")
    selected = config.selected(day) if session.cash_close else None
    previous = next((s for s in reversed(config.sessions) if s.day < day and s.cash_close), None)
    reasons = []
    if session.cash_close is None:
        reasons.append("cash_closed")
    elif session.cash_close != "16:00":
        reasons.append("early_close")
    if previous is None:
        reasons.append("previous_session_unknown")
    elif previous.cash_close != "16:00":
        reasons.append("previous_early_close")
    if previous and selected and config.selected(previous.day).key != selected.key:
        reasons.append("roll_session")
    cut = local_ns(day, "15:30") + config.delay_ns
    decision = min(asof_ns, cut)
    lookup = {(r.contract, r.end): r for r in rows if r.available <= decision}
    values = {}
    if selected:
        refs = {
            "10:00": local_ns(day, "10:00"),
            "15:00": local_ns(day, "15:00"),
            "15:30": local_ns(day, "15:30"),
        }
        if previous and previous.cash_close == "16:00":
            refs["previous_close"] = local_ns(previous.day, "16:00")
        for name, end in refs.items():
            row = lookup.get((selected.key, end))
            if row is not None and row.volume > 0:
                values[name] = {
                    "close": row.close,
                    "end": row.end,
                    "available": row.available,
                    "contract": row.contract,
                }
            else:
                reasons.append(f"unavailable:{name}")
        # Only gaps already knowable by the decision cutoff can affect this snapshot.
        last = min(local_ns(day, "15:30"), decision - config.delay_ns)
        for end in range(local_ns(day, "09:30") + MINUTE, last + 1, MINUTE):
            tradable = any(a <= end - MINUTE < end <= b for a, b in session.intervals)
            if tradable and (selected.key, end) not in lookup:
                reasons.append("unknown_gap_before_decision")
                break
    return {
        "day": day,
        "asof_ns": decision,
        "contract": selected.key if selected else None,
        "inputs_ready": not reasons and len(values) == 4,
        "values": values,
        "reasons": sorted(set(reasons)),
    }


def coverage(config: Config, rows: list[Observation]) -> list[dict[str, Any]]:
    lookup = {(r.contract, r.end): r for r in rows}
    result = []
    for s in config.sessions:
        if not config.payload["study_start"] <= s.day <= config.payload["study_end"]:
            continue
        snap = snapshot(config, rows, s.day, local_ns(s.day, "15:30") + config.delay_ns)
        selected = config.selected(s.day) if s.cash_close else None
        expected = (
            []
            if not s.cash_close
            else list(
                range(local_ns(s.day, "09:30") + MINUTE, local_ns(s.day, s.cash_close) + 1, MINUTE)
            )
        )
        scheduled = [
            end for end in expected if not any(a <= end - MINUTE < end <= b for a, b in s.intervals)
        ]
        expected = sorted(set(expected) - set(scheduled))
        present = [end for end in expected if (selected.key, end) in lookup] if selected else []
        missing = sorted(set(expected) - set(present))
        target = lookup.get((selected.key, local_ns(s.day, "16:00"))) if selected else None
        result.append(
            {
                "day": s.day,
                "contract": selected.key if selected else None,
                "cash_close": s.cash_close,
                "expected_minutes": len(expected),
                "scheduled_closed_minutes": len(scheduled),
                "received_minutes": len(present),
                "unknown_gap_count": len(missing),
                "missing_end_ns": missing,
                "data_complete": not missing,
                "inputs_ready": snap["inputs_ready"],
                "input_reasons": snap["reasons"],
                "outcome_status": "observed"
                if target and target.volume > 0
                else "unresolved"
                if s.cash_close == "16:00"
                else "not_applicable",
            }
        )
    return result


def provenance(rows: list[Observation], source: dict[str, str]) -> list[dict[str, Any]]:
    return [
        {k: v for k, v in asdict(r).items() if k not in {"open", "high", "low", "close", "volume"}}
        | source
        | {
            "availability_kind": "modeled",
            "raw_label_ns": r.start,
            "utc_date": instant(r.start).date().isoformat(),
        }
        for r in rows
    ]


def endpoint_references(config: Config, rows: list[Observation]) -> list[dict[str, Any]]:
    """Audit keys, not features/orders. Targets are explicitly retrospective."""
    lookup = {(r.contract, r.end): r for r in rows}
    result = []
    for session in config.sessions:
        if not config.payload["study_start"] <= session.day <= config.payload["study_end"]:
            continue
        previous = next(
            (s for s in reversed(config.sessions) if s.day < session.day and s.cash_close), None
        )
        selected = config.selected(session.day) if session.cash_close else None
        for name in ("previous_close", "10:00", "15:00", "15:30", "16:00"):
            end = (
                (
                    local_ns(previous.day, "16:00")
                    if previous and previous.cash_close == "16:00"
                    else None
                )
                if name == "previous_close"
                else local_ns(session.day, name)
            )
            row = lookup.get((selected.key, end)) if selected and end is not None else None
            result.append(
                {
                    "day": session.day,
                    "name": name,
                    "role": "outcome" if name == "16:00" else "input",
                    "contract": selected.key if selected else None,
                    "reference_end_ns": end,
                    "available_at_ns": end + config.delay_ns if end is not None else None,
                    "present": row is not None and row.volume > 0,
                    "source_refs": list(row.source_refs) if row else [],
                }
            )
    return result
