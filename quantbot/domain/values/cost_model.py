# quantbot/domain/values/cost_model.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostModel:
    """一趟交易要付出的比例成本。

    兩個欄位分開，因為它們的來源完全不同：手續費是交易所公告的數字（查得到、
    固定），滑價是市場給的（估出來的、會變）。混成一個「交易成本 0.1%」看起來省事，
    但那樣就沒辦法回答「手續費降到 VIP 等級之後這個策略成不成立」。

    **一律用 taker 費率。** 積木庫產生的訊號是「這一根收盤價成交」，而要保證成交
    只能用市價單，那就是 taker。maker 費率比較便宜，但掛單有可能不成交——一個
    「掛不到就不進場」的策略跟回測算的完全是兩件事。maker_fee_rate 留在這裡是為了
    Day 20 的敏感度分析（如果改成掛單策略，成本會差多少），NEVER 用它算主線回測。

    比例而不是金額：金額要知道部位大小，而部位大小是 Day 24 的事。這一階段的
    回測是滿倉進出，所以成本就是名目金額的一個比例。

    帳務用 Decimal、行情用 float64 是本專案的規矩，而這裡是**研究路徑**：權益曲線
    是統計量不是帳本，所以用 float64。真的要下單記帳（Day 23 之後）時，
    金額換成 Decimal，轉換發生在 application 邊界。
    """

    taker_fee_rate: float = 0.001
    slippage_rate: float = 0.0005
    maker_fee_rate: float = 0.001

    def __post_init__(self) -> None:
        for name in ("taker_fee_rate", "slippage_rate", "maker_fee_rate"):
            value = getattr(self, name)
            if value < 0.0:
                raise ValueError(f"{name} 不能是負數，收到 {value}")

    @classmethod
    def frictionless(cls) -> CostModel:
        """完全沒有成本。

        它是**理想回測**，用來當對照組而不是結論。理想回測的三個假設——能用收盤價
        成交、不用付錢、想買多少有多少——三個都是假的，Day 20 會逐一把它們加回去。
        """
        return cls(taker_fee_rate=0.0, slippage_rate=0.0, maker_fee_rate=0.0)

    @property
    def one_way_rate(self) -> float:
        """單邊（進場或出場其中一次）的成本比例。

        手續費與滑價相加。滑價在買進時讓成交價變高、賣出時變低，兩邊都是損失，
        所以它跟手續費一樣是單邊各付一次。
        """
        return self.taker_fee_rate + self.slippage_rate

    @property
    def round_trip_rate(self) -> float:
        """一買一賣的來回成本。策略要先賺贏這個數字才有得談。"""
        return 2.0 * self.one_way_rate

    def describe(self) -> str:
        if self.one_way_rate == 0.0:
            return "無成本（理想回測）"
        return (
            f"taker {self.taker_fee_rate:.4%} ＋ 滑價 {self.slippage_rate:.4%}"
            f"，來回 {self.round_trip_rate:.4%}"
        )
