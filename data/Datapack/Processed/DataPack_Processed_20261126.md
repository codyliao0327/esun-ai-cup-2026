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
trade_date: "2026-11-26" | as_of_date: "2026-11-25" | generated_at: "2026-11-26T01:30:15.170204+08:00"
missing: []
狀態判讀: account 與 holdings 為 2026-11-25 收盤結算後的狀態。

### prev_day_orders
outcome: "executed" | void_reasons: [] | excluded_codes: []

### account
cash: 143324328.51 | cash_ratio_tradable: 0.172399 | nav_tradable: 831352578.51 | aum: 831352578.51 | receivable_cash: 0 | holdings_count: 25

### 賽期進度
start_date: 2026-10-27 | end_date: 2026-11-27 | elapsed_trading_days: 23 | remaining_trading_days: 2 | progress_pct: 95.8% | phase: sprint (最後衝刺期，避免新建倉低波動防禦股)

### 帳戶淨值演變
initial_nav: 1,000,000,000 | latest_nav (2026-11-25): 831,352,578.51 | cum_return_pct: -16.86% | peak_nav (2026-10-28): 1,016,667,892.06 | drawdown_from_peak_pct: -18.23% | max_drawdown_pct: -18.23%
nav_return_1d_pct: -4.06% | nav_return_3d_pct: -0.75% | nav_return_5d_pct: -6.64% | consecutive_loss_days: 1
recent_5d_trajectory: 11-19: 8.772億 (-1.50%) -> 11-20: 8.376億 (-4.51%) -> 11-23: 8.321億 (-0.66%) -> 11-24: 8.665億 (+4.14%) -> 11-25: 8.314億 (-4.06%)

