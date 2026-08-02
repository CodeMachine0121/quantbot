# quantbot/infrastructure/configuration/yaml_pipeline_configuration_loader.py
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from quantbot.domain.values.instrument import Instrument
from quantbot.domain.values.market import Market
from quantbot.domain.values.pipeline_configuration import PipelineConfiguration
from quantbot.domain.values.timeframe import Timeframe


class YamlPipelineConfigurationLoader:
    """把 YAML 讀成 PipelineConfiguration。

    YAML 的長相是 infrastructure 的細節；domain 只認得 PipelineConfiguration
    這個值物件。所以要換成 TOML 或環境變數，只要多寫一個 loader。
    """

    def load(self, path: Path) -> PipelineConfiguration:
        document = yaml.safe_load(path.read_text())
        defaults = document["defaults"]
        market = Market(defaults["market"])

        instruments = tuple(
            Instrument(
                symbol=entry["symbol"],
                market=market,
                timeframe=Timeframe(timeframe_value),
            )
            for entry in document["symbols"]
            for timeframe_value in entry["timeframes"]
        )
        crosscheck = document.get("crosscheck", {})

        return PipelineConfiguration(
            instruments=instruments,
            history_start=pd.Timestamp(defaults["start"], tz="UTC"),
            maximum_concurrency=defaults.get("max_concurrency", 4),
            cross_check_tolerance=crosscheck.get("tolerance", 0.01),
            cross_check_sample_days=crosscheck.get("sample_days", 5),
        )
