# 2026 玉山人工智慧挑戰賽 · 投資決策與持股看板 (Portfolio Dashboard)

- **參賽隊伍**：`TEAM_11402`
- **設計風格**：富果 Fugle 專業看盤佈局 + Apple iOS 液態毛玻璃 (Liquid Glassmorphism)
- **核心功能**：
  - **頁籤 1【📊 帳戶總覽與庫存損益】**：可交易淨值 (NAV)、現金水位、累計報酬率、持股損益明細 (支援即時多欄位排序)、自 10-27 以來的 NAV/Cash 歷史資產折線圖。
  - **頁籤 2【📈 自選行情觀察群組】**：動態劃分「我的持股 (25 檔)」與「其餘標的 (125 檔)」，具備漲跌幅排序、即時搜尋過濾、以及自 10-27 起的微型股價趨勢走勢圖 (Sparklines)。
  - **雙模式主題**：一鍵切換深色（深邃星空灰黑 + 晶瑩磨砂）與淺色（純淨象牙白 + 柔和光暈）。
  - **RWD 響應式排版**：手機、平板、電腦端完美適配。

---

## 一、 每日收盤後更新流程（超簡單 3 步驟）

每天收盤後（下午或晚上），只要做這三件事：

### 步驟 1：下載後台網頁並放入資料夾
1. 登入玉山比賽後台的「每日數據」頁面。
2. 在瀏覽器按 `Ctrl + S`（另存新檔），存成 `.htm` 或 `.html` 檔案（例如 `每日數據_20261103.htm`）。
3. 將該檔案丟入專案的 **`data/backend_reports/`** 資料夾中。
> 註：若當日 DataPack 有更新，也請一併將 `DataPack_*.json` 放入 `data/Datapack/Raw/`。

### 步驟 2：執行一鍵更新腳本
在終端機切換至 `code/portfolio_dashboard/` 並執行：
```bash
python run_update.py
```
*(若希望更新完自動執行 git commit 與 git push，可直接加上 `--push`：)*
```bash
python run_update.py --push
```
- 腳本會自動登入玉山行情 SDK、抓取 150 檔最新行情、計算持股加權成本與損益、並重新生成 `dist/index.html`。

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
├── tracker.py             # 成本與損益計算引擎 (解析 backend_reports/*.htm 與 Datapack/Raw/*.json)
├── market_api.py          # 玉山行情 API 模組 (取得 150 檔標的行情與 10-27 起趨勢)
├── builder.py             # 前端 HTML 產生器 (渲染 Fugle 版面與 Apple 毛玻璃特效)
├── run_update.py          # 每日一鍵執行調度腳本
├── market_cache.json      # 行情與日線趨勢本地快取
├── dist/
│   └── index.html         # 最終產出之單頁完整應用 (SPA)
└── README.md              # 本說明文件
```
