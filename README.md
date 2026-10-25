# 2026 玉山人工智慧挑戰賽 (AI CUP 2026)

本專案為 **2026 Agent 基金經理人競賽** 之量化投資與 Multi-Agent 決策系統程式碼庫。

系統依據官方 **D-Plan Schema v4.3** 規範設計，實作分層 Multi-Agent 架構（L0 資料擷取 ➔ L1 客觀事實 ➔ L2M 市場觀點 ➔ L2 個股推論 ➔ L3 組合決策 ➔ L4 委託試算 ➔ 本地合規檢驗），支援每日自動化接收 DataPack、結合台股量化指標與社群情緒數據，產生合規且具可解釋性之投資決策。

---

## 專案架構與目錄說明

```text
code/
├── configs/                              # 專案配置與外部 API 封裝
│   ├── settings.py                       # 隊伍 ID、credentials 憑證讀取、全域路徑設定
│   └── gemini_client.py                  # Google GenAI Interactions API 客戶端 (支援 Structured Outputs)
│
├── schemas/                              # 【Schema 定義與檢驗層】
│   ├── dplan_models.py                   # 依 D-Plan Schema v4.3 建立的 Pydantic 模型
│   └── verify_dplan.ipynb                # D-Plan JSON 格式校驗與測試 Notebook
│
├── L0_sources/                           # 【L0 資料來源層】
│   ├── datapack_loader.py                # 讀取官方每日 DataPack JSON (取現金、庫存、NAV 等)
│   ├── finlab_market_loader.py           # 透過 FinLab API 下載 31 檔市場/財務資料並快取為 Parquet
│   ├── cmoney_stance_crawler.py          # 爬取 CMoney 個股 AI 觀點與社群多空情緒
│   └── esun_trial_loader.ipynb           # 玉山證券行情 Web API 盤前試撮資料快照擷取
│
├── L1_observations/                      # 【L1 資訊擷取層】
│   └── fact_extractor.py                 # 提取客觀事實陳述，產出數值字典 values (僅客觀數據)
│
├── L2M_market_view/                      # 【L2M 市場研判核心】
│   └── market_view_agent.py              # 產出市場狀態 (regime)、多空態度 (stance)、目標水位 (posture)
│
├── L2_inferences/                        # 【L2 個股推論核心】
│   └── stock_inference_agent.py          # 結合 ETF 理念針對候選池產出個股推論 (I1, I2...)
│
├── L3_decisions/                         # 【L3 決策核心】
│   └── portfolio_decision_agent.py       # 昨日持股全覆蓋分配 (decisions 異動 + no_trade 續抱)
│
├── L4_orders/                            # 【L4 委託執行層】
│   └── order_calculator.py               # 嚴格依官方公式計算目標股數 (千股整股，嚴禁手調)
│
├── validator/                            # 【本地合規檢查儀 (Guardrails)】
│   └── compliance_checker.py             # 引用鏈完整性、持股 20~30 檔、現金 0~25%、淨額容差檢驗
│
├── etf_strategy/                         # 【ETF 策略說明與建置】
│   ├── strategy.ipynb                    # ETF 策略說明文件生成工具 (含格式校驗與 Word/JSON 匯出)
│   └── etf_profile.py                    # 已繳交之 ETF 策略主題、核心理念與核心因子常數
│
├── convert_slack_qa/                     # 【官方問答整理工具】
│   └── convert_slack.ipynb               # Slack 官方問答區訊息池化與討論串縫合轉換工具
│
├── active_etf_constituents/              # 【市場主動型 ETF 分析】
│   └── top_15_constituents.ipynb         # 盤點市場主動型 ETF 前 15 大成分股比重與產業分佈
│
├── archive/                              # 【技術驗證與備查紀錄】
│   ├── finlab_api_test.ipynb             # FinLab 連線與基本 API 測試
│   ├── finlab_download_limit_test.ipynb  # FinLab 下載限制機制實測 (確認無伺服器端過濾)
│   ├── finlab_download_limit_test_report.csv # 下載實測報告數據
│   ├── finlab_incremental_update.ipynb   # 增量更新機制測試紀錄
│   ├── CMoney_test.ipynb                 # CMoney API 早期連線測試
│   └── cmoney_ru.ipynb                   # CMoney 討論區與情感分析實驗
│
├── run_daily_dplan.py                    # 每日自動化排程執行的主程式入口 (含自動重試機制)
├── credentials.json                      # [本地] 本地憑證與 API 金鑰 (已被 gitignore 忽略)
├── requirements.txt                      # 專案 Python 相依套件清單
└── README.md                             # 專案說明文件 (本檔案)
```

