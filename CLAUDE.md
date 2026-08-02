# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**quantbot** — 加密貨幣**量化交易研究與執行**的 Python 專案：把交易所的歷史與即時行情**正規化**後存進時序資料庫，計算指標與特徵，組合成可回測、可驗證的交易策略，最後走到自動下單與監控。核心立場：**每一個數字都要能被追溯與驗證**——每個主資料來源配一個對照組、每個計算配一份測試、每次執行留下一份可讀的報告。

本專案同時是 iThome 2026 鐵人賽系列文章《工程師的量化交易入門：從 K 線到可組合的交易策略引擎》的實作專案。文章與程式碼是同一件事的兩面：

- 文章原始碼在 `~/workspace/CodeMachine0121.github.io/src/content/blogs/ithome/2026-02/`。
- **文章裡的程式碼與這個專案 MUST 一致**（類別名、模組路徑、依賴方向、命名）。一邊改了，另一邊要跟著改，不可漂移。
- 寫文章的程式碼時**以本專案的實際實作為準**；本檔的架構與命名規範就是雙方共用的那份契約。

## Tech Stack

| 層面 | 選型 | 角色 / 備註 |
| :--- | :--- | :--- |
| 語言 | **Python 3.14** | `requires-python = ">=3.14"`；型別標註為強制（見 Conventions） |
| 套件管理 | **uv** | `uv sync` / `uv run`；NEVER 用 pip / poetry / conda |
| 資料處理 | **pandas 3.x + numpy** | 行情資料一律 `DataFrame`／`Series`，UTC `DatetimeIndex`；**NEVER 用 for loop 遍歷 K 線** |
| HTTP | **httpx**（`AsyncClient`） | 批次檔下載與 REST 對照組。**NEVER 引入 aiohttp / requests**，同一專案只留一套 HTTP 客戶端 |
| 交易所 SDK | **ccxt**（`ccxt.async_support`） | REST 補洞與（第三階段）下單；統一介面，換交易所只換實作 |
| 資料庫 | **PostgreSQL + TimescaleDB** | hypertable 存 K 線；continuous aggregate 產生粗粒度 timeframe |
| DB 驅動 | **asyncpg** | 直接寫 SQL（無 ORM）；SQL **只允許出現在 `infrastructure/persistence/`** |
| 設定 | **pydantic-settings** | `quantbot/config.py` 的 `Settings`；密鑰一律從 `.env` 讀，NEVER 進版控 |
| 設定檔 | **PyYAML** | 管線要顧哪些交易對寫在 YAML，不寫在程式碼裡 |
| 落地格式 | **pyarrow / parquet** | 原始資料快取與封存；唯一真相來源是資料庫 |
| 視覺化 | **plotly** | 圖表一律在 `infrastructure/charting/`，domain 永不接觸 plotly |
| 測試 | **pytest + pytest-asyncio** | 黑箱測試放 `tests/`，鏡射套件結構 |
| 品質 | **ruff** ＋ **mypy** ＋ **import-linter** | 見 Enforcement；約束一律自動化，不靠人記 |
| 部署 | **單一 VPS + Docker Compose** | 不用 K8s、不用微服務 |

## Architecture — Clean / Onion Architecture

**依賴方向一律指向 domain（核心）；domain 不依賴任何人。**

```
   Entrypoint ───▶ Application ───▶ Domain ◀─── Infrastructure
   (CLI/組裝根)      (use cases)      (核心)      (Source/Repository/Parser/Renderer 實作)
                                        ▲
                        quantbot/domain/interfaces/ 放所有對外介面（一介面一檔）
```

- **Domain（核心）**：value object、entity、指標、**Domain Service**，以及**所有對外介面**（集中在 `quantbot/domain/interfaces/`，一檔一介面）。**domain NEVER import 其他層**——它不認識 httpx、ccxt、asyncpg、plotly。
- **Application** 依賴 domain：注入介面與 domain service，編排用例，回傳 DTO 或 entity。
- **Infrastructure** 依賴 domain 的**形狀**（value/entity），實作 domain 宣告的介面（DIP——細節依賴抽象）。因為介面是 `Protocol`（結構型），實作**不需要也不應該** import 介面本身。
- **Entrypoint**（`quantbot/entrypoints/*.py`）是**唯一**知道所有具體型別的地方：組裝依賴、跑用例、印報告、決定 exit code。
- 沒有 Controller 層（沒有 HTTP 對外服務）；CLI 就是 controller ＋ 組裝根。

