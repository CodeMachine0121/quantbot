# quantbot/domain/features/feature_pipeline.py
from __future__ import annotations

import pandas as pd

from quantbot.domain.interfaces.feature import Feature
from quantbot.domain.values.market_input import MarketInput
from quantbot.domain.values.market_view import MarketView


class FeaturePipeline:
    """一組特徵，一次算完，交出一張對齊好的表。

    它負責四件事，而這四件事之前散在每個 notebook 與 entrypoint 裡各寫一次：

    1. **檢查原料**：算之前就確認每個特徵要的資料都在。缺了就報錯，NEVER 算出一整
       欄 NaN——那會跟暖機期混在一起，而兩者的處理方式完全不同。
    2. **算完 concat**：每個特徵回傳一條與 K 線同 index 的序列，所以橫向併起來就是
       一張特徵表。
    3. **暖機期**：切掉前面不能用的那幾根。這一步比看起來麻煩，見下面。
    4. **快取**：同一份資料、同一個特徵不重算。

    它是 domain service 的形狀（純計算、無 I/O），但它住在 features/ 而不是
    services/，因為它是特徵家族的一部分——要拿它去算東西的人會先找到 features/。
    """

    def __init__(self, features: tuple[Feature, ...]) -> None:
        if not features:
            raise ValueError("至少要有一個特徵")
        duplicated = self._duplicated_names(features)
        if duplicated:
            raise ValueError(f"特徵名稱重複：{duplicated}")
        self._features = features
        self._cache: dict[tuple[int, str], pd.Series] = {}

    @property
    def features(self) -> tuple[Feature, ...]:
        return self._features

    @property
    def required_inputs(self) -> frozenset[MarketInput]:
        """整條管線需要的原料，是每個特徵的聯集。"""
        return frozenset[MarketInput]().union(
            *(feature.required_inputs for feature in self._features)
        )

    @property
    def declared_warmup_bar_count(self) -> int:
        """所有特徵宣告的暖機期裡最長的那一個。

        它是**宣告值**，不是實際值。Day 12 的鐘點基準與 Day 14 的距離 POC 都答不出
        精確的根數（它們的暖機期取決於一天幾根，而那是 timeframe 的事），所以它們
        回的是下限。真正的暖機期由 NaN 決定，見 trimmed()。
        """
        return max(feature.warmup_bar_count for feature in self._features)

    def compute(self, view: MarketView) -> pd.DataFrame:
        """算出所有特徵，橫向併成一張表。索引與 K 線完全相同。"""
        self._ensure_inputs(view)
        columns = {
            feature.name: self._compute_one(feature, view) for feature in self._features
        }
        return pd.DataFrame(columns, index=view.candles.frame.index)

    def trimmed(self, view: MarketView) -> pd.DataFrame:
        """算完之後切掉暖機期。

        切法是「丟掉第一個所有欄位都有值的位置之前的所有列」，而不是
        `iloc[declared_warmup_bar_count:]`。兩個理由：

        - 宣告值只是下限（見 declared_warmup_bar_count），照它切會留下 NaN。
        - 有些特徵的 NaN 不在開頭。掛單簿只有錄製的那幾段有資料，所以 OBI 中間
          就是 NaN，而那不是暖機期——照 NaN 切會把整段資料切光。

        所以它用 first_valid_index 找那個位置，而中間的 NaN 保持原樣交給呼叫端。
        「哪些列可以用」是策略的決定（有些條件容忍缺值），不是管線的。
        """
        table = self.compute(view)
        start = table.dropna().first_valid_index()
        if start is None:
            return table.iloc[0:0]
        return table.loc[start:]

    def _compute_one(self, feature: Feature, view: MarketView) -> pd.Series:
        """快取的鍵是「這份 view 的身分」加「特徵的名字」。

        用 id(view) 而不是雜湊整張 DataFrame：後者要走過每一個值，對幾十萬列的資料
        來說比重算特徵還慢。代價是快取只在同一個 view 物件上有效——而那正是要的
        效果，因為 MarketView 是 frozen 的，同一個物件的內容不會變。
        """
        key = (id(view), feature.name)
        if key not in self._cache:
            self._cache[key] = feature.compute(view)
        return self._cache[key]

    def _ensure_inputs(self, view: MarketView) -> None:
        """缺原料就報錯，而且要指名是哪幾個特徵在要它。

        訊息裡的列舉一律轉成 str：MarketInput 是 StrEnum，但它在容器裡的 repr 是
        `<MarketInput.DEPTH: 'depth'>`，那對讀錯誤訊息的人沒有幫助。
        """
        missing = view.missing_inputs(self.required_inputs)
        if not missing:
            return

        blocked = {
            feature.name: sorted(
                str(item) for item in feature.required_inputs & missing
            )
            for feature in self._features
            if feature.required_inputs & missing
        }
        absent = ", ".join(sorted(str(item) for item in missing))
        raise ValueError(f"缺少原料：{absent}。需要它們的特徵：{blocked}")

    @staticmethod
    def _duplicated_names(features: tuple[Feature, ...]) -> list[str]:
        """同名的特徵會在 concat 之後互相蓋掉，所以建構時就擋。

        這件事很容易發生：兩個 `ema` 都用 period=12 就會同名，而使用者以為自己
        設了兩個不同的東西。
        """
        seen: set[str] = set()
        duplicated: list[str] = []
        for feature in features:
            if feature.name in seen:
                duplicated.append(feature.name)
            seen.add(feature.name)
        return duplicated
