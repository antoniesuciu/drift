"""Alpaca minute contracts using authored data only; sockets remain disabled."""

import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

import pytest
from helpers import day_candles

from drift.backtest.engine import make_instrument
from drift.data.alpaca import AlpacaClient, Credentials, Receipt, decode
from drift.data.equity import NVDA_2021_SPLIT, PilotRequest, Split, iso, normalize
from drift.data.equity_store import acquire, load, publish
from drift.data.model import DataError, canonical
from drift.strategies.calendar import SessionSpec

KEY, SECRET = "SYNTHETIC_KEY_A", "SYNTHETIC_SECRET_B"
NOW = datetime(2026, 10, 30, tzinfo=UTC)
DAYS = ("2021-07-16", "2021-07-19", "2021-07-20", "2021-07-21")


def receipt(stream, params, value):
    endpoint = "https://data.alpaca.markets/v2/stocks/bars"
    return Receipt(stream, params, canonical(value), NOW.isoformat(), {}, endpoint)


def fixture(request=None):
    request = request or PilotRequest()
    days = [d for d in DAYS if request.start <= d <= request.end]
    result = [
        receipt(
            "calendar",
            {"start": request.start, "end": request.end, "date_type": "TRADING"},
            [{"date": d, "open": "09:30", "close": "16:00"} for d in days],
        ),
        receipt(
            "asset",
            {"symbol": "NVDA"},
            {"symbol": "NVDA", "class": "us_equity", "exchange": "NASDAQ", "id": "synthetic-asset"},
        ),
    ]
    for day in days:
        bars = []
        for c in day_candles(day, default="800.0001" if day < "2021-07-20" else "200.0001"):
            bars.append(
                {
                    "t": iso(c.start),
                    "o": str(c.open),
                    "h": str(c.high),
                    "l": str(c.low),
                    "c": str(c.close),
                    "v": c.volume,
                }
            )
        result.append(
            receipt(
                "bars",
                request.query(SessionSpec(day)),
                {"bars": {"NVDA": bars}, "next_page_token": None},
            )
        )
    return result


class Clock:
    elapsed = 0.0

    def sleep(self, delay):
        self.elapsed += delay


class Reply(BytesIO):
    status = 200

    def __init__(self, url, value, headers=None):
        super().__init__(canonical(value))
        self.url, self.headers = url, headers or {}

    def geturl(self):
        return self.url


def client(opener, **kwargs):
    clock = Clock()
    c = AlpacaClient(
        Credentials(KEY, SECRET),
        opener=opener,
        clock=lambda: clock.elapsed,
        sleep=clock.sleep,
        now=lambda: NOW,
        **kwargs,
    )
    return c, clock


def test_literal_credentials_redacted_and_not_shell_evaluated(tmp_path):
    env = tmp_path / ".env"
    env.write_text(f'export ALPACA_API_KEY="{KEY}"\nALPACA_SECRET_KEY={SECRET}\n')
    credentials = Credentials.read(env)
    assert credentials == Credentials(KEY, SECRET)
    assert KEY not in repr(credentials) and SECRET not in repr(credentials)
    for body in (
        f"ALPACA_API_KEY=$(touch {tmp_path / 'executed'})",
        "ALPACA_PAPER=false",
        f"ALPACA_API_KEY={KEY}\nAPCA_API_KEY_ID=DIFFERENT_KEY\nALPACA_SECRET_KEY={SECRET}",
    ):
        env.write_text(body)
        with pytest.raises(DataError):
            Credentials.read(env)
    assert not (tmp_path / "executed").exists()


def test_get_only_explicit_feed_and_decimal_safe_response():
    seen = []

    def opener(req, timeout):
        seen.append(req)
        assert req.method == "GET" and req.data is None
        assert req.get_header("Apca-api-key-id") == KEY
        assert SECRET not in req.full_url
        return Reply(
            req.full_url,
            {"bars": {}, "next_page_token": None},
            {"X-Request-ID": "synthetic", "Authorization": SECRET},
        )

    c, _ = client(opener)
    r = c.get("bars", PilotRequest().query(SessionSpec(DAYS[0])))
    assert "authorization" not in r.headers
    assert parse_qs(urlparse(seen[0].full_url).query)["feed"] == ["sip"]
    assert decode(b'{"price":100.0001}')["price"] == Decimal("100.0001")
    for patch in (
        {"feed": "boats"},
        {"adjustment": "split"},
        {"timeframe": "1Day"},
        {"end": "2024-01-02T20:00:00Z"},
        {"secret": SECRET},
    ):
        with pytest.raises(DataError):
            c.get("bars", PilotRequest().query(SessionSpec(DAYS[0])) | patch)
    with pytest.raises(DataError):
        c.get("orders", {})
    assert len(seen) == 1