### holdings
{
  "_note": "原生欄位: shares, receivable_shares, close_price, tradable_weight；追蹤欄位(百分比單位 %): entry_date, holding_days, avg_cost, pnl_pct, peak_price, peak_pnl_pct, dd_from_peak_pct",
  "2059": {"shares": 1000, "receivable_shares": 0, "close_price": 6505, "tradable_weight": 0.007825, "entry_date": "2026-11-24", "holding_days": 2, "avg_cost": 6200.0, "pnl_pct": 4.92, "peak_price": 6505, "peak_pnl_pct": 4.92, "dd_from_peak_pct": 0.0},
  "2308": {"shares": 32000, "receivable_shares": 0, "close_price": 1055, "tradable_weight": 0.040609, "entry_date": "2026-11-24", "holding_days": 2, "avg_cost": 1085.0, "pnl_pct": -2.76, "peak_price": 1085, "peak_pnl_pct": 0.0, "dd_from_peak_pct": -2.76},
  "2317": {"shares": 153000, "receivable_shares": 0, "close_price": 206.5, "tradable_weight": 0.038004, "entry_date": "2026-11-20", "holding_days": 4, "avg_cost": 216.9, "pnl_pct": -4.8, "peak_price": 226.5, "peak_pnl_pct": 4.42, "dd_from_peak_pct": -8.83},
  "2330": {"shares": 54000, "receivable_shares": 0, "close_price": 2150, "tradable_weight": 0.139652, "entry_date": "2026-10-27", "holding_days": 22, "avg_cost": 2256.5, "pnl_pct": -4.72, "peak_price": 2425, "peak_pnl_pct": 7.47, "dd_from_peak_pct": -11.34},
  "2345": {"shares": 24000, "receivable_shares": 0, "close_price": 1475, "tradable_weight": 0.042581, "entry_date": "2026-11-24", "holding_days": 2, "avg_cost": 1485.0, "pnl_pct": -0.67, "peak_price": 1485, "peak_pnl_pct": 0.0, "dd_from_peak_pct": -0.67},
  "2368": {"shares": 28000, "receivable_shares": 0, "close_price": 905, "tradable_weight": 0.03048, "entry_date": "2026-11-24", "holding_days": 2, "avg_cost": 860.0, "pnl_pct": 5.23, "peak_price": 905, "peak_pnl_pct": 5.23, "dd_from_peak_pct": 0.0},
  "2382": {"shares": 106000, "receivable_shares": 0, "close_price": 261, "tradable_weight": 0.033278, "entry_date": "2026-11-24", "holding_days": 2, "avg_cost": 280.82, "pnl_pct": -7.06, "peak_price": 282.5, "peak_pnl_pct": 0.6, "dd_from_peak_pct": -7.61},
  "2383": {"shares": 6000, "receivable_shares": 0, "close_price": 3355, "tradable_weight": 0.024214, "entry_date": "2026-11-24", "holding_days": 2, "avg_cost": 3395.0, "pnl_pct": -1.18, "peak_price": 3395, "peak_pnl_pct": 0.0, "dd_from_peak_pct": -1.18},
  "2454": {"shares": 10000, "receivable_shares": 0, "close_price": 3645, "tradable_weight": 0.043844, "entry_date": "2026-11-24", "holding_days": 2, "avg_cost": 4050.0, "pnl_pct": -10.0, "peak_price": 4050, "peak_pnl_pct": 0.0, "dd_from_peak_pct": -10.0},
  "2603": {"shares": 83000, "receivable_shares": 0, "close_price": 252.5, "tradable_weight": 0.025209, "entry_date": "2026-11-25", "holding_days": 1, "avg_cost": 251.52, "pnl_pct": 0.39, "peak_price": 252.5, "peak_pnl_pct": 0.39, "dd_from_peak_pct": 0.0},
  "2618": {"shares": 600000, "receivable_shares": 0, "close_price": 45.7, "tradable_weight": 0.032982, "entry_date": "2026-11-25", "holding_days": 1, "avg_cost": 45.82, "pnl_pct": -0.26, "peak_price": 45.7, "peak_pnl_pct": -0.26, "dd_from_peak_pct": 0.0},
  "3017": {"shares": 11000, "receivable_shares": 0, "close_price": 2545, "tradable_weight": 0.033674, "entry_date": "2026-11-24", "holding_days": 2, "avg_cost": 2600.0, "pnl_pct": -2.12, "peak_price": 2600, "peak_pnl_pct": 0.0, "dd_from_peak_pct": -2.12},
  "3227": {"shares": 96000, "receivable_shares": 0, "close_price": 178, "tradable_weight": 0.020554, "entry_date": "2026-11-19", "holding_days": 5, "avg_cost": 181.28, "pnl_pct": -1.81, "peak_price": 188, "peak_pnl_pct": 3.71, "dd_from_peak_pct": -5.32},
  "3260": {"shares": 76000, "receivable_shares": 0, "close_price": 244, "tradable_weight": 0.022306, "entry_date": "2026-11-24", "holding_days": 2, "avg_cost": 272.3, "pnl_pct": -10.39, "peak_price": 271, "peak_pnl_pct": -0.48, "dd_from_peak_pct": -9.96},
  "3293": {"shares": 22000, "receivable_shares": 0, "close_price": 775, "tradable_weight": 0.020509, "entry_date": "2026-11-17", "holding_days": 7, "avg_cost": 783.97, "pnl_pct": -1.14, "peak_price": 799, "peak_pnl_pct": 1.92, "dd_from_peak_pct": -3.0},
  "3661": {"shares": 8000, "receivable_shares": 0, "close_price": 3605, "tradable_weight": 0.03469, "entry_date": "2026-11-24", "holding_days": 2, "avg_cost": 3915.0, "pnl_pct": -7.92, "peak_price": 3915, "peak_pnl_pct": 0.0, "dd_from_peak_pct": -7.92},
  "3665": {"shares": 21000, "receivable_shares": 0, "close_price": 1630, "tradable_weight": 0.041174, "entry_date": "2026-11-24", "holding_days": 2, "avg_cost": 1570.0, "pnl_pct": 3.82, "peak_price": 1630, "peak_pnl_pct": 3.82, "dd_from_peak_pct": 0.0},
  "3711": {"shares": 29000, "receivable_shares": 0, "close_price": 488, "tradable_weight": 0.017023, "entry_date": "2026-11-24", "holding_days": 2, "avg_cost": 530.0, "pnl_pct": -7.92, "peak_price": 530, "peak_pnl_pct": 0.0, "dd_from_peak_pct": -7.92},
  "5289": {"shares": 23000, "receivable_shares": 0, "close_price": 768, "tradable_weight": 0.021247, "entry_date": "2026-11-24", "holding_days": 2, "avg_cost": 853.0, "pnl_pct": -9.96, "peak_price": 853, "peak_pnl_pct": 0.0, "dd_from_peak_pct": -9.96},
  "6139": {"shares": 34000, "receivable_shares": 0, "close_price": 555, "tradable_weight": 0.022698, "entry_date": "2026-11-24", "holding_days": 2, "avg_cost": 606.0, "pnl_pct": -8.42, "peak_price": 606, "peak_pnl_pct": 0.0, "dd_from_peak_pct": -8.42},
  "6223": {"shares": 4000, "receivable_shares": 0, "close_price": 3770, "tradable_weight": 0.018139, "entry_date": "2026-11-24", "holding_days": 2, "avg_cost": 4185.0, "pnl_pct": -9.92, "peak_price": 4185, "peak_pnl_pct": 0.0, "dd_from_peak_pct": -9.92},
  "6669": {"shares": 16000, "receivable_shares": 0, "close_price": 1430, "tradable_weight": 0.027521, "entry_date": "2026-11-24", "holding_days": 2, "avg_cost": 1510.0, "pnl_pct": -5.3, "peak_price": 1510, "peak_pnl_pct": 0.0, "dd_from_peak_pct": -5.3},
  "7828": {"shares": 19000, "receivable_shares": 0, "close_price": 1275, "tradable_weight": 0.029139, "entry_date": "2026-11-23", "holding_days": 3, "avg_cost": 1291.46, "pnl_pct": -1.27, "peak_price": 1415, "peak_pnl_pct": 9.57, "dd_from_peak_pct": -9.89},
  "8299": {"shares": 21000, "receivable_shares": 0, "close_price": 1485, "tradable_weight": 0.037511, "entry_date": "2026-11-24", "holding_days": 2, "avg_cost": 1595.0, "pnl_pct": -6.9, "peak_price": 1595, "peak_pnl_pct": 0.0, "dd_from_peak_pct": -6.9},
  "8415": {"shares": 465000, "receivable_shares": 0, "close_price": 40.65, "tradable_weight": 0.022737, "entry_date": "2026-11-20", "holding_days": 4, "avg_cost": 40.33, "pnl_pct": 0.8, "peak_price": 42.1, "peak_pnl_pct": 4.4, "dd_from_peak_pct": -3.44}
}

### compliance
violations: 1 | notices: 0
incidents (date,check_code,status,message):
2026-11-12,decision_consistency,fail,當日未於繳交窗口內完成申報
