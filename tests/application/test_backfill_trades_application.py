from unittest.mock import create_autospec

import numpy as np
import pandas as pd

from quantbot.application.backfill_trades_application import BackfillTradesApplication
from quantbot.domain.entities.trade_series import TradeSeries
from quantbot.domain.interfaces.candle_source import CandleSource
from quantbot.domain.interfaces.trade_repository import TradeRepository
from quantbot.domain.interfaces.trade_source import TradeSource
from quantbot.domain.services.candle_agreement_service import CandleAgreementService
from quantbot.domain.values.listing import Listing
from quantbot.domain.values.market import Market
from quantbot.domain.values.time_range import TimeRange
from quantbot.domain.values.timeframe import Timeframe
from quantbot.domain.values.trade_columns import TradeColumns

LISTING = Listing(symbol="BTC/USDT", market=Market.SPOT)
PERIOD = TimeRange(
    pd.Timestamp("2026-07-15T00:00:00Z"), pd.Timestamp("2026-07-15T00:05:00Z")
)


def make_trades(count: int = 120) -> TradeSeries:
    """五分鐘、每 2.5 秒一筆，價格走一段隨機路徑。"""
    generator = np.random.default_rng(20260923)
    prices = 65_000 * np.exp(np.cumsum(generator.normal(0, 0.0002, count)))
    index = pd.DatetimeIndex(
        PERIOD.start + pd.to_timedelta(np.arange(count) * 2.5, unit="s"),
        name=TradeColumns.TRANSACT_TIME,
    )
    trade_ids = np.arange(5_000, 5_000 + count)
    return TradeSeries(
        LISTING,
        pd.DataFrame(
            {
                TradeColumns.TRADE_ID: trade_ids,
                TradeColumns.FIRST_TRADE_ID: trade_ids,
                TradeColumns.LAST_TRADE_ID: trade_ids,
                TradeColumns.PRICE: prices,
                TradeColumns.QUANTITY: generator.uniform(0.001, 0.5, count),
                TradeColumns.BUYER_IS_MAKER: generator.random(count) < 0.5,
            },
            index=index,
        ),
    )


def build(trades: TradeSeries, *, official_from: TradeSeries | None = None):
    """組出用例。**注入真的 domain service**，只對最外層的 Protocol 做替身。

    official 預設就是「拿同一段成交自己聚合出來的 K 線」，也就是刻意讓對帳通過；
    要測不通過的情況時才傳一份被動過的。
    """
    source = create_autospec(TradeSource, spec_set=True, instance=True)
    source.load.return_value = trades

    repository = create_autospec(TradeRepository, spec_set=True, instance=True)
    repository.save.return_value = len(trades)

    candles = create_autospec(CandleSource, spec_set=True, instance=True)
    candles.load.return_value = (official_from or trades).aggregate_to_candles(
        Timeframe("1m")
    )

    application = BackfillTradesApplication(
        trades=source,
        repository=repository,
        candles=candles,
        agreement=CandleAgreementService(),
    )
    return application, source, repository, candles


async def test_reconciliation_passes_when_the_rebuild_matches():
    trades = make_trades()
    application, _, repository, _ = build(trades)

    report = await application.run(LISTING, PERIOD)

    assert report.fetched_row_count == 120
    assert report.written_row_count == 120
    assert report.missing_trade_id_count == 0
    assert report.agreement is not None
    assert report.agreement.compared_bar_count == 5
    assert report.passed
    repository.save.assert_awaited_once()


async def test_a_wrong_taker_side_is_caught_by_the_reconciliation():
    """把 buyer_is_maker 反過來，價格與成交量全對，只有兩個 taker 欄位會壞。

    這正是這道對帳存在的理由：taker 方向寫反不會影響任何一個價格欄位，
    所以沒有這道檢查的話，它會一路活到某個資金流特徵的正負號整批顛倒為止。
    """
    trades = make_trades()
    flipped = TradeSeries(
        LISTING,
        trades.frame.assign(
            **{TradeColumns.BUYER_IS_MAKER: ~trades.frame[TradeColumns.BUYER_IS_MAKER]}
        ),
    )
    application, _, _, _ = build(flipped, official_from=trades)

    report = await application.run(LISTING, PERIOD)

    assert report.agreement is not None
    assert not report.passed
    assert report.agreement.worst_column.startswith("taker_buy")
    assert report.agreement.maximum_relative_difference["close"] == 0.0


async def test_empty_period_reports_nothing_instead_of_failing():
    application, _, repository, candles = build(TradeSeries.empty(LISTING))

    report = await application.run(LISTING, PERIOD)

    assert report.fetched_row_count == 0
    assert report.agreement is None
    assert not report.passed  # 沒抓到資料 NEVER 算通過
    repository.save.assert_not_awaited()
    candles.load.assert_not_awaited()


async def test_rerun_writes_nothing_and_still_passes():
    """重跑同一天：抓到的還是一樣多，寫進去的是 0。冪等在報告上要看得出來。"""
    trades = make_trades()
    application, _, repository, _ = build(trades)
    repository.save.return_value = 0

    report = await application.run(LISTING, PERIOD)

    assert report.fetched_row_count == 120
    assert report.written_row_count == 0
    assert report.passed