### 介面用 Protocol，家族骨架用 ABC

Python 有兩種「介面」，用途不同，**NEVER 混用**：

| 機制 | 語意 | 對應 Go | 用在哪 |
| :--- | :--- | :--- | :--- |
| `typing.Protocol` | **結構型**：實作不繼承、不 import 抽象，型別檢查器在注入點驗證 | 就是 Go 的隱式介面 | **所有對外相依**：`CandleSource`、`CandleRepository`、`CandleParser`、`ReferencePriceSource`、`Clock` |
| `abc.ABC` ＋ `@abstractmethod` | **名義型**：實作必須繼承，可帶共用實作（template method） | Java/C# 的 `implements` | 同一家族要共用骨架：`Indicator` |

- 對外介面 **MUST** 是 `Protocol`，放 `domain/interfaces/`，**一個檔案一個 Protocol**。
- **NEVER 用 `@runtime_checkable` ＋ `isinstance` 驗介面**：它只比對方法名、不比對簽章，給的是假的安全感。相容性由 `mypy` 在組裝點檢查。
- `Indicator` 是 ABC（要強制 `name` 與 `_compute`、並共用 `compute()` 的契約），這是唯一的 ABC 家族。要新增一種指標就繼承它。
- **實例檔內 NEVER 宣告 Protocol**；介面只住在 `domain/interfaces/`。**不使用「port」一詞或資料夾。**

### Domain 內部結構

domain 只依「種類」分六個資料夾，不出現概念資料夾（不會有 `ingest/`、`backtest/`）：

- `values/` — value object：**frozen dataclass 或 StrEnum**，不可變、可有推導用的 property 與方法，但**沒有 I/O**。例：`Instrument`、`Timeframe`、`Market`、`TimeRange`、`CandleColumns`、`BackfillPlan`、`Gap`、`SourceKind`。
- `entities/` — 充血實體（含行為的類別）。例：`CandleSeries`（包住 `DataFrame`，負責去重、合併、切片、丟未收盤的那一根）。
- `indicators/` — `Indicator` ABC 與其子類別（`SMA`、`EMA`、`RSI`…）＋ `INDICATORS` 註冊表。指標是純計算，屬於 domain。
- `services/` — **Domain Service**：跨 value/entity 的計算與編排，**純函數性、無 I/O、不吃 `Protocol`**。命名 `XxxService`，**一個檔案一個 service 類別**。例：`BackfillPlanningService`、`SourceRoutingService`、`DataIntegrityService`、`CandleSanitationService`、`PriceCrossCheckService`。
- `dto/` — **只用於報告類回傳形狀**（`Dto` 後綴的 frozen dataclass）。例：`DataIntegrityReportDto`。行情資料**不轉 DTO**——它以 `CandleSeries` 跨層，因為主體是 `DataFrame`，每次轉一層是純儀式。
- `interfaces/` — 對外 `Protocol`，一檔一介面。

**呼叫鏈**：`Entrypoint → Application → (Domain Service ＋ 注入的 Protocol 實作) → Entity/Value → 回傳 Entity 或 Dto`。

**Domain Service 不吃 I/O 介面。** 要 I/O 的編排屬於 application；domain service 只吃已經在手上的資料，回傳值。這讓每個 service 都能用純資料 table-driven 測試，不需要任何替身。

## Engineering Conventions（強制）

### 命名

