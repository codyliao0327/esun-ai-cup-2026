Title: finlab.data API：data.get 資料下載、data.search 欄位搜尋與快取設定 - 量化交易工具文檔

URL Source: https://finlab.finance/docs/reference/data/

Markdown Content:
`finlab.data` 是 FinLab 的資料下載核心模組。最常用的流程是先用 `data.search()` 找到資料表欄位，再用 `data.get()` 下載資料，最後用 `data.universe()` 或 `data.set_market()` 控制市場範圍。

| 工作 | API | 常見用法 |
| --- | --- | --- |
| 下載股價、財報、月營收、籌碼資料 | `data.get()` | `data.get('price:收盤價')` |
| 搜尋資料表與欄位名稱 | `data.search()` | `data.search('ROE')` |
| 限定上市、上櫃、產業或美股成分股 | `data.universe()` / `data.us_universe()` | `with data.universe(market='TSE'):` |
| 控制下載速度與記憶體 | `truncate_start`、快取設定 | `data.truncate_start = '2020-01-01'` |

第一次使用請先讀[資料取得詳細說明](https://finlab.finance/docs/details/get_data/)；若要把資料轉成選股條件，接著看 [finlab.dataframe](https://finlab.finance/docs/reference/dataframe/)。

## 使用情境

*   下載股價、財報、籌碼等歷史資料
*   篩選特定市場或類股的資料
*   搜尋可用的資料表與欄位
*   設定資料快取策略
*   限制資料下載範圍以節省記憶體

## 快速範例

### 基本用法：下載資料

```
from finlab import data

# 下載收盤價
close = data.get('price:收盤價')

# 下載本益比
pe_ratio = data.get('price_earning_ratio:本益比')

# 下載月營收
revenue = data.get('monthly_revenue:當月營收')
```

### 台股 OHLCV 英文別名

預設台股市場或 `data.set_market("tw")` 下，以下英文 key 與既有中文 key 取得相同資料，並共用快取。`data.gets()`、`lazy=True` 與 `start`／`end` 日期篩選也支援這些別名。`volume` 是成交股數。

| 英文 key | 既有台股 key |
| --- | --- |
| `price:open` | `price:開盤價` |
| `price:high` | `price:最高價` |
| `price:low` | `price:最低價` |
| `price:close` | `price:收盤價` |
| `price:volume` | `price:成交股數` |

```
data.set_market("tw")
tw_close = data.get("price:close")
data.set_market("us")
us_close = data.get("price:close")
```

切換到美股後，`price:close` 仍取得美股收盤價。上述五個別名之外的欄位請使用原本的 key。

### 搜尋可用欄位

```
# 搜尋包含「收盤」的欄位
data.search('收盤')
# 輸出: ['price:收盤價', 'etl:不含除權息收盤價', ...]

# 搜尋美股資料
data.search('close', market='us')

# 搜尋美股 ETF / 基金資料
data.search('close', market='us_fund')
```

### 限制市場範圍

```
# 只取上市公司資料
with data.universe(market='TSE'):
    close = data.get('price:收盤價')

# 只取特定類股
with data.universe(category=['水泥工業', '食品工業']):
    close = data.get('price:收盤價')

# 切換到美股 ETF / 基金資料
data.set_market('us_fund')
fund_close = data.get('price:adj_close')
```

### 取消股票範圍篩選

用 `data.reset_universe()` 取消篩選。不帶任何篩選條件的 `data.set_universe()`、 `data.universe()` 與 `data.us_universe()` 效果相同，不會排除任何代號：

```
data.set_universe(sector='半導體業')
filtered = data.get('price:收盤價')
data.reset_universe()
unfiltered = data.get('price:收盤價')
```

重設會套用到後續的 `data.get()`、`data.gets()`，包含快取讀取；不會刪除快取、 切換市場、改變日期限制，或修改已回傳的 DataFrame。在 `data.universe()` 或 `data.us_universe()` 區塊內重設後，篩選會停用直到下一次設定或離開區塊； 離開區塊仍會還原進入前的篩選。可以重複呼叫重設。

* * *

## 詳細教學

參考 [資料取得詳細說明](https://finlab.finance/docs/details/get_data/)，了解： - 完整資料下載教學 - 資料表結構說明 - 進階篩選技巧 - 錯誤處理方法

* * *

## 全域變數配置

### 強制使用雲端/本地資料

```
from finlab import data

# 強制使用雲端資料（每次都重新下載）
data.force_cloud_download = True

# 強制使用本地快取（無網路環境）
data.use_local_data_only = True
```

### 限制資料時間範圍

```
# 只下載 2020-2023 年的資料（節省記憶體）
data.truncate_start = '2020-01-01'
data.truncate_end = '2023-12-31'

# 之後所有 data.get() 都會套用此範圍
close = data.get('price:收盤價')
```

建議用法

*   **開發階段**：使用 `truncate_start` 限制資料範圍，加快測試速度
*   **正式回測**：移除 truncate 限制，使用完整歷史資料
*   **記憶體不足**：設定 `truncate_start` 或使用 `use_local_data_only`

* * *

## API Reference

### data.get()

## finlab.data.get

Shared fetch pipeline plus `data.get()` single-dataset wrapper.

### DownloadedFrame`module-attribute`

```
DownloadedFrame = tuple[pd.DataFrame, bytes | None]
```

`(df, raw_feather_bytes)` — bytes is None when payload was inlined.

### get

```
get(
    dataset,
    save_to_storage=True,
    force_download=False,
    lazy=False,
    progress='silent',
    progress_callback=None,
    *,
    start=None,
    end=None,
    as_of=None,
    version=None,
)
```

Download historical data.

See https://ai.finlab.tw/database for the full data catalogue.

| PARAMETER | DESCRIPTION |
| --- | --- |
| `dataset` | The name of dataset. `tw_tick:SYMBOL` and `tw_minute:SYMBOL` return after-market long-form pandas frames and require both dates (at most 31 calendar days). See the intraday data guide. **TYPE:**`str` |
| `save_to_storage` | Whether to cache intraday data or retained versions (`as_of`/`version`). `False` raises `ValueError` for ordinary reads; use `data.set_storage(data.CacheStorage())` instead. **TYPE:**`bool`**DEFAULT:**`True` |
| `force_download` | Whether to force download the dataset from cloud. **TYPE:**`bool`**DEFAULT:**`False` |
| `lazy` | Return a lazy computation wrapper after fetching the dataset. **TYPE:**`bool`**DEFAULT:**`False` |
| `progress` | `'display'`, `'event'`, or `'silent'`. **TYPE:**`ProgressMode`**DEFAULT:**`'silent'` |
| `progress_callback` | Receives structured events in event mode. **TYPE:**`Callable[[ProgressEvent], None] | None`**DEFAULT:**`None` |
| `start` | Optional inclusive lower bound on the `date` column. Accepts any date-like value (string or `Timestamp`). Pushed down to the Arrow read so only in-range rows are materialised. Requires the dataset to have a `date` column/index, otherwise raises `ValueError`. **TYPE:**`DateBound`**DEFAULT:**`None` |
| `end` | Optional inclusive upper bound on the `date` column. Same rules as `start`. When both `start` and `end` are `None` the result is byte-identical to a plain read. **TYPE:**`DateBound`**DEFAULT:**`None` |
| `as_of` | Return the dataset exactly as it was published at this time (naive values are Asia/Taipei, for every market; a bare date means 00:00 that day, before that day's publications). Only versions the server still retains are available; list them with `data.versions(dataset)`. Requires a paid data plan and counts toward the download quota; a version already downloaded is read from local storage. `financial_statement` keeps permanent vintages instead (`financial_statement_versions`). **TYPE:**`DateBound`**DEFAULT:**`None` |
| `version` | Return exactly this generation from `data.versions(dataset)`. Mutually exclusive with `as_of`. **TYPE:**`str | int | None`**DEFAULT:**`None` |

| RETURNS | DESCRIPTION |
| --- | --- |
| `DataFrame` | financial data as a DataFrame. |

### get_role

```
get_role()
```

Return the current user role (e.g. `'free'` or `'vip'`).

### is_tradable

```
is_tradable(market=None)
```

Whether loaded data completed its final scheduled refresh before next open.

Daily TW data is judged by publication evidence, not expiry; use data.readiness() for the reason. Markets without publication evidence and runs without a trading calendar fall back to the published expiry.

### is_vip

```
is_vip()
```

Return True if the current user is a VIP member.

### next_future_expiry

```
next_future_expiry()
```

Next future expiry time among cached datasets (UTC).

Returns only expiry times in the future, skipping already expired data.

| RETURNS | DESCRIPTION |
| --- | --- |
| `datetime | None` | datetime in UTC representing the next future expiry, or None if |
| `datetime | None` | no future expiries exist or no data is available. |

### process_data

```
process_data(dataset, df)
```

Process raw data into standardized format.

### suggested_tradable_time

```
suggested_tradable_time(market=None)
```

Latest required scheduled source check, not a guaranteed arrival time.

Returns None if readiness is unknown or every required slot has passed. Rerun the strategy after the scheduled check and confirm readiness again.

常用資料表

**股價資料**： - `price:收盤價` - 每日收盤價 - `price:開盤價` - 每日開盤價 - `price:最高價` / `price:最低價` - 日內極值 - `price:成交股數` - 成交量

**財報資料**： - `price_earning_ratio:本益比` - P/E ratio - `price_earning_ratio:股價淨值比` - P/B ratio - `fundamental_features:股東權益報酬率` - ROE - `financial_statement:每股盈餘` - EPS

**籌碼資料**： - `institutional_investors_trading_summary:投信買賣超股數` - `margin_transactions:融資使用率` - `etl:外資持股比例`

**月營收**： - `monthly_revenue:當月營收` - `monthly_revenue:去年同月增減(%)`

完整列表請至 [資料庫目錄](https://ai.finlab.tw/database) 查詢。

常見錯誤

*   **KeyError**: 資料表名稱錯誤或 API token 未設定
*   **Empty DataFrame**: 查詢條件過嚴或資料不存在
*   **記憶體不足**: 下載資料過多，使用 `truncate_start` 限制範圍

### data.search()

## finlab.data.search

```
search(keyword=None, market=None, *, details=False)
```

Search available data fields in the finlab database.

The keyword matches dataset keys and, when the catalog provides them, each dataset's name, description, aliases and table columns. Matching ignores case, full/half-width differences, 占/佔, `(%)` and `今日`/`當日`.

Returns a pandas Series of dataset names (object dtype, name "dataset"). With `details=True`, returns a DataFrame with `dataset`, `auth` (`free` or `vip`) and `free_until` (inclusive cutoff, or None). Missing catalog permissions remain unknown; search does not grant access.

**範例**：

```
# 搜尋包含「股東」的欄位
data.search('股東')
# ['fundamental_features:股東權益報酬率', 'internal_equity_pledge:百分之十以上大股東持有股數', ...]

# 用常見說法搜尋：也會比對資料名稱、說明、別名與整表欄位
data.search('市值')  # ['etl:market_value', ...]
data.search('集保')  # ['inventory', 'etl:inventory:零股股數', ...]

# 比對時忽略全半形、占/佔、(%)、今日/當日
data.search('融資餘額')  # ['margin_transactions:融資今日餘額']

# 搜尋美股 PE ratio
data.search('pe', market='us')

# 列出所有台股欄位
all_fields = data.search()
print(f"共 {len(all_fields)} 個欄位")
```

key 打錯時的提示

`data.get()` 找不到資料集時會拋出 `finlab.exceptions.DatasetNotFoundError`（`RuntimeError` 的子類別），並列出拼法接近的正確 key。若輸入的是已登記的等價舊名稱，會發出 `UserWarning` 並自動改抓正確的 key。

下載失敗時的例外

`data.get()` 下載資料失敗時拋出 `finlab.exceptions.SignedDownloadError`（`DataError` 的子類別）。訊息寫出資料集、HTTP 狀態碼或連線問題的類別與建議做法，不含下載網址。程式要判斷原因時讀 `e.kind`（`"http"`、`"timeout"`、`"connection"`、`"ssl"`、`"redirects"`、`"browser"`、`"invalid_reply"`、`"other"`）與 `e.status`（HTTP 狀態碼，沒有收到回應時是 `None`），不要比對訊息字串。為了相容，它也保留原本的 `requests` 例外型別（例如 `requests.HTTPError`、`requests.Timeout`），並且是 `requests.RequestException` 與 `OSError`；新寫的程式建議用 `except DataError`。

每日下載額度

免費與 VIP 帳號在下載回應的當日用量達 80% 時，都會顯示一次預警。額度用完時，`data.get()`／`data.gets()` 會拋出 `finlab.exceptions.QuotaExceededError`（同時是 `DataError` 與 `RuntimeError` 的子類別），訊息包含額度與每日台灣時間 08:00 重置的說明。批次回測請先捕捉這個例外，再處理一般回測錯誤，避免將額度用完誤認成策略失敗。

### data.describe()

## finlab.data.describe

```
describe(dataset, market=None)
```

Inspect an exact dataset key or category using the cached search catalog.

No dataset is downloaded. `layout` describes the published dataset (pivot/table/long), whereas `source_layout` is only populated if the catalog explicitly describes upstream storage. `frequency` is never inferred from the crawler's cron `schedule`.

`index_end` is the catalog's last index label, which can be a future period label. It is not the latest available observation date. `source_created_time` is the published artifact's creation time, not a row's availability time. `latest_data_date` is None unless explicitly published under that name. Missing metadata stays None.

An unlisted `category:key_date` returns category context with `catalogued=False` and unknown layout/availability. Absence from the catalog does not prove that get() cannot download it, nor that its values represent announcement dates. Check the category description for semantics. Other unknown keys raise KeyError; an unavailable/empty catalog raises RuntimeError. Markets follow search(), except that "all" is not supported.

```
data.describe('price:收盤價')
data.describe('monthly_revenue')  # 整張表的欄位與說明
data.describe('monthly_revenue:key_date')
data.describe('us_price:close', market='us')
```

查詢共用搜尋的目錄快取，不下載資料。`layout` 是發布資料的格式，`source_layout` 是目錄明列的上游儲存格式；沒有提供的資訊回傳 `None`。`schedule` 是更新排程，不能當成觀測頻率 `frequency`。`index_end` 是最後一個索引標籤，可能包含未來的期間日期；`source_created_time` 是資料檔建立時間，兩者都不能當成逐筆資料的可用時間或 `latest_data_date`。

`columns` 列出目錄可查到的欄位。未列出的 `key_date` 會回傳 `catalogued=False`、`key_date_available=None`，並保留 `category_description`；這不代表無法下載，也不能據此判定它是公告日。其他查無的名稱會拋出 `KeyError`，目錄無法取得或為空時拋出 `RuntimeError`。

### data.universe()

## finlab.data.universe

### universe

```
universe(
    exchange='ALL',
    sector='ALL',
    exclude_sector=None,
    industry='ALL',
    asset_type=None,
    security_type='ALL',
    index=None,
    *,
    whitelist=None,
    market=None,
    category=None,
    exclude_category=None,
)
```

Context manager to set a global stock universe filter for data retrieval.

Auto-dispatches TW vs international logic based on the active data context.

##### Parameters

exchange : str | list[str], default 'ALL' TW: 'TWSE'/'TPEx' (or legacy 'TSE'/'OTC'). International: 'NASDAQ'/'NYSE'/'AMEX'/'HKEX'/'TSE'/etc. sector : str | list[str], default 'ALL' Sector name(s) with regex matching. exclude_sector : str | list[str] | None, default None Sector(s) to exclude (TW only). industry : str | list[str], default 'ALL' Industry filter (international markets). asset_type : str | None, default None TW only: 'ETF' or 'STOCK_FUTURE'. security_type : str | list[str], default 'ALL' Security type filter (international markets), e.g. 'common_stock'. index : str | None, default None Market index to filter by (international markets only). For US market: 'SP500'/'SPX', 'NASDAQ100'/'NDX'. Uses the latest constituent list for every historical date. For historical index selection, see the `us_universe` backtest example. whitelist : str | Iterable[str] | None, default None Explicit security IDs; a string is one ID. Alone, bypasses the current market catalog, so delisted IDs can be retained. With other filters, takes their intersection. Empty or zero-overlap selections return empty security data. IDs must already exclude unwanted security types; this static set does not encode listing eligibility by date. market : str | None **Legacy alias** for TW exchange+asset_type. category : str | list[str] | None **Legacy alias** for `sector`. exclude_category : str | list[str] | None **Legacy alias** for `exclude_sector`.

##### Examples

TW market (default):

> > > from finlab import data with data.universe(exchange=['TWSE', 'TPEx'], sector=['鋼鐵工業', '航運業']): ... close = data.get('price:收盤價')

Legacy TW usage (still works):

> > > with data.universe(market='TSE_OTC', sector='水泥', exclude_sector='ETF'): ... close = data.get('price:收盤價')

US market (S&P 500):

> > > data.set_market('us') with data.universe(index='SP500'): ... close = data.get('price:close')

US market (NASDAQ 100 Technology stocks):

> > > data.set_market('us') with data.universe(index='NDX', sector='Technology'): ... close = data.get('price:close')

JP market:

> > > data.set_market('jp') with data.universe(sector='Technology'): ... close = data.get('price:close')

### us_universe

```
us_universe(
    sector='ALL',
    industry='ALL',
    exchange='ALL',
    security_type='ALL',
    index=None,
)
```

Context manager to set a global stock universe filter for US market data retrieval.

This context manager limits the set of US stocks returned by data functions to a specific sector, industry, exchange, and/or index selection. The filter is applied globally within the context and is restored after the context exits.

##### Parameters

sector : str | list[str], default 'ALL' Sector name(s) to include. Supports regex-like substring matching. industry : str | list[str], default 'ALL' Industry name(s) to include. Supports regex-like substring matching. exchange : str | list[str], default 'ALL' Exchange name(s) to include. Common values: 'NASDAQ', 'NYSE', 'AMEX'. security_type : str | list[str], default 'ALL' Security type(s) to include. Use 'common_stock' for clean US equities. index : str | None, default None Market index to filter by. Supported values: 'SP500'/'SPX' (S&P 500), 'NASDAQ100'/'NDX' (NASDAQ 100). Can be combined with sector/industry/exchange for further filtering.

##### Notes

`index` uses the latest row of the constituent table to select columns for the entire price history. Backtesting these columns introduces survivorship and look-ahead bias; later index changes can also change results for earlier dates.

For historical selection, read unfiltered prices and apply the dated constituent records to scores before ranking, as shown below. Dates before the first record and price symbols absent from the table are False. The example matches symbols exactly: spelling differences, renamed stocks and missing price history can exclude constituents. Source delays or later corrections remain in the records; this is not an immutable snapshot of what was known at the time. Use each date's mask after that day's close.

##### Examples

> > > from finlab import data with data.us_universe(sector='Technology', exchange='NASDAQ'): ... close = data.get('us_price:close')

Filter to common stocks only:

> > > with data.us_universe(security_type='common_stock'): ... close = data.get('us_price:close')

Filter to the latest S&P 500 constituents (all historical dates):

> > > with data.us_universe(index='SP500'): ... close = data.get('us_price:close')

Filter to the latest NASDAQ 100 Technology stocks (all historical dates):

> > > with data.us_universe(index='NDX', sector='Technology'): ... close = data.get('us_price:close')

Historical index backtest:

> > > with data.us_universe(): # Temporarily clear any existing universe filter. ... close = data.get('us_price:close') ... constituents = data.get('us_index_constituents:sp500') in_index = constituents.reindex(close.index, method='ffill').eq(True) score = close.pct_change(20) position = score.where(in_index).is_largest(3)

For NASDAQ 100, replace `us_index_constituents:sp500` with `us_index_constituents:nasdaq100`.

### membership

```
membership(market='TSE_OTC', *, force_download=False)
```

Return daily TW listing eligibility for explicit pre-ranking masking.

Supports TSE, OTC, and TSE_OTC. Dates/columns follow the unfiltered Taiwan close-price table (subject to the active data date window). Listing dates are inclusive and termination dates exclusive. Suspensions and zero-volume days do not terminate membership. Unknown periods are False and reported by warning/attrs. This is effective-date eligibility reconstructed from current records, not a historical data vintage or an as-known-at-the-time guarantee. Source corrections may change historical eligibility.

Existing universe context/filter state is neither applied nor changed. Obtain scores without a snapshot universe that already removed securities. Apply the mask before _each_ cross-sectional ranking. No version argument or automatic changes to ranking methods are introduced.

##### Examples

> > > from finlab import data from finlab.data import universe close = data.get('price:收盤價') eligible = universe.membership('TSE_OTC') position = close.pct_change(20)[eligible].is_largest(20)

### reset_universe

```
reset_universe()
```

Disable the global stock universe filter for subsequent data reads.

Securities absent from the market catalog are included again. `set_universe()` without filters does the same. Cached data, the active market and date limits are preserved. Existing DataFrames are not modified.

Inside `universe` or `us_universe`, this disables filtering until the next selection or context exit. Exiting restores the selection that was active before entering that context.

### set_universe

```
set_universe(
    exchange='ALL',
    sector='ALL',
    exclude_sector=None,
    industry='ALL',
    asset_type=None,
    security_type='ALL',
    index=None,
    *,
    whitelist=None,
    market=None,
    category=None,
    exclude_category=None,
)
```

Set global stock universe filter. Auto-dispatches based on current market.

When `data.set_market('tw')` (or no market set), uses TW logic (`security_categories`). For any other market (us, hk, jp, kr, uk), loads `{market}_company_profile` and filters by available columns.

Calling without any filter is the same as :func:`reset_universe`: the filter is removed and no security is dropped.

##### Parameters

exchange : str | list[str], default 'ALL' TW: 'TWSE', 'TPEx' (or legacy 'TSE', 'OTC'). International: 'NASDAQ', 'NYSE', 'AMEX', 'HKEX', 'TSE', etc. sector : str | list[str], default 'ALL' Sector name(s) with regex matching. exclude_sector : str | list[str] | None, default None Sector(s) to exclude (TW only). industry : str | list[str], default 'ALL' Industry filter (international markets). asset_type : str | None, default None TW only: 'ETF' or 'STOCK_FUTURE'. security_type : str | list[str], default 'ALL' Security type filter (international markets), e.g. 'common_stock'. index : str | None, default None Market index to filter by (international markets only). For US market: 'SP500'/'SPX', 'NASDAQ100'/'NDX'. Uses the latest constituent list for every historical date. For historical index selection, see the `us_universe` backtest example. whitelist : str | Iterable[str] | None, default None Explicit security IDs; a string is one ID. Alone, bypasses the current market catalog, so delisted IDs can be retained. With other filters, takes their intersection. Empty or zero-overlap selections return empty security data. IDs must already exclude unwanted security types; this static set does not encode listing eligibility by date. market : str | None **Legacy alias** for TW exchange+asset_type (e.g. 'TSE_OTC', 'ETF'). category : str | list[str] | None **Legacy alias** for `sector`. exclude_category : str | list[str] | None **Legacy alias** for `exclude_sector`.

### set_us_universe

```
set_us_universe(
    sector='ALL',
    industry='ALL',
    exchange='ALL',
    security_type='ALL',
    index=None,
)
```

Set global US stock universe filter.

Thin wrapper around `_set_intl_universe_impl` for backward compatibility.

##### Parameters

sector : str | list[str], default 'ALL' Sector filter with regex-like substring matching. industry : str | list[str], default 'ALL' Industry filter with regex-like substring matching. exchange : str | list[str], default 'ALL' Exchange filter (e.g., 'NASDAQ', 'NYSE', 'AMEX'). security_type : str | list[str], default 'ALL' Security type filter. Use 'common_stock' for clean US equities. index : str | None, default None Market index to filter by. Supported values: 'SP500'/'SPX' (S&P 500), 'NASDAQ100'/'NDX' (NASDAQ 100). Uses the latest constituent list for every historical date. For historical index selection, see the `us_universe` backtest example.

**範例**：

```
# 範例 1：只取上市公司
with data.universe(market='TSE'):
    close = data.get('price:收盤價')
    print(f"上市公司數量: {len(close.columns)}")

# 範例 2：特定類股
with data.universe(category=['半導體業']):
    close = data.get('price:收盤價')

# 範例 3：市值前 100 大
with data.universe(size=100):
    close = data.get('price:收盤價')

# 範例 4：組合條件
with data.universe(market='TSE_OTC', category=['電子工業'], size=50):
    close = data.get('price:收盤價')
```

**可用 market 參數**： - `'TSE'` - 上市 - `'OTC'` - 上櫃 - `'TSE_OTC'` - 上市+上櫃 - `'ALL'` - 全部（含興櫃）

### data.us_universe()

## finlab.data.us_universe

```
us_universe(
    sector='ALL',
    industry='ALL',
    exchange='ALL',
    security_type='ALL',
    index=None,
)
```

Context manager to set a global stock universe filter for US market data retrieval.

This context manager limits the set of US stocks returned by data functions to a specific sector, industry, exchange, and/or index selection. The filter is applied globally within the context and is restored after the context exits.

#### Parameters

sector : str | list[str], default 'ALL' Sector name(s) to include. Supports regex-like substring matching. industry : str | list[str], default 'ALL' Industry name(s) to include. Supports regex-like substring matching. exchange : str | list[str], default 'ALL' Exchange name(s) to include. Common values: 'NASDAQ', 'NYSE', 'AMEX'. security_type : str | list[str], default 'ALL' Security type(s) to include. Use 'common_stock' for clean US equities. index : str | None, default None Market index to filter by. Supported values: 'SP500'/'SPX' (S&P 500), 'NASDAQ100'/'NDX' (NASDAQ 100). Can be combined with sector/industry/exchange for further filtering.

#### Notes

`index` uses the latest row of the constituent table to select columns for the entire price history. Backtesting these columns introduces survivorship and look-ahead bias; later index changes can also change results for earlier dates.

For historical selection, read unfiltered prices and apply the dated constituent records to scores before ranking, as shown below. Dates before the first record and price symbols absent from the table are False. The example matches symbols exactly: spelling differences, renamed stocks and missing price history can exclude constituents. Source delays or later corrections remain in the records; this is not an immutable snapshot of what was known at the time. Use each date's mask after that day's close.

#### Examples

> > > from finlab import data with data.us_universe(sector='Technology', exchange='NASDAQ'): ... close = data.get('us_price:close')

Filter to common stocks only:

> > > with data.us_universe(security_type='common_stock'): ... close = data.get('us_price:close')

Filter to the latest S&P 500 constituents (all historical dates):

> > > with data.us_universe(index='SP500'): ... close = data.get('us_price:close')

Filter to the latest NASDAQ 100 Technology stocks (all historical dates):

> > > with data.us_universe(index='NDX', sector='Technology'): ... close = data.get('us_price:close')

Historical index backtest:

> > > with data.us_universe(): # Temporarily clear any existing universe filter. ... close = data.get('us_price:close') ... constituents = data.get('us_index_constituents:sp500') in_index = constituents.reindex(close.index, method='ffill').eq(True) score = close.pct_change(20) position = score.where(in_index).is_largest(3)

For NASDAQ 100, replace `us_index_constituents:sp500` with `us_index_constituents:nasdaq100`.

**美股市場篩選**：

```
data.set_market('us')

# 取得最新 S&P 500 成分股的整段價格歷史
with data.us_universe(index='SP500'):
    close = data.get('price:close')

# 取得最新 NASDAQ 100 成分股中的科技股
with data.us_universe(index='NDX', sector='Technology'):
    close = data.get('price:close')

# 取得乾淨的美股普通股 universe
with data.us_universe(security_type='common_stock'):
    close = data.get('price:close')

# 也可以用 data.universe() 搭配 set_market
with data.universe(index='SP500', exchange='NASDAQ'):
    close = data.get('price:close')
```

**支援的 `index` 參數值**：

| 指數 | 可用別名 |
| --- | --- |
| S&P 500 | `'SP500'`, `'SPX'`, `'S&P500'`, `'S&P 500'` |
| NASDAQ 100 | `'NASDAQ100'`, `'NDX'`, `'NASDAQ 100'` |

`index` 可與 `sector`、`industry`、`exchange`、`security_type` 組合使用，篩選結果為交集。

#### 指數成分股回測

`index='SP500'` 或 `'NDX'` 取成分股表的最後一列，再用這份最新名單篩選整段歷史的欄位。直接拿來回測會有存活者偏誤與前視：後來才加入的股票會出現在加入前的日期，已剔除的股票則會從整段歷史消失。指數調整後，同一策略重跑也可能改變過去的結果。`data.universe()`、`data.set_universe()` 與 `data.set_us_universe()` 的 `index` 參數也採這個方式。

要依歷史紀錄篩選，先讀取未篩選的美股價格，再將當日或之前最近一筆成分股紀錄套在分數上，最後才排名選股：

```
from finlab import data

with data.us_universe():  # 暫時清除既有 universe 篩選，離開後會還原
    close = data.get('us_price:close')
    constituents = data.get('us_index_constituents:sp500')
in_index = constituents.reindex(close.index, method='ffill').eq(True)
score = close.pct_change(20)
position = score.where(in_index).is_largest(3)
```

NASDAQ 100 改讀 `us_index_constituents:nasdaq100`。成分股紀錄開始前的日期與表中沒有的價格代號都設為 `False`；請在當日收盤後使用當日遮罩。這份範例以代號完全相同為準，代號寫法不同、更名或缺少價格歷史時，仍可能漏掉成分股。遮罩依目前保存的紀錄重建，來源延遲、缺漏與事後更正仍會影響結果，不能視為當時已知資料的完整快照。

### data.indicator()

## finlab.data.indicator

Technical indicator computation: `data.indicator()`.

### get_strategies

```
get_strategies(api_token=None)
```

取得已上傳量化平台的策略回傳資料。

可取得自己策略儀表板上的數據，例如每個策略的報酬率曲線、報酬率統計、夏普率、近期部位、近期換股日...， 這些數據可以用來進行多策略彙整的應用喔！

| PARAMETER | DESCRIPTION |
| --- | --- |
| `api_token` | 若未帶入finlab模組的api_token，會自動跳出[GUI](https://ai.finlab.tw/api_token/)頁面， 複製網頁內的api_token貼至輸入欄位即可。 **TYPE:**`str`**DEFAULT:**`None` |

Returns: (dict): strategies data Response detail:

```
``` py
{
  strategy1:{
    'asset_type': '',
    'drawdown_details': {
       '2015-06-04': {
         'End': '2015-11-03',
         'Length': 152,
         'drawdown': -0.19879090089478024
         },
         ...
      },
    'fee_ratio': 0.000475,
    'last_trading_date': '2022-06-10',
    'last_updated': 'Sun, 03 Jul 2022 12:02:27 GMT',
    'ndays_return': {
      '1': -0.01132480035770611,
      '10': -0.0014737286933147464,
      '20': -0.06658015749110646,
      '5': -0.002292995729485159,
      '60': -0.010108700314771735
      },
    'next_trading_date': '2022-06-10',
    'positions': {
      '1413 宏洲': {
        'entry_date': '2022-05-10',
        'entry_price': 10.05,
        'exit_date': '',
        'next_weight': 0.1,
        'return': -0.010945273631840613,
        'status': '買進',
        'weight': 0.1479332345384493
        },
      'last_updated': 'Sun, 03 Jul 2022 12:02:27 GMT',
      'next_trading_date': '2022-06-10',
      'trade_at': 'open',
      'update_date': '2022-06-10'
      },
    'return_table': {
      '2014': {
        'Apr': 0.0,
        'Aug': 0.06315180932606546,
        'Dec': 0.0537589857541485,
        'Feb': 0.0,
        'Jan': 0.0,
        'Jul': 0.02937490104459939,
        'Jun': 0.01367930162104769,
        'Mar': 0.0,
        'May': 0.0,
        'Nov': -0.0014734320286596825,
        'Oct': -0.045082529665408266,
        'Sep': 0.04630906972509852,
        'YTD': 0.16626214846456966
        },
        ...
      },
    'returns': {
      'time': [
        '2014-06-10',
        '2014-06-11',
        '2014-06-12',
        ...
        ],
      'value': [
        100,
        99.9,
        100.2,
        ...
        ]
      },
    'stats': {
      'avg_down_month': -0.03304015302646822,
      'avg_drawdown': -0.0238021414698247,
      'avg_drawdown_days': 19.77952755905512,
      'avg_up_month': 0.05293384465715908,
      'cagr': 0.33236021285588846,
      'calmar': 1.65261094975066,
      'daily_kurt': 4.008888367138843,
      'daily_mean': 0.3090784769257415,
      'daily_sharpe': 1.747909002374217,
      'daily_skew': -0.6966018726321078,
      'daily_sortino': 2.8300677082214034,
      ...
      },
    'tax_ratio': 0.003,
    'trade_at': 'open',
    'update_date': '2022-06-10'
    },
  strategy2:{...},
  ...}
```
```

### indicator

```
indicator(
    indname,
    adjust_price=False,
    resample='D',
    *,
    strict=False,
    **kwargs,
)
```

支援 Talib 和 pandas_ta 上百種技術指標，計算 2000 檔股票、10年的所有資訊。

在使用這個函式前，需要安裝計算技術指標的 Packages

*   [Ta-Lib](https://github.com/mrjbq7/ta-lib)
*   [Pandas-ta](https://github.com/twopirllc/pandas-ta)

| PARAMETER | DESCRIPTION |
| --- | --- |
| `indname` | 指標名稱， 以 TA-Lib 舉例，例如 SMA, STOCH, RSI 等，可以參考 [talib 文件](https://mrjbq7.github.io/ta-lib/doc_index.html)。 以 Pandas-ta 舉例，例如 supertrend, ssf 等，可以參考 [Pandas-ta 文件](https://twopirllc.github.io/pandas-ta/#indicators-by-category)。 **TYPE:**`str` |
| `adjust_price` | 是否使用還原股價計算。 **TYPE:**`bool`**DEFAULT:**`False` |
| `resample` | 技術指標價格週期，ex: `D` 代表日線, `W` 代表週線, `M` 代表月線。 **TYPE:**`str`**DEFAULT:**`'D'` |
| `market` | 市場選擇，ex: `TW_STOCK` 代表台股, `US_STOCK` 代表美股。 **TYPE:**`str` |
| `strict` | 預設 False。True 時只接受 TA-Lib 的數值參數名稱， 拒絕輸入價格 selector；pandas_ta 尚不支援，會拋出 NotImplementedError。 例如 `data.indicator('RSI', strict=True, timeperiod=14)`。 只檢查名稱，不保證參數在每種設定下都影響結果；參數值由 TA-Lib 檢查。 無股票或全 NaN 時不執行指標計算。 **TYPE:**`bool`**DEFAULT:**`False` |
| `**kwargs` | 技術指標的參數設定，TA-Lib 中的 RSI 為例，調整項為計算週期 `timeperiod=14`。 **TYPE:**`dict`**DEFAULT:**`{}` |

建議使用者可以先參考以下範例，並且搭配 talib官方文件，就可以掌握製作技術指標的方法了。

**技術指標範例**：

```
from finlab import data

# 取得 MACD 指標
macd = data.indicator('macd', data.get('price:收盤價'))

# 取得 RSI 指標
rsi = data.indicator('rsi', data.get('price:收盤價'), period=14)
```

### 快取管理

## finlab.data.set_storage

```
set_storage(storage)
```

設定本地端儲存歷史資料的方式 假設使用 `data.get` 獲取歷史資料則，在預設情況下，程式會自動在本地複製一份，以避免重複下載大量數據。 storage 就是用來儲存歷史資料的接口。我們提供兩種 `storage` 接口，分別是 `finlab.data.CacheStorage` (預設) 以及 `finlab.data.FileStorage`。前者是直接存在記憶體中，後者是存在檔案中。詳情請參考 `CacheStorage` 和 `FileStorage` 來獲得更詳細的資訊。 在預設情況下，程式會自動使用 `finlab.data.FileStorage` 並將重複索取之歷史資料存在作業系統預設「暫時資料夾」。

| PARAMETER | DESCRIPTION |
| --- | --- |
| `storage` | The interface of storage **TYPE:**`Storage` |

Examples:

欲切換成以檔案方式儲存，可以用以下之方式：

```
from finlab import data
data.set_storage(data.FileStorage())
close = data.get('price:收盤價')
```

可以在本地端的 `./finlab_db/price#收盤價.pickle` 中，看到下載的資料， 可以使用 `pickle` 調閱歷史資料：

```
import pickle
close = pickle.load(open('finlab_db/price#收盤價.pickle', 'rb'))
```

## finlab.data.CacheStorage

```
CacheStorage()
```

將歷史資料儲存於快取中

Examples:

欲切換成以檔案方式儲存，可以用以下之方式：

```
from finlab import data
data.set_storage(data.CacheStorage())
close = data.get('price:收盤價')
```

可以直接調閱快取資料：

```
close = data._storage._cache['price:收盤價']
```

### cache_version

```
cache_version(name)
```

Identifies the cached frame; changes on every write, even at the same revision.

### clear

```
clear()
```

Remove all in-memory data and timestamp metadata.

### get_time_expired

```
get_time_expired(name)
```

Return the published expiry known for the cached version read, if any.

### read_dataframe_date_range

```
read_dataframe_date_range(name, start, end)
```

Return in-cache rows with `date` in `[start, end]` (both inclusive).

The whole frame already lives in memory here, so there is no memory win over a full read; the filter is applied for API parity with :class:`FileStorage`.

### release_memory

```
release_memory()
```

Release cached data in RAM; with no disk copy, this clears everything.

### set_revision

```
set_revision(name, revision)
```

Date the cached frame at _revision_.

## finlab.data.FileStorage

```
FileStorage(path=None, use_cache=True)
```

將歷史資料儲存於檔案中

| PARAMETER | DESCRIPTION |
| --- | --- |
| `path` | 資料儲存的路徑 **TYPE:**`str`**DEFAULT:**`None` |
| `use_cache` | 是否額外使用快取，將資料複製一份到記憶體中。 **TYPE:**`bool`**DEFAULT:**`True` |

Examples:

欲切換成以檔案方式儲存，可以用以下之方式：

```
from finlab import data
data.set_storage(data.FileStorage())
close = data.get('price:收盤價')
```

可以在本地端的 `./finlab_db/price#收盤價.feather` 中，看到下載的資料， 可以使用 `pandas.read_feather` 調閱歷史資料：

```
import pandas as pd
close = pd.read_feather('finlab_db/price#收盤價.feather')
```

### cache_version

```
cache_version(name)
```

Identifies the bytes this storage last read or wrote, even across replacements dated the same revision; else the file on disk.

### diagnose

```
diagnose(dataset=None)
```

診斷本地儲存狀態

| PARAMETER | DESCRIPTION |
| --- | --- |
| `dataset` | 指定要檢查的資料集名稱，例如 'price:收盤價'。如果不指定，則列出所有本地資料。 **TYPE:**`str`**DEFAULT:**`None` |

Examples:

```
from finlab import data
data._storage.diagnose()  # 列出所有本地資料
data._storage.diagnose('price:收盤價')  # 檢查特定資料集
```

### get_dataframe_index

```
get_dataframe_index(name)
```

Return the local dataframe index.

### get_dataframe_row_count

```
get_dataframe_row_count(name)
```

Return the local dataframe row count.

### get_time_created

```
get_time_created(name)
```

The cache's revision: its file mtime, stamped by the last download.

### get_time_expired

```
get_time_expired(name)
```

Return the published expiry known for the cached version read, if any.

### has_feather_cache

```
has_feather_cache(name)
```

Return whether `name` has a Feather (non-legacy) cache on disk.

### merge_recent_delta

```
merge_recent_delta(
    name, short_df, expected_hash, revision=None
)
```

Apply a `.recent` delta to the cached Feather via a streaming merge.

The stored table is walked one Arrow record batch at a time, so peak memory is ~= one batch + the delta instead of the three full-table copies the in-memory merge materialises. Returns `False` (leaving the existing cache untouched) when the streamed hash does not match `expected_hash`, so the caller can fall back to a full download. The replacement is atomic (`os.replace`).

### merge_table_delta

```
merge_table_delta(
    name, delta, expected_hash, revision=None
)
```

Apply a full table's delta to the cached Feather via a streaming merge.

Like :meth:`merge_recent_delta`: `False` leaves the cache untouched.

### read_dataframe_date_range

```
read_dataframe_date_range(name, start, end)
```

Read on-disk rows with `date` in `[start, end]` (both inclusive).

The date bounds are pushed down to the Arrow layer for Feather V2 caches, so only in-range rows are decoded and the full table is never materialised. Legacy pickle caches have no columnar pushdown, so they are read fully and then filtered. Bypasses the in-memory `_cache` on purpose so a slice read never pins the whole table in memory.

### release_memory

```
release_memory()
```

Release the in-memory DataFrame cache, keeping files and their revisions.

### set_dataframe_bytes

```
set_dataframe_bytes(name, payload, revision=None)
```

Persist a feather payload verbatim, skipping pandas re-encoding.

### set_revision

```
set_revision(name, revision)
```

Re-date the cache file at a revision whose bytes it already holds.

A file another process replaced since this one was loaded keeps its date. Read-only caches keep their existing date; these bytes remain usable.

**自訂快取策略**：

```
from finlab.data import set_storage, FileStorage

# 使用自訂資料夾
storage = FileStorage('/path/to/custom/cache')
set_storage(storage)

# 之後所有資料會快取到指定位置
close = data.get('price:收盤價')
```

### 使用者角色

## finlab.data.get_role

```
get_role()
```

Return the current user role (e.g. `'free'` or `'vip'`).

## finlab.data.is_vip

```
is_vip()
```

Return True if the current user is a VIP member.

**範例**：

```
from finlab import data

# 查詢使用者角色（需先執行至少一次 data.get()）
close = data.get('price:收盤價')

role = data.get_role()  # 'free', 'vip', ...
print(f"目前角色: {role}")

if data.is_vip():
    print("VIP 會員，享有完整資料存取權限")
```

### 其他工具

## finlab.data.get_strategies

```
get_strategies(api_token=None)
```

取得已上傳量化平台的策略回傳資料。

可取得自己策略儀表板上的數據，例如每個策略的報酬率曲線、報酬率統計、夏普率、近期部位、近期換股日...， 這些數據可以用來進行多策略彙整的應用喔！

| PARAMETER | DESCRIPTION |
| --- | --- |
| `api_token` | 若未帶入finlab模組的api_token，會自動跳出[GUI](https://ai.finlab.tw/api_token/)頁面， 複製網頁內的api_token貼至輸入欄位即可。 **TYPE:**`str`**DEFAULT:**`None` |

Returns: (dict): strategies data Response detail:

```
``` py
{
  strategy1:{
    'asset_type': '',
    'drawdown_details': {
       '2015-06-04': {
         'End': '2015-11-03',
         'Length': 152,
         'drawdown': -0.19879090089478024
         },
         ...
      },
    'fee_ratio': 0.000475,
    'last_trading_date': '2022-06-10',
    'last_updated': 'Sun, 03 Jul 2022 12:02:27 GMT',
    'ndays_return': {
      '1': -0.01132480035770611,
      '10': -0.0014737286933147464,
      '20': -0.06658015749110646,
      '5': -0.002292995729485159,
      '60': -0.010108700314771735
      },
    'next_trading_date': '2022-06-10',
    'positions': {
      '1413 宏洲': {
        'entry_date': '2022-05-10',
        'entry_price': 10.05,
        'exit_date': '',
        'next_weight': 0.1,
        'return': -0.010945273631840613,
        'status': '買進',
        'weight': 0.1479332345384493
        },
      'last_updated': 'Sun, 03 Jul 2022 12:02:27 GMT',
      'next_trading_date': '2022-06-10',
      'trade_at': 'open',
      'update_date': '2022-06-10'
      },
    'return_table': {
      '2014': {
        'Apr': 0.0,
        'Aug': 0.06315180932606546,
        'Dec': 0.0537589857541485,
        'Feb': 0.0,
        'Jan': 0.0,
        'Jul': 0.02937490104459939,
        'Jun': 0.01367930162104769,
        'Mar': 0.0,
        'May': 0.0,
        'Nov': -0.0014734320286596825,
        'Oct': -0.045082529665408266,
        'Sep': 0.04630906972509852,
        'YTD': 0.16626214846456966
        },
        ...
      },
    'returns': {
      'time': [
        '2014-06-10',
        '2014-06-11',
        '2014-06-12',
        ...
        ],
      'value': [
        100,
        99.9,
        100.2,
        ...
        ]
      },
    'stats': {
      'avg_down_month': -0.03304015302646822,
      'avg_drawdown': -0.0238021414698247,
      'avg_drawdown_days': 19.77952755905512,
      'avg_up_month': 0.05293384465715908,
      'cagr': 0.33236021285588846,
      'calmar': 1.65261094975066,
      'daily_kurt': 4.008888367138843,
      'daily_mean': 0.3090784769257415,
      'daily_sharpe': 1.747909002374217,
      'daily_skew': -0.6966018726321078,
      'daily_sortino': 2.8300677082214034,
      ...
      },
    'tax_ratio': 0.003,
    'trade_at': 'open',
    'update_date': '2022-06-10'
    },
  strategy2:{...},
  ...}
```
```

* * *

## 常見問題

### Q: 如何知道有哪些資料可以下載？

**方法 1：使用 search()**

```
# 列出所有欄位
all_fields = data.search()
for field in all_fields[:10]:
    print(field)
```

**方法 2：查看線上資料庫** 前往 [FinLab 資料庫目錄](https://ai.finlab.tw/database) 瀏覽完整列表。

### Q: 下載資料很慢怎麼辦？

```
# 方法 1：限制時間範圍
data.truncate_start = '2020-01-01'

# 方法 2：使用快取（第二次會很快）
close = data.get('price:收盤價')  # 第一次慢
close = data.get('price:收盤價')  # 第二次快（使用快取）

# 方法 3：使用 universe 限制股票數量
with data.universe(size=100):
    close = data.get('price:收盤價')  # 只下載 100 檔
```

### Q: KeyError: 'price:收盤價' 怎麼辦？

可能原因： 1. **未登入** - 執行 `finlab.login()` 完成登入 2. **欄位名稱錯誤** - 使用 `data.search('收盤')` 確認正確名稱 3. **資料權限不足** - 確認帳戶是否能存取該資料

```
import finlab

# 檢查是否已登入
try:
    token, token_type = finlab.get_token()
    print(f"✅ 已登入（{token_type}）")
except:
    print("❌ 未登入，請執行 finlab.login()")
```

### Q: 如何下載美股資料？

```
from finlab import data

# 美股收盤價
us_close = data.get('price:close', market='us')

# 搜尋美股欄位
us_fields = data.search(market='us')
```

### Q: 資料有缺失值怎麼辦？

```
close = data.get('price:收盤價')

# 檢查缺失值
print(f"缺失值比例: {close.isna().sum().sum() / close.size:.2%}")

# 填補缺失值
close_filled = close.fillna(method='ffill')  # 向前填補

# 或刪除有缺失值的股票
close_clean = close.dropna(axis=1, thresh=len(close) * 0.8)  # 保留 80% 以上資料的股票
```

### Q: 如何節省記憶體？

```
# 方法 1：限制時間範圍
data.truncate_start = '2020-01-01'

# 方法 2：分批處理
all_stocks = close.columns
for batch in [all_stocks[i : i + 100] for i in range(0, len(all_stocks), 100)]:
    batch_close = close[batch]
    # 處理 100 檔...

# 方法 3：只下載需要的欄位
# 不要一次 data.get() 太多資料表
```

* * *

## 參考資源

*   [資料取得詳細教學](https://finlab.finance/docs/details/get_data/) - 完整使用指南
*   [FinLab 資料庫目錄](https://ai.finlab.tw/database) - 所有可用資料表
*   [快速上手指南](https://finlab.finance/docs/getting-started/) - 新手入門
*   [常見問題 FAQ](https://finlab.finance/docs/faq/) - 更多疑難排解

## 按歷史日期取得上市櫃資格

`universe.membership()` 回傳布林 `FinlabDataFrame`，日期與股票欄位依台股收盤價資料排列。支援 `TSE`、`OTC`、`TSE_OTC`；不改變現有 `with data.universe(...)` 或排名方法。

```
from finlab import data
from finlab.data import universe

# 在沒有舊 universe 過濾的情況下取得完整原始資料。
close = data.get("price:收盤價")
score = close.pct_change(20)
eligible = universe.membership("TSE_OTC")
position = score[eligible].is_largest(20)
```

每次橫斷面排名前都要套用遮罩。若原始資料已被舊 universe 刪掉股票，新遮罩無法補回那些資料。`membership()` 本身不受舊股票集合限制，也不改動該集合；日期範圍仍遵循資料截取設定。可用 `force_download=True` 重新下載來源。

資格以現有公司基本資料、下市櫃公司資料及兩市場終止名單中的有效日期建立：上市櫃日包含在內，終止日起排除；支援多段上市期間及轉板。停牌、沒有成交不等於終止上市，應另外加入交易條件。遮罩不清空指標計算所需的前期資料。

缺少上市日期的歷史期間維持 `False`，並發出警告；可從 `eligible.attrs["membership_missing_history"]` 查看需要補齊歷史的股票。沒有公司上市資格紀錄的證券（例如 ETF）也不會因價格欄位存在就被納入。這份資料不能當作完整的 ETF 母體。

此功能依目前可得紀錄重建歷史有效資格，沒有保存母體版本，也不是「當時已知資訊」快照。補正歷史事件仍可能改變結果；無法保證重現舊回測。

[台股交易日曆、更新期間與資料就緒](https://finlab.finance/docs/details/trading-calendar-readiness/)
