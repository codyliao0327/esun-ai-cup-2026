# D-Plan — 當日 Agent 決策報告及交易書規格說明書 (v4.3)

- **文件定位**：每台股交易日繳交之 JSON 文件（每日唯一繳交物），包含決策過程和當日委託內容。
- **Schema ID**：`https://esun-ai-challenge.tw/schemas/D-Plan.schema.json`
- **限制原則**：`additionalProperties: false`（嚴格禁止未定義之自訂欄位，出現即退回）。

---

## 📌 頂層欄位與架構 (Root Properties)

本份 JSON 最外層必須為 `object`，所有必填欄位均不可缺漏：

| 欄位名稱 | 型別 / 格式 | 必填 | 說明與檢核限制 |
| :--- | :--- | :---: | :--- |
| `schema_version` | String | **是** | 規格版本，正規表達式：`^4\.\d+$`（例如 `4.3`） |
| `doc_type` | String | **是** | 固定常數：`"D-Plan"` |
| `team_id` | String | **是** | 隊伍 ID，長度 1~32 字元，限制：`^[A-Za-z0-9_-]{1,32}$` |
| `trade_date` | String (Date) | **是** | 本計劃書所對應之交易日（非繳交日），格式 `YYYY-MM-DD` |
| `sources` | Array [Source] | **是** | **L0 資料來源層**。1 ~ 50 筆 |
| `observations` | Array [Obs] | **是** | **L1 資訊擷取層**。1 ~ 100 筆。**只准可核對的事實，禁止推論性語句** |
| `market_view` | Object | **是** | **L2M 整體市場判斷鏈**。市場級依據 → 走向研判 → 風險姿態 → 可驗證部位含意 |
| `inferences` | Array [Inf] | **是** | **L2 個股推論層**。1 ~ 60 筆。事實 + 策略規則 → 結論 |
| `decisions` | Array [Dec] | **是** | **L3 決策層（異動）**。0 ~ 60 筆。無交易日可為空陣列 |
| `no_trade_decisions`| Array [NoDec] | **是** | **L3 決策層（續抱）**。0 ~ 30 筆。每檔未異動持股各一筆，附引用理由 |
| `orders` | Array [Order] | **是** | **L4 委託層**。0 ~ 60 筆。須與推導演算法結果一致（ticker/side/shares） |
| `agent_metadata` | Object | **是** | Agent 執行紀錄、模型資訊與程式碼版本 |
| `_NOTE` | String | 否 | 非正式欄位：範例檔備註用，正式提交可省略 |

---

## 🏗️ 核心層級結構詳細規格

### L0：資料來源層 (`sources`)
> 列出本份計劃書實際引用的所有外部資料來源（1 ~ 50 筆）。

- **`source_id`** *(必填, String)*: 層內唯一 ID，格式：`^S[0-9]{1,3}$`（例如 `S1`, `S02`）。
- **`authority`** *(必填, Enum)*: 來源機關與類別：
  - `twse` / `tpex` / `taifex` / `mops`：交易所與主管機關公開資料。
  - `fininst`：投信/券商/銀行等金融機構發布之研究報告、基金與 ETF 資料。
  - `media`：新聞媒體。
  - `vendor`：行情/數據服務商（CMoney、富果 Fugle 等之 API 或數據）。
  - `other`：未涵蓋者。
- **`url`** *(必填, URI)*: 資料來源網址。
- **`content_as_of`** *(必填, Timestamp)*: 資料內容所描述之時點（非抓取時間，ISO-8601，時區限 `+08:00`）。
- **`name`** *(選填, String)*: 人讀名稱（上限 300 字元）。
- **`archive_url`** *(選填, URI)*: 第三方存檔連結（web.archive.org / archive.today）。media/vendor 建議填入。
- **`published_at`** *(選填, Timestamp)*: 新聞/公告發布時間（時區限 `+08:00`）。
- **`fetched_at`** *(選填, Timestamp)*: 抓取時刻，供異常排查；有填時須 $\le$ 伺服器收件戳。

---

### L1：資訊擷取層 (`observations`)
> 只准可核對的事實，禁止推論性語句（1 ~ 100 筆）。

