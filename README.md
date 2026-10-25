# 2026 玉山人工智慧挑戰賽

ETF 投資策略相關程式碼。

## 環境
- Python 3.11(Jupyter kernel: `esunaicup2026_py311`)
- 套件:`finlab`, `python-docx`, `requests`, `pandas`, `pyarrow`

```bash
pip install -r requirements.txt
```

## FinLab 登入
使用瀏覽器互動式登入,憑證存於本機 `~/.finlab/credentials.json`:

```bash
python -m finlab login
```

## FinLab 市場資料下載(`L0_sources/finlab_market_loader.py`)
依 `data/Data Directory Structure.md` 清單下載 31 筆資料(M1~M3、F1、F2、F1F2、F4),各自存入對應資料夾,資料起始日 `2025-04-24`。

- 檔案格式:Parquet(zstd 壓縮),檔名 `<檔案名稱>_YYYYMMDD.parquet`(日期為下載當日)
- 內容為「日期 × 股票」寬表,日期存在 `date` 欄位;`company_basic_info` 僅含「產業類別」

```bash
python L0_sources/finlab_market_loader.py                      # 下載全部(當日已存在則略過)
python L0_sources/finlab_market_loader.py --only price_收盤價 M1  # 依名稱/資料夾關鍵字篩選
python L0_sources/finlab_market_loader.py --overwrite          # 強制重新下載
```

其他程式讀取(預設讀最新日期的檔案,`date` 會還原為索引):

```python
from finlab_market_loader import load_dataset
close = load_dataset("price_收盤價")
```

> 注意:FinLab 每次 `data.get` 都會整包下載資料集(見下方實測結論),請勿頻繁重跑;額度用完(`QuotaExceededError`)時程式會中止,台灣時間 08:00 重置。

## 內容
- `L0_sources/finlab_market_loader.py`: FinLab 市場資料下載與讀取(見上節)
- `convert_slack.ipynb`: Slack 官方問答區跨天訊息池化與線程縫合轉換工具（解析 `slackdump/官方問答區/json`，依討論串 ID 全域去重與縫合官方回覆，輸出供 NotebookLM 與 LLM 檢索的單一 Markdown 彙整文件）
- `finlab_api_test.ipynb`: FinLab API 連線與資料測試
- `finlab_download_limit_test.ipynb`: FinLab API 下載限制機制實測（**備查紀錄**，實測證明無論限制時間或個股，API 皆會全量下載完整資料後才在地端切片）
- `finlab_incremental_update.ipynb`: 增量更新測試（**備查紀錄**，因 API 無法在伺服器端限制下載範圍，此增量方式已不適用）
- `strategy.ipynb`: ETF 投資策略說明文件生成（利用 LLM 如 Ollama / Gemini 生成符合競賽規範的 ETF 名稱、投資主題與投資理念，支援自動格式驗證、重試機制與 Word/JSON 紀錄匯出）
- `verify_dplan.ipynb`: D-Plan schema 驗證
- `esun_trial_match.ipynb`: 玉山證券行情 Web API 盤前試撮資料快照擷取（支援單股試撮報價、五檔委託簿、逐筆試撮明細與多檔標的/全市場試撮快照）

## 重要實測結論與注意事項
- **FinLab API 無伺服器端篩選 (Server-side Filter)**：
  - 經 `finlab_download_limit_test.ipynb` 攔截 HTTP 封包實測，無論設定 `start` 日期、`truncate_start` 或 `universe(whitelist)` 限制個股，API 伺服器皆是**將完整資料集（全歷史日數、全市場 2,700+ 檔標的，單檔約 17+ MB）整包下載至本地**，才由 FinLab 本地端 SDK 進行切片遮罩。
  - **結論**：限制條件**完全無法節省每日 API 下載流量配額**。因此 `finlab_incremental_update.ipynb` 與 `finlab_download_limit_test.ipynb` 僅保留作為機制驗證紀錄，後續日常運作不再使用。
  - **使用建議**：資料下載一次後請善用本機快取或直接存檔於本地，避免使用 `force_download=True` 造成流量重複浪費。
- `data/` 與 CSV/Parquet 檔不會被上傳 (見 `.gitignore`)，FinLab 資料請在本機自行下載。
- 請勿提交任何 token 或憑證。