@pytest.mark.parametrize("status", [301, 401, 403, 404, 422])
def test_http_errors_stop_without_reading_body_or_fallback(status):
    class Unread(BytesIO):
        def read(self, *args):
            raise AssertionError("error bodies must not be read")

    def opener(req, timeout):
        raise HTTPError(req.full_url, status, "sensitive diagnostics", {}, Unread())

    c, _ = client(opener)
    with pytest.raises(DataError, match=f"HTTP {status}"):
        c.pages(PilotRequest().query(SessionSpec(DAYS[0])))
    assert len(c.requests) == 1
    assert SECRET not in str(c.requests)


def test_short_pages_pagination_retries_and_shared_quota_budget():
    calls = []

    def opener(req, timeout):
        calls.append(req)
        if len(calls) == 1:
            raise HTTPError(req.full_url, 429, "rate limit", {"Retry-After": "2"}, BytesIO())
        token = "page-two" if len(calls) == 2 else None
        return Reply(req.full_url, {"bars": {}, "next_page_token": token})

    c, clock = client(opener)
    assert len(c.pages(PilotRequest().query(SessionSpec(DAYS[0])))) == 2
    assert clock.elapsed >= 2.5 and len(c.requests) == 3
    assert parse_qs(urlparse(calls[-1].full_url).query)["page_token"] == ["page-two"]
    c, _ = client(opener, max_requests=1)
    c.get("asset", {"symbol": "NVDA"})
    with pytest.raises(DataError, match="budget"):
        c.get("asset", {"symbol": "NVDA"})


@pytest.mark.parametrize(
    "value",
    [
        {"bars": {}},
        {"bars": {}, "next_page_token": "repeated"},
        {"bars": {}, "next_page_token": 7},
    ],
)
def test_pagination_missing_invalid_or_repeated_token_fails(value):
    c, _ = client(lambda req, timeout: Reply(req.full_url, value))
    with pytest.raises(DataError):
        c.pages(PilotRequest().query(SessionSpec(DAYS[0])))
    assert len(c.requests) <= 2


def test_network_and_cooldown_deadlines_are_bounded():
    def network(req, timeout):
        raise URLError(SECRET)

    c, _ = client(network, retries=1)
    with pytest.raises(DataError, match="diagnostics withheld") as error:
        c.get("asset", {"symbol": "NVDA"})
    assert len(c.requests) == 2 and SECRET not in str(error.value)
    c, _ = client(
        lambda req, timeout: Reply(
            req.full_url,
            {},
            {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(NOW.timestamp() + 70)},
        )
    )
    c.get("asset", {"symbol": "NVDA"})
    with pytest.raises(DataError, match="budget"):
        c.get("asset", {"symbol": "NVDA"})


def test_raw_split_boundary_and_closed_bar_availability():
    data, quality = normalize(PilotRequest(), fixture())
    assert len(data.candles) == 1560
    assert data.instrument.tick == Decimal("0.01") and data.instrument.precision == 4
    assert data.candles[0].close == Decimal("800.0001")
    assert data.candles[780].close == Decimal("200.0001")  # raw, not retrospectively adjusted
    assert data.candles[389].end == SessionSpec(DAYS[0]).close
    assert data.candles[389].available > SessionSpec(DAYS[0]).close
    assert all(not s["missing_starts"] for s in quality["sessions"])
    assert make_instrument(data.instrument).price_increment.as_decimal() == Decimal("0.01")
    assert NVDA_2021_SPLIT.ratio == 4
    for ratio in (Decimal(4), Decimal(10)):
        split = Split("2021-07-20", ratio, "2021-05-22T00:00:00Z", "synthetic-issuer")
        raw_previous, shares = Decimal(800), Decimal(3)
        assert (raw_previous / split.ratio) * (shares * split.ratio) == raw_previous * shares
    with pytest.raises(DataError):
        Split("2021-07-20", Decimal(4), "2021-07-20T14:00:00Z", "late")