- **`obs_id`** *(必填, String)*: ID，格式：`^O[0-9]{1,3}$`（例如 `O1`, `O2`）。
- **`source_ref`** *(必填, Array[String])*: 引用之來源 ID 清單（1 ~ 10 筆）。**每個 ID 必須存在於 `sources`，未通過整份退回**。
- **`statement`** *(必填, String)*: 客觀事實陳述（長度 5 ~ 500 字元）。
- **`values`** *(必填, Object)*: 數值事實清單（抽檢時逐值回對證據包快照，**Value 僅收數字**，至少 1 個屬性）。
- **`topic`** *(選填, String)*: 分類標籤，格式：`^[a-z][a-z0-9_]{1,40}$`。

---

### L2M：整體市場判斷鏈 (`market_view`)
> 整體市場判斷依據與資產配置姿態宣告。系統將檢查宣告與委託總效果之一致性。

- **`basis_refs`** *(必填, Array[String])*: 市場級依據 ID（1 ~ 10 筆，大盤、期貨夜盤、隔夜美股、匯率等）。**每個 ID 必須存在於 `observations`，未通過整份退回**。
- **`logic`** *(必填, String)*: 從依據推導到走向與姿態之邏輯過程（長度 20 ~ 1000 字元）。
- **`regime`** *(必填, Enum)*: 整體市場走向研判：
  - `risk_on` / `neutral` / `risk_off`
- **`stance`** *(必填, Enum)*: 本日操作姿態：
  - `aggressive`（積極）/ `neutral`（中性）/ `defensive`（保守）
- **`posture`** *(必填, Object)*: 可驗證的部位意圖：
  - **`net_exposure_intent`** *(必填, Enum)*: 淨曝險意圖（以 T-1 收盤價重算委託淨流向比對）：
    - `increase`：淨買超
    - `reduce`：淨賣超
    - `hold`：$|\text{淨流向}| \le \text{容差}$（伺服器參數，預設 2% NAV）
  - **`target_cash_pct_range`** *(必填, Array[Number])*: 目標現金比率區間 `[下限, 上限]`，長度為 2，數值範圍 0 ~ 0.25（0% ~ 25%），且下限 $\le$ 上限。
- **`counter_evidence`** *(必填, String 或 null)*: 與研判相反的市場反向訊號（上限 500 字元；若無反向訊號須明確填 `null`）。
- **`confidence`** *(選填, Number)*: 信心度（0.0 ~ 1.0）。

---

### L2：個股推論層 (`inferences`)
> 個股事實 + 策略規則 $\rightarrow$ 結論（1 ~ 60 筆）。

- **`inf_id`** *(必填, String)*: ID，格式：`^I[0-9]{1,3}$`（例如 `I1`, `I2`）。
- **`premise_refs`** *(必填, Array[String])*: 依據之事實 ID（1 ~ 10 筆）。**每個 ID 必須存在於 `observations`，未通過整份退回**。
- **`logic`** *(必填, String)*: 推導過程（哪些前提、為何成立，長度 20 ~ 1000 字元）。
- **`conclusion`** *(選填, String)*: 人讀摘要結論（上限 300 字元）。
- **`counter_evidence`** *(必填, String 或 null)*: 與本推論相反的訊號（上限 500 字元；若無須填 `null`）。
- **`confidence`** *(選填, Number)*: 信心度（0.0 ~ 1.0）。

---

### L3：決策層（異動）(`decisions`)
> 當日預計執行的部位買賣調度決策（0 ~ 60 筆）。

- **`decision_id`** *(必填, String)*: ID，格式：`^D[0-9]{1,3}$`（例如 `D1`, `D2`）。
- **`ticker`** *(必填, String)*: 台股四位代碼，格式：`^[0-9]{4}$`。
- **`action`** *(必填, Enum)*: 決策動作：
  - `BUY`：新建倉（前一交易日持股為 0）
  - `ADD`：加碼既有持股
  - `TRIM`：減碼但保留部位
  - `SELL_ALL`：全數出清部位