---

## 環境建置

- **Python 版本**：Python 3.11 (推薦 Jupyter Kernel 名稱: `esunaicup2026_py311`)
- **相依套件安裝**：

```bash
pip install -r requirements.txt
```

### 核心相依套件列表 (`requirements.txt`)
- `google-genai`：Google 官方 GenAI SDK (Interactions API / Structured Outputs)
- `pydantic>=2.0`：資料模型與 D-Plan Schema 結構化輸出驗證
- `finlab`：市場、財務與量化資料介面
- `requests`、`python-docx`：HTTP 請求與 Word 文件輸出
- `pandas`、`numpy`、`pyarrow`：高效能矩陣與 Parquet 本機資料快取

---

## 憑證與認證設定

為維護金鑰安全，所有敏感憑證均**嚴禁**上傳至版本控制庫（已於 `.gitignore` 排除）。

### 1. 專案憑證檔 (`code/credentials.json`)
在 `code/` 目錄下建立 `credentials.json`，配置隊伍 ID 與 Gemini API Key：

```json
{
  "team_id": "TEAM_11402",
  "gemini_api_key": "YOUR_GEMINI_API_KEY_HERE"
}
```

- 模組 `configs/settings.py` 會自動讀取此檔案中的 `team_id` 與 `gemini_api_key`。
- 若未在 `credentials.json` 配置，系統亦支援從環境變數 `GEMINI_API_KEY` 或 `GOOGLE_API_KEY` 作為備援 fallback。

### 2. FinLab 登入
使用瀏覽器互動式登入，憑證會自動儲存於使用者家目錄 (`~/.finlab/credentials.json`)：

```bash
python -m finlab login
```

---

## FinLab 市場資料下載 (`L0_sources/finlab_market_loader.py`)

依 `data/Data Directory Structure.md` 清單下載 31 筆資料 (M1~M3、F1、F2、F1F2、F4)，存入對應本機資料夾，資料起始日為 `2025-04-24`。

- **檔案格式**：Parquet (zstd 壓縮)，檔名格式 `<檔案名稱>_YYYYMMDD.parquet`（日期為下載當日）。
- **寬表結構**：內容為「日期 × 股票」寬表，日期存在 `date` 欄位；`company_basic_info` 僅含「產業類別」。

### 執行下載指令
```bash
python L0_sources/finlab_market_loader.py                      # 下載全部(當日已存在則略過)
python L0_sources/finlab_market_loader.py --only price_收盤價 M1  # 依名稱/資料夾關鍵字篩選
python L0_sources/finlab_market_loader.py --overwrite          # 強制重新下載
```

### 程式內讀取快取
預設讀取本地最新日期的 Parquet 檔案，並將 `date` 還原為索引：

```python
from L0_sources.finlab_market_loader import load_dataset

close = load_dataset("price_收盤價")
```

---

## Google GenAI Client 使用說明 (`configs/gemini_client.py`)

採用 Google 官方 `google-genai` SDK 與 Interactions API 規範封裝：

```python
from configs.gemini_client import GeminiClient
from schemas.dplan_models import DPlanModel  # 範例 Pydantic Model

client = GeminiClient()

# 1. 純文字生成
response = client.generate_text("請簡述台股高股息 ETF 趨勢")

# 2. 結構化輸出 (Structured Outputs / JSON Schema)
structured_plan = client.generate_structured(
    prompt="請產出今日之 D-Plan 決策 JSON...",
    response_model=DPlanModel,
)
```

---

## 重要實測結論與注意事項

1. **FinLab API 無伺服器端過濾機制 (Server-side Filter)**：
   - 經 `archive/finlab_download_limit_test.ipynb` 攔截 HTTP 封包實測，無論設定 `start`、`truncate_start` 或 `universe(whitelist)` 限制個股，API 伺服器端皆是**將完整資料集（全歷史日數、全市場 2,700+ 檔標的，單檔約 17+ MB）全量傳輸至地端**，再由 SDK 進行地端切片遮罩。
   - **結論**：限制條件無法節省每日 API 下載流量配額。下載完成後請善用本地 Parquet 快取，避免頻繁使用 `force_download=True`。每日額度耗盡時將拋出 `QuotaExceededError`，於台灣時間 08:00 重置。
2. **本地快取與資料隔離**：
   - `data/` 與所有 Parquet/CSV/Pickle 資料檔案皆已被 `.gitignore` 排除，請勿上傳。
3. **金鑰與憑證保護**：
   - 請勿在程式碼中寫入任何 API Key、密碼或 token，請統一透過 `credentials.json` 進行配置。
