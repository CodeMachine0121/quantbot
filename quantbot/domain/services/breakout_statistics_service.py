# quantbot/domain/services/breakout_statistics_service.py
from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from quantbot.domain.dto.breakout_statistics_report import (
    BreakoutStatisticsReportDto,
    ObservationContrastDto,
)
from quantbot.domain.services.breakout_labelling_service import (
    BreakoutLabellingService,
)
from quantbot.domain.values.breakout_label import BreakoutLabel


class BreakoutStatisticsService:
    """比較「守住」與「被打回來」兩組突破，在突破當下有什麼可觀察的差異。

    這個 service 的價值全在於它只吃**突破當下觀察得到**的量。標籤來自未來（那是
    BreakoutLabellingService 的工作），但拿來對照的每一個量都必須是當下就在手上的，
    否則這張表會變成一個華麗的同義反覆：用未來解釋未來。

    它不碰 I/O、不知道特徵怎麼算出來的，只吃兩張已經對齊好的表。
    """

    def summarize(
        self,
        labels: pd.DataFrame,
        observations: Mapping[str, pd.Series],
        *,
        horizon: int,
    ) -> BreakoutStatisticsReportDto:
        label_column = labels[BreakoutLabellingService.LABEL_COLUMN]
        held = label_column == BreakoutLabel.HELD.value

        return BreakoutStatisticsReportDto(
            event_count=len(labels),
            held_count=int(held.sum()),
            horizon=horizon,
            favourable_median=self._by_label(
                labels[BreakoutLabellingService.FAVOURABLE_COLUMN], held
            ),
            adverse_median=self._by_label(
                labels[BreakoutLabellingService.ADVERSE_COLUMN], held
            ),
            contrasts=tuple(
                self._contrast(name, values.reindex(labels.index), held)
                for name, values in observations.items()
            ),
        )

    @staticmethod
    def _by_label(values: pd.Series, held: pd.Series) -> Mapping[str, float]:
        return {
            BreakoutLabel.HELD.value: float(values.loc[held].median()),
            BreakoutLabel.FAILED.value: float(values.loc[~held].median()),
        }

    @staticmethod
    def _contrast(
        name: str, values: pd.Series, held: pd.Series
    ) -> ObservationContrastDto:
        return ObservationContrastDto(
            name=name,
            held_median=float(values.loc[held].median()),
            failed_median=float(values.loc[~held].median()),
        )