- **`target_weight`** *(必填, Number)*: 委託執行後之目標權重，範圍 0 ~ 0.25（0% ~ 25%），分母為前日結算淨值（`account.nav_tradable`）。
- **`inference_refs`** *(必填, Array[String])*: 引用之推論 ID（1 ~ 8 筆）。**必須存在於 `inferences`，每筆決策不得為孤兒決策**。
- **`risk_check`** *(選填, String)*: 風險核核人讀自述（上限 300 字元）。
- **`funding_for`** *(選填, Array[String])*: 資金調度宣告（1 ~ 5 筆 `D[0-9]{1,3}`）。限 `TRIM` / `SELL_ALL` 填寫，指明是為了支應哪筆買進決策；系統將驗證現金缺口是否真實存在。

---

### L3：決策層（續抱）(`no_trade_decisions`)
> 既有持股中當日不異動者，每檔持股各列一筆（0 ~ 30 筆）。未通過即整份退回。

- **`ticker`** *(必填, String)*: 台股四位代碼，格式：`^[0-9]{4}$`。
- **`reason_refs`** *(必填, Array[String])*: 續抱理由引用之推論 ID（1 ~ 5 筆，指向 `I[0-9]{1,3}`）。
- **`reason`** *(選填, String)*: 人讀續抱理由（上限 300 字元）。

---

### L4：委託層 (`orders`)
> 實際發送給交易所執行的委託單（0 ~ 60 筆）。

- **`ticker`** *(必填, String)*: 台股四位代碼，格式：`^[0-9]{4}$`。
- **`side`** *(必填, Enum)*: 買賣方向：`BUY` 或 `SELL`。
- **`shares`** *(必填, Integer)*: 委託股數。**整股限制：須為 1000 之正整數倍（$\ge 1000$ 且 multipleOf 1000）**。
- **`decision_ref`** *(必填, String)*: 指向之決策 ID（格式 `^D[0-9]{1,3}$`）。**須存在於 `decisions` 且推導結果完全一致**。
- **`derivation_detail`** *(選填, String)*: 人讀推導展開式（上限 300 字元）。

---

### Agent 執行環境與元資料 (`agent_metadata`)

- **`model_provider`** *(必填, Enum)*:
  - 可選項目：`anthropic`, `openai`, `google`, `xai`, `deepseek`, `alibaba`, `meta`, `mistral`, `cohere`, `amazon`, `microsoft`, `nvidia`, `taide`, `other`。
  - *自架開源模型請填釋出權重之組織（如 Llama 填 `meta`，Qwen 填 `alibaba`），清單未涵蓋填 `other` 並於版本說明。*
- **`model_version`** *(必填, String)*: 模型確切版本名稱（3 ~ 60 字元，抽檢重跑需同一版本）。
- **`run_started_at`** *(必填, Timestamp)*: 執行起始時間（ISO-8601，時區限 `+08:00`）。
- **`run_completed_at`** *(必填, Timestamp)*: 執行完成時間（$\le$ 伺服器收件時間戳記）。
- **`code_version`** *(必填, String)*: 程式碼版本識別，長度 1 ~ 64 字元，正規表達式：`^[A-Za-z0-9_.:/\-]{1,64}$`（例如 `git:a1b2c3d`、`v1.4.2` 或 sha256 前綴）。
- **`input_tokens`** *(選填, Integer)*: 輸入 Token 消耗量（$\ge 0$）。
- **`output_tokens`** *(選填, Integer)*: 輸出 Token 消耗量（$\ge 0$）。
- **`tool_use_count`** *(選填, Integer)*: 工具呼叫次數（$\ge 0$）。

---

## ⚙️ 通用型別與格式標準 ($defs)

1. **日期格式 (`date`)**：`YYYY-MM-DD`（正規表達式：`^[0-9]{4}-[0-9]{2}-[0-9]{2}$`）。
2. **時間戳記 (`timestamp`)**：ISO-8601 且**一律為台北時區 `+08:00`**。
   - 正規表達式：`^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?\+08:00$`
3. **股票代號 (`ticker`)**：四位台股數字代碼，正規表達式：`^[0-9]{4}$`。
4. **雜湊值 (`sha256_prefixed`)**：`^sha256:[0-9a-f]{64}$`。