# DataPack（官方每日帳戶/部位/合規快照）
## 欄位說明（依官方 DataPack 規格書 v4.3）
單位：金額=元；比率=小數(0.1125 表示 11.25%)；股數=整數股；日期=YYYY-MM-DD；時間=台北時間(+08:00)。
- trade_date：本檔對應的交易日，即接下來要繳交的那一個交易日。
- as_of_date：account 與 holdings 實際反映的交易日（有日期時為 trade_date 的前一交易日收盤結算後結果）。null=尚無結算資料：第一個交易日（account 為全現金、0 檔的真值），或前一交易日結算尚未產生（missing 含 prev_settlement，此時 account 整段為 null）。
- missing：系統缺少的資料源，齊備時為 []。prev_settlement=前一交易日結算尚未產生，account、as_of_date、holdings 皆為 null；prev_close=收盤價尚未匯入，account.cash_ratio_tradable 為 null。
- prev_day_orders.outcome：none=前一交易日未繳交，沒有委託；unknown=委託結果尚未判定；voided=已繳交但整批作廢、未成交；executed=有成交。
- prev_day_orders.void_reasons：整批作廢的全部原因（outcome 為 voided 時至少一筆，其餘為 []）。值：insufficient_funds資金不足 / oversell賣出股數超過持股 / no_price委託標的缺當日成交均價且不在標的池內 / compliance_fail合規檢查未通過（持股檔數、標的池限制、現金部位、當日加碼個股權重之一，不細分） / dplan_reference_chain文件引用鏈不完整 / dplan_decision_coverage決策覆蓋不完整 / dplan_round_lot委託非整股。
- prev_day_orders.excluded_codes：被排除、未成交，但其餘委託照常成交的證券代號（outcome 為 executed 時仍可能非空：該檔缺當日成交均價）。
- account.cash：可動用現金（不含應收配息）。不等於當日買進上限，交割以淨額計，同日賣出款也計入結算。
- account.cash_ratio_tradable：cash ÷ nav_tradable。missing 非空時為 null。
- account.nav_tradable：可交易淨值 = cash + Σ(holdings.shares × holdings.close_price)，是計算現金比與個股權重的分母。
- account.aum：總資產，另含應收配息與應收配股市值。不是 nav_tradable，不可用於計算比率。
- account.receivable_cash：已生效的應收配息。計入 aum，賽期內不會到帳，不可用於下單。
- account.holdings_count：持股檔數，只計 shares>0 的檔；與 holdings 的列數不一定相同。
- holdings（逐檔一列，shares 與 receivable_shares 之一不為 0 即列出）：code=證券代號；shares=庫存持股，賣出不得超過此數；receivable_shares=應收配股，賽期內不可賣、不計入 holdings_count 與權重；close_price=as_of_date 收盤價，null=該檔查無行情，計算 nav_tradable 時以 0 計入；tradable_weight=個股權重(分母為 nav_tradable)，null=不適用（只有應收配股或無收盤價，不是 0）。
  holdings 為 [] 只在成功建倉前，代表真的空手；為 null（結算未產生）則不是空手，兩者不同。
- compliance.violations：違規天數（累計），為取消資格的依據（對應後台右上角「警告次數」）。compliance.notices：異常提示列數（累計），不計入取消資格。
- compliance.incidents：違規與異常提示紀錄。status=fail 計入 violations；status=warn 計入 notices。message 為判定說明。
- 賽期進度與帳戶淨值演變（由歷史 DataPack 計算）：
  - elapsed_trading_days / remaining_trading_days / progress_pct / phase：賽期已過交易日、剩餘交易日、進度 (%) 與階段（剩餘 <=5 日為 sprint 衝刺期）。
  - cum_return_pct：相對初始 10 億之累計帳面報酬率 (%)；peak_nav / drawdown_from_peak_pct / max_drawdown_pct：賽期最高淨值、距高點回撤 (%) 與歷史最大回撤 MDD (%)。
  - nav_return_1d_pct / nav_return_3d_pct / nav_return_5d_pct：近 1 / 3 / 5 個交易日淨值變化率 (%)；consecutive_loss_days：連續虧損天數；recent_5d_trajectory：近 5 日淨值走勢。
- holdings 衍生追蹤欄位（由歷史 DataPack 與 backend_reports 實際成交紀錄計算，百分比欄位單位為 %）：
  - entry_date / holding_days：最近一次建倉日期與已持有交易日數；avg_cost：實際成交移動加權平均成本；pnl_pct：目前未實現損益 (%)。
  - peak_price / peak_pnl_pct / dd_from_peak_pct：持有期間最高收盤價、最高浮盈 (%) 與自高點回落幅度 (%)（移動停利依據）。

## 資料
schema_version: "3.0" | doc_type: "DataPack" | team_id: "TEAM_11402"
trade_date: "2026-11-19" | as_of_date: "2026-11-18" | generated_at: "2026-11-18T19:17:18.283618+08:00"
missing: []
狀態判讀: account 與 holdings 為 2026-11-18 收盤結算後的狀態。

