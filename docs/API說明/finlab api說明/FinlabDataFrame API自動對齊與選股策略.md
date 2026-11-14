Title: FinlabDataFrame API：自動對齊、選股排名、hold_until 與權重建構 - 量化交易工具文檔

URL Source: https://finlab.finance/docs/reference/dataframe/

Markdown Content:
`FinlabDataFrame` 是 pandas DataFrame 的擴充類別，專為股票策略開發設計。`data.get()` 下載的資料多數會回傳這個型別，因此股價、月營收、財報等不同頻率資料可以直接做條件運算，不必手動 `reindex`。

| 你想做什麼 | 主要方法 | 範例 |
| --- | --- | --- |
| 對齊日頻、月頻、季頻資料 | 自動對齊 | `(close > close.average(20)) & (revenue > 1e8)` |
| 挑選排名前 N 名股票 | `is_largest()` / `is_smallest()` | `marketcap.is_smallest(30)` |
| 產生持倉訊號並加入停損停利 | `hold_until()` | `position.hold_until(stop_loss=0.1)` |
| 做橫截面與產業處理 | `df.cs` / `df.sector` | `factor.cs.rank()` |
| 建構投資組合權重 | `df.weight` | `position.weight.equal()` |

若還不熟 `data.get()`，先看 [finlab.data](https://finlab.finance/docs/reference/data/)；要完整策略範例可接著看[從研究到實盤](https://finlab.finance/docs/workflows/complete_strategy_workflow/)。

## 使用情境

*   自動對齊不同頻率的資料（日、週、月、季）
*   快速進行選股操作（排名、篩選前 N 名）
*   計算移動平均與技術指標
*   管理進出場訊號（持倉至停損/停利）
*   產業中性化（neutralize）
*   跨股票因子預處理（`df.cs`：排名、縮尾、標準化）
*   產業內轉換與聚合（`df.sector`：產業內排名、平均、標準差）
*   投資組合權重建構（`df.weight`：反波動率、風險平價、回撤控制）

## 快速範例

### 自動對齊與選股

```
from finlab import data

# data.get() 回傳的都是 FinlabDataFrame
close = data.get('price:收盤價')  # 日頻
revenue = data.get('monthly_revenue:當月營收')  # 月頻

# 自動對齊日期（revenue 會自動填補到日頻）
position = (close > close.average(20)) & (revenue > 1e8)
```

### 排名與篩選

```
from finlab import data

close = data.get('price:收盤價')
marketcap = data.get('etl:market_value')

# 選擇市值最小的 30 檔
small_cap = marketcap.is_smallest(30)

# 選擇漲幅最大的 20 檔
momentum = (close / close.shift(20)).is_largest(20)

# 組合策略
position = small_cap & momentum
```

### 持倉管理

```
from finlab import data
from finlab.backtest import sim

close = data.get('price:收盤價')
position = close > close.average(20)
exit_condition = close < close.average(60)

# 持倉至出場條件、停損 10% 或停利 20%
position_with_stops = position.hold_until(
    exit=exit_condition,
    stop_loss=0.1,
    take_profit=0.2,
)

# 回測
report = sim(position_with_stops, resample='M')
report.display()
```

* * *

## FinlabDataFrame vs pandas DataFrame

| 特性 | pandas DataFrame | FinlabDataFrame |
| --- | --- | --- |
| 基本操作 | ✅ 完全支援 | ✅ 完全支援（繼承 pandas） |
| 自動對齊 | ❌ 需手動處理 | ✅ 自動對齊不同頻率資料 |
| 選股方法 | ❌ 需自行撰寫 | ✅ 內建 `is_largest()`, `is_smallest()` |
| 技術指標 | ❌ 需額外套件 | ✅ 內建 `average()`, `rise()`, `fall()` |
| 持倉管理 | ❌ 需自行撰寫 | ✅ 內建 `hold_until()`, `exit_when()` |
| 產業分析 | ❌ 需自行撰寫 | ✅ 內建 `industry_rank()`, `neutralize_industry()` |
| 因子預處理 | ❌ 需自行撰寫 | ✅ 內建 `df.cs` 跨股票轉換 |
| 產業內分析 | ❌ 需自行撰寫 | ✅ 內建 `df.sector` 產業內轉換與聚合 |
| 權重建構 | ❌ 需自行撰寫 | ✅ 內建 `df.weight` 8 種加權方法 |

* * *

## API Reference

### FinlabDataFrame

## finlab.dataframe.FinlabDataFrame

```
FinlabDataFrame(*args, **kwargs)
```

Bases: `IndexConversionMixin`, `SignalMixin`, `NeutralizeMixin`, `IndustryMixin`, `DataFrame`

回測語法糖 除了使用熟悉的 Pandas 語法外，我們也提供很多語法糖，讓大家開發程式時，可以用簡易的語法完成複雜的功能，讓開發策略更簡潔！ 我們將所有的語法糖包裹在 `FinlabDataFrame` 中，用起來跟 `pd.DataFrame` 一樣，但是多了很多功能！ 只要使用 `finlab.data.get()` 所獲得的資料，皆為 `FinlabDataFrame` 格式， 接下來我們就來看看， `FinlabDataFrame` 有哪些好用的語法糖吧！

當資料日期沒有對齊（例如: 財報 vs 收盤價 vs 月報）時，在使用以下運算符號： `+`, `-`, `*`, `/`, `>`, `>=`, `==`, `<`, `<=`, `&`, `|`, `~`， 不需要先將資料對齊，因為 `FinlabDataFrame` 會自動幫你處理，以下是示意圖。

![Image 1: steps](https://i.ibb.co/pQr5yx5/Screen-Shot-2021-10-26-at-5-32-44-AM.png)

以下是範例：`cond1` 與 `cond2` 分別為「每天」，和「每季」的資料，假如要取交集的時間，可以用以下語法：

```
from finlab import data
# 取得 FinlabDataFrame
close = data.get('price:收盤價')
roa = data.get('fundamental_features:ROA稅後息前')

# 運算兩個選股條件交集
cond1 = close > 37
cond2 = roa > 0
cond_1_2 = cond1 & cond2
```

擷取 1101 台泥 的訊號如下圖，可以看到 `cond1` 跟 `cond2` 訊號的頻率雖然不相同， 但是由於 `cond1` 跟 `cond2` 是 `FinlabDataFrame`，所以可以直接取交集，而不用處理資料頻率對齊的問題。   
![Image 2: imageconds](https://i.ibb.co/m9chXSQ/imageconds.png)

總結來說，FinlabDataFrame 與一般 dataframe 唯二不同之處： 1. 多了一些 method，如`df.is_largest()`, `df.sustain()`...等。 2. 在做四則運算、不等式運算前，會將 df1、df2 的 index 取聯集，column 取交集。

與 `pd.Series` 運算時，依 Series 的 index 判斷對齊方向：日期（或季/月字串） index 對齊日期；股票代號 index 對齊股票、套用到每一天（`&` / `|` 缺少的股票視為 `False`，四則運算為 `NaN`）；兩者皆符合或皆不符合時會報錯，請改用 `df.mul(s, axis=0)`（日期）或 `df.mul(s, axis=1)`（股票）明確指定。 日期布林 Series 擇時：`position[cond]` 與 `position & cond` 都保留每個日期， False 的日期空手。

### align

```
align(other, *args, **kwargs)
```

`pd.DataFrame.align` that converts a quarterly side to dates first.

### average

```
average(n)
```

取 n 筆移動平均

若股票在時間窗格內，有 N/2 筆 NaN，則會產生 NaN。 Args: n (positive-int): 設定移動窗格數。 Returns: (pd.DataFrame): data Examples: 股價在均線之上

```
from finlab import data
close = data.get('price:收盤價')
sma = close.average(10)
cond = close > sma
```

只需要簡單的語法，就可以將其中一部分的訊號繪製出來檢查：

```
import matplotlib.pyplot as plt

close.loc['2021', '2330'].plot()
sma.loc['2021', '2330'].plot()
cond.loc['2021', '2330'].mul(20).add(500).plot()

plt.legend(['close', 'sma', 'cond'])
```

![Image 3: sma](https://i.ibb.co/Mg1P85y/sma.png)

### corrwith

```
corrwith(other, *args, **kwargs)
```

Compute pairwise correlations with pandas alignment and arithmetic.

### fall

```
fall(n=1)
```

數值下降中

取是否比前第n筆低，若符合條件的值則為True，反之為False。 ![Image 4: Screen-Shot-2021-10-26-at-6-43-41-AM](https://i.ibb.co/Y72bN5v/Screen-Shot-2021-10-26-at-6-43-41-AM.png) Args: n (positive-int): 設定比較前第n筆低。 Returns: (pd.DataFrame): data Examples: 收盤價是否低於10日前股價

```
from finlab import data
data.get('price:收盤價').fall(10)
```

### is_largest

```
is_largest(n)
```

取每列前 n 筆大的數值

若符合 `True` ，反之為 `False` 。用來篩選每天數值最大的股票。

![Image 5: is-largest](https://i.ibb.co/8rh3tbt/is-largest.png) Args: n (positive-int): 設定每列前 n 筆大的數值。 Returns: (pd.DataFrame): data Examples: 每季 ROA 前 10 名的股票

```
from finlab import data

roa = data.get('fundamental_features:ROA稅後息前')
good_stocks = roa.is_largest(10)
```

```
只在符合條件的股票中排名：用 `score[cond]` 排除不符合的股票，
不要用 `cond * score`。後者讓不符合的股票分數為 0，符合的股票
少於 n 檔時會被補進來，並發出 `TopNPaddingWarning`。
```py
top = score[cond].is_largest(10)
```
```

### is_smallest

```
is_smallest(n)
```

取每列前 n 筆小的數值

若符合 `True` ，反之為 `False` 。用來篩選每天數值最小的股票。 Args: n (positive-int): 設定每列前 n 筆小的數值。 Returns: (pd.DataFrame): data Examples: 股價淨值比最小的 10 檔股票

```
from finlab import data

pb = data.get('price_earning_ratio:股價淨值比')
cheap_stocks = pb.is_smallest(10)
```

```
只在符合條件的股票中排名時用 `pb[cond].is_smallest(10)`。
每列同為最高值的股票多於剩餘名額、只能依欄位順序挑選時，
會發出 `TopNPaddingWarning`。
```

### lazy

```
lazy()
```

Wrap this DataFrame into a lazy computation handle.

Returns a `LazyWide` proxy that records operations without executing them. Call `.rebalance(freq)` or `.collect()` on the result to trigger execution at specific dates only.

Example::

```
close = data.get('price:收盤價')
position = (
    close.lazy()
    .rolling(60).mean()
    .rank(axis=1, pct=True)
    .is_largest(10)
    .rebalance('M')
)
```

### quantile_row

```
quantile_row(c)
```

股票當天數值分位數

取得每列c定分位數的值。 Args: c (positive-int): 設定每列 n 定分位數的值。 Returns: (pd.DataFrame): data Examples: 取每日股價前90％分位數

```
from finlab import data
data.get('price:收盤價').quantile_row(0.9)
```

### rank

```
rank(*args, valid=None, **kwargs)
```

Cross-sectional or time-series ranking.

| PARAMETER | DESCRIPTION |
| --- | --- |
| `valid` | 只有 valid 為 True 的 cell 才參與排名。 valid 為 False/NaN 的 cell 在排名前設為 NaN， 因此不影響 pct=True 的分母。 常見用法：fillna 後傳入原始 notna() mask， 避免新上市或歷史不足的股票污染百分位排名。 **TYPE:**`DataFrame or Series of bool`**DEFAULT:**`None` |

### rebalance

```
rebalance(freq)
```

Downsample to keep only the last observation per period.

Equivalent to `self.resample(freq).last()`.

| PARAMETER | DESCRIPTION |
| --- | --- |
| `freq` | Pandas frequency string, e.g. `'ME'` (month-end), `'W'` (weekly), `'QE'` (quarter-end), or explicit dates to select with `reindex`. **TYPE:**`str | Index | list` |

### reindex

```
reindex(*args, **kwargs)
```

`pd.DataFrame.reindex` that understands quarterly string indexes.

Reindexing a quarterly ('2013-Q1') FinlabDataFrame onto dates first converts the quarters to disclosure dates with `index_str_to_date()`, so `df.reindex(close.index, method='ffill')` gives each stock's latest disclosed value instead of all NaN or a TypeError.

### rise

```
rise(n=1)
```

數值上升中

取是否比前第n筆高，若符合條件的值則為True，反之為False。 ![Image 6: Screen-Shot-2021-10-26-at-6-43-41-AM](https://i.ibb.co/Y72bN5v/Screen-Shot-2021-10-26-at-6-43-41-AM.png) Args: n (positive-int): 設定比較前第n筆高。 Returns: (pd.DataFrame): data Examples: 收盤價是否高於10日前股價

```
from finlab import data
data.get('price:收盤價').rise(10)
```

**FinlabDataFrame 主要方法**：

#### 選股與排名

| 方法 | 說明 | 範例 |
| --- | --- | --- |
| `is_largest(n)` | 選擇最大的 N 個值 | `marketcap.is_largest(30)` |
| `is_smallest(n)` | 選擇最小的 N 個值 | `pe_ratio.is_smallest(20)` |
| `rank()` | 每日跨股票排名 | `close.rank(axis=1, pct=True)` |
| `industry_rank()` | 產業內排名 | `close.industry_rank()` |

#### 技術指標

| 方法 | 說明 | 範例 |
| --- | --- | --- |
| `average(n)` | N 期移動平均 | `close.average(20)` |
| `rise(n)` | 連續 N 期上漲 | `close.rise(3)` |
| `fall(n)` | 連續 N 期下跌 | `close.fall(2)` |
| `sustain(n)` | 條件持續 N 期 | `(close > ma20).sustain(5)` |

#### 持倉管理

| 方法 | 說明 | 範例 |
| --- | --- | --- |
| `hold_until()` | 持倉至出場條件 | `position.hold_until(close < ma20)` |
| `exit_when()` | 遇到條件出場 | `position.exit_when(close < ma20)` |
| `entry_price()` | 取得進場價格 | `position.entry_price('close')` |

#### 產業分析

| 方法 | 說明 | 範例 |
| --- | --- | --- |
| `neutralize_industry()` | 產業中性化 | `factor.neutralize_industry()` |
| `groupby_category()` | 按產業分組 | `close.groupby_category().mean()` |

* * *

### average()

計算移動平均。

**使用範例**：

```
from finlab import data

close = data.get('price:收盤價')

# 20 日均線
ma20 = close.average(20)

# 60 日均線
ma60 = close.average(60)

# 均線交叉策略
golden_cross = ma20 > ma60
```

與 pandas rolling() 的差異

*   `average(20)` 等同於 `rolling(20).mean()`
*   更簡潔易讀
*   回傳值仍為 FinlabDataFrame，可繼續串接其他方法

* * *

### is_largest() / is_smallest()

選擇排名前/後 N 名。

**使用範例**：

```
from finlab import data

close = data.get('price:收盤價')
marketcap = data.get('etl:market_value')

# 選擇市值最小的 30 檔（小型股）
small_cap = marketcap.is_smallest(30)

# 選擇漲幅最大的 20 檔（動能股）
momentum = (close / close.shift(20)).is_largest(20)

# 組合：小型股中的動能股
position = small_cap & momentum
```

注意事項

*   `is_largest(n)` 每期（每日/每月）都會重新排名
*   若股票數少於 N，則全選
*   回傳 Boolean DataFrame（True 表示選中）

只在符合條件的股票中排名時，用 `score[cond]`（或 `score.where(cond)`）排除不符合的股票：

```
# 不符合 cond 的股票是 NaN，不參與排名；符合的少於 10 檔時就只選這些
position = score[cond].is_largest(10)
```

`(cond * score).is_largest(10)` 會讓不符合的股票分數為 0。符合的股票少於 10 檔時，這些 0 分股票會依欄位順序（1101、1102、1103…）被補進來。每列用最低分（`is_smallest` 為最高分）的同分股票補滿名額時，finlab 會發出 `TopNPaddingWarning`，選股結果不變。

* * *

### rank()

計算排名（支援百分比排名）。用 `axis=1` 在每個日期跨股票排名；產業內排名請用 `industry_rank()`。

**使用範例**：

```
from finlab import data

close = data.get('price:收盤價')
marketcap = data.get('etl:market_value')

# 計算百分位排名（0-1）
cap_rank = marketcap.rank(pct=True, axis=1)

# 選擇市值前 30%
position = cap_rank > 0.7

# 或使用 is_largest（更直觀）
position = marketcap.is_largest(int(len(marketcap.columns) * 0.3))
```

* * *

### industry_rank()

產業內排名。

**使用範例**：

```
from finlab import data

close = data.get('price:收盤價')

# 計算產業內排名（0-1）
industry_rank = close.industry_rank()

# 選擇產業內百分位分數高於 0.7 的股票
position = industry_rank > 0.7
```

產業分類來源

*   台股（`tw_stock` 與 `rotc_stock`）的分類來自[櫃買中心產業價值鏈資訊平台](https://ic.tpex.org.tw/)，透過 `data.get('security_industry_themes')` 取得。
*   `categories=None` 時只用名稱不含 `:` 的大分類；傳入 `categories=[...]` 可指定特定分類，包含子分類。
*   每個日期在各分類內以 `rank(axis=1, pct=True)` 排名；同時屬於多個分類的股票取各分類百分位的平均。

分類是最新快照，不是歷史當時的資料

`security_industry_themes` 是最新的分類快照，套用到每個日期，所以歷史排名可能用到當時還不知道的分類。回測時請留意。

* * *

### rise() / fall()

判斷連續上漲/下跌。

**使用範例**：

```
from finlab import data

close = data.get('price:收盤價')

# 連續 3 日上漲
rising = close.rise(3)

# 連續 2 日下跌
falling = close.fall(2)

# 策略：連續上漲後反手做空
position = ~rising  # 反向訊號
```

* * *

### sustain()

判斷條件持續 N 期。

**使用範例**：

```
from finlab import data

close = data.get('price:收盤價')
ma20 = close.average(20)

# 連續 5 日站穩 20 日均線
sustained_above_ma = (close > ma20).sustain(5)

# 策略
position = sustained_above_ma
```

sustain vs rise

*   `rise(n)`: 連續 n 期**數值上漲**
*   `sustain(n)`: 連續 n 期**條件為 True**

* * *

### hold_until()

持倉至出場條件、停損、停利或移動停利觸發。

**使用範例**：

```
from finlab import data
from finlab.backtest import sim

close = data.get('price:收盤價')
position = close > close.average(20)
exit_condition = close < close.average(60)

# 基礎用法：出場條件
position_with_exit = position.hold_until(exit_condition)

# 出場條件 + 停損 10% + 停利 20%
position_with_stops = position.hold_until(
    exit=exit_condition,
    stop_loss=0.1,
    take_profit=0.2,
)

# 出場條件 + 移動停利 10%，且獲利先達 20% 後才啟用
position_with_trail = position.hold_until(
    exit=exit_condition,
    trail_stop=0.1,
    trail_stop_activation=0.2,
)

# 回測
report = sim(position_with_stops, resample='M')
report.display()
```

重要概念

*   `hold_until()` 會**延長持倉**至觸發條件
*   停損/停利以**進場價格**為基準計算
*   `trail_stop` 會從持倉最高報酬回落指定比例時出場；`trail_stop_activation` 可設定需先達到的獲利門檻

#### 出場訊號是狀態還是事件（`exit_mode`）

進場訊號只在自己有的日期生效。出場訊號的日期比進場稀疏時（月營收、財報、週／月頻條件），`exit` 沒有的日期由 `exit_mode` 決定：

| `exit_mode` | `exit` 沒有的日期 | 適合的出場條件 |
| --- | --- | --- |
| `'state'`（預設） | 沿用前一筆的值，直到下一筆資料 | 月營收、財報等低頻條件：公布後一直有效，這段期間不會再進場 |
| `'event'` | 視為不出場 | 只列出事件日的資料：在 `exit` 有資料的日期出場，之後進場訊號為 True 就再買進 |

```
from finlab import data

close = data.get('price:收盤價')
entries = close > close.average(20)
yoy = data.get('monthly_revenue:去年同月增減(%)')

# 年增率為負就出場，之後公布的年增率不再是負數，才會再進場
position = entries.hold_until(yoy < 0)

# 只在月營收有資料的日期出場
position = entries.hold_until(yoy < 0, exit_mode='event')
```

`'state'` 會一直沿用最後一筆

`exit` 最後一筆是 True、之後沒有 False 時，該股票之後都不會再進場。只有一個日期的單次事件（例如只列出事件日的 DataFrame）也一樣會一直擋住進場，這類資料請用 `exit_mode='event'`。

NaN 在兩種模式都視為不出場。`'state'` 只補 `exit` 沒有的日期，不會把 NaN 換成更早的 True。`'state'` 需要 `exit` 的日期由舊到新排序，否則會拋出 `ValueError`，請先 `exit.sort_index()`。

什麼時候兩種模式結果相同

`exit` 在每個進場日都有一列時，兩種模式結果相同，例如兩者都由同一張日頻價格表算出；季頻字串索引以轉換後的日期比較。rank 或停損停利的價格額外帶進的日期上沒有進場訊號，不影響結果。日頻的 `exit` 只要少了某個進場日，例如資料晚一天更新或缺一個交易日，那一天 `'state'` 沿用前一筆，`'event'` 視為不出場，結果就可能不同。

`'event'` 只看得到傳進來的 `exit` 有哪些日期

下列情況傳進 `hold_until` 的 `exit` 已經被往後填到比較密的時間軸，填出來的每一列都當成一次事件，`'event'` 無法還原原本只在公布日出現的出場：

*   和日頻資料運算過的條件，例如 `(yoy < 0) | (close < close.average(60))`：結果和 `'state'` 相同。要當成事件，請直接傳入原本的月頻條件。
*   季報字串索引（如 `2024-Q1`）：`index_str_to_date()` 以所有公司的財報公告日為索引，每家公司的值會延續到其他公司的公告日，所以值為 True 時，`'event'` 在其他公司的公告日也會出場，不是只在自己的公告日。
*   lazy 的 `exit`（`data.get(..., lazy=True)` 或 `.lazy()` 算出的條件）：lazy 引擎在呼叫 `hold_until` 之前，會先把它往後填到 lazy 的時間軸，所以即使指定 `'event'`，結果也和 `'state'` 相同，而且不會報錯。要事件語意，請傳入 eager 的 `exit`，或先只對低頻的出場條件呼叫 `.collect()`：

```
# eager 的出場條件（取資料時不加 lazy=True）
position = entries.lazy().hold_until(yoy < 0, exit_mode='event').collect()

# 出場條件是 lazy 時，先單獨 collect
yoy_lazy = data.get('monthly_revenue:去年同月增減(%)', lazy=True)
exits = (yoy_lazy < 0).collect()
position = entries.lazy().hold_until(exits, exit_mode='event').collect()
```

2.1.0～2.2.0 的預設是 `'event'`；2.1.0 以前（至 2.0.23）和目前的預設是 `'state'`。要維持 2.1.0～2.2.0 的持股，請加上 `exit_mode='event'`。

* * *

### exit_when()

遇到特定條件出場。

**使用範例**：

```
from finlab import data

close = data.get('price:收盤價')
ma20 = close.average(20)
ma60 = close.average(60)

# 進場：短均線向上突破長均線
entry = ma20 > ma60

# 出場：短均線向下跌破長均線
exit_signal = ma20 < ma60

# 持倉至出場訊號
position = entry.exit_when(exit_signal)
```

exit_when vs hold_until

*   `exit_when()`: 自訂出場條件（如技術指標）
*   `hold_until()`: 固定停損/停利比例

* * *

### neutralize_industry()

產業中性化，移除產業因子影響。

**使用範例**：

```
from finlab import data

# 原始因子（含產業影響）
factor = data.get('fundamental_features:股東權益報酬率')

# 產業中性化（移除產業平均）
neutral_factor = factor.neutralize_industry()

# 使用中性化因子
position = neutral_factor.is_largest(30)
```

為什麼要中性化？

*   某些產業天生 ROE 高（如金融業）
*   中性化可避免過度集中單一產業
*   提升策略穩定性

* * *

## 投資組合權重建構 `df.weight`

`df.weight` accessor 提供一系列權重建構方法，可直接對選股結果（Boolean 或數值 DataFrame）建構與調整投資組合權重。所有方法回傳 `FinlabDataFrame`，可鏈式串接。

### 方法一覽

| 方法 | 說明 | 範例 |
| --- | --- | --- |
| `cap_industry(max_weight)` | 限制每個產業的最大權重，超額按比例重新分配 | `w.weight.cap_industry(0.3)` |
| `clip_by_volume(total_fund, max_participation_ratio, volume, window)` | 依日均成交金額限制個股權重 | `w.weight.clip_by_volume(1e7)` |
| `inverse_volatility(window, price)` | 反波動率加權，低波動股票獲得較高權重 | `w.weight.inverse_volatility(60)` |
| `risk_parity(window, price)` | 風險平價加權，使每個持股的風險貢獻相等 | `w.weight.risk_parity(60)` |
| `correlation(window, price, diversify)` | 依相關性調整權重，分散化或集中化 | `w.weight.correlation(diversify=True)` |
| `target_volatility(target, window, price)` | 縮放權重以達成目標年化波動率 | `w.weight.target_volatility(0.15)` |
| `limit_turnover(max_turnover)` | 限制相鄰換倉的雙向換手率 | `w.weight.limit_turnover(0.3)` |
| `drawdown_control(max_drawdown, price)` | 回撤超過門檻時自動縮減曝險 | `w.weight.drawdown_control(0.15)` |

### 使用範例

```
from finlab import data
from finlab.backtest import sim

close = data.get('price:收盤價')
marketcap = data.get('etl:market_value')

# 選股
position = marketcap.is_smallest(30)

# 鏈式建構權重
weighted = (
    position.weight.inverse_volatility(window=60)  # 反波動率加權
    .weight.cap_industry(max_weight=0.3)  # 產業權重上限 30%
    .weight.limit_turnover(max_turnover=0.3)  # 換手率上限 30%
    .weight.drawdown_control(max_drawdown=0.15)  # 回撤控制 15%
)

report = sim(weighted, resample='M')
report.display()
```

權重方法的先後順序

*   建議先做**加權**（inverse_volatility / risk_parity），再做**約束**（cap_industry / clip_by_volume）
*   `limit_turnover` 和 `drawdown_control` 通常放在最後

* * *

## 跨股票資料轉換 `df.cs`

`df.cs`（cross-sectional）accessor 提供跨股票的資料轉換方法。所有計算都是在每個日期、跨所有股票進行。

### 方法一覽

| 方法 | 說明 | 範例 |
| --- | --- | --- |
| `rank()` | 百分位排名（0, 1] | `factor.cs.rank()` |
| `winsorize(lower, upper)` | 百分位縮尾處理 | `factor.cs.winsorize(0.05, 0.95)` |
| `bucket(n)` | 等分位分組（1..n） | `factor.cs.bucket(5)` |
| `zscore()` | 標準化（均值 0，標準差 1） | `factor.cs.zscore()` |
| `demean()` | 去均值 | `factor.cs.demean()` |

### 使用範例

```
from finlab import data

roe = data.get('fundamental_features:股東權益報酬率')

# 因子預處理：縮尾 + 標準化
clean_roe = roe.cs.winsorize(0.05, 0.95).cs.zscore()

# 分成 5 組回測
group = roe.cs.bucket(5)
long_group = group == 5  # 做多最高組

# 百分位排名選股
position = roe.cs.rank() > 0.8  # 選前 20%
```

cs vs rank()

*   `df.cs.rank()` 回傳 (0, 1] 的百分位排名，每個日期跨所有股票計算
*   `df.rank(pct=True, axis=1)` 是 pandas 原生方法，效果類似但 `cs.rank()` 更語義化

* * *

## 產業內資料轉換與聚合 `df.sector`

`df.sector` accessor 提供兩類功能：

1.   **產業內轉換**：與 `df.cs` 相同的 5 個方法（rank / winsorize / bucket / zscore / demean），但在同產業內計算
2.   **產業內聚合**：mean / std / median / sum / min / max / count，回傳產業內的聚合統計量

### 轉換方法

| 方法 | 說明 | 範例 |
| --- | --- | --- |
| `rank()` | 產業內百分位排名 | `factor.sector.rank()` |
| `winsorize(lower, upper)` | 產業內百分位縮尾 | `factor.sector.winsorize(0.05, 0.95)` |
| `bucket(n)` | 產業內等分位分組 | `factor.sector.bucket(3)` |
| `zscore()` | 產業內標準化 | `factor.sector.zscore()` |
| `demean()` | 產業內去均值 | `factor.sector.demean()` |

### 聚合方法

| 方法 | 說明 | 範例 |
| --- | --- | --- |
| `mean()` | 產業內平均值 | `roe.sector.mean()` |
| `std(ddof=1)` | 產業內標準差 | `roe.sector.std()` |
| `median()` | 產業內中位數 | `roe.sector.median()` |
| `sum()` | 產業內總和 | `revenue.sector.sum()` |
| `min()` | 產業內最小值 | `close.sector.min()` |
| `max()` | 產業內最大值 | `close.sector.max()` |
| `count()` | 產業內有效值數量 | `roe.sector.count()` |

### 使用範例

```
from finlab import data

roe = data.get('fundamental_features:股東權益報酬率')
close = data.get('price:收盤價')

# 產業內排名選股（各產業內 ROE 前 20%）
position = roe.sector.rank() > 0.8

# 產業內標準化（消除產業差異）
neutralized_roe = roe.sector.zscore()

# 取得產業平均 ROE 做比較
sector_avg_roe = roe.sector.mean()
above_avg = roe > sector_avg_roe  # 高於產業平均的股票
```

sector vs neutralize_industry()

*   `df.sector.zscore()` 等同於 `neutralize_industry()` 的效果（產業中性化）
*   `df.sector` 提供更多彈性：除了中性化，還能做排名、分組、聚合

* * *

## 完整範例：多重篩選策略

```
from finlab import data
from finlab.backtest import sim

# 步驟 1：載入資料
close = data.get('price:收盤價')
marketcap = data.get('etl:market_value')
revenue = data.get('monthly_revenue:當月營收')
roe = data.get('fundamental_features:股東權益報酬率')

# 步驟 2：定義篩選條件
cond1 = marketcap.is_smallest(100)  # 小型股
cond2 = (revenue.average(3) / revenue.average(12)) > 1.2  # 營收成長
cond3 = roe.rank(pct=True, axis=1) > 0.7  # ROE 前 30%
cond4 = (close > close.average(20)).sustain(3)  # 連續 3 日站穩 20MA

# 步驟 3：組合條件
position = cond1 & cond2 & cond3 & cond4

# 步驟 4：限制持股數
position = position.is_largest(20)  # 最多 20 檔

# 步驟 5：回測並加入停損停利
report = sim(position, resample='M', stop_loss=0.1, take_profit=0.2)
report.display()

# 步驟 6：分析績效
metrics = report.get_metrics()
print(f"年化報酬: {metrics['annual_return']:.2%}")
print(f"夏普率: {metrics['daily_sharpe']:.2f}")
print(f"最大回撤: {metrics['max_drawdown']:.2%}")
```

* * *

## 常見問題

### Q: FinlabDataFrame 如何自動對齊不同頻率的資料？

```
from finlab import data

# 日頻資料
close = data.get('price:收盤價')  # 每天更新
print(close.index[0])  # 2010-01-04

# 月頻資料
revenue = data.get('monthly_revenue:當月營收')  # 每月 10 號公告
print(revenue.index[0])  # 2010-01-10

# 直接運算會自動對齊（revenue 向前填補到日頻）
position = (close > 100) & (revenue > 1e8)
# position 是日頻資料，revenue 已自動填補
```

**對齊規則**： - **低頻 → 高頻**：向前填補（forward fill） - **季報（財報）**：自動延遲至財報公告日

### Q: 為什麼一般 pandas DataFrame 放在左邊，結果不一樣？

自動對齊由左邊的運算元決定。一般 `pd.DataFrame` 在左邊時，`+ - * / // % ** & | ^` 會用 pandas 規則：日期不向前填補、股票取聯集、結果是一般 DataFrame（比較運算 `> < ==` 不受影響）。兩邊日期或股票不同時會發出 `PandasLeftOperandWarning`。

```
mask = pd.DataFrame(True, index=close.index[:1], columns=close.columns)
mask & (close > 0)  # pandas 對齊：只有第一天是 True，會警告
(close > 0) & FinlabDataFrame(mask)  # FinlabDataFrame 對齊：向前填補到每一天
```

請把 FinlabDataFrame 放在左邊，或用 `FinlabDataFrame(df)` 包起來（`from finlab.dataframe import FinlabDataFrame`）。

### Q: 如何串接多個 FinlabDataFrame 方法？

```
from finlab import data

close = data.get('price:收盤價')

# 串接方法（類似 pandas method chaining）
position = (
    close.average(20)  # 計算 20MA
    .rank(pct=True, axis=1)  # 排名
    .is_largest(30)  # 取前 30 名
)

# 等同於
ma20 = close.average(20)
ranked = ma20.rank(pct=True, axis=1)
position = ranked.is_largest(30)
```

### Q: is_largest() 和 rank() + 閾值有什麼差別？

```
from finlab import data

close = data.get('price:收盤價')

# 方法 1：is_largest（固定數量）
position1 = close.is_largest(30)  # 永遠選 30 檔

# 方法 2：rank + 閾值（固定比例）
position2 = close.rank(pct=True, axis=1) > 0.8  # 選前 20%（數量會變）

# 差異：
# - 方法 1：持股數固定（適合固定資金配置）
# - 方法 2：持股數浮動（適合市場狀況調整）
```

### Q: 移動停利（trail_stop）如何運作？

一般多單、使用 `trade_at_price="close"` 且未啟用 `touched_exit` 時，從最高價回落的幅度是以進場成本為分母，而不是以最高價為分母：`(持倉最高價 - 目前價格) / 進場成本 > trail_stop` 時產生出場訊號。公式採嚴格不等式，實際邊界仍可能受浮點誤差影響。

這是出場訊號的門檻，不是保證成交價：實際成交日期與價格仍依 `sim()` 的成交設定決定。`touched_exit=True` 改用盤中高低價及觸價規則；`retain_cost_when_rebalance` 決定換股時是否重設進場成本與最高價。

移動停利可透過 `sim(trail_stop=...)` 在回測引擎中處理，也可在 `hold_until(trail_stop=...)` 產生部位時先轉成出場訊號。若希望獲利先達指定門檻後才啟用移動停利，可加上 `trail_stop_activation`。

```
import pandas as pd
from finlab import data
from finlab.backtest import sim

close = data.get('price:收盤價')
position = close > close.average(20)

# 範例：進場價 100 元
# - stop_loss=0.1: 跌破 90 元出場
# - take_profit=0.2: 漲到 120 元出場（固定停利）
# - trail_stop=0.2: 從最高價回落超過進場成本的 20% 時產生出場訊號

# 情境：進場 100 → 漲到 150 → 回落到 120
# - take_profit=0.2: 漲到 120 即出場，不會等到 150
# - trail_stop=0.2: 門檻為 150 - 0.2 * 100 = 130（不是 120），跌破 130 才產生訊號

# 固定停利
report_fixed = sim(position, resample='M', stop_loss=0.1, take_profit=0.2)

# 移動停利
report_trailing = sim(position, resample='M', stop_loss=0.1, trail_stop=0.2)

# 在 hold_until 階段先產生移動停利出場訊號
position_trailing = position.hold_until(
    exit=pd.DataFrame(False, index=position.index, columns=position.columns),
    trail_stop=0.2,
    trail_stop_activation=0.3,
)
```

### Q: 如何在 FinlabDataFrame 上使用 pandas 方法？

```
from finlab import data

close = data.get('price:收盤價')

# FinlabDataFrame 完全兼容 pandas
close.rolling(20).mean()  # pandas 方法
close.fillna(0)  # pandas 方法
close.dropna()  # pandas 方法

# 所有 pandas 方法都可用
# 運算結果仍為 FinlabDataFrame（保留擴充功能）
```

* * *

## 參考資源

*   [選股條件教學](https://finlab.finance/docs/details/backtest_decorator/) - FinlabDataFrame 實戰應用
*   [歷史回測教學](https://finlab.finance/docs/details/backtest/) - 完整回測流程
*   [技術指標選股範例](https://finlab.finance/docs/tools/technical_indicator_selection/) - 實戰策略範例
*   [pandas 官方文檔](https://pandas.pydata.org/docs/) - pandas 基礎知識

## 批次產業中性化與對齊 profiling

`neutralize_industry_batch()` 接受 factor list 或 dict。相同日期與股票欄位的因子會 共用 categories mapping、日期轉換與向量化產業運算；回傳容器形狀與輸入一致。

```
from finlab.dataframe import neutralize_industry_batch, factor_alignment_profile

neutral = neutralize_industry_batch({"value": value, "quality": quality})
with factor_alignment_profile() as profile:
    combined = daily_factor + quarterly_factor
print(profile.to_dict())
```

預設 categories 使用依 market 與目前 data lifecycle 管理的 cache；切換 storage、 強制更新分類資料及 `data.clear()` 都會失效。也可手動呼叫 `data.clear_category_cache()`；`data.category_cache_stats()` 可檢查 raw/mapping hits。
