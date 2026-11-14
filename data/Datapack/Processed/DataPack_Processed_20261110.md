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

## 資料
schema_version: "3.0" | doc_type: "DataPack" | team_id: "TEAM_11402"
trade_date: "2026-11-10" | as_of_date: "2026-11-09" | generated_at: "2026-11-09T22:29:30.068386+08:00"
missing: []
狀態判讀: account 與 holdings 為 2026-11-09 收盤結算後的狀態。

### prev_day_orders
outcome: "executed" | void_reasons: [] | excluded_codes: []

### account
cash: 109957096.43 | cash_ratio_tradable: 0.120349 | nav_tradable: 913650396.4300001 | aum: 913650396.43 | receivable_cash: 0 | holdings_count: 30

### holdings
code,shares,receivable_shares,close_price,tradable_weight
1216,489000,0,76.7,0.041051
1303,107000,0,263,0.030801
2207,37000,0,533,0.021585
2317,149000,0,239,0.038977
2330,23000,0,2235,0.056263
2368,17000,0,894,0.016634
2376,87000,0,309.5,0.029471
2379,35000,0,743,0.028463
2382,36000,0,296.5,0.011683
2383,3000,0,4070,0.013364
2404,16000,0,930,0.016286
2412,300000,0,159,0.052208
2603,160000,0,245.5,0.042992
2880,456000,0,49.6,0.024755
2881,181000,0,153.5,0.030409
2882,253000,0,111,0.030737
2886,752000,0,52.8,0.043458
2891,542000,0,75.9,0.045026
3034,71000,0,486.5,0.037806
3037,14000,0,757,0.0116
3045,336000,0,131,0.048176
3189,10000,0,690,0.007552
3231,171000,0,168.5,0.031537
3443,2000,0,6705,0.014677
3533,16000,0,1705,0.029858
4904,279000,0,106,0.032369
4938,408000,0,95.4,0.042602
4958,24000,0,398,0.010455
5880,641000,0,27.8,0.019504
6505,200000,0,88.4,0.019351

### compliance
violations: 0 | notices: 0
incidents: []