### prev_day_orders
outcome: "executed" | void_reasons: [] | excluded_codes: []

### account
cash: 157169606.27 | cash_ratio_tradable: 0.176491 | nav_tradable: 890526706.27 | aum: 890526706.27 | receivable_cash: 0 | holdings_count: 24

### 賽期進度
start_date: 2026-10-27 | end_date: 2026-11-27 | elapsed_trading_days: 18 | remaining_trading_days: 7 | progress_pct: 75.0% | phase: mid-late (中後期)

### 帳戶淨值演變
initial_nav: 1,000,000,000 | latest_nav (2026-11-18): 890,526,706.27 | cum_return_pct: -10.95% | peak_nav (2026-10-28): 1,016,667,892.06 | drawdown_from_peak_pct: -12.41% | max_drawdown_pct: -12.41%
nav_return_1d_pct: -0.59% | nav_return_3d_pct: -5.38% | nav_return_5d_pct: -5.36% | consecutive_loss_days: 3
recent_5d_trajectory: 11-12: 9.267億 (-1.52%) -> 11-13: 9.412億 (+1.57%) -> 11-16: 9.037億 (-3.98%) -> 11-17: 8.958億 (-0.88%) -> 11-18: 8.905億 (-0.59%)

### holdings
{
  "_note": "原生欄位: shares, receivable_shares, close_price, tradable_weight；追蹤欄位(百分比單位 %): entry_date, holding_days, avg_cost, pnl_pct, peak_price, peak_pnl_pct, dd_from_peak_pct",
  "1216": {"shares": 735000, "receivable_shares": 0, "close_price": 78.8, "tradable_weight": 0.065038, "entry_date": "2026-11-05", "holding_days": 10, "avg_cost": 79.99, "pnl_pct": -1.49, "peak_price": 80.9, "peak_pnl_pct": 1.13, "dd_from_peak_pct": -2.6},
  "2207": {"shares": 50000, "receivable_shares": 0, "close_price": 538, "tradable_weight": 0.030207, "entry_date": "2026-11-06", "holding_days": 9, "avg_cost": 531.8, "pnl_pct": 1.17, "peak_price": 538, "peak_pnl_pct": 1.17, "dd_from_peak_pct": 0.0},
  "2330": {"shares": 22000, "receivable_shares": 0, "close_price": 2175, "tradable_weight": 0.053732, "entry_date": "2026-10-27", "holding_days": 17, "avg_cost": 2386.33, "pnl_pct": -8.86, "peak_price": 2425, "peak_pnl_pct": 1.62, "dd_from_peak_pct": -10.31},
  "2379": {"shares": 31000, "receivable_shares": 0, "close_price": 734, "tradable_weight": 0.025551, "entry_date": "2026-10-27", "holding_days": 17, "avg_cost": 785.38, "pnl_pct": -6.54, "peak_price": 803, "peak_pnl_pct": 2.24, "dd_from_peak_pct": -8.59},
  "2412": {"shares": 381000, "receivable_shares": 0, "close_price": 164.5, "tradable_weight": 0.070379, "entry_date": "2026-11-05", "holding_days": 10, "avg_cost": 162.59, "pnl_pct": 1.18, "peak_price": 165, "peak_pnl_pct": 1.48, "dd_from_peak_pct": -0.3},
  "2454": {"shares": 6000, "receivable_shares": 0, "close_price": 3940, "tradable_weight": 0.026546, "entry_date": "2026-11-16", "holding_days": 3, "avg_cost": 3912.0, "pnl_pct": 0.72, "peak_price": 3940, "peak_pnl_pct": 0.72, "dd_from_peak_pct": 0.0},
  "2603": {"shares": 133000, "receivable_shares": 0, "close_price": 257.5, "tradable_weight": 0.038458, "entry_date": "2026-10-27", "holding_days": 17, "avg_cost": 259.55, "pnl_pct": -0.79, "peak_price": 274.5, "peak_pnl_pct": 5.76, "dd_from_peak_pct": -6.19},
  "2610": {"shares": 1163000, "receivable_shares": 0, "close_price": 22.9, "tradable_weight": 0.029907, "entry_date": "2026-11-17", "holding_days": 2, "avg_cost": 22.9, "pnl_pct": -0.01, "peak_price": 23.1, "peak_pnl_pct": 0.86, "dd_from_peak_pct": -0.87},
  "2618": {"shares": 838000, "receivable_shares": 0, "close_price": 46.8, "tradable_weight": 0.04404, "entry_date": "2026-11-16", "holding_days": 3, "avg_cost": 47.71, "pnl_pct": -1.91, "peak_price": 48.1, "peak_pnl_pct": 0.81, "dd_from_peak_pct": -2.7},
  "2880": {"shares": 529000, "receivable_shares": 0, "close_price": 48.2, "tradable_weight": 0.028632, "entry_date": "2026-11-09", "holding_days": 8, "avg_cost": 49.59, "pnl_pct": -2.8, "peak_price": 51.9, "peak_pnl_pct": 4.66, "dd_from_peak_pct": -7.13},
  "2881": {"shares": 89000, "receivable_shares": 0, "close_price": 149, "tradable_weight": 0.014891, "entry_date": "2026-10-27", "holding_days": 17, "avg_cost": 161.5, "pnl_pct": -7.74, "peak_price": 162, "peak_pnl_pct": 0.31, "dd_from_peak_pct": -8.02},
  "2882": {"shares": 205000, "receivable_shares": 0, "close_price": 110, "tradable_weight": 0.025322, "entry_date": "2026-10-27", "holding_days": 17, "avg_cost": 114.13, "pnl_pct": -3.62, "peak_price": 116.5, "peak_pnl_pct": 2.07, "dd_from_peak_pct": -5.58},
  "2884": {"shares": 374000, "receivable_shares": 0, "close_price": 42.15, "tradable_weight": 0.017702, "entry_date": "2026-11-10", "holding_days": 7, "avg_cost": 47.29, "pnl_pct": -10.87, "peak_price": 48.3, "peak_pnl_pct": 2.13, "dd_from_peak_pct": -12.73},
  "2886": {"shares": 900000, "receivable_shares": 0, "close_price": 52.6, "tradable_weight": 0.05316, "entry_date": "2026-11-05", "holding_days": 10, "avg_cost": 54.08, "pnl_pct": -2.74, "peak_price": 55.4, "peak_pnl_pct": 2.43, "dd_from_peak_pct": -5.05},
  "2891": {"shares": 693000, "receivable_shares": 0, "close_price": 73.4, "tradable_weight": 0.057119, "entry_date": "2026-10-27", "holding_days": 17, "avg_cost": 74.99, "pnl_pct": -2.12, "peak_price": 78.7, "peak_pnl_pct": 4.95, "dd_from_peak_pct": -6.73},
  "2892": {"shares": 425000, "receivable_shares": 0, "close_price": 41, "tradable_weight": 0.019567, "entry_date": "2026-11-18", "holding_days": 1, "avg_cost": 40.94, "pnl_pct": 0.15, "peak_price": 41, "peak_pnl_pct": 0.15, "dd_from_peak_pct": 0.0},
  "3045": {"shares": 306000, "receivable_shares": 0, "close_price": 127.5, "tradable_weight": 0.043811, "entry_date": "2026-11-05", "holding_days": 10, "avg_cost": 132.8, "pnl_pct": -3.99, "peak_price": 133, "peak_pnl_pct": 0.15, "dd_from_peak_pct": -4.14},
  "3293": {"shares": 39000, "receivable_shares": 0, "close_price": 799, "tradable_weight": 0.034992, "entry_date": "2026-11-17", "holding_days": 2, "avg_cost": 792.83, "pnl_pct": 0.78, "peak_price": 799, "peak_pnl_pct": 0.78, "dd_from_peak_pct": 0.0},
  "3491": {"shares": 21000, "receivable_shares": 0, "close_price": 1510, "tradable_weight": 0.035608, "entry_date": "2026-11-17", "holding_days": 2, "avg_cost": 1409.78, "pnl_pct": 7.11, "peak_price": 1510, "peak_pnl_pct": 7.11, "dd_from_peak_pct": 0.0},
  "3533": {"shares": 6000, "receivable_shares": 0, "close_price": 1695, "tradable_weight": 0.01142, "entry_date": "2026-10-27", "holding_days": 17, "avg_cost": 1900.12, "pnl_pct": -10.8, "peak_price": 1955, "peak_pnl_pct": 2.89, "dd_from_peak_pct": -13.3},
  "3661": {"shares": 5000, "receivable_shares": 0, "close_price": 3950, "tradable_weight": 0.022178, "entry_date": "2026-11-16", "holding_days": 3, "avg_cost": 3821.48, "pnl_pct": 3.36, "peak_price": 3950, "peak_pnl_pct": 3.36, "dd_from_peak_pct": 0.0},
  "4904": {"shares": 290000, "receivable_shares": 0, "close_price": 109, "tradable_weight": 0.035496, "entry_date": "2026-11-06", "holding_days": 9, "avg_cost": 109.19, "pnl_pct": -0.17, "peak_price": 112, "peak_pnl_pct": 2.58, "dd_from_peak_pct": -2.68},
  "5876": {"shares": 336000, "receivable_shares": 0, "close_price": 52.9, "tradable_weight": 0.019959, "entry_date": "2026-11-18", "holding_days": 1, "avg_cost": 53.03, "pnl_pct": -0.24, "peak_price": 52.9, "peak_pnl_pct": -0.24, "dd_from_peak_pct": 0.0},
  "5880": {"shares": 641000, "receivable_shares": 0, "close_price": 27.5, "tradable_weight": 0.019794, "entry_date": "2026-11-09", "holding_days": 8, "avg_cost": 27.99, "pnl_pct": -1.75, "peak_price": 28.55, "peak_pnl_pct": 2.0, "dd_from_peak_pct": -3.68}
}

### compliance
violations: 1 | notices: 0
incidents (date,check_code,status,message):
2026-11-12,decision_consistency,fail,當日未於繳交窗口內完成申報
