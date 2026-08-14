# quantbot/domain/values/holding_rules.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HoldingRules:
    """出場與再進場的兩條時間規則。

    為什麼它們不是條件：條件吃的是特徵表，而特徵表裡沒有「這個部位已經抱了幾根」
    這一欄，也不可能有——那個數字取決於哪一根進場，而那是引擎解出來的結果。
    一個吃特徵表的函式算不出依賴自身輸出的東西，所以這兩條規則只能是引擎的行為。

    界線就畫在這裡：**條件負責看市場，這個值負責看部位。** 兩者混在一起的話，
    條件的契約（吃一張表、回一條布林序列）就守不住了。

    - maximum_holding_bars：抱超過這麼多根還沒等到出場條件就認錯離場。
    - cooldown_bars：出場之後這麼多根之內不准再進場。

    None 代表沒有這條限制。兩個都是 None 就是 unbounded()，也是 Day 16 的預設——
    今天的策略只靠條件出場，Day 18 的兩個策略才會把它們填起來。
    """

    maximum_holding_bars: int | None = None
    cooldown_bars: int | None = None

    def __post_init__(self) -> None:
        if self.maximum_holding_bars is not None and self.maximum_holding_bars < 1:
            raise ValueError(
                f"maximum_holding_bars 必須 >= 1，收到 {self.maximum_holding_bars}"
            )
        if self.cooldown_bars is not None and self.cooldown_bars < 1:
            raise ValueError(f"cooldown_bars 必須 >= 1，收到 {self.cooldown_bars}")

    @classmethod
    def unbounded(cls) -> HoldingRules:
        """沒有時間限制：抱到出場條件成立為止，出場後下一根就能再進。"""
        return cls()

    def describe(self) -> str:
        if self.maximum_holding_bars is None and self.cooldown_bars is None:
            return "無時間限制"
        parts = []
        if self.maximum_holding_bars is not None:
            parts.append(f"最多抱 {self.maximum_holding_bars} 根")
        if self.cooldown_bars is not None:
            parts.append(f"出場後冷卻 {self.cooldown_bars} 根")
        return "、".join(parts)
