Title: finlab.report - 量化交易工具文檔

URL Source: https://finlab.finance/docs/reference/report/

Markdown Content:
回測報告模組，`Report` 物件由 `sim()` 函數產生，包含完整的回測績效資訊。

## 自訂比較基準（benchmark）

在回測前繼承策略所用的 Market（例如 `TWMarket`），覆寫 `get_benchmark()` 回傳日期索引的價格或累積淨值 Series，再以 `market=` 傳入 `sim()`。以下以還原後的 0050 價格為基準：

```
from finlab import data
from finlab.backtest import sim
from finlab.markets.tw import TWMarket

class ETFBenchmarkMarket(TWMarket):
    @staticmethod
    def get_benchmark():
        return data.get("etl:adj_close")["0050"]

close = data.get("price:收盤價")
position = close > close.average(20)
report = sim(position, market=ETFBenchmarkMarket(), resample="M", upload=False)
report.display()
```

請回傳涵蓋回測期間的價格或累積淨值，不要傳入每日報酬率。更換基準時，請用新的 Market 重跑 `sim()`；回測後直接指定 `report.benchmark = ...`，不會同步更新所有圖表與統計。美股策略可同樣繼承 `USMarket` 或 `USFundMarket`（例如回傳 `data.get("us_fund_price:adj_close")["SPY"]`）。`get_benchmark()` 的完整規格請見 [Market 物件](https://finlab.finance/docs/reference/market/) 與[自訂市場物件完整指南](https://finlab.finance/docs/details/market_customization/)。

## 在 Python 列印策略體檢

```
print(report.to_checkup_text())  # 五類白話摘要、各項指標說明與達標判定
checkup = report.get_checkup()  # 相同內容的 dict，可程式化讀取
print(report.to_checkup_text(lang="en"))
```

內容與 HTML 策略體檢共用定義。`categories` 每類含 `question`、`summary`、 `health_label`、`passed`、`total` 與 `checks`；每項檢查含 `key`、`name`、 `explanation`、`value`、`formatted`、`rule`、`target`、`passed`、`status`。 資料不足時 `value` 為 `None`、`status` 為 `insufficient_data`，不計為通過； 未提供的指標不列入檢查。空交易會有明確提示，流動性僅於支援的台灣市場列出。 `get_metrics()` 仍回傳原有數值，不包含這些文字。

## 使用情境

*   查看回測績效（年化報酬、夏普率、最大回撤）
*   分析交易記錄（進出場時間、持有天數、報酬率）
*   視覺化淨值曲線與回撤
*   儲存報告供日後查閱
*   上傳至 FinLab 雲端進行實盤追蹤
*   執行深度分析（流動性、選股能力、持股分布）

## 快速範例

### 基礎用法：產生並查看報告

```
from finlab import data
from finlab.backtest import sim

# 建立策略並回測
close = data.get('price:收盤價')
position = close > close.average(20)

# 產生回測報告
report = sim(position, resample='M')

# 顯示報告（包含視覺化圖表）
report.display()
```

### 取得績效指標

```
# 取得績效統計（dict）
stats = report.get_stats()
print(f"年化報酬率: {stats['daily_mean'] * 100:.2f}%")
print(f"夏普率: {stats['daily_sharpe']:.2f}")
print(f"最大回撤: {stats['max_drawdown'] * 100:.2f}%")
print(f"勝率: {stats['win_ratio'] * 100:.2f}%")

# 取得結構化績效指標（nested dict）
metrics = report.get_metrics()
print(f"年化報酬率: {metrics['profitability']['annualReturn']:.2%}")
print(f"夏普率: {metrics['ratio']['sharpeRatio']:.2f}")
print(f"最大回撤: {metrics['risk']['maxDrawdown']:.2%}")
```

### 查看交易記錄

```
# 取得所有交易記錄
trades = report.get_trades()
print(f"總交易次數: {len(trades)}")
print(trades.head())

# 篩選獲利交易
profitable_trades = trades[trades['return'] > 0]
print(f"獲利交易比例: {len(profitable_trades) / len(trades):.1%}")
```

* * *

## 詳細教學

參考 [歷史回測教學](https://finlab.finance/docs/details/backtest/)，了解： - 完整回測流程 - Report 物件的所有方法 - 績效指標解讀 - 交易記錄分析

* * *

## API Reference

### Report

`Report` 物件由 `sim()` 函數產生，包含完整的回測績效資訊。

```
from finlab.backtest import sim

report = sim(position)
```

**Report 物件主要方法**：

| 方法 | 說明 | 常用程度 |
| --- | --- | --- |
| `display()` | 顯示完整報告（含視覺化圖表） | ⭐⭐⭐⭐⭐ |
| `get_stats()` | 取得績效統計（dict） | ⭐⭐⭐⭐⭐ |
| `get_metrics()` | 取得結構化績效指標（nested dict） | ⭐⭐⭐⭐⭐ |
| `get_trades()` | 取得交易記錄（DataFrame） | ⭐⭐⭐⭐⭐ |
| `get_mae_mfe()` | 取得最大不利/有利偏移 | ⭐⭐⭐⭐ |
| `position_info()` | 取得近期持有部位與換股資訊 | ⭐⭐⭐⭐ |
| `upload()` | 上傳至 FinLab 雲端 | ⭐⭐⭐ |
| `run_analysis()` | 執行深度分析模組 | ⭐⭐⭐ |
| `display_mae_mfe_analysis()` | 顯示波動分析圖組 | ⭐⭐⭐ |
| `to_text()` | 文字格式的回測摘要 | ⭐⭐ |
| `to_terminal()` | 終端 ASCII 圖表顯示 | ⭐⭐ |
| `to_html(path, title=None)` | 匯出 HTML 報告，可指定瀏覽器分頁標題 | ⭐⭐ |
| `to_pickle()` / `from_pickle()` | 儲存/載入報告 | ⭐⭐ |

* * *

### display()

顯示完整回測報告，包含視覺化圖表與績效指標。

**使用範例**：

```
# 基礎用法
report.display()

# 回傳 plotly figure 物件供進一步客製化
fig = report.display(return_fig=True)
fig.update_layout(title='我的策略回測')
fig.show()
```

**顯示內容**： - 淨值曲線（策略 vs 基準） - 回撤曲線 - 績效指標表格（年化報酬、夏普率、最大回撤等）

* * *

### get_stats()

取得績效統計資料。

**簽名**：`get_stats(riskfree_rate=0.02)`

`resample` 參數已棄用：它從未生效，現在傳入會發出 `DeprecationWarning`。統計一律以日頻報酬計算（`daily_*`、`monthly_*`、`yearly_*` 欄位已涵蓋各頻率）。

**回傳**：`dict`

**使用範例**：

```
stats = report.get_stats()

print(f"回測期間: {stats['start']} ~ {stats['end']}")
print(f"年化報酬: {stats['daily_mean'] * 100:.2f}%")
print(f"夏普率: {stats['daily_sharpe']:.2f}")
print(f"索提諾比率: {stats['daily_sortino']:.2f}")
print(f"最大回撤: {stats['max_drawdown'] * 100:.2f}%")
print(f"平均回撤: {stats['avg_drawdown'] * 100:.2f}%")
print(f"勝率: {stats['win_ratio'] * 100:.2f}%")
```

**主要回傳欄位**：

| 欄位 | 說明 |
| --- | --- |
| `start` | 回測開始日期（str） |
| `end` | 回測結束日期（str） |
| `daily_mean` | 年化報酬率 |
| `daily_sharpe` | 夏普率 |
| `daily_sortino` | 索提諾比率 |
| `max_drawdown` | 最大回撤 |
| `avg_drawdown` | 平均回撤 |
| `win_ratio` | 勝率 |
| `return_table` | 年月報酬率表（dict） |
| `drawdown_details` | 最大回撤詳情 |

**與 `get_metrics()` 共用的別名**：以下數值同時也能用 `get_metrics()` 的欄位名稱取得，兩種寫法結果相同。

| `get_stats()` 欄位 | 別名（`get_metrics()` 名稱） |
| --- | --- |
| `cagr` | `annualReturn` |
| `daily_sharpe` | `sharpeRatio` |
| `daily_sortino` | `sortinoRatio` |
| `calmar` | `calmarRatio` |
| `daily_vol` | `volatility` |
| `max_drawdown` | `maxDrawdown` |
| `avg_drawdown` | `avgDrawdown` |
| `avg_drawdown_days` | `avgDrawdownDays` |
| `twelve_month_win_perc` | `m12WinRate` |

`win_ratio` 沒有別名：它只計算已出場的交易，`get_metrics()` 的 `winRate` 則包含持有中的交易。

* * *

### get_metrics()

取得結構化績效指標（nested dict），適合上傳雲端或程式化處理。

**簽名**：`get_metrics(stats_=None, riskfree_rate=0.02)`

**回傳**：`dict`，包含以下分類：

**使用範例**：

```
metrics = report.get_metrics()

# 盈利指標
print(f"年化報酬: {metrics['profitability']['annualReturn']:.2%}")
print(f"Alpha: {metrics['profitability']['alpha']:.4f}")
print(f"Beta: {metrics['profitability']['beta']:.4f}")

# 風險指標
print(f"最大回撤: {metrics['risk']['maxDrawdown']:.2%}")
print(f"VaR: {metrics['risk']['valueAtRisk']:.2%}")

# 比率指標
print(f"夏普率: {metrics['ratio']['sharpeRatio']:.2f}")
print(f"索提諾比率: {metrics['ratio']['sortinoRatio']:.2f}")

# 勝率指標
print(f"勝率: {metrics['winrate']['winRate']:.2%}")
```

**回傳結構**：

| 分類 | 欄位 | 說明 |
| --- | --- | --- |
| `backtest` | `startDate`, `endDate`, `feeRatio`, `taxRatio`, `tradeAt`, `market`, `freq` | 回測設定 |
| `profitability` | `annualReturn`, `alpha`, `beta`, `avgNStock`, `maxNStock` | 盈利指標 |
| `risk` | `maxDrawdown`, `avgDrawdown`, `avgDrawdownDays`, `valueAtRisk`, `cvalueAtRisk` | 風險指標 |
| `ratio` | `sharpeRatio`, `sortinoRatio`, `calmarRatio`, `volatility`, `profitFactor`, `tailRatio` | 比率指標 |
| `winrate` | `winRate`, `m12WinRate`, `expectancy`, `mae`, `mfe` | 勝率指標 |
| `liquidity` | `capacity`, `disposalStockRatio`, `warningStockRatio`, `fullDeliveryStockRatio` | 流動性指標 |

* * *

### get_trades()

取得所有交易記錄的詳細資訊。

**回傳**：`pd.DataFrame`

**使用範例**：

```
trades = report.get_trades()

# 分析交易表現
print(f"總交易次數: {len(trades)}")
print(f"平均報酬率: {trades['return'].mean():.2%}")
print(f"勝率: {(trades['return'] > 0).mean():.2%}")

# 篩選大賺或大賠的交易
big_wins = trades[trades['return'] > 0.2]
big_losses = trades[trades['return'] < -0.1]

# 按股票統計
trades_by_stock = trades.groupby('stock_id')['return'].agg(['count', 'mean'])
print(trades_by_stock.sort_values('mean', ascending=False).head())
```

**DataFrame 欄位**：

| 欄位 | 說明 |
| --- | --- |
| `stock_id` | 股票代號（只有代號，例如 `2330`） |
| `name` | 股票名稱（例如 `台積電`；查無名稱時為空字串） |
| `symbol` | 代號加名稱（例如 `2330 台積電`），為相容舊程式保留 |
| `entry_sig_date` | 進場訊號產生日 |
| `exit_sig_date` | 出場訊號產生日 |
| `entry_date` | 進場日 |
| `exit_date` | 出場日 |
| `position` | 持有佔比 |
| `period` | 持有天數 |
| `return` | 報酬率 |
| `trade_price@entry_date` | 進場價 |
| `trade_price@exit_date` | 出場價 |
| `mae` | 持有期間最大不利報酬率幅度 |
| `gmfe` | 持有期間最大有利報酬率幅度 |
| `bmfe` | mae 發生前的最大有利報酬率幅度 |
| `mdd` | 持有期間最大回撤 |
| `pdays` | 處於獲利時的天數 |
| `industry` | 產業別 |

* * *

### get_mae_mfe()

取得最大不利偏移（MAE）與最大有利偏移（MFE）分析。

**使用範例**：

```
# 取得 MAE/MFE 資料
mae_mfe = report.get_mae_mfe()

# 視覺化 MAE/MFE 分布
report.display_mae_mfe_analysis()
```

**應用場景**： - **設定停損點**：觀察 MAE 分布，決定合理的停損幅度 - **設定停利點**：觀察 MFE 分布，決定合理的停利幅度 - **優化進出場**：若 MFE 大但最終報酬小，表示停利過晚

MAE/MFE 解讀

*   **MAE (Maximum Adverse Excursion)**: 持倉期間的最大未實現虧損
*   **MFE (Maximum Favorable Excursion)**: 持倉期間的最大未實現獲利
*   理想情況：MFE 大、MAE 小，表示進場時機佳

* * *

### upload()

上傳回測報告至 FinLab 雲端，供實盤追蹤使用。

**使用範例**：

```
# 上傳報告
report.upload(name='我的動能策略')

# 之後可在 FinLab 網站查看：
# https://ai.finlab.tw/strategies
```

上傳前提

*   需登入 FinLab 帳號（`finlab.login()`）
*   需為 VIP 會員
*   上傳後可用於實盤下單、績效追蹤

* * *

### run_analysis()

執行策略分析外掛模組。

**簽名**：`run_analysis(analysis, display=True, **kwargs)`

**使用範例**：

```
# 傳入分析模組名稱（字串）
report.run_analysis('Liquidity')
report.run_analysis('MaeMfe')
report.run_analysis('AlphaBeta')
report.run_analysis('PeriodStats')
report.run_analysis('Drawdown')

# 不顯示圖表，只取得結果
result = report.run_analysis('Liquidity', display=False)
```

詳細說明請參考 [策略分析模組](https://finlab.finance/docs/reference/analysis/)。

* * *

### to_text()

將回測報告以文字方式呈現，適合 Line 通知、日誌記錄等場景。

**簽名**：`to_text(name=None)`

**使用範例**：

```
text = report.to_text(name='我的策略')
print(text)
```

* * *

### to_terminal()

在終端顯示累積報酬 ASCII 圖表與回撤。

**簽名**：`to_terminal(height=12, width=80, show_benchmark=True, show_drawdown=True)`

**使用範例**：

```
report.to_terminal()

# 自訂高度與寬度
report.to_terminal(height=8, width=60)

# 不顯示 benchmark 和 drawdown
report.to_terminal(show_benchmark=False, show_drawdown=False)
```

安裝

需安裝 `asciichartpy`：`pip install 'finlab[terminal]'`

* * *

### to_pickle() / from_pickle()

儲存與載入報告。

**使用範例**：

```
# 儲存報告
report.to_pickle('my_strategy_report.pkl')

# 載入報告
from finlab.core.report import Report

loaded_report = Report.from_pickle('my_strategy_report.pkl')
loaded_report.display()
```

使用時機

*   回測需要很長時間，想保存結果
*   需要對比不同時期的回測報告
*   與他人分享回測結果

* * *

## 常見問題

### Q: 如何對比多個策略的績效？

```
report1 = sim(position1, resample='M')
report2 = sim(position2, resample='M')

stats1 = report1.get_stats()
stats2 = report2.get_stats()

import pandas as pd

comparison = pd.DataFrame(
    {
        '策略 A': {
            '年化報酬': stats1['daily_mean'],
            '夏普率': stats1['daily_sharpe'],
            '最大回撤': stats1['max_drawdown'],
        },
        '策略 B': {
            '年化報酬': stats2['daily_mean'],
            '夏普率': stats2['daily_sharpe'],
            '最大回撤': stats2['max_drawdown'],
        },
    }
)
print(comparison)
```

### Q: 為什麼我的報告顯示不出來？

```
# 原因 1：忘記呼叫 .display()
report  # ❌ 不會顯示

report.display()  # ✅ 正確

# 原因 2：Jupyter Notebook 環境問題
# 在 notebook 開頭加入：
%matplotlib inline

# 原因 3：資料為空（無任何交易）
trades = report.get_trades()
if len(trades) == 0:
    print("策略無任何交易記錄，請檢查進場條件")
```

### Q: 如何調整報告的視覺化樣式？

```
# 取得 plotly figure 物件
fig = report.display(return_fig=True)

# 修改標題
fig.update_layout(title='我的策略回測報告')

# 修改顏色
fig.update_traces(line_color='blue', selector=dict(name='策略'))

# 調整圖表大小
fig.update_layout(width=1200, height=600)

# 顯示
fig.show()
```

* * *

## 參考資源

*   [歷史回測教學](https://finlab.finance/docs/details/backtest/) - 完整回測流程
*   [策略分析模組](https://finlab.finance/docs/reference/analysis/) - 深度分析工具
*   [多策略組合管理](https://finlab.finance/docs/reference/portfolio/) - Portfolio 物件
*   [完整策略開發流程](https://finlab.finance/docs/workflows/complete_strategy_workflow/) - 端到端工作流程
