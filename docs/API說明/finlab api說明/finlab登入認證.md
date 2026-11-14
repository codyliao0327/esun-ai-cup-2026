Title: finlab - 量化交易工具文檔

URL Source: https://finlab.finance/docs/reference/finlab/

Markdown Content:
FinLab 核心模組，提供登入認證和憑證管理功能。

## 使用情境

*   首次使用 FinLab 時進行登入認證
*   在不同環境（本機、Colab、伺服器、排程）進行認證
*   查詢當前登入狀態

## 快速範例

### 本機電腦（推薦）

在終端機執行一次，之後同一台電腦的 Python 都會自動使用這份憑證：

```
python -m finlab login
```

或在 Python / Jupyter 中登入：

```
import finlab

# 啟動瀏覽器登入（會自動開啟瀏覽器）
finlab.login()

# 登入成功後，憑證會儲存在 ~/.finlab/credentials.json
# 之後使用不需要再次登入
```

### Google Colab

```
import finlab

finlab.login()  # 依畫面指示在瀏覽器完成登入
```

### 伺服器、Docker、排程（無瀏覽器環境）

先在**已登入的本機**匯出憑證：

```
python -m finlab token --env
# export FINLAB_REFRESH_TOKEN="..."
# export FINLAB_SESSION_ID="..."
# export FINLAB_API_KEY="..."
```

再把這三個值設成目標環境的環境變數（例如 docker-compose、GitHub Actions secrets、Cloud Functions 環境變數），程式中不需要呼叫 `finlab.login()`：

```
from finlab import data

close = data.get('price:收盤價')  # 自動讀取 FINLAB_REFRESH_TOKEN 等環境變數
```

`FINLAB_API_TOKEN` 已棄用

舊版 `FINLAB_API_TOKEN` 環境變數與 `finlab.login('YOUR_API_TOKEN')` 已棄用，使用時會出現 `DeprecationWarning`。請改用上述瀏覽器登入或 `python -m finlab token --env` 產生的三個環境變數。遷移指引可執行 `python -m finlab migrate`。

* * *

## 認證方式比較

| 方式 | 優點 | 缺點 | 適用場景 |
| --- | --- | --- | --- |
| **瀏覽器登入**（`python -m finlab login` / `finlab.login()`） | 安全、方便、自動更新 Token | 需要瀏覽器 | 本機開發、Jupyter、Colab |
| **環境變數憑證**（`python -m finlab token --env`） | 不需瀏覽器、不寫入程式碼 | 需先在本機登入一次 | 伺服器、Docker、排程、CI |
| **`FINLAB_API_TOKEN`**（已棄用） | — | 已棄用，未來將移除 | 請遷移 |

* * *

## 認證優先順序

FinLab 會按照以下順序尋找認證資訊：

1.   **`FINLAB_REFRESH_TOKEN` + `FINLAB_SESSION_ID` + `FINLAB_API_KEY` 環境變數**（三個都設定時才生效）
2.   **`~/.finlab/credentials.json`** - 瀏覽器登入產生的憑證
3.   **`FINLAB_ID_TOKEN` 環境變數** - 供瀏覽器 / Pyodide 執行環境使用
4.   **`FINLAB_API_TOKEN` 環境變數** - 舊版 API Token（已棄用，會出現警告）
5.   **互動式登入** - 以上都沒有時啟動瀏覽器登入

* * *

## 詳細教學

### 瀏覽器登入流程

```
import finlab

# 1. 呼叫 login() 不帶參數
finlab.login()

# 2. 瀏覽器會自動開啟 FinLab 登入頁面
# 3. 登入成功後，憑證會自動儲存
# 4. 之後使用不需要再次登入
```

**憑證儲存位置**：`~/.finlab/credentials.json`

**有效期限**：60 天（自動更新）

若瀏覽器登入失敗、被拒絕或逾時，`finlab.login()` 會拋出 `finlab.exceptions.LoginError`（`RuntimeError` 的子類別），不會再默默返回。

### 查詢登入狀態與登出

```
python -m finlab status   # 顯示登入狀態與方案
python -m finlab logout   # 清除本機憑證並移除伺服器端 session
```