def test_overlap_merges_provenance_conflict_rejects_and_gap_stays_unknown():
    req = PilotRequest(start=DAYS[0], end=DAYS[0])
    originals = fixture(req)
    r = originals[-1]
    value = json.loads(r.body)
    first, rest = value["bars"]["NVDA"][:2], value["bars"]["NVDA"][1:]
    a = receipt("bars", r.params, {"bars": {"NVDA": first}, "next_page_token": "p2"})
    b = receipt(
        "bars", r.params | {"page_token": "p2"}, {"bars": {"NVDA": rest}, "next_page_token": None}
    )
    data, quality = normalize(req, originals[:2] + [a, b])
    assert len(data.candles) == 390 and quality["identical_duplicates"] == 1
    rest[0]["c"] = "900"
    rest[0]["h"] = "900"
    conflict = receipt("bars", b.params, {"bars": {"NVDA": rest}, "next_page_token": None})
    with pytest.raises(DataError, match="conflicting"):
        normalize(req, originals[:2] + [a, conflict])
    value["bars"]["NVDA"].pop(5)
    _, quality = normalize(req, originals[:2] + [receipt("bars", r.params, value)])
    assert len(quality["sessions"][0]["missing_starts"]) == 1
    assert not quality["sessions"][0]["input_minutes_complete"]


@pytest.mark.parametrize(
    "patch",
    [
        {"t": "2021-07-16T20:00:00Z"},
        {"t": "2021-07-16T13:30:00.000000001Z"},
        {"v": True},
        {"v": "1.5"},
        {"v": "-1"},
        {"o": "NaN"},
        {"l": "0"},
        {"c": "800.00001"},
    ],
)
def test_invalid_minute_values_fail_closed(patch):
    req = PilotRequest(start=DAYS[0], end=DAYS[0])
    records = fixture(req)
    value = json.loads(records[-1].body)
    value["bars"]["NVDA"][0].update(patch)
    records[-1] = receipt("bars", records[-1].params, value)
    with pytest.raises(DataError):
        normalize(req, records)


def test_immutable_native_publication_replay_and_corruption(tmp_path):
    request = PilotRequest()
    root = publish(request, fixture(), tmp_path)
    data, manifest = load(root)
    assert len(data.candles) == 1560 and data.source_ref == root.name
    assert manifest["request"]["feed"] == "sip"
    assert publish(request, fixture(), tmp_path) == root
    iex = replace(request, feed="iex")
    other = publish(iex, fixture(iex), tmp_path)
    assert other != root and load(other)[0].sha256 != data.sha256
    target = root / manifest["receipts"][0]["file"]
    target.write_bytes(b"corrupt")
    with pytest.raises(DataError):
        load(root)


def test_acquisition_offline_and_resume_completed_requests(tmp_path):
    req = PilotRequest()
    records = fixture(req)
    calls = []

    def opener(request, timeout):
        calls.append(request)
        params = parse_qs(urlparse(request.full_url).query)
        if "/calendar" in request.full_url:
            r = records[0]
        elif "/assets/" in request.full_url:
            r = records[1]
        else:
            r = next(r for r in records[2:] if r.params["start"] == params["start"][0])
        return Reply(request.full_url, decode(r.body))

    c, _ = client(opener)
    root = acquire(req, c, tmp_path)
    assert len(calls) == 6
    assert len(load(root)[0].candles) == 1560
    c, _ = client(lambda *args, **kwargs: pytest.fail("completed requests must be reused"))
    assert acquire(req, c, tmp_path) == root
    assert len(list((tmp_path / "requests").rglob("attempt-*.json"))) == 2


def test_historical_backtest_native_engine_and_cli(tmp_path, monkeypatch, capsys):
    import sys

    from drift.__main__ import main
    from drift.backtest.config import BacktestConfig, default_config
    from drift.backtest.engine import run_on
    from drift.data.model import local_ns

    req = PilotRequest()
    records = fixture(req)
    for i, r in enumerate(records[2:], 2):
        value = json.loads(r.body)
        bars = value["bars"]["NVDA"]
        for index, move in ((29, 1), (359, 2)):
            bars[index]["c"] = bars[index]["h"] = str(Decimal(bars[index]["c"]) + move)
        records[i] = receipt("bars", r.params, value)
    root = publish(req, records, tmp_path)
    data, manifest = load(root)
    raw = default_config("itsm")
    raw.update(
        version=2,
        synthetic=False,
        name="synthetic-wire-pilot",
        instrument=manifest["instrument"],
        data={"dataset_id": root.name},
    )
    raw["strategy"]["params"] = {"allow_short": False, "splits": [["2021-07-20", "4"]]}
    config = BacktestConfig.parse(raw)
    result = run_on(config, data)
    assert result.reconciliation["ok"] and result.trades
    assert result.to_dict()["synthetic"] is False  # source mode, fixture prices are authored
    assert "bar-open fill proxies" in result.markdown()
    for trade in result.trades:
        day = next(s.day for s in data.calendar.sessions if s.open <= trade.entry_ts < s.close)
        assert trade.entry_ts == local_ns(day, "15:31")
        assert trade.exit_ts == local_ns(day, "15:59")
    path = tmp_path / "config.json"
    path.write_bytes(canonical(raw))
    monkeypatch.setattr(
        sys,
        "argv",
        ["drift", "backtest", "--config", str(path), "--dataset", str(root), "--json"],
    )
    main()
    report = json.loads(capsys.readouterr().out)
    assert report["results_sha256"] == result.results_sha256
    assert report["data"]["source_ref"] == root.name
    assert report["data"]["feed"] == "sip"
    raw["strategy"]["params"]["splits"] = []
    path.write_bytes(canonical(raw))
    with pytest.raises(SystemExit):
        main()
    assert "reviewed action evidence" in capsys.readouterr().err
    monkeypatch.setattr(
        sys,
        "argv",
        ["drift", "backtest", "--strategy", "itsm", "--dataset", str(root), "--dump-config"],
    )
    main()
    template = json.loads(capsys.readouterr().out)
    assert BacktestConfig.parse(template).data.dataset_id == root.name
    assert template["strategy"]["params"]["allow_short"] is False


