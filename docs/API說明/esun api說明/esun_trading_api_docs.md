# 玉山證券交易 API（Trading API）完整技術說明文件

> **官方文件來源**：[玉山證券 API 交易服務 - 交易 API 說明文件](https://www.esunsec.com.tw/trading-platforms/api-trading/docs/trading/intro/)

## 一、簡介與主要功能

### 1. 服務概述
玉山交易 API 提供模擬交易環境，讓開發者及投資人能在無風險環境下測試交易策略，確保穩定性與準確性。同時支援 Python、JavaScript（Node.js），兼容 Windows、macOS、Linux 等不同作業系統開發，可跨平台存取交易、行情、帳務管理等核心功能。

* **平台特色**：
  1. **支援跨平台**：Windows、macOS、Linux。
  2. **支援跨語言**：Python（3.7 ～ 3.13）、JavaScript（Node.js 16+）。
  3. **模擬交易環境**：提供無風險的模擬下單與測試環境。

### 2. 主要功能
1. **交易功能**：建立委託單、修改或取消委託單、查詢委託單狀態，以及取得歷史委託紀錄與成交明細等。
2. **帳務管理**：取得帳戶內的庫存損益、已實現損益、未實現損益、交割款與銀行餘額等資訊。
3. **主動回報與即時行情**：透過 WebSocket 接收即時委託與成交回報，並可搭配行情 API 取得股票、權證、期權等即時報價。

## 二、快速開始（Quick Start）

> **官方章節**：[快速開始](https://www.esunsec.com.tw/trading-platforms/api-trading/docs/trading/quick_start)

### 1. 確認環境與檔案結構
開始開發前，請先於官網完成「事前準備」（申請憑證、簽署同意書、下載正式／模擬環境設定檔 `.ini` 與憑證 `.p12`）。資料夾結構應如下：

```text
.
├── config.ini
└── XXXXXXXXXX_XXXXXXXX.p12
```

設定檔（`config.ini` / `config.simulation.ini`）格式範例：

```ini
[Core]
Entry = https://esuntradingapi-simulation.esunsec.com.tw/api/v1
Environment = SIMULATION

[Cert]
Path = ;Your Cert File Path Ex: ./python/cert.p12

[Api]
Key = XXXXXXXXXXXXXXXX
Secret = XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

[User]
Account = 884XXXXXXXX
```

### 2. 安裝 SDK 套件

* **Python**（支援 Python 3.7、3.8、3.9、3.10、3.11、3.12、3.13）：
  ```bash
  pip install esun_trade-<version>-<platform>.whl
  ```

* **Node.js**（支援 Node.js 16 以上版本）：
  ```bash
  npm init
  ```
  於 `package.json` 的 `dependencies` 加入本地安裝檔路徑：
  ```json
  {
    "dependencies": {
      "esun-trade": "file://<path-to-js-binary>/esun-trade-<version>.tgz"
    }
  }
  ```
  執行安裝：
  ```bash
  npm install
  ```

### 3. 登入驗證
初次登入或更換執行環境時，SDK 會於命令列提示輸入**玉山證券登入密碼**與**憑證密碼**（因資安要求，SDK 不支援於設定檔中使用明文設定密碼）。

* **Python（`index.py`）**：
  ```python
  from configparser import ConfigParser
  from esun_trade.sdk import SDK

  config = ConfigParser()
  config.read('/path/to/config.ini')

  sdk = SDK(config)
  sdk.login()
  ```
  執行後依提示輸入密碼：
  ```bash
  $ python index.py
  Enter esun account password: # 請輸入您玉山證券的登入密碼
  Enter cert password: # 請輸入您的憑證密碼
  ```

* **Node.js（`index.js`）**：
  ```javascript
  import { EsunTrade, Order } from "@esun/trade";

  const esun = new EsunTrade({
    configPath: "/path/to/config.ini",
  });

  await esun.login();
  ```
  執行後依提示輸入密碼：
  ```bash
  $ node index.js
  Enter esun account password # 請輸入您玉山證券的登入密碼
  Enter cert password # 請輸入您的憑證密碼
  ```

### 4. 送出第一筆委託
> **注意事項**：
> * 在執行任何 API 呼叫之前，必須先完成一次 `login()` 登入。
> * 取得正式環境的使用權限前，必須先在模擬環境至少成功送出一筆委託。

以下範例示範以跌停價買入玉山金（`2884`）：

* **Python**：
  ```python
  from configparser import ConfigParser
  from esun_trade.sdk import SDK
  from esun_trade.order import OrderObject
  from esun_trade.constant import (APCode, Trade, PriceFlag, BSFlag, Action)

  config = ConfigParser()
  config.read('/path/to/config.ini')

  sdk = SDK(config)
  sdk.login()

  order = OrderObject(
      buy_sell=Action.Buy,
      price_flag=PriceFlag.LimitDown,
      price=None,
      stock_no="2884",
      quantity=2,
      ap_code=APCode.Common
  )

  sdk.place_order(order)
  ```

* **Node.js**：
  ```javascript
  import { EsunTrade, Order } from '@esun/trade';

  const esun = new EsunTrade({ configPath: './config.simulation.ini' });
  await esun.login();

  const order = new Order({
    buySell: Order.Side.Buy,
    price: '',
    stockNo: '2884',
    quantity: 1,
    apCode: Order.ApCode.Common,
    priceFlag: Order.PriceFlag.LimitDown,
    bsFlag: Order.BsFlag.ROD,
    trade: Order.Trade.Cash,
  });

  await esun.placeOrder(order);
  ```

## 三、SDK 教學（Tutorials）

### 1. 交易流程（買入、查詢、改價、當沖賣出）

> **官方章節**：[SDK 教學 > 交易](https://www.esunsec.com.tw/trading-platforms/api-trading/docs/trading/tutorial/trade)

1. **買入股票**（以 28.00 元買進 2 張玉山金 `2884`，並附帶自訂標記 `user_def` / `userDef`）：
   * **Python**：
     ```python
     order = OrderObject(
         buy_sell=Action.Buy,
         price=28.00,
         stock_no="2884",
         quantity=2,
         ap_code=APCode.Common,
         user_def="strategy_test"
     )
     sdk.place_order(order)
     ```
   * **Node.js**：
     ```javascript
     const order = new Order({
       buySell: Order.Side.Buy,
       price: 28.00,
       stockNo: '2884',
       quantity: 2,
       apCode: Order.ApCode.Common,
       priceFlag: Order.PriceFlag.Limit,
       bsFlag: Order.BsFlag.ROD,
       trade: Order.Trade.Cash,
       userDef: "strategy_test"
     });
     await esun.placeOrder(order);
     ```

2. **確認委託及成交狀態**：
   * **Python**：`orderResults = sdk.get_order_results()`
   * **Node.js**：`const orders = await esun.getOrders();`

3. **修改委託價格**（改價為 29.95 元）：
   * **Python**：
     ```python
     orderResults = sdk.get_order_results()
     sdk.modify_price(orderResults[0], 29.95)
     ```
   * **Node.js**：
     ```javascript
     const [ order, ...orders ] = await esun.getOrders();
     await esun.replacePrice(order, 29.95);
     ```

4. **當沖賣出股票**（以 31.10 元當沖賣出 1 張玉山金 `2884`，須具備當沖權限）：
   * **Python**：
     ```python
     order = OrderObject(
         buy_sell=Action.Sell,
         price=31.10,
         stock_no="2884",
         quantity=1,
         ap_code=APCode.Common,
         trade=Trade.DayTradingSell
     )
     sdk.place_order(order)
     ```
   * **Node.js**：
     ```javascript
     const order = new Order({
       buySell: Order.Side.Sell,
       price: 31.10,
       stockNo: '2884',
       quantity: 1,
       apCode: Order.ApCode.Common,
       priceFlag: Order.PriceFlag.Limit,
       bsFlag: Order.BsFlag.ROD,
       trade: Order.TradeType.DayTradingSell,
     });
     await esun.placeOrder(order);
     ```

### 2. 查詢帳務（成交明細、庫存、交割款）

> **官方章節**：[SDK 教學 > 查詢帳務](https://www.esunsec.com.tw/trading-platforms/api-trading/docs/trading/tutorial/account)
> **抓取限制**：每 5 秒一次；若超出上限，請於 10 秒後再試。交易當日盤中取得的交割款僅為試算結果，需待當日 **21:00** 帳務系統更新後，才可取得正確的 T+2 交割金額。

* **Python**：
  ```python
  # 成交明細（近期區間 / 指定日期區間）
  transactions = sdk.get_transactions("0d")
  transactions_by_date = sdk.get_transactions_by_date("2022-10-01", "2023-02-24")

  # 庫存明細
  inventories = sdk.get_inventories()

  # T+2 交割資訊
  settlements = sdk.get_settlements()
  ```

* **Node.js**：
  ```javascript
  // 成交明細
  const transactions = await esun.getTransactions({ duration: "0d" });
  const transactionsByDate = await esun.getTransactions({
    startDate: "2022-10-01",
    endDate: "2023-02-24"
  });

  // 庫存明細
  const inventories = await esun.getInventories();

  // T+2 交割資訊
  const settlements = await esun.getSettlements();
  ```

### 3. 主動回報（WebSocket 委託與成交推播）

> **官方章節**：[SDK 教學 > 主動回報](https://www.esunsec.com.tw/trading-platforms/api-trading/docs/trading/tutorial/report)

* **Python**：
  ```python
  @sdk.on('error')
  def on_error(err):
      print(err)

  @sdk.on('order')
  def on_order(data):
      print(data)

  @sdk.on('dealt')
  def on_dealt(data):
      print(data)

  # 註冊完成後建立 WebSocket 連線
  sdk.connect_websocket()
  ```

* **Node.js**：
  ```javascript
  esun.streamer.connect();

  esun.streamer.on('order', (data) => {
    console.log(data);
  });

  esun.streamer.on('trade', (data) => {
    console.log(data);
  });

  esun.streamer.on('error', (err) => {
    console.log(err);
  });
  ```

## 四、使用限制與速率控制（Rate Limits）

> **官方章節**：[使用限制](https://www.esunsec.com.tw/trading-platforms/api-trading/docs/trading/reference/rate_limit)

### 1. 登入及委託下單限制

| 行為 | 每秒上限 | 每分鐘上限 | 每日上限 |
| :--- | :--- | :--- | :--- |
| 登入 | - | 10 次 | 300 次 |
| 委託下單 | 20 次 | - | 2000 次 |

### 2. 交易及帳務查詢 Function 限制

| 行為 | Python Function | Node.js Function | 使用上限 |
| :--- | :--- | :--- | :--- |
| 庫存查詢 | `get_inventories()` | `getInventories()` | 每分鐘 12 次 |
| 委託查詢 | `get_order_results()`、`get_order_results_by_date()` | `getOrders()`、`getHistoricalOrders(options)` | 每分鐘 12 次 |
| 成交明細查詢 | `get_transactions()`、`get_transactions_by_date()` | `getTransactions(options)` | 每分鐘 12 次 |
| 交割款查詢 | `get_settlements()` | `getSettlements()` | 每分鐘 3 次 |
| 銀行餘額查詢 | `get_balance()` | `getBalance()` | 每 3 分鐘 1 次 |

> **超限說明**：若超出每秒／每分鐘上限，於 1 分鐘後可繼續執行指令；若超出當日上限，請於隔日再試或聯繫客服調整。

## 五、Python SDK Reference

> **官方章節**：[Python SDK Reference](https://www.esunsec.com.tw/trading-platforms/api-trading/docs/trading/reference/python)

### 1. 登入及用戶資訊

| 方法 | 參數 | 說明與注意事項 |
| :--- | :--- | :--- |
| `sdk.login()` | `None` | 登入有效時間為一天，每日有登入次數限制；執行任何功能前必先呼叫一次。 |
| `sdk.reset_password()` | `None` | 於命令列重設儲存在 SDK 的證券密碼及憑證密碼。密碼錯誤超過 3 次將鎖定帳號。 |
| `sdk.certinfo()` | `None` | 取得憑證資訊（`cn`、`is_valid`、`not_after`、`serial`）。憑證效期為申請日起一年。 |
| `sdk.get_key_info()` | `None` | 取得金鑰資訊（`api_key`、`api_key_memo`、`api_key_name`、`created_at`、`scope`、`status`）。效期為建立日起一年。 |
| `sdk.get_trade_status()` | `None` | 取得交易額度與信用／當沖權限（`trade_limit`、`margin_limit`、`short_limit`、`day_trade_code`、`margin_code`、`short_code`）。 |

`get_trade_status()` 回傳範例：
```json
{
  "trade_limit": 0,
  "margin_limit": 500000,
  "short_limit": 500000,
  "day_trade_code": "X",
  "margin_code": "0",
  "short_code": "0"
}
```
* `day_trade_code`：`X` 已啟用、`Y` 僅可先買後賣、`N` 未啟用
* `margin_code` / `short_code`：`0` 可買賣、`1` 可買、`2` 可賣、`9` 不可買賣

### 2. 交易下單與市場狀態

#### `place_order(order_object)`
* **參數**：`order_object`（`OrderObject`）
* **回傳範例**：
  ```json
  {
    "ord_date": "20220310",
    "ord_time": "094932438",
    "ord_type": "2",
    "ord_no": "A4461",
    "ret_code": "000000",
    "ret_msg": "",
    "work_date": "20220310"
  }
  ```

#### `modify_price(order_result, target_price, price_flag)`
* **參數**：
  * `order_result`（`OrderResult`）：委託單資料
  * `target_price`（`float | None`）：目標價格；非限價時須傳 `None`
  * `price_flag`（`PriceFlag`，選填）：價格旗標
* **規則**：只能修改 **ROD 限價單** 的價格；市價與其他價格旗標不可互相變更；除限價外，不可變更為原本相同的價格旗標。
* **範例**：
  ```python
  sdk.modify_price(order_result, 10.00)                    # 改成限價 10.00 元
  sdk.modify_price(order_result, None, PriceFlag.LimitDown) # 改成跌停
  sdk.modify_price(order_result, None, PriceFlag.LimitUp)   # 改成漲停
  sdk.modify_price(order_result, None, PriceFlag.Flat)      # 改成平盤
  ```
* **回傳範例**：
  ```json
  {
    "ret_code": "000000",
    "ret_msg": "",
    "ord_date": "20220310",
    "ord_time": "104605207"
  }
  ```

#### `cancel_order(order_result, **kwargs)`
* **說明**：減少委託單量，或刪除整筆委託。
* **參數**：
  * `order_result`（`OrderResult`）：委託單資料
  * `cel_qty`（`int`，選填）：取消張數
  * `cel_qty_share`（`int`，選填）：取消股數
* **規則**：`cel_qty` 與 `cel_qty_share` 擇一提供即可減量；若兩者皆未提供，則刪除整筆委託。

#### `get_order_results()` 與 `get_order_results_by_date(start_date, end_date)`
* `get_order_results()`：取得當日委託列表（回傳 `OrderResult[]`）。
* `get_order_results_by_date(start_date, end_date)`：查詢歷史委託列表（日期格式 `yyyy-MM-dd`），查詢範圍上限為 **180 日**（超過回傳 `AW00003`），無法查詢已刪除單與預約單，且 `PriceFlag` 僅區分市價與限價。

#### `get_market_status()` 與 `get_machine_time()`
* `get_market_status()`：回傳 `is_trading_day`（布林）、`last_trading_day`、`next_trading_day`。
* `get_machine_time()`：回傳主機端時間 `{ "time": "2022-03-10 10:23:48.464" }`；若本機時間與主機誤差過大將導致驗證失敗。

### 3. 帳務查詢方法

| 方法 | 參數 | 說明 |
| :--- | :--- | :--- |
| `get_transactions(query_range)` | `query_range` (`string`): `"0d"`、`"3d"`、`"1m"`、`"3m"` | 取得近期成交明細彙總與逐筆明細（`mat_dats`）。 |
| `get_transactions_by_date(start_date, end_date)` | `yyyy-MM-dd` | 依指定日期區間查詢成交明細，上限 **180 日**（超過回傳 `AW00002`）。 |
| `get_inventories()` | `None` | 取得當下庫存彙總與逐筆明細（`stk_dats`），含成本、損益平衡價、即時市值等。 |
| `get_balance()` | `None` | 取得銀行可用餘額（`available_balance`）、票據交換金額（`exange_balance`）、圈存金額（`stock_pre_save_amount`）。每 180 秒限查一次。 |
| `get_settlements()` | `None` | 取得 T+2 交割款資訊（`c_date`、`date`、`price`）。 |

### 4. Decorators（主動回報事件）
* `@sdk.on('order')`：接收 `NotifyAck` 委託回報物件。
* `@sdk.on('dealt')`：接收 `NotifyDealt` 成交回報物件。
* `@sdk.on('error')`：接收 WebSocket 錯誤資訊。

### 5. Classes（物件類別欄位規格）

#### `OrderObject`（建立委託單）

| 參數 | 型別 | 預設值 | 說明 |
| :--- | :--- | :--- | :--- |
| `ap_code` | `APCode` | `APCode.Common` | 盤別 |
| `buy_sell` | `Action` | `-` | 買賣別 |
| `price` | `float` | `-` | 委託價格（限價時必填，其餘價格旗標填 `None`） |
| `stock_no` | `string` | `-` | 股票代號 |
| `quantity` | `int` | `-` | 委託數量（單位與範圍依 `ap_code` 而異） |
| `price_flag` | `PriceFlag` | `PriceFlag.Limit` | 價格旗標 |
| `bs_flag` | `BSFlag` | `BSFlag.ROD` | 委託條件 |
| `trade` | `Trade` | `Trade.Cash` | 交易類別 |
| `user_def`（選填） | `string` | `-` | 自訂欄位（上限 50 字元，不含特殊符號；模擬環境不支援） |

#### `OrderResult`（委託紀錄物件）

| 欄位 | 型別 | 說明 |
| :--- | :--- | :--- |
| `ap_code` | `APCode` | 盤別 |
| `avg_price` | `number` | 成交均價 |
| `bs_flag` | `BSFlag` | 委託條件 |
| `buy_sell` | `Action` | 買賣別 |
| `cel_qty` / `cel_qty_share` | `number` | 已取消數量（張）／（股） |
| `celable` | `string` | 可取消狀態：`1` 可取消、`2` 不可取消 |
| `err_code` / `err_msg` | `string` | 錯誤碼與錯誤訊息 |
| `mat_qty` / `mat_qty_share` | `number` | 已成交數量（張）／（股） |
| `od_price` | `number` | 委託價格 |
| `ord_date` / `ord_time` | `string` | 原始委託日期與時間 |
| `ord_no` | `string` | 委託書編號 |
| `ord_status` | `string` | 預約狀態：`1` 預約單、`2` 盤中單 |
| `org_qty` / `org_qty_share` | `number` | 原始委託數量（張）／（股） |
| `pre_ord_no` | `string` | 預約單編號（預約單才有值） |
| `price_flag` | `PriceFlag` | 價格旗標 |
| `stock_no` | `string` | 股票代號 |
| `trade` | `Trade` | 交易類別 |
| `work_date` | `string` | 有效交易日期 |
| `user_def` | `string` | 自訂欄位（模擬環境不支援） |

#### `NotifyAck`（主動委託回報物件）

| 欄位 | 型別 | 說明 |
| :--- | :--- | :--- |
| `work_date` | `string` | 有效交易日期 |
| `ret_date` / `ret_time` | `string` | 委託日期／委託時間 |
| `ord_status` | `string` | 預約狀態（`1` 預約單、`2` 盤中單） |
| `ord_no` / `pre_ord_no` | `string` | 委託書編號／預約單編號 |
| `stock_no` | `string` | 股票代號 |
| `buy_sell` | `string` | 買賣別 |
| `ap_code` | `string` | 盤別 |
| `price_flag` | `string` | 價格旗標 |
| `trade` | `string` | 交易類別 |
| `od_price` | `string` | 委託價格 |
| `org_qty` / `mat_qty` / `cel_qty` | `string` | 原始委託／已成交／已取消數量 |
| `cel_type` | `string` | 可取消狀態（`1` 可取消、`2` 不可取消） |
| `err_code` / `err_msg` | `string` | 錯誤碼與錯誤訊息 |
| `before_qty` / `after_qty` | `string` | 變更前數量／變更後數量 |
| `bs_flag` | `string` | 委託條件 |

#### `NotifyDealt`（主動成交回報物件）

| 欄位 | 型別 | 說明 |
| :--- | :--- | :--- |
| `mat_time` | `string` | 成交時間 |
| `ord_no` | `string` | 委託書編號 |
| `stock_no` | `string` | 股票代號 |
| `buy_sell` | `string` | 買賣別 |
| `ap_code` | `string` | 盤別 |
| `trade` | `string` | 交易類別 |
| `mat_price` | `string` | 成交價格 |
| `mat_qty` | `string` | 已成交數量 |
| `pay_price` | `string` | 價金 |
| `mkt_seq_num` | `string` | 市場總序號 |

### 6. Constants（常數 Enum 與規則對照）

* **`Action`（買賣別）**：`Buy = "B"`（買）、`Sell = "S"`（賣）
* **`Trade`（交易類別）**：`Cash = "0"`（現股）、`Margin = "3"`（融資）、`Short = "4"`（融券）、`DayTrading = "9"`（信用當沖，僅適用於帳務）、`DayTradingSell = "A"`（現股當沖賣）
* **`PriceFlag`（價格旗標）**：`Limit = "0"`（限價）、`Flat = "1"`（平盤）、`LimitDown = "2"`（跌停）、`LimitUp = "3"`（漲停）、`Market = "4"`（市價）
* **`BSFlag`（委託條件）**：`FOK = "F"`（立即全部成交否則取消）、`IOC = "I"`（立即成交否則取消）、`ROD = "R"`（當日委託有效單）
* **`KeyScope`（金鑰權限）**：`Trade = "A"`（下單）、`Query = "B"`（查詢）、`All = "C"`（全部）

**`APCode`（盤別）數量範圍與可用價格旗標對照表**：

| 常數名稱 | 值 | 盤別說明 | Quantity 單位 | Quantity 範圍 | 可用 `PriceFlag` |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `APCode.Common` | `"1"` | 整股 | 張 | 1 ～ 499 | `Limit`, `Flat`, `LimitDown`, `LimitUp`, `Market` |
| `APCode.AfterMarket` | `"2"` | 盤後定價 | 張 | 1 ～ 499 | `Limit` |
| `APCode.Odd` | `"3"` | 盤後零股 | 股 | 1 ～ 999 | `Limit`, `Flat`, `LimitDown`, `LimitUp` |
| `APCode.Emg` | `"4"` | 興櫃 | 股 | 1 ～ 999、1000 ～ 499000（超過 1000 須為 1000 倍數） | `Limit` |
| `APCode.IntradayOdd` | `"5"` | 盤中零股 | 股 | 1 ～ 999 | `Limit`, `Flat`, `LimitDown`, `LimitUp` |

## 六、Node.js SDK Reference

> **官方章節**：[Node.js SDK Reference](https://www.esunsec.com.tw/trading-platforms/api-trading/docs/trading/reference/nodejs)

### 1. `EsunTrade` 類別與方法

#### 初始化：`new EsunTrade(options)`
* `configPath` `{string}`：設定檔路徑（如 `'/path/to/config.ini'`）。
* `config` `{Object}`：直接傳入設定物件（含 `apiUrl`、`apiKey`、`apiSecret`、`certPath`、`certPass`、`aid`、`password`）。

#### 核心方法總覽（回傳欄位均為 camelCase 命名）

| 分類 | 方法簽章 | 說明 |
| :--- | :--- | :--- |
| **認證** | `esun.login()` | 登入遠端伺服器。 |
| **認證** | `esun.logout()` | 登出並刪除驗證憑據。 |
| **交易** | `esun.placeOrder(order)` | 送出 `Order` 委託單，回傳 `PlaceOrderResponse`。 |
| **交易** | `esun.getOrders()` | 取得當日委託列表（`OrderResult[]`）。 |
| **交易** | `esun.replacePrice(order, price)` | 修改進行中委託單價格（`number \| Order.PriceFlag`）。 |
| **交易** | `esun.replaceQuantity(order, quantity)` | 修改進行中委託單數量。 |
| **交易** | `esun.replaceOrder(order, options)` | 修改價格或數量（`options.price` 或 `options.quantity` 擇一）。 |
| **交易** | `esun.cancelOrder(order)` | 取消進行中委託單。 |
| **交易** | `esun.getHistoricalOrders(options)` | 查詢歷史委託（`options: { startDate, endDate }`）。 |
| **帳務** | `esun.getTransactions(options)` | 查詢成交明細（`duration`: `'0d'\|'3d'\|'1m'\|'3m'` 或 `{ startDate, endDate }`）。 |
| **帳務** | `esun.getInventories()` | 取得現有庫存明細（`Stock[]`）。 |
| **帳務** | `esun.getSettlements()` | 取得交割資訊（`Settlement[]`）。 |
| **帳務** | `esun.getBalance()` | 取得銀行帳戶餘額（`BalanceStatus`）。 |
| **資訊** | `esun.getTradeStatus()` | 取得交易額度與融資／融券／當沖狀態。 |
| **資訊** | `esun.getMarketStatus()` | 取得市場開盤與上下交易日狀態。 |
| **資訊** | `esun.getKeyInfo()` | 取得 API 金鑰資訊。 |
| **資訊** | `esun.getCertInfo()` | 取得憑證資訊。 |
| **資訊** | `esun.getMachineTime()` | 取得遠端伺服器時間字串。 |

### 2. `esun.streamer`（WebSocket 主動回報）
繼承自 `EventEmitter`，包含以下方法與事件：
* **方法**：`esun.streamer.connect()`、`esun.streamer.disconnect()`
* **事件**：`'connect'`、`'disconnect'`、`'order'`（委託回報）、`'trade'`（成交回報）、`'message'`（原始訊息）、`'error'`（錯誤物件）

### 3. `Order` 類別與 Enum 常數對照表

* **建構子**：`new Order({ stockNo, buySell, price, quantity, apCode, priceFlag, bsFlag, trade })`
* **鏈式 Setter**：`setSymbol()`、`setSide()`、`setPrice()`、`setQuantity()`、`setApCode()`、`setPriceFlag()`、`setBsFlag()`、`setTradeType()`、`toObject()`

| Enum 類別 | 常數名稱與值 |
| :--- | :--- |
| `Order.Side` | `Buy` (`'B'`)、 `Sell` (`'S'`) |
| `Order.ApCode` | `Common` (`'1'`)、 `AfterMarket` (`'2'`)、 `Odd` (`'3'`)、 `Emg` (`'4'`)、 `IntradayOdd` (`'5'`) |
| `Order.PriceFlag` | `Limit` (`'0'`)、 `Flat` (`'1'`)、 `LimitDown` (`'2'`)、 `LimitUp` (`'3'`)、 `Market` (`'4'`) |
| `Order.BsFlag` | `ROD` (`'R'`)、 `IOC` (`'I'`)、 `FOK` (`'F'`) |
| `Order.TradeType` | `Cash` (`'0'`)、 `Margin` (`'3'`)、 `Short` (`'4'`)、 `DayTrading` (`'9'`)、 `DayTradingSell` (`'A'`) |

## 七、錯誤代碼總表（Error Codes）

> **官方章節**：[錯誤代碼](https://www.esunsec.com.tw/trading-platforms/api-trading/docs/trading/reference/error_codes)

### 1. AG 系列（交易閘道與委託錯誤）

| 錯誤代碼 | 訊息 | 說明 |
| :--- | :--- | :--- |
| `AG00000` | Parameter error | 參數錯誤 |
| `AG00001` | Cert error | 驗章錯誤（可能因憑證過期或已刪除），請重新匯出憑證 |
| `AG00003` | OrdNo Error | 單號不存在，刪改單參數錯誤 |
| `AG00004` | The trading system is temporarily suspended | 交易系統暫停服務中，請稍後再試 |
| `AG00005` | This order cannot be deleted | 此單目前不可刪除（例如 `celable` 狀態為 `2`） |
| `AG00006` | Reservation order cannot be changed | 預約單不可改單，請刪單後重新下單 |

### 2. AGA 系列（登入、金鑰與 IP 驗證錯誤）

| 錯誤代碼 | 訊息 | 說明 |
| :--- | :--- | :--- |
| `AGA0000` | login error | 登入密碼錯誤 |
| `AGA0001` | Missing Header | 缺少請求標頭 |
| `AGA0002` | Invalid IP | IP 未加入白名單，請至金鑰網站新增目前 IP |
| `AGA0003` | Invalid Signature | 簽章無效（可能為設定檔 `Secret` 錯誤） |
| `AGA0004` | Invalid Nonce | 無效的 Nonce |
| `AGA0005` | Invalid Timestamp | 本機時間與伺服器時間誤差過大，請開啟系統自動校時 |
| `AGA0006` | No Such Key | 設定檔 `Key` 不存在或誤改 |
| `AGA0007` | Key Is Invalid | 金鑰已遭刪除或失效 |
| `AGA0008` | Invalid Scope | 金鑰權限不符（例如使用僅具帳務權限之金鑰下單） |
| `AGA0009` | Not Allowed to Use | 不允許使用 |
| `AGA0010` | Not Allowed To Login | 未完成金鑰申請流程或帳號已暫停，請聯繫客服 |
| `AGA0011` | Not Allowed Account Type | 須為玉山證券帳戶方可使用 |
| `AGA0012` | Key And Login Account Error | 設定檔中的 `Key` 與 `Account` 不匹配 |

### 3. AGR 系列（速率限制錯誤）

| 錯誤代碼 | 訊息 | 說明 |
| :--- | :--- | :--- |
| `AGR0000` | Exceed Login Rate Limit | 達每分鐘登入次數上限，請 1 分鐘後再試 |
| `AGR0001` | Exceed User Daily Order Rate Limit `{userLimit}` | 達單日委託次數上限 |
| `AGR0002` | Exceed User Second Order Rate Limit | 達每秒委託次數上限，請 1 分鐘後再試 |
| `AGR0003` | Exceed Transaction Rate Limit | 達帳務明細抓取限制，請 1 分鐘後再試 |
| `AGR0004` | Exceed Login Daily Rate Limit `{userLimit}` | 達單日登入次數上限 |
| `AGR0005` | Exceed OrderResult Rate Limit | 達委託查詢頻率上限，請 1 分鐘後再試 |
| `AGR0006` | Exceed Settlement Query Rate Limit | 達交割款查詢頻率上限，請 1 分鐘後再試 |

### 4. AWA / AW 系列（查詢與標頭錯誤）

| 錯誤代碼 | 訊息 | 說明 |
| :--- | :--- | :--- |
| `AWA0001` | Missing Header | 缺少請求標頭 |
| `AWA0004` | Invalid Nonce | 無效的 Nonce |
| `AWA0005` | Invalid Timestamp | 請檢查本機端時間 |
| `AW00000` / `AW00001` | 參數錯誤 | 請確認 SDK 版本是否已更新 |
| `AW00002` | 參數錯誤 | 成交明細查詢日期超過範圍限制（上限 180 日） |
| `AW00003` | 參數錯誤 | 歷史委託列表查詢日期超過範圍限制（上限 180 日） |

### 5. C 系列（憑證讀取錯誤）

| 錯誤代碼 | 訊息 | 說明 |
| :--- | :--- | :--- |
| `C00000` | certs file open failed | 憑證檔案權限或路徑錯誤 |
| `C00001` / `C00002` | key error / certs error | 憑證檔案（`.p12`）損毀或非玉證憑證 |
| `C00003` | password may be wrong | 輸入的憑證密碼錯誤 |
| `C00004` | load keys error | 電腦記憶體不足 |
| `C00005` | certs error | 憑證已過期 |

### 6. A 系列（請求格式與參數驗證）

| 錯誤代碼 | 訊息 | 說明 |
| :--- | :--- | :--- |
| `A00001` / `A00002` / `A00004` | JSON parse Error | 與伺服器之 GET / POST 請求解析異常 |
| `A00003` | 憑證跟帳號不合 | 可能使用了非本人的憑證 |
| `A00005` | 參數錯誤 | `transaction` 須使用 `0d\|3d\|1m\|3m` |
| `A00006` | 參數錯誤 | 日期格式錯誤（須為 `yyyy-MM-dd`） |

### 7. O 系列（下單參數校驗錯誤）

| 錯誤代碼 | 訊息 | 說明 |
| :--- | :--- | :--- |
| `O00001` ～ `O00005` | must use valid `apcode`/`bs`/`trade`/`price_flag`/`bs_flag` | 輸入了無效的盤別、買賣別、交易類別、價格旗標或委託條件 |
| `O00006` / `O00007` | quantity value error / must > 0 | 委託數量數值有誤或未大於 0 |
| `O00008` | quantity must <= 499 | 整股／盤後定價張數須小於等於 499 張 |
| `O00009` | quantity must <= 999 | 零股股數須小於等於 999 股 |
| `O00010` | quantity must <= 499000 | 興櫃整股股數須小於等於 499000 股 |
| `O00011` | quantity must be multiple of 1000, or any value under 1000 | 興櫃委託須為 1000 的倍數或小於 1000 股 |
| `O00012` | In after market, price_flag can only be Limit | 盤後定價僅可使用限價 |
| `O00013` | price must be valid float string | 價格格式不正確 |
| `O00014` | price should be None if priceFlag not Limit | 非限價委託時，價格須設為 `None` |
| `O00015` | price_flag can only be Limit if APCode is Emg | 興櫃股票僅可使用限價 |
| `O00016` | Trade can only be Cash if APCode is Emg | 興櫃股票僅可使用現股交易 |
| `O00017` | price_flag must 0, bs_flag must R | 改單／改量僅限 ROD 限價單 |

## 八、最佳實踐（Best Practice）

> **官方章節**：[最佳實踐](https://www.esunsec.com.tw/trading-platforms/api-trading/docs/trading/best_practice)

1. **瞭解交易規則與限制**：開發前務必確認交易所買賣規則、交易時間與帳戶交易額度限制。
2. **強化安全性**：妥善保管 `.p12` 憑證與 API 金鑰，於部署主機設置防火牆與存取權限控管。
3. **錯誤處理與異常應對**：驗證輸入參數並妥善處理網路斷線與下單失敗重試機制。
4. **請求節流與即時行情搭配**：盤中追蹤報價請優先使用 **WebSocket 行情 API**，避免高頻輪詢 HTTP；同時避免在盤中過於頻繁查詢庫存與銀行餘額。
5. **主動回報與本地快取同步**：善用 WebSocket 主動回報（`order` / `dealt`）即時更新本地快取的持股與可用資金，確保下單前狀態同步。
6. **監控與日誌記錄**：建立完整的 API 回應時間、健康狀態與交易流程日誌以利除錯。
7. **模擬環境充分測試**：正式上線前務必於模擬環境或非交易時段完整驗證交易邏輯。

## 九、交易 SDK 遷移指南（Migration Guide）

> **官方章節**：[遷移指南](https://www.esunsec.com.tw/trading-platforms/api-trading/docs/trading/migration_guide)

原本的 `fugle_trade`（Python）與 `@fugle/trade`（Node.js）套件已更名為 `esun_trade` 與 `@esun/trade`，需調整 `import` 與類別名稱：

### 1. Python 遷移對照

```python
# --- 舊版 (fugle_trade) ---
from configparser import ConfigParser
from fugle_trade.sdk import SDK
from fugle_trade.order import OrderObject
from fugle_trade.constant import (APCode, Trade, PriceFlag, BSFlag, Action)

config = ConfigParser()
config.read('/path/to/config.ini')
sdk = SDK(config)
sdk.login()

# --- 新版 (esun_trade) ---
from configparser import ConfigParser
from esun_trade.sdk import SDK
from esun_trade.order import OrderObject
from esun_trade.constant import (APCode, Trade, PriceFlag, BSFlag, Action)

config = ConfigParser()
config.read('/path/to/config.ini')
sdk = SDK(config)
sdk.login()
```

### 2. Node.js 遷移對照

```javascript
// --- 舊版 (@fugle/trade) ---
import { FugleTrade, Order } from '@fugle/trade';

const fugle = new FugleTrade({
  configPath: '/path/to/config.ini',
});
await fugle.login();

// --- 新版 (@esun/trade) ---
import { EsunTrade, Order } from '@esun/trade';

const esun = new EsunTrade({
  configPath: '/path/to/config.ini',
});
await esun.login();
```
