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
trade_date: "2026-11-13" | as_of_date: "2026-11-12" | generated_at: "2026-11-12T19:15:49.231427+08:00"
missing: []
狀態判讀: account 與 holdings 為 2026-11-12 收盤結算後的狀態。

### prev_day_orders
outcome: "none" | void_reasons: [] | excluded_codes: []

### account
cash: 183823752.51 | cash_ratio_tradable: 0.198372 | nav_tradable: 926659552.51 | aum: 926659552.51 | receivable_cash: 0 | holdings_count: 30

### 賽期進度
start_date: 2026-10-27 | end_date: 2026-11-27 | elapsed_trading_days: 14 | remaining_trading_days: 11 | progress_pct: 58.3% | phase: mid-late (中後期)

### 帳戶淨值演變
initial_nav: 1,000,000,000 | latest_nav (2026-11-12): 926,659,552.51 | cum_return_pct: -7.33% | peak_nav (2026-10-28): 1,016,667,892.06 | drawdown_from_peak_pct: -8.85% | max_drawdown_pct: -12.02%
nav_return_1d_pct: -1.52% | nav_return_3d_pct: +1.42% | nav_return_5d_pct: +0.36% | consecutive_loss_days: 1
recent_5d_trajectory: 11-06: 8.945億 (-3.13%) -> 11-09: 9.137億 (+2.15%) -> 11-10: 9.221億 (+0.93%) -> 11-11: 9.410億 (+2.05%) -> 11-12: 9.267億 (-1.52%)