def test_fetch_requires_authorization_before_reading_credentials(monkeypatch, capsys):
    import sys

    from drift.__main__ import main

    monkeypatch.setattr(Credentials, "read", lambda p: pytest.fail("must not access credentials"))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "drift",
            "alpaca-fetch",
            "--request",
            "none.json",
            "--output",
            "none",
            "--credentials-file",
            "none",
        ],
    )
    with pytest.raises(SystemExit):
        main()
    assert "--authorize-historical" in capsys.readouterr().err


def test_provider_calendar_dst_holiday_and_early_close():
    req = PilotRequest("2022-03-11", "2022-03-14")
    dates = [("2022-03-11", "16:00"), ("2022-03-14", "13:00")]
    records = [
        receipt(
            "calendar",
            {"start": req.start, "end": req.end, "date_type": "TRADING"},
            [{"date": d, "open": "09:30", "close": c} for d, c in dates],
        ),
        receipt(
            "asset",
            {"symbol": "NVDA"},
            {"symbol": "NVDA", "class": "us_equity", "exchange": "NASDAQ", "id": "synthetic"},
        ),
    ]
    for day, close in dates:
        bars = [
            {
                "t": iso(c.start),
                "o": str(c.open),
                "h": str(c.high),
                "l": str(c.low),
                "c": str(c.close),
                "v": c.volume,
            }
            for c in day_candles(day, close)
        ]
        records.append(
            receipt(
                "bars",
                req.query(SessionSpec(day, close)),
                {"bars": {"NVDA": bars}, "next_page_token": None},
            )
        )
    data, quality = normalize(req, records)
    assert iso(data.calendar.sessions[0].open).endswith("14:30:00Z")
    assert iso(data.calendar.sessions[1].open).endswith("13:30:00Z")
    assert [s["expected"] for s in quality["sessions"]] == [390, 210]
    assert not data.calendar.sessions[1].full
    assert len(data.calendar.sessions) == 2  # no weekend padding or inferred sessions


def test_failure_retains_raw_pages_without_publishing_and_resumes(tmp_path):
    req = PilotRequest(DAYS[0], DAYS[0])
    records = fixture(req)
    original = decode(records[-1].body)
    seen = []

    def opener(request, timeout):
        seen.append(request.full_url)
        if "/calendar" in request.full_url:
            return Reply(request.full_url, decode(records[0].body))
        if "/assets/" in request.full_url:
            return Reply(request.full_url, decode(records[1].body))
        if "page_token" in request.full_url:
            raise HTTPError(request.full_url, 403, "unavailable", {}, BytesIO())
        return Reply(request.full_url, original | {"next_page_token": "more"})

    c, _ = client(opener)
    with pytest.raises(DataError):
        acquire(req, c, tmp_path)
    assert not list(tmp_path.rglob("COMPLETE"))
    assert len(list((tmp_path / "requests").rglob("raw/*.json"))) == 3
    c, _ = client(lambda request, timeout: Reply(request.full_url, original))
    root = acquire(req, c, tmp_path)
    assert len(c.requests) == 1  # completed calendar/asset requests were retained
    assert len(load(root)[0].candles) == 390


def test_auth_echo_never_persisted_as_provenance():
    c, _ = client(lambda request, timeout: Reply(request.full_url, {"echo": SECRET}))
    with pytest.raises(DataError, match="evidence withheld"):
        c.get("asset", {"symbol": "NVDA"})
