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
trade_date: "2026-11-23" | as_of_date: "2026-11-20" | generated_at: "2026-11-22T22:53:15.013204+08:00"
missing: []
狀態判讀: account 與 holdings 為 2026-11-20 收盤結算後的狀態。

### prev_day_orders
outcome: "executed" | void_reasons: [] | excluded_codes: []

### account
cash: 143579672.93 | cash_ratio_tradable: 0.171413 | nav_tradable: 837624222.9300001 | aum: 837624222.93 | receivable_cash: 0 | holdings_count: 24

### 賽期進度
start_date: 2026-10-27 | end_date: 2026-11-27 | elapsed_trading_days: 20 | remaining_trading_days: 5 | progress_pct: 83.3% | phase: sprint (最後衝刺期，避免新建倉低波動防禦股)

### 帳戶淨值演變
initial_nav: 1,000,000,000 | latest_nav (2026-11-20): 837,624,222.93 | cum_return_pct: -16.24% | peak_nav (2026-10-28): 1,016,667,892.06 | drawdown_from_peak_pct: -17.61% | max_drawdown_pct: -17.61%
nav_return_1d_pct: -4.51% | nav_return_3d_pct: -6.50% | nav_return_5d_pct: -11.00% | consecutive_loss_days: 5
recent_5d_trajectory: 11-16: 9.037億 (-3.98%) -> 11-17: 8.958億 (-0.88%) -> 11-18: 8.905億 (-0.59%) -> 11-19: 8.772億 (-1.50%) -> 11-20: 8.376億 (-4.51%)

