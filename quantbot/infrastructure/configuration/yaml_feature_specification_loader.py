# quantbot/infrastructure/configuration/yaml_feature_specification_loader.py
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import yaml

from quantbot.domain.values.feature_specification import FeatureSpecification


class YamlFeatureSpecificationLoader:
    """讀一份 YAML，變成一串 FeatureSpecification。

    格式刻意很淺——一個 features 清單，每項一個 kind 加上參數：

        features:
          - kind: ema
            period: 12
          - kind: rsi
            period: 14
          - kind: activity
            measure: trade_count
            window: 168

    參數跟 kind 平放在同一層，不另外包一層 parameters。理由是使用者要寫的東西越少
    越好，而 kind 是保留字這件事只要講一次。代價是「kind」不能當參數名，而那不是
    任何特徵需要的參數名。

    這個類別只負責「YAML 長得對不對」，NEVER 驗證參數的值——那是 builder 的事。
    分開的好處是錯誤訊息不會混在一起：格式錯誤說「第 3 項少了 kind」，
    參數錯誤說「aggregation 只能是 mean 或 last」。
    """

    def load(self, path: Path) -> tuple[FeatureSpecification, ...]:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(document, Mapping):
            raise ValueError(f"{path} 的最外層應該是一個對映")

        raw_features = document.get("features")
        if not isinstance(raw_features, Sequence) or isinstance(raw_features, str):
            raise ValueError(f"{path} 缺少 features 清單")

        return tuple(
            self._specification(entry, index)
            for index, entry in enumerate(raw_features, start=1)
        )

    @staticmethod
    def _specification(entry: object, index: int) -> FeatureSpecification:
        if not isinstance(entry, Mapping):
            raise ValueError(f"features 第 {index} 項應該是一個對映，實得 {entry!r}")
        if "kind" not in entry:
            raise ValueError(f"features 第 {index} 項少了 kind")

        parameters = {
            str(key): value for key, value in entry.items() if str(key) != "kind"
        }
        for key, value in parameters.items():
            if not isinstance(value, (int, float, str)) or isinstance(value, bool):
                raise ValueError(
                    f"features 第 {index} 項的 {key} 只能是數字或字串，實得 {value!r}"
                )

        return FeatureSpecification(kind=str(entry["kind"]), parameters=parameters)