- **命名一律全名，禁止英文單字的縮寫。** `specification` 不寫 `spec`、`candles` 不寫 `df`、`relative_difference` 不寫 `rel_diff`、`semaphore` 不寫 `sem`、`configuration` 不寫 `cfg`、`directory` 不寫 `dir`。
- **例外只有領域縮寫與業界標準縮寫**，它們是正式用語不是省字：`OHLCV`、`SMA`、`EMA`、`RSI`、`UTC`、`CSV`、`URL`、`REST`、`API`、`SQL`、`DTO`、`DSN`、`HTTP`。這些可以直接當類別名（`SMA`、`RSI`）或欄名。
- Python 慣例大小寫：類別 `PascalCase`、函式／變數 `snake_case`、常數 `UPPER_SNAKE_CASE`、內部符號前綴 `_`。DB 表／欄 `snake_case` 全名。
- **介面命名抽象化，不綁實作技術；實作命名帶技術／來源前綴。**
  - 介面描述「能力／行為契約」，**不得**出現實作技術字眼，**且不加 `I` 前綴**（Python 的慣例是 `Iterable` 而不是 `IIterable`）。例：`CandleSource`、`CandleRepository`、`CandleParser`、`ReferencePriceSource`、`Clock`。
  - 實作以「**技術／來源前綴 ＋ 介面能力名**」命名，讓同一介面的多種後端一眼可辨：`BinanceArchiveCandleSource`、`BinanceRestCandleSource`、`TimescaleCandleRepository`、`BinanceCandleCsvParser`、`CoinGeckoReferencePriceSource`、`SystemClock`。
- **各層角色用固定後綴，且只有這七種**（NEVER 出現 `Manager` / `Handler` / `Helper` / `Utils` / `Processor`）：

  | 角色 | 後綴 | 層 |
  | :--- | :--- | :--- |
  | Domain service | `Service` | domain |
  | 用例 | `Application` | application |
  | 持久化 | `Repository` | infrastructure |
  | 外部資料拉取 | `Source` | infrastructure |
  | 位元組／外部格式轉領域形狀 | `Parser` | infrastructure |
  | 圖表輸出 | `Renderer` | infrastructure |
  | 保護性能力（限流、退避） | `Guard` | infrastructure |

- **一個 entity 對應一個 repository**：`CandleSeries` → `CandleRepository`。該 entity 的所有持久化（讀＋寫）都在它的 repository，不另立 `*Writer` / `*Reader`。
- **檔名 snake_case，且對齊其主要型別**：`candle_repository.py`（Protocol）、`timescale_candle_repository.py`（實作）、`binance_candle_csv_parser.py`、`backfill_planning_service.py`。

### 型別與資料

- **所有公開函式與方法 MUST 有完整型別標註**（參數與回傳值）。`mypy --strict` 是驗收條件。
- **禁用 `Any`、`object` 當逃生口，禁用反射式分派**（`getattr(self, name)()`）。需要多型時用 `Protocol` 或泛型；需要有限選項時用 `StrEnum`。
- **禁止「先宣告後賦值」**：不可先 `value: float` 之後才指派；`__init__` 內把所有欄位一次賦值完。
- **禁止可變的預設參數**（`list` / `dict` / `set`），也禁止在類別屬性上放可變預設；共用常數用 `ClassVar` ＋ 不可變型別（`tuple` / `frozenset` / `MappingProxyType`）。
- **浮點與精確數字的界線**：
  - **行情與指標路徑用 `float64`**（pandas 沒得選，且 TimescaleDB 對 float8 有專門的壓縮編碼）。
  - **帳務與下單數量用 `decimal.Decimal`**（餘額、已實現損益、委託數量與價格）。**NEVER 用 float 做帳**，DB 欄位對應 `NUMERIC`。
  - 兩者的轉換只在 `application` 邊界發生，並且要有測試釘住。
- **時間一律 tz-aware UTC。** 進資料庫、跨層傳遞、寫檔的時間戳 MUST 帶 UTC 時區；naive datetime 一律在邊界就擋掉並丟 `ValueError`。K 線的時間戳語意固定是**開盤時間**（`open_time`）。
- **「現在幾點」是注入的能力，不是隨手可取的全域。** 需要當下時間的程式碼 MUST 收 `Clock`（或一個 `now` 參數），NEVER 在 domain / application 內直接呼叫 `pd.Timestamp.now()` / `datetime.now()`。理由是可測試性：時間相關的判斷（這根收完了沒、批次檔上傳了沒）只要偷讀系統時間就再也寫不出可靠的測試。**只有 `entrypoints/` 與 `infrastructure/system_clock.py` 可以讀系統時間。**

