# 2026 玉山人工智慧挑戰賽 · 投資決策與持股看板 (Portfolio Dashboard)

- **參賽隊伍**：`TEAM_11402`
- **設計風格**：富果 Fugle 專業看盤佈局 + Apple macOS 冷冽藍灰 / 冰川銀液態玻璃 (Liquid Glassmorphism)
- **核心功能（6 大分頁）**：
  - **頁籤 1【📊 帳戶總覽】**：可交易淨值 (NAV)、現金水位、累計與當日報酬率、**競賽排名 (總/社會組)**、**NAV/Cash、累計總報酬率、競賽排名與單日報酬率四組圖表**、持股損益明細（含**持有天數**、**FIFO 分批買進明細展開抽屜**與多欄位排序）。
  - **頁籤 2【📈 行情群組】**：動態劃分「我的持股」與「其餘標的」，具備漲跌幅排序、即時搜尋過濾、以及自 10-27 起的微型股價趨勢走勢圖 (Sparklines)。
  - **頁籤 3【🧾 歷史成交明細】**：彙整官方後台 JSON 累計買賣金額、手續費與證交稅摩擦成本、淨已實現損益，並支援依交易日、買賣方向與個股搜尋篩選成交明細。
  - **頁籤 4【📄 決策報告】**：歷史與最新 Markdown 決策報告瀏覽器，支援日期切換、自動章節目錄與一鍵複製原文。
  - **頁籤 5【🤖 AI 模型成本監控】**：19 項 LiteLLM Usage 指標、每日花費與 Token 消耗趨勢圖、L1~L4 階段費用佔比、全階段動態路由與備援架構及每日下鑽執行明細。
  - **頁籤 6【💡 專案亮點】**：ETF 投資策略、系統 L0 ➔ L4 架構概覽、6 大技術亮點與 GitHub Repository 導覽。
- **三段式主題（淺色預設）& 懸浮導航**：一鍵切換淺色（預設，冰川銀灰）／深色（冷冽藍灰）／跟隨系統主題（支援 Android Chrome 動態網址列 `theme-color`），支援下滑自動精簡為單行懸浮導航膠囊與通透度調節。
- **RWD 響應式排版**：手機、平板、電腦端完美適配。

---

## 一、 每日收盤後更新流程（超簡單 3 步驟）

每天收盤後（下午或晚上），只要做這三件事：

### 步驟 1：確認環境憑證（全自動同步後台與 DataPack）
1. 確認 `code/.env` 已設定 `ESUN_EMAIL` 與 `ESUN_PASSWORD`；執行 `run_update.py` 時會自動呼叫 `L0_sources/backend_history_loader.py` 與 `L0_sources/datapack_loader.py`，同步最新後台歷史數據至 **`data/backend_reports/backend_all_history.json`** 與最新 DataPack 至 **`data/Datapack/Raw/`**。
2. 若暫無最新 JSON，亦可另存後台「每日數據」`.htm` 至 `data/backend_reports/` 作為備援。
> 註：若當日 DataPack 有更新，也請一併將 `DataPack_*.json` 放入 `data/Datapack/Raw/`。

### 步驟 2：執行一鍵更新腳本
在終端機切換至 `code/portfolio_dashboard/` 並執行：
```bash
python run_update.py
```
*(其他常用參數：)*
```bash
python run_update.py --push             # 更新完自動執行 git commit 與 git push
python run_update.py --rebuild-candles  # 強制從玉山 historical.candles 重建 150 檔自 10/27 起完整歷史日線
python run_update.py --reports-only     # 僅用本地快取行情快速重繪網頁（不呼叫玉山 API）
```
- 腳本會自動讀取 `docs/API說明/esun api說明/config.ini` 登入玉山行情 SDK：
  - **2330 官方開市日曆比對**：先以 `2330` 日 K 同步真實開市日曆；若偵測到 `market_cache.json` 缺漏交易日或混入非交易日資料，會自動觸發 `historical.candles` 清洗重建。
  - **開發者方案高速抓取**：日常更新直接透過 `intraday.quote`（600 次/分鐘，無須分批冷卻）抓取 150 檔最新行情。
  - **日期防呆**：存檔日期一律以 API 回傳之交易日（`date`）為準（凌晨或假日執行不會誤存成當日系統日期）；若於台股盤中（`09:00 ~ 13:35`）執行會自動顯示盤中即時價提醒。

### 步驟 3：查看網頁
- **本機預覽**：直接雙擊打開 `code/portfolio_dashboard/dist/index.html` 即可在瀏覽器瀏覽！
- **線上查看**：若已綁定 Cloudflare Pages，推送後約 5~10 秒內專屬網址即會自動更新，手機與電腦隨時皆可查看。

---

## 二、 Cloudflare Pages 綁定 GitHub Private Repo 教學（完全免費）

只需設定一次（約 3 分鐘），以後每次 `git push` 就會自動發布！

1. 前往 [Cloudflare 官網](https://pages.cloudflare.com/) 免費註冊 / 登入帳號。
2. 進入左側選單 **Workers & Pages** ➔ 點擊 **Create application** ➔ 選擇 **Pages** 標籤 ➔ 點擊 **Connect to Git**。
3. 授權您的 GitHub 帳號，並在清單中選取隊伍的 **Private Repository**。
4. 填寫建置設定（Set up builds and deployments）：
   - **Project name**：自訂名稱（例如 `esun-team11402-portfolio`）
   - **Production branch**：選擇您的主要分支（如 `main` 或 `master`）
   - **Framework preset**：選擇 **`None`**
   - **Build command**：**留空**（不需要填任何指令，因為網頁是由本地 Python 產生）
   - **Build output directory**：填入 **`portfolio_dashboard/dist`**
5. 點擊 **Save and Deploy** 即可完成！
   - 您會獲得一個專屬網址（例如 `https://esun-team11402-portfolio.pages.dev`）。

### 🔒 隱私安全加分（可選）：
若擔心專屬網址被其他人猜到，可以在 Cloudflare 專案後台點擊 **Settings** ➔ **Access policy** ➔ 開啟 **Zero Trust** 免費信箱驗證（Email PIN），將存取權限限制只有您與組員的 Email 能登入查看，100% 確保參賽資訊隱私！

---

## 三、 專案檔案架構

```text
code/portfolio_dashboard/
├── tracker.py             # 成本與損益計算引擎 (優先解析 backend_all_history.json 與 Datapack/Raw/*.json)
├── market_api.py          # 玉山行情 API 模組 (config.ini 認證、intraday.quote 抓取、2330 日曆比對與自動重建)
├── builder.py             # 前端 HTML 產生器 (渲染 Fugle 版面與 Apple 毛玻璃特效)
├── run_update.py          # 每日一鍵執行調度腳本
├── market_cache.json      # 行情與日線趨勢本地快取
├── dist/
│   └── index.html         # 最終產出之單頁完整應用 (SPA)
└── README.md              # 本說明文件
```