### holdings
{
  "_note": "原生欄位: shares, receivable_shares, close_price, tradable_weight；追蹤欄位(百分比單位 %): entry_date, holding_days, avg_cost, pnl_pct, peak_price, peak_pnl_pct, dd_from_peak_pct",
  "1216": {"shares": 489000, "receivable_shares": 0, "close_price": 77.9, "tradable_weight": 0.041108, "entry_date": "2026-11-05", "holding_days": 6, "avg_cost": 80.62, "pnl_pct": -3.37, "peak_price": 80.9, "peak_pnl_pct": 0.35, "dd_from_peak_pct": -3.71},
  "1303": {"shares": 107000, "receivable_shares": 0, "close_price": 293, "tradable_weight": 0.033832, "entry_date": "2026-10-27", "holding_days": 13, "avg_cost": 303.52, "pnl_pct": -3.47, "peak_price": 319, "peak_pnl_pct": 5.1, "dd_from_peak_pct": -8.15},
  "2207": {"shares": 21000, "receivable_shares": 0, "close_price": 521, "tradable_weight": 0.011807, "entry_date": "2026-11-06", "holding_days": 5, "avg_cost": 526.52, "pnl_pct": -1.05, "peak_price": 533, "peak_pnl_pct": 1.23, "dd_from_peak_pct": -2.25},
  "2317": {"shares": 149000, "receivable_shares": 0, "close_price": 240, "tradable_weight": 0.03859, "entry_date": "2026-10-27", "holding_days": 13, "avg_cost": 246.84, "pnl_pct": -2.77, "peak_price": 251.5, "peak_pnl_pct": 1.89, "dd_from_peak_pct": -4.57},
  "2330": {"shares": 23000, "receivable_shares": 0, "close_price": 2340, "tradable_weight": 0.05808, "entry_date": "2026-10-27", "holding_days": 13, "avg_cost": 2392.08, "pnl_pct": -2.18, "peak_price": 2425, "peak_pnl_pct": 1.38, "dd_from_peak_pct": -3.51},
  "2368": {"shares": 17000, "receivable_shares": 0, "close_price": 975, "tradable_weight": 0.017887, "entry_date": "2026-10-27", "holding_days": 13, "avg_cost": 1095.62, "pnl_pct": -11.01, "peak_price": 1185, "peak_pnl_pct": 8.16, "dd_from_peak_pct": -17.72},
  "2376": {"shares": 60000, "receivable_shares": 0, "close_price": 289.5, "tradable_weight": 0.018745, "entry_date": "2026-10-27", "holding_days": 13, "avg_cost": 357.46, "pnl_pct": -19.01, "peak_price": 362.5, "peak_pnl_pct": 1.41, "dd_from_peak_pct": -20.14},
  "2379": {"shares": 35000, "receivable_shares": 0, "close_price": 739, "tradable_weight": 0.027912, "entry_date": "2026-10-27", "holding_days": 13, "avg_cost": 786.83, "pnl_pct": -6.08, "peak_price": 803, "peak_pnl_pct": 2.05, "dd_from_peak_pct": -7.97},
  "2383": {"shares": 3000, "receivable_shares": 0, "close_price": 4105, "tradable_weight": 0.01329, "entry_date": "2026-10-27", "holding_days": 13, "avg_cost": 4889.99, "pnl_pct": -16.05, "peak_price": 5025, "peak_pnl_pct": 2.76, "dd_from_peak_pct": -18.31},
  "2404": {"shares": 9000, "receivable_shares": 0, "close_price": 970, "tradable_weight": 0.009421, "entry_date": "2026-10-27", "holding_days": 13, "avg_cost": 1085.8, "pnl_pct": -10.66, "peak_price": 1105, "peak_pnl_pct": 1.77, "dd_from_peak_pct": -12.22},
  "2412": {"shares": 300000, "receivable_shares": 0, "close_price": 162, "tradable_weight": 0.052446, "entry_date": "2026-11-05", "holding_days": 6, "avg_cost": 162.14, "pnl_pct": -0.09, "peak_price": 163.5, "peak_pnl_pct": 0.84, "dd_from_peak_pct": -0.92},
  "2603": {"shares": 111000, "receivable_shares": 0, "close_price": 251.5, "tradable_weight": 0.030126, "entry_date": "2026-10-27", "holding_days": 13, "avg_cost": 259.74, "pnl_pct": -3.17, "peak_price": 274.5, "peak_pnl_pct": 5.68, "dd_from_peak_pct": -8.38},
  "2880": {"shares": 456000, "receivable_shares": 0, "close_price": 50.5, "tradable_weight": 0.024851, "entry_date": "2026-11-09", "holding_days": 4, "avg_cost": 49.46, "pnl_pct": 2.1, "peak_price": 50.5, "peak_pnl_pct": 2.1, "dd_from_peak_pct": 0.0},
  "2881": {"shares": 181000, "receivable_shares": 0, "close_price": 159, "tradable_weight": 0.031057, "entry_date": "2026-10-27", "holding_days": 13, "avg_cost": 161.41, "pnl_pct": -1.49, "peak_price": 162, "peak_pnl_pct": 0.37, "dd_from_peak_pct": -1.85},
  "2882": {"shares": 217000, "receivable_shares": 0, "close_price": 112, "tradable_weight": 0.026228, "entry_date": "2026-10-27", "holding_days": 13, "avg_cost": 114.11, "pnl_pct": -1.85, "peak_price": 116.5, "peak_pnl_pct": 2.1, "dd_from_peak_pct": -3.86},
  "2884": {"shares": 289000, "receivable_shares": 0, "close_price": 47.2, "tradable_weight": 0.01472, "entry_date": "2026-11-10", "holding_days": 3, "avg_cost": 47.26, "pnl_pct": -0.13, "peak_price": 47.6, "peak_pnl_pct": 0.72, "dd_from_peak_pct": -0.84},
  "2886": {"shares": 752000, "receivable_shares": 0, "close_price": 54.4, "tradable_weight": 0.044147, "entry_date": "2026-11-05", "holding_days": 6, "avg_cost": 54.11, "pnl_pct": 0.54, "peak_price": 54.4, "peak_pnl_pct": 0.54, "dd_from_peak_pct": 0.0},
  "2891": {"shares": 542000, "receivable_shares": 0, "close_price": 75.4, "tradable_weight": 0.044101, "entry_date": "2026-10-27", "holding_days": 13, "avg_cost": 74.77, "pnl_pct": 0.84, "peak_price": 75.9, "peak_pnl_pct": 1.51, "dd_from_peak_pct": -0.66},
  "3034": {"shares": 38000, "receivable_shares": 0, "close_price": 462, "tradable_weight": 0.018945, "entry_date": "2026-10-27", "holding_days": 13, "avg_cost": 595.24, "pnl_pct": -22.38, "peak_price": 599, "peak_pnl_pct": 0.63, "dd_from_peak_pct": -22.87},
  "3037": {"shares": 14000, "receivable_shares": 0, "close_price": 792, "tradable_weight": 0.011966, "entry_date": "2026-10-27", "holding_days": 13, "avg_cost": 1083.4, "pnl_pct": -26.9, "peak_price": 1100, "peak_pnl_pct": 1.53, "dd_from_peak_pct": -28.0},
  "3045": {"shares": 288000, "receivable_shares": 0, "close_price": 130, "tradable_weight": 0.040403, "entry_date": "2026-11-05", "holding_days": 6, "avg_cost": 133.03, "pnl_pct": -2.28, "peak_price": 133, "peak_pnl_pct": -0.02, "dd_from_peak_pct": -2.26},
  "3189": {"shares": 10000, "receivable_shares": 0, "close_price": 667, "tradable_weight": 0.007198, "entry_date": "2026-10-27", "holding_days": 13, "avg_cost": 980.19, "pnl_pct": -31.95, "peak_price": 1035, "peak_pnl_pct": 5.59, "dd_from_peak_pct": -35.56},
  "3231": {"shares": 118000, "receivable_shares": 0, "close_price": 170, "tradable_weight": 0.021648, "entry_date": "2026-10-27", "holding_days": 13, "avg_cost": 190.17, "pnl_pct": -10.61, "peak_price": 194.5, "peak_pnl_pct": 2.28, "dd_from_peak_pct": -12.6},
  "3443": {"shares": 2000, "receivable_shares": 0, "close_price": 7860, "tradable_weight": 0.016964, "entry_date": "2026-10-27", "holding_days": 13, "avg_cost": 7470.14, "pnl_pct": 5.22, "peak_price": 8170, "peak_pnl_pct": 9.37, "dd_from_peak_pct": -3.79},
  "3533": {"shares": 16000, "receivable_shares": 0, "close_price": 1740, "tradable_weight": 0.030043, "entry_date": "2026-10-27", "holding_days": 13, "avg_cost": 1900.12, "pnl_pct": -8.43, "peak_price": 1955, "peak_pnl_pct": 2.89, "dd_from_peak_pct": -11.0},
  "4904": {"shares": 218000, "receivable_shares": 0, "close_price": 108, "tradable_weight": 0.025407, "entry_date": "2026-11-06", "holding_days": 5, "avg_cost": 109.4, "pnl_pct": -1.28, "peak_price": 112, "peak_pnl_pct": 2.37, "dd_from_peak_pct": -3.57},
  "4938": {"shares": 408000, "receivable_shares": 0, "close_price": 92.2, "tradable_weight": 0.040595, "entry_date": "2026-10-27", "holding_days": 13, "avg_cost": 104.33, "pnl_pct": -11.63, "peak_price": 108, "peak_pnl_pct": 3.52, "dd_from_peak_pct": -14.63},
  "4958": {"shares": 24000, "receivable_shares": 0, "close_price": 430, "tradable_weight": 0.011137, "entry_date": "2026-10-27", "holding_days": 13, "avg_cost": 546.34, "pnl_pct": -21.29, "peak_price": 550, "peak_pnl_pct": 0.67, "dd_from_peak_pct": -21.82},
  "5880": {"shares": 641000, "receivable_shares": 0, "close_price": 28.2, "tradable_weight": 0.019507, "entry_date": "2026-11-09", "holding_days": 4, "avg_cost": 27.99, "pnl_pct": 0.75, "peak_price": 28.2, "peak_pnl_pct": 0.75, "dd_from_peak_pct": 0.0},
  "6505": {"shares": 200000, "receivable_shares": 0, "close_price": 90.2, "tradable_weight": 0.019468, "entry_date": "2026-10-27", "holding_days": 13, "avg_cost": 106.04, "pnl_pct": -14.94, "peak_price": 106, "peak_pnl_pct": -0.04, "dd_from_peak_pct": -14.91}
}

### compliance
violations: 1 | notices: 0
incidents (date,check_code,status,message):
2026-11-12,decision_consistency,fail,當日未於繳交窗口內完成申報
