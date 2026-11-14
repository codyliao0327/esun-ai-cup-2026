Title: finlab.backtest - 量化交易工具文檔

URL Source: https://finlab.finance/docs/reference/backtest/

Markdown Content:
回測引擎模組，用於評估策略在歷史資料上的表現。

## 使用情境

*   **驗證策略邏輯**: 確認策略的進出場邏輯是否符合預期，檢視實際交易記錄
*   **評估風險報酬**: 計算年化報酬、夏普率、最大回撤等關鍵績效指標
*   **優化策略參數**: 結合 `finlab.optimize` 模組測試不同參數組合（調倉頻率、停損停利等）
*   **對比多個策略**: 比較不同策略的績效表現，找出最適合的交易方法

## 快速範例

```
from finlab import data
from finlab.backtest import sim

# 載入資料
close = data.get('price:收盤價')

# 策略邏輯：價格突破 20 日均線
ma20 = close.average(20)
position = close > ma20

# 回測（每月調倉，單股上限 10%）
report = sim(
    position,
    resample='M',  # 每月調倉
    position_limit=0.1,  # 單股權重上限 10%
)

# 顯示績效報告
report.display()
```

## 詳細教學

參考 [歷史回測完整指南](https://finlab.finance/docs/details/backtest/)，了解：

*   完整回測參數說明（resample, position_limit, stop_loss 等）
*   績效指標詳細解讀（年化報酬、夏普率、勝率等）
*   進階回測技巧（多市場、自訂手續費、滑價設定）
*   回測報告的深度分析方法

## API Reference

### sim()

## finlab.backtest.sim

Backtest simulation orchestrator.

This is the main entry point for running backtests via `sim()`. Configuration, validation, report building, and notifications are delegated to focused package modules:

*   `finlab.backtest.config` -- SimConfig, input validation
*   `finlab.backtest.report` -- trades, MAE/MFE, report assembly
*   `finlab.backtest.notify` -- Line notification delivery

### SimConfig`dataclass`

```
SimConfig(
    resample=None,
    data_readiness=None,
    planned_rebalance_date=None,
    resample_offset=None,
    trade_at_price='close',
    position_limit=1,
    fee_ratio=None,
    tax_ratio=None,
    name='未命名',
    stop_loss=None,
    take_profit=None,
    trail_stop=None,
    trail_stop_activation=None,
    touched_exit=False,
    retain_cost_when_rebalance=False,
    stop_trading_next_period=True,
    live_performance_start=None,
    end_date=None,
    mae_mfe_window=0,
    mae_mfe_window_step=1,
    market=None,
    upload=None,
    notification_enable=False,
    line_access_token='',
)
```

Configuration for backtest simulation parameters.

Groups the many sim() parameters into a single config object for cleaner internal passing between phases.

### columns_to_numpy

```
columns_to_numpy(df)
```

Convert DataFrame columns to numpy array for pandas 3.0+ compatibility.

### sim

```
sim(
    position: DataFrame | Series,
    resample: str | None = None,
    resample_offset: str | None = None,
    trade_at_price: str | DataFrame = 'close',
    position_limit: float = 1,
    fee_ratio: float | None = None,
    tax_ratio: float | None = None,
    name: str = '未命名',
    stop_loss: float | DataFrame | None = None,
    take_profit: float | DataFrame | None = None,
    trail_stop: float | None = None,
    trail_stop_activation: float | None = None,
    touched_exit: bool = False,
    retain_cost_when_rebalance: bool = False,
    stop_trading_next_period: bool = True,
    live_performance_start: str | None = None,
    mae_mfe_window: int = 0,
    mae_mfe_window_step: int = 1,
    market: Market | None = None,
    upload: bool | None = None,
    *,
    end_date: str | date | Timestamp | None = None,
    metrics_only: Literal[True],
    notification_enable: bool = False,
    line_access_token: str = '',
) -> Metrics
```

```
sim(
    position: DataFrame | Series,
    resample: str | None = None,
    resample_offset: str | None = None,
    trade_at_price: str | DataFrame = 'close',
    position_limit: float = 1,
    fee_ratio: float | None = None,
    tax_ratio: float | None = None,
    name: str = '未命名',
    stop_loss: float | DataFrame | None = None,
    take_profit: float | DataFrame | None = None,
    trail_stop: float | None = None,
    trail_stop_activation: float | None = None,
    touched_exit: bool = False,
    retain_cost_when_rebalance: bool = False,
    stop_trading_next_period: bool = True,
    live_performance_start: str | None = None,
    mae_mfe_window: int = 0,
    mae_mfe_window_step: int = 1,
    market: Market | None = None,
    upload: bool | None = None,
    *,
    end_date: str | date | Timestamp | None = None,
    metrics_only: Literal[False] = False,
    notification_enable: bool = False,
    line_access_token: str = '',
) -> report.Report
```

```
sim(
    position,
    resample=None,
    resample_offset=None,
    trade_at_price='close',
    position_limit=1,
    fee_ratio=None,
    tax_ratio=None,
    name='未命名',
    stop_loss=None,
    take_profit=None,
    trail_stop=None,
    trail_stop_activation=None,
    touched_exit=False,
    retain_cost_when_rebalance=False,
    stop_trading_next_period=True,
    live_performance_start=None,
    mae_mfe_window=0,
    mae_mfe_window_step=1,
    market=None,
    upload=None,
    *,
    end_date=None,
    metrics_only=False,
    notification_enable=False,
    line_access_token='',
)
```

Simulate the equity given the stock position history.

See the module-level docstring and the parameter docs below for full details.

| PARAMETER | DESCRIPTION |
| --- | --- |
| `position` | Buy/sell signal history. True = hold, False = flat. Can also be a `LazyWide` — it will be auto-collected at the rebalance dates determined by _resample_. **TYPE:**`DataFrame | Series` |
| `resample` | Trading period frequency (e.g. 'W', 'M', 'Q'), or a DataFrame/Series, DatetimeIndex or datetime list supplying rebalance dates. FinlabDataFrame period labels are converted to disclosure dates. **TYPE:**`str | None`**DEFAULT:**`None` |
| `resample_offset` | Pandas offset string (e.g. '7D') added to each rebalance date, for both frequency strings and supplied dates. Applied after disclosure-date conversion and before filtering the backtest period. **TYPE:**`str | None`**DEFAULT:**`None` |
| `trade_at_price` | Price type for trade execution ('close', 'open', etc.). **TYPE:**`str | DataFrame`**DEFAULT:**`'close'` |
| `position_limit` | Maximum single-stock weight (0-1). **TYPE:**`float`**DEFAULT:**`1` |
| `fee_ratio` | Trading fee ratio. **TYPE:**`float | None`**DEFAULT:**`None` |
| `tax_ratio` | Trading tax ratio. **TYPE:**`float | None`**DEFAULT:**`None` |
| `name` | Strategy name. **TYPE:**`str`**DEFAULT:**`'未命名'` |
| `stop_loss` | Stop-loss threshold, or a DataFrame of per-date, per-stock thresholds indexed by the date each value becomes available. Each bar uses the latest value dated on or before it (strictly before it with touched_exit=True, since intraday touches happen before that day's value exists). NaN, 0 and dates before the first value mean no stop. With a DataFrame, `report.stop_loss` is None. **TYPE:**`float | DataFrame | None`**DEFAULT:**`None` |
| `take_profit` | Take-profit threshold, or a DataFrame with the same rules as `stop_loss`. **TYPE:**`float | DataFrame | None`**DEFAULT:**`None` |
| `trail_stop` | Drop from peak return, measured relative to entry cost. For a long position with close-price execution and touched_exit=False, signal an exit when (peak_price - close) / entry_cost > trail_stop. Entry 100, peak 150 and trail_stop=0.2 give a 130 threshold. The signal is executed on the next bar, not at a guaranteed threshold price. **TYPE:**`float | None`**DEFAULT:**`None` |
| `trail_stop_activation` | Profit threshold before trailing stop activates. **TYPE:**`float | None`**DEFAULT:**`None` |
| `touched_exit` | Use intraday touched stop-loss/take-profit. **TYPE:**`bool`**DEFAULT:**`False` |
| `retain_cost_when_rebalance` | Keep original cost basis on rebalance. **TYPE:**`bool`**DEFAULT:**`False` |
| `stop_trading_next_period` | Skip next period after stop-loss/take-profit. **TYPE:**`bool`**DEFAULT:**`True` |
| `live_performance_start` | ISO date string marking live trading start. **TYPE:**`str | None`**DEFAULT:**`None` |
| `mae_mfe_window` | Window size for MAE/MFE calculation. **TYPE:**`int`**DEFAULT:**`0` |
| `mae_mfe_window_step` | Step size for MAE/MFE window. **TYPE:**`int`**DEFAULT:**`1` |
| `market` | Market instance or name string ('TW_STOCK', 'US_STOCK'). **TYPE:**`Market | None`**DEFAULT:**`None` |
| `upload` | Whether to upload the strategy report to FinLab cloud. Defaults to `None`: upload only in cloud-scheduled runs (the `FINLAB_FORCED_STRATEGY_NAME` environment variable is set). FinLab Studio, local, Jupyter and Colab runs upload only when `upload=True` is passed. **TYPE:**`bool | None`**DEFAULT:**`None` |
| `end_date` | Last date of the backtest (inclusive; a bare date covers the whole day). Position, prices and the report (creturn, trades, stats) stop there, as if the backtest ran on that day. Positions still open on `end_date` stay open in `report.trades`. `None` (default) keeps the current behavior: the end is inferred from the position's signal spacing. **TYPE:**`str | date | Timestamp | None`**DEFAULT:**`None` |
| `metrics_only` | Return the same `Metrics` type as `Report.metrics` without constructing a Report. Return-series metrics such as CAGR, Sharpe ratio and maximum drawdown remain available. **TYPE:**`bool`**DEFAULT:**`False` |
| `notification_enable` | Send Line notifications on completion. **TYPE:**`bool`**DEFAULT:**`False` |
| `line_access_token` | Line Notify access token. **TYPE:**`str`**DEFAULT:**`''` |

| RETURNS | DESCRIPTION |
| --- | --- |
| `Report | Metrics` | A Report, or a Metrics object when `metrics_only=True`. |

`upload` 預設值（2.0.24 起）

`upload` 預設為 `None`：只有雲端排程執行（設定了 `FINLAB_FORCED_STRATEGY_NAME` 環境變數）時才會上傳報告。FinLab Studio、本機、Jupyter、Colab 預設**不上傳**，需要上傳請明確傳入 `upload=True`，或回測後呼叫 `report.upload()`。

常用參數組合

**月線策略（適合上班族）**:

```
report = sim(
    position,
    resample='M',  # 每月調倉
    position_limit=0.1,  # 單股上限 10%
    upload=True,  # 上傳至雲端（本機預設不上傳，需明確指定）
)
```

**週線策略（適合積極型）**:

```
report = sim(
    position,
    resample='W',  # 每週調倉
    position_limit=0.05,  # 單股上限 5%（分散風險）
    trade_at_price='open',  # 以開盤價交易（更保守）
)
```

**停損停利策略**:

```
# 方法 1: 在 sim() 中設定
report = sim(
    position,
    resample='M',
    stop_loss=0.1,  # 虧損 10% 停損
    take_profit=0.2,  # 獲利 20% 停利
)

# 方法 2: 使用 hold_until() 更靈活
exit_condition = close < ma20  # 跌破均線出場
position_with_exit = position.hold_until(
    exit=exit_condition,
    stop_loss=0.1,  # 虧損 10% 停損
    take_profit=0.2,  # 獲利 20% 停利
)
report = sim(position_with_exit, resample='M')
```

常見錯誤與解決方法

**1. 策略無任何交易記錄**

```
# 問題：進場條件過嚴，position 全為 False
report = sim(position, resample='M')
trades = report.get_trades()
if len(trades) == 0:
    print("⚠️ 警告：策略無任何交易記錄！")
    # 檢查進場次數
    print(f"平均每日進場股票數：{position.sum(axis=1).mean():.1f}")
    print(f"最大進場股票數：{position.sum(axis=1).max()}")

# 解決：放寬條件或檢查資料範圍
```

**2. KeyError: 日期不存在**

```
# 問題：資料日期範圍不匹配
# 解決：使用 truncate_start 對齊起始日期
import finlab

finlab.truncate_start = '2020-01-01'  # 只回測 2020 年後的資料
report = sim(position, resample='M')
```

**3. 忘記設定 resample 導致每日調倉**

```
# 錯誤：交易成本過高
report = sim(position)  # ❌ 預設每日調倉

# 正確：設定合理的調倉頻率
report = sim(position, resample='M')  # ✅ 每月調倉
```

### metrics_from_nav()

## finlab.backtest.metrics_from_nav

```
metrics_from_nav(nav)
```

Measure any engine's daily NAV with FinLab's curve-only Metrics.

Supply costs-adjusted NAV neutralized for deposits/withdrawals. Dates must increase with one observation per day; invalid rows are never dropped or sorted. This computes caller-provided performance, not audited returns. Measurement uses local calendar dates without a timezone, so midnight DST transitions do not invalidate otherwise valid daily observations. No report, holdings, upload or orders are inferred from the curve.

`metrics_from_nav()` 接受任意框架或自訂帳本的日頻淨值，提供與 `sim()` 相同口徑的淨值績效，供研究／策略管理工具登錄結果。不需要改寫成 FinLab 回測：

```
import pandas as pd
from finlab.backtest import metrics_from_nav
from finlab.backtest.metrics import metrics_to_dict

nav = pd.Series([100, 102, 101], index=pd.date_range("2026-01-01", periods=3))
metrics = metrics_from_nav(nav)
print(metrics.annual_return(), metrics.sharpe_ratio(), metrics.max_drawdown())
print(metrics_to_dict(metrics))  # 無法計算的非有限指標轉為 None
print(metrics.provenance)  # 量測方式、期間與有效觀測筆數
```

輸入為數值 Series 與 DatetimeIndex，至少兩筆、日期遞增且每天最多一筆，值有限且為正。依輸入的當地日曆日期量測，首筆正規化為 1，不排序或刪除錯值。淨值必須已扣成本，並排除入金／出金造成的假報酬；結果不是券商查核收益。回傳獨立 Metrics，僅提供淨值可量測的指標，不產生 Report、交易明細、持倉或委託。

任意框架的程式與必要檔案仍可透過現有 ZIP 部署，第三方相依放在根目錄 requirements.txt；入口程式執行框架後呼叫 metrics_from_nav。雲端的 Python、相依套件與資源限制仍適用：

```
python -m finlab cloud deploy external_nav --zip strategy.zip --entry-script main.py --time 09:30 --no-contest
```

量測函式不建立或上傳雲端 Report，也不宣告競賽資格。

### line_notify()

## finlab.backtest.line_notify

```
line_notify(
    report=None, line_access_token='', test=False, name=''
)
```

Send backtest position and recent trade signals to a Line chat room.

| PARAMETER | DESCRIPTION |
| --- | --- |
| `report` | The backtest result report. **TYPE:**`Report | None`**DEFAULT:**`None` |
| `line_access_token` | Line Notify access token. **TYPE:**`str`**DEFAULT:**`''` |
| `test` | If True, send a test message instead of report data. **TYPE:**`bool`**DEFAULT:**`False` |
| `name` | Strategy name for the notification header. **TYPE:**`str`**DEFAULT:**`''` |

LINE 通知設定

1.   前往 [LINE Notify](https://notify-bot.line.me/) 取得個人 token
2.   設定環境變數： ```
import os

os.environ['LINE_NOTIFY_TOKEN'] = 'YOUR_TOKEN'
``` 
3.   發送通知： ```
from finlab.backtest import line_notify

# 策略執行後發送報告
report = sim(position, resample='M')
line_notify(f"策略回測完成\n年化報酬：{report.stats['annual_return']:.2%}")
``` 

## 常見問題

### Q: 回測結果與實盤有落差怎麼辦？

常見原因與解決方法：

1.   **回測未考慮滑價**：

```
# 使用開盤價交易（更保守）
report = sim(position, trade_at_price='open', resample='M')
``` 
2.   **成交量不足**：

```
# 使用 LiquidityAnalysis 檢測流動性
from finlab.analysis import LiquidityAnalysis

liq = LiquidityAnalysis(report)
liq.display()  # 查看成交量風險
``` 
3.   **交易價格與實際執行價差**： `sim()` 的訊號永遠是「今天產生、隔天執行」，`trade_at_price` 決定的是**隔天**用哪個價格成交：

```
# trade_at_price='close'（預設）→ 隔日收盤價成交
# 實務上難以精確在收盤價成交，容易產生滑價
report = sim(position, trade_at_price='close')  # ⚠️ 隔日收盤價，實務不易精確成交

# trade_at_price='open' → 隔日開盤價成交（推薦）
# 更貼近實際下單情境：盤後看訊號，隔日開盤掛單
report = sim(position, trade_at_price='open')  # ✅ 隔日開盤價，較貼近實盤
``` 

### Q: 如何設定自訂手續費？

```
report = sim(
    position,
    resample='M',
    fee_ratio=0.001425,  # 買賣各 0.1425%（券商手續費）
    tax_ratio=0.003,  # 賣出證交稅 0.3%
)
```

### Q: 如何限制最大持股數量？

```
# 方法 1: 使用 is_largest() 限制進場股票數
position = (close > ma20).is_largest(30)  # 最多持有 30 檔

# 方法 2: 在 sim() 中限制
report = sim(
    position,
    resample='M',
    position_limit=0.1,  # 單股上限 10%
    # 如果 position 中有 50 檔，實際最多持有 10 檔（100% / 10% = 10）
)
```

### Q: 回測速度太慢怎麼辦？

```
# 1. 使用更長的調倉週期
report = sim(position, resample='Q')  # 季度調倉（比月線快 3 倍）

# 2. 縮短回測期間
import finlab

finlab.truncate_start = '2018-01-01'  # 只測試近 5 年

# 3. 減少股票數量
position = (close > ma20).is_largest(50)  # 只測試 50 檔
```

## 參考資源

*   [歷史回測完整教學](https://finlab.finance/docs/details/backtest/) - 深入理解回測引擎
*   [完整策略開發流程](https://finlab.finance/docs/workflows/complete_strategy_workflow/) - 從研究到實盤
*   [策略優化指南](https://finlab.finance/docs/details/optimize_strategy/) - 找出最佳參數
*   [風險管理完整指南](https://finlab.finance/docs/workflows/risk_management/) - 停損停利實戰
*   [GitHub 原始碼](https://github.com/finlab-python/finlab/blob/main/finlab/backtest.py)
*   [範例策略集](https://github.com/finlab-python/finlab/tree/main/tests) - 學習實戰範例
