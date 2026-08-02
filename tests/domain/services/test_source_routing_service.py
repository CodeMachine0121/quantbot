# tests/domain/services/test_source_routing_service.py
import pandas as pd

from quantbot.domain.services.source_routing_service import SourceRoutingService
from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market
from quantbot.domain.values.source_kind import SourceKind
from quantbot.domain.values.time_range import TimeRange
from quantbot.domain.values.timeframe import Timeframe

INSTRUMENT = Instrument(
    symbol="BTC/USDT", market=Market.SPOT, timeframe=Timeframe("1m")
)
NOW = pd.Timestamp("2026-09-22 04:00", tz="UTC")


def test_routing_sends_new_data_to_rest():
    period = TimeRange(pd.Timestamp("2026-09-22 02:00", tz="UTC"), NOW)
    instructions = SourceRoutingService().route(period, now=NOW)

    assert [i.source_kind for i in instructions] == [SourceKind.REST]


def test_routing_sends_short_gaps_to_rest_even_when_old():
    period = TimeRange(
        pd.Timestamp("2026-09-20 11:07", tz="UTC"),
        pd.Timestamp("2026-09-20 11:12", tz="UTC"),
    )
    instructions = SourceRoutingService().route(period, now=NOW)

    assert [i.source_kind for i in instructions] == [SourceKind.REST]


def test_routing_splits_a_long_gap_into_archive_then_rest():
    period = TimeRange(pd.Timestamp("2026-06-01", tz="UTC"), NOW)
    instructions = SourceRoutingService().route(period, now=NOW)

    assert [i.source_kind for i in instructions] == [
        SourceKind.ARCHIVE,
        SourceKind.REST,
    ]
    # 兩段必須首尾相接，不重疊也不留洞
    assert instructions[0].period.end == instructions[1].period.start
    assert instructions[1].period.end == period.end


def test_routing_returns_nothing_for_an_empty_period():
    empty = TimeRange(NOW, NOW)
    assert SourceRoutingService().route(empty, now=NOW) == ()