### holdings
{
  "_note": "原生欄位: shares, receivable_shares, close_price, tradable_weight；追蹤欄位(百分比單位 %): entry_date, holding_days, avg_cost, pnl_pct, peak_price, peak_pnl_pct, dd_from_peak_pct",
  "1216": {"shares": 802000, "receivable_shares": 0, "close_price": 75, "tradable_weight": 0.07181, "entry_date": "2026-11-05", "holding_days": 12, "avg_cost": 79.62, "pnl_pct": -5.8, "peak_price": 80.9, "peak_pnl_pct": 1.61, "dd_from_peak_pct": -7.29},
  "2207": {"shares": 80000, "receivable_shares": 0, "close_price": 516, "tradable_weight": 0.049282, "entry_date": "2026-11-06", "holding_days": 11, "avg_cost": 531.68, "pnl_pct": -2.95, "peak_price": 546, "peak_pnl_pct": 2.69, "dd_from_peak_pct": -5.49},
  "2317": {"shares": 99000, "receivable_shares": 0, "close_price": 210, "tradable_weight": 0.02482, "entry_date": "2026-11-20", "holding_days": 1, "avg_cost": 211.67, "pnl_pct": -0.79, "peak_price": 210, "peak_pnl_pct": -0.79, "dd_from_peak_pct": 0.0},
  "2330": {"shares": 10000, "receivable_shares": 0, "close_price": 2000, "tradable_weight": 0.023877, "entry_date": "2026-10-27", "holding_days": 19, "avg_cost": 2386.33, "pnl_pct": -16.19, "peak_price": 2425, "peak_pnl_pct": 1.62, "dd_from_peak_pct": -17.53},
  "2379": {"shares": 31000, "receivable_shares": 0, "close_price": 668, "tradable_weight": 0.024722, "entry_date": "2026-10-27", "holding_days": 19, "avg_cost": 785.38, "pnl_pct": -14.95, "peak_price": 803, "peak_pnl_pct": 2.24, "dd_from_peak_pct": -16.81},
  "2412": {"shares": 422000, "receivable_shares": 0, "close_price": 162.5, "tradable_weight": 0.081868, "entry_date": "2026-11-05", "holding_days": 12, "avg_cost": 162.7, "pnl_pct": -0.13, "peak_price": 166, "peak_pnl_pct": 2.03, "dd_from_peak_pct": -2.11},
  "2603": {"shares": 85000, "receivable_shares": 0, "close_price": 233, "tradable_weight": 0.023644, "entry_date": "2026-10-27", "holding_days": 19, "avg_cost": 259.55, "pnl_pct": -10.23, "peak_price": 274.5, "peak_pnl_pct": 5.76, "dd_from_peak_pct": -15.12},
  "2609": {"shares": 367000, "receivable_shares": 0, "close_price": 53, "tradable_weight": 0.023222, "entry_date": "2026-11-19", "holding_days": 2, "avg_cost": 58.26, "pnl_pct": -9.04, "peak_price": 57.3, "peak_pnl_pct": -1.66, "dd_from_peak_pct": -7.5},
  "2610": {"shares": 1163000, "receivable_shares": 0, "close_price": 21.3, "tradable_weight": 0.029574, "entry_date": "2026-11-17", "holding_days": 4, "avg_cost": 22.9, "pnl_pct": -7.0, "peak_price": 23.1, "peak_pnl_pct": 0.86, "dd_from_peak_pct": -7.79},
  "2618": {"shares": 838000, "receivable_shares": 0, "close_price": 44.65, "tradable_weight": 0.04467, "entry_date": "2026-11-16", "holding_days": 5, "avg_cost": 47.71, "pnl_pct": -6.42, "peak_price": 48.1, "peak_pnl_pct": 0.81, "dd_from_peak_pct": -7.17},
  "2880": {"shares": 448000, "receivable_shares": 0, "close_price": 47, "tradable_weight": 0.025138, "entry_date": "2026-11-20", "holding_days": 1, "avg_cost": 47.26, "pnl_pct": -0.54, "peak_price": 47, "peak_pnl_pct": -0.54, "dd_from_peak_pct": 0.0},
  "2886": {"shares": 812000, "receivable_shares": 0, "close_price": 51.8, "tradable_weight": 0.050215, "entry_date": "2026-11-05", "holding_days": 12, "avg_cost": 54.08, "pnl_pct": -4.22, "peak_price": 55.4, "peak_pnl_pct": 2.43, "dd_from_peak_pct": -6.5},
  "2891": {"shares": 606000, "receivable_shares": 0, "close_price": 68, "tradable_weight": 0.049196, "entry_date": "2026-10-27", "holding_days": 19, "avg_cost": 74.99, "pnl_pct": -9.32, "peak_price": 78.7, "peak_pnl_pct": 4.95, "dd_from_peak_pct": -13.6},
  "2892": {"shares": 425000, "receivable_shares": 0, "close_price": 37.6, "tradable_weight": 0.019078, "entry_date": "2026-11-18", "holding_days": 3, "avg_cost": 40.94, "pnl_pct": -8.15, "peak_price": 41, "peak_pnl_pct": 0.15, "dd_from_peak_pct": -8.29},
  "2912": {"shares": 95000, "receivable_shares": 0, "close_price": 204, "tradable_weight": 0.023137, "entry_date": "2026-11-19", "holding_days": 2, "avg_cost": 211.64, "pnl_pct": -3.61, "peak_price": 210, "peak_pnl_pct": -0.78, "dd_from_peak_pct": -2.86},
  "3045": {"shares": 306000, "receivable_shares": 0, "close_price": 123, "tradable_weight": 0.044934, "entry_date": "2026-11-05", "holding_days": 12, "avg_cost": 132.8, "pnl_pct": -7.38, "peak_price": 133, "peak_pnl_pct": 0.15, "dd_from_peak_pct": -7.52},
  "3227": {"shares": 96000, "receivable_shares": 0, "close_price": 169.5, "tradable_weight": 0.019426, "entry_date": "2026-11-19", "holding_days": 2, "avg_cost": 181.28, "pnl_pct": -6.5, "peak_price": 178.5, "peak_pnl_pct": -1.53, "dd_from_peak_pct": -5.04},
  "3293": {"shares": 55000, "receivable_shares": 0, "close_price": 754, "tradable_weight": 0.049509, "entry_date": "2026-11-17", "holding_days": 4, "avg_cost": 787.46, "pnl_pct": -4.25, "peak_price": 799, "peak_pnl_pct": 1.47, "dd_from_peak_pct": -5.63},
  "4749": {"shares": 23000, "receivable_shares": 0, "close_price": 590, "tradable_weight": 0.016201, "entry_date": "2026-11-19", "holding_days": 2, "avg_cost": 663.53, "pnl_pct": -11.08, "peak_price": 655, "peak_pnl_pct": -1.29, "dd_from_peak_pct": -9.92},
  "4904": {"shares": 290000, "receivable_shares": 0, "close_price": 103, "tradable_weight": 0.03566, "entry_date": "2026-11-06", "holding_days": 11, "avg_cost": 109.19, "pnl_pct": -5.67, "peak_price": 112, "peak_pnl_pct": 2.58, "dd_from_peak_pct": -8.04},
  "5871": {"shares": 176000, "receivable_shares": 0, "close_price": 94, "tradable_weight": 0.019751, "entry_date": "2026-11-20", "holding_days": 1, "avg_cost": 95.63, "pnl_pct": -1.71, "peak_price": 94, "peak_pnl_pct": -1.71, "dd_from_peak_pct": 0.0},
  "5876": {"shares": 657000, "receivable_shares": 0, "close_price": 49.6, "tradable_weight": 0.038904, "entry_date": "2026-11-18", "holding_days": 3, "avg_cost": 52.32, "pnl_pct": -5.19, "peak_price": 53.4, "peak_pnl_pct": 2.07, "dd_from_peak_pct": -7.12},
  "5880": {"shares": 641000, "receivable_shares": 0, "close_price": 26.4, "tradable_weight": 0.020203, "entry_date": "2026-11-09", "holding_days": 10, "avg_cost": 27.99, "pnl_pct": -5.68, "peak_price": 28.55, "peak_pnl_pct": 2.0, "dd_from_peak_pct": -7.53},
  "8415": {"shares": 415000, "receivable_shares": 0, "close_price": 39.85, "tradable_weight": 0.019744, "entry_date": "2026-11-20", "holding_days": 1, "avg_cost": 40.33, "pnl_pct": -1.19, "peak_price": 39.85, "peak_pnl_pct": -1.19, "dd_from_peak_pct": 0.0}
}

### compliance
violations: 1 | notices: 0
incidents (date,check_code,status,message):
2026-11-12,decision_consistency,fail,當日未於繳交窗口內完成申報