* * *

## API Reference

### finlab.login()

## finlab.login

```
login(api_token=None)
```

登錄量化平台。

不傳入參數時啟動瀏覽器登入，成功後憑證存於 `~/.finlab/credentials.json`， 之後同一台機器會自動使用。Colab 同樣直接呼叫 `finlab.login()`。 無瀏覽器的環境（伺服器、排程）請在本機執行 `python -m finlab token --env`， 並設定 `FINLAB_REFRESH_TOKEN`、`FINLAB_SESSION_ID`、`FINLAB_API_KEY`。

| PARAMETER | DESCRIPTION |
| --- | --- |
| `api_token` | 已棄用的舊版 api_token，請改用瀏覽器登入。 **TYPE:**`str`**DEFAULT:**`None` |

| RAISES | DESCRIPTION |
| --- | --- |
| `LoginError` | 瀏覽器登入失敗、被拒絕或逾時。 |

推薦使用方式

*   **本機開發 / Jupyter / Colab**：`python -m finlab login` 或 `finlab.login()` 瀏覽器登入
*   **伺服器 / 排程 / CI**：在本機執行 `python -m finlab token --env`，把 `FINLAB_REFRESH_TOKEN`、`FINLAB_SESSION_ID`、`FINLAB_API_KEY` 設為環境變數

憑證安全

*   不要將憑證環境變數或 `~/.finlab/credentials.json` 上傳到 GitHub 等公開平台
*   使用平台的 secrets 功能或 `.env` 檔案管理憑證

### finlab.get_token()

## finlab.get_token

```
get_token()
```

取得登錄會員的認證 token。

認證優先順序： 1. ~/.finlab/credentials.json (新版 Firebase auth) → 返回 id_token 2. FINLAB_ID_TOKEN 環境變數 (新版 Firebase auth) → 返回 id_token 3. FINLAB_API_TOKEN 環境變數 (舊版) → 返回 api_token 4. 互動式登入

| RETURNS | DESCRIPTION |
| --- | --- |
| `tuple` | (token_string, token_type) where token_type is 'id_token' or 'api_token' **TYPE:**`tuple[str, str]` |

* * *

## 常見問題

### Q: 如何檢查是否已登入？

```
python -m finlab status
```

或在 Python 中：

```
import finlab

try:
    token, token_type = finlab.get_token()
    print(f"✅ 已登入（{token_type}）")
except RuntimeError:
    print("❌ 未登入")
```

### Q: 瀏覽器登入失敗怎麼辦？

`finlab.login()` 失敗時會拋出 `LoginError` 並附上處理方式。常見原因：

1.   **缺少 cryptography 套件**

```
pip install cryptography
``` 
2.   **無瀏覽器環境（如伺服器）**

3.   在本機執行 `python -m finlab login`，再執行 `python -m finlab token --env`
4.   把輸出的 `FINLAB_REFRESH_TOKEN`、`FINLAB_SESSION_ID`、`FINLAB_API_KEY` 設為伺服器環境變數

5.   **登入逾時或防火牆阻擋**

6.   重新執行 `finlab.login()`，並在時限內完成瀏覽器登入
7.   檢查網路設定

### Q: 還在使用 `FINLAB_API_TOKEN` 怎麼辦？

執行 `python -m finlab migrate` 查看遷移步驟：本機改用 `python -m finlab login`，無瀏覽器環境改用 `python -m finlab token --env` 產生的三個環境變數，然後移除 `FINLAB_API_TOKEN`。

### Q: 如何登出？

```
python -m finlab logout
```

若曾設定環境變數憑證，也請一併移除 `FINLAB_REFRESH_TOKEN`、`FINLAB_SESSION_ID`、`FINLAB_API_KEY`（以及舊版 `FINLAB_API_TOKEN`）。

* * *

## 參考資源

*   [命令列工具](https://finlab.finance/docs/cli/) - `login`、`token`、`status`、`logout`、`migrate` 指令說明
*   [快速上手指南](https://finlab.finance/docs/getting-started/) - 完整安裝與登入教學
*   [常見問題 FAQ](https://finlab.finance/docs/faq/) - 更多登入相關問題