### 行為擺放

- **計算行為掛在物件的方法上，禁止散落的 module-level 計算函式當「靜態工具」。** 屬於單一 value/entity 的計算放它自己的方法；跨多個物件的運算放 Domain Service。**單元測試與其 helper 除外。**
- **示範「錯誤寫法」的對照程式碼除外**（例如文章裡用來對比效能的迴圈版 `sma_loop`），但它 NEVER 進正式路徑。
- 交付物級別的程式碼一律收進類別。`entrypoints/` 的 `main()` 是唯一允許的 module-level 函式。

### 資料存取

- **SQL 字串只允許出現在 `infrastructure/persistence/`。** 其他任何層出現 SQL 都是缺陷。
- **表名／view 名若必須拼進 SQL，MUST 走白名單**（`frozenset` 常數）；其餘一切值用綁定參數（`$1`、`$2`）。
- **寫入一律冪等**：`candles` 的複合主鍵 `(symbol, market, timeframe, open_time)` ＋ `ON CONFLICT DO NOTHING`；批次寫入走 `COPY` 進暫存表再合併。
- **NEVER 寫入還沒收完的那一根 K 線**（`DO NOTHING` 會讓那個錯的收盤價永遠留著）。時間軸右端一律開區間。

## Enforcement（約束一律自動化）

尚未納入自動把關的規範視為**待補**，不視為已生效。

- **ruff** — 格式化 ＋ lint。啟用 `ANN`（缺型別標註）、`ARG`、`B`（bugbear，含可變預設）、`C4`、`E`、`F`、`I`（import 排序）、`N`（命名慣例）、`PD`（pandas-vet）、`RUF`、`SIM`、`UP`。
- **mypy `--strict`** — Protocol 相容性只有型別檢查器驗得出來，沒有它 `Protocol` 只是註解。
- **import-linter** — 把「依賴方向」變成 CI 會紅的東西。契約（寫在 `pyproject.toml`）：

  ```toml
  [[tool.importlinter.contracts]]
  name = "分層：依賴方向一律指向 domain"
  type = "layers"
  layers = ["quantbot.entrypoints", "quantbot.application", "quantbot.domain"]

  [[tool.importlinter.contracts]]
  name = "domain 不認識任何外部技術"
  type = "forbidden"
  source_modules = ["quantbot.domain"]
  forbidden_modules = ["httpx", "ccxt", "asyncpg", "plotly", "yaml", "quantbot.infrastructure"]
  ```

- **pytest** — `uv run pytest`；整合測試以 marker 分開，沒有連線字串時 skip 並印出原因，**不假裝通過**。

## Testing 策略（強制）

- **測試放 `tests/`，目錄鏡射 `quantbot/`**，一律**黑箱**：import 公開 API、只測公開行為。
- **Value object / Entity / Indicator**：直接 table-driven（`pytest.mark.parametrize`）。指標**MUST 有獨立實作的對照組**（照數學定義手寫的 `Reference*` 類別，只住在 `tests/`），並跟現成套件對數字；跨實作比對前要丟掉暖機期。
- **Domain Service**：**不做替身、不單獨 mock**。它沒有介面，以具體實例注入 application。
- **Application**：注入**真實的 domain service**，**只對最外層的 Protocol 做替身**，且替身一律用 `unittest.mock.create_autospec(CandleRepository, spec_set=True)`（簽章會被檢查）——**NEVER 手寫 fake 類別**。這樣測 application 會連帶測到 domain service 與 entity，是刻意的測試力度放大。
- **資料庫語意（冪等、交易、聚合正確性）不得以替身驗證。** 把寫入通道換成替身，驗到的只會是替身自己的行為。這類保證一律用**真 PostgreSQL 的整合測試**。
- **時間相關行為一律注入 `Clock` 或 `now` 參數來測**，不用 `freezegun` 這類 monkeypatch 系統時鐘的做法。

## Commands

```bash
uv sync                       # 安裝依賴（含 dev group）
uv run pytest                 # 全部單元測試
uv run pytest -m integration  # 整合測試（需真 PostgreSQL）
uv run pytest tests/domain/indicators/test_relative_strength_index.py::test_matches_reference
uv run ruff format . && uv run ruff check --fix .
uv run mypy quantbot
uv run lint-imports           # import-linter：檢查依賴方向
docker compose -f docker/docker-compose.yml up -d   # 起 TimescaleDB
uv run python -m quantbot.entrypoints.backfill_command --help
uv run python -m quantbot.entrypoints.ingest_pipeline_command
```

## Layout

```
quantbot/
├── config.py                          Settings（pydantic-settings）
├── domain/
│   ├── values/                        Instrument, Timeframe, Market, TimeRange,
│   │                                  CandleColumns, BackfillPlan, Gap, SourceKind
│   ├── entities/candle_series.py      CandleSeries（充血）
│   ├── indicators/                    Indicator(ABC), SMA, EMA, RSI,
│   │                                  WilderSmoother, CrossoverSignals, INDICATORS
│   ├── services/                      BackfillPlanningService, SourceRoutingService,
│   │                                  DataIntegrityService, CandleSanitationService,
│   │                                  PriceCrossCheckService
│   ├── dto/                           DataIntegrityReportDto, PriceCrossCheckReportDto
│   └── interfaces/                    CandleSource, CandleRepository, CandleParser,
│                                      ReferencePriceSource, Clock（一檔一 Protocol）
├── application/                       BackfillCandlesApplication, IngestPipelineApplication
├── infrastructure/
│   ├── binance/                       BinanceArchiveUrlBuilder, BinanceArchiveDownloader,
│   │                                  BinanceArchiveCandleSource, BinanceRestCandleSource,
│   │                                  BinanceCandleCsvParser, BinanceRateLimitGuard
│   ├── coingecko/                     CoinGeckoReferencePriceSource
│   ├── persistence/                   PostgresDatabase, TimescaleCandleRepository,
│   │                                  migrations/*.sql
│   ├── charting/                      Plotly*Renderer
│   ├── configuration/                 YamlPipelineConfigurationLoader
│   └── system_clock.py                SystemClock
├── entrypoints/                       backfill_command.py, ingest_pipeline_command.py（組裝根）
└── tests/                             鏡射上述結構的黑箱測試
```

## 現況（2026-08-02）

分層結構已就位，對應 iThome 系列 Day 01–08，四項檢查全過：

```
uv run pytest          67 passed, 2 skipped
uv run mypy            Success（strict，66 檔）
uv run lint-imports    3 contracts kept
uv run ruff check      All checks passed
```

Day 02 的舊模組（`quantbot/ingest/`、`quantbot/plotting.py`）已隨文章改寫一併移除，功能分別由
`infrastructure/binance/binance_candle_csv_parser.py`、`infrastructure/charting/plotly_candle_chart_renderer.py`
與 `entrypoints/fetch_candles_command.py` 接手。ruff 與 mypy 因此不再需要任何排除規則。

### 還沒落地的部分

- `infrastructure/persistence/migrations/*.sql` 與 `migrate.py`（Day 07 的內容）還沒寫，所以 `TimescaleCandleRepository` 目前沒有可以跑的資料庫 schema。
- `tests/infrastructure/persistence/` 的整合測試（真 PostgreSQL）還沒寫。**冪等、交易邊界、聚合正確性這三件事目前沒有任何測試在守**，這是現在最大的缺口，而且照本檔的測試策略，它們不能用替身驗。
- `entrypoints/backfill_command.py` 的 `--store` 選項（Day 07 驗收標準第 2 項）還沒接上 repository。
- Day 09 之後的內容（Tick／掛單簿、特徵管線、策略引擎、回測、下單）都還沒開始。
