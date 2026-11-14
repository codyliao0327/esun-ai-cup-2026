# 玉山證券行情 API（Market Data API）完整技術說明文件

> **官方文件來源**：[玉山證券 API 交易服務 - 行情 API 說明文件](https://www.esunsec.com.tw/trading-platforms/api-trading/docs/market-data/intro)

## 一、簡介與服務聲明

### 1. 服務概述

玉山證券行情 API（Market Data API）由 **群馥科技（Fugle）** 技術團隊開發提供，整合臺灣證券市場即時與歷史行情數據，提供開發者透過 RESTful Web API 與 WebSocket 串流介面獲取台股市場資訊。

* **數據覆蓋範圍**：臺灣證券交易所（TWSE）、證券櫃檯買賣中心（TPEx）、臺灣期貨交易所（TAIFEX）。

* **資訊提供商**：時報資訊、群馥科技（Fugle）。

* **支援開發語言**：Python（支援 Python 3.7 ～ 3.13）與 Node.js。

### 2. 使用規範與免責聲明

1. **行情參考性**：透過本服務取得之行情資料僅供參考，成交值及成交量 **不含零股及鉅額交易**（盤中零股需另帶參數查詢），使用者需自行承擔交易風險與損失。

2. **免責聲明**：時報資訊與群馥科技對資料內容錯誤、更新延誤或傳輸中斷不負任何法律責任。

3. **智慧財產與轉載限制**：使用者須遵守臺灣證券交易所、證券櫃檯買賣中心、臺灣期貨交易所之「交易資訊使用管理辦法」及相關智慧財產權法規，**嚴禁盜接、轉接、出售、出租、轉讓、再授權或編製衍生商品予第三方**。

## 二、速率限制與連線配額（Rate Limits）

> **官方章節**：[速率限制](https://www.esunsec.com.tw/trading-platforms/api-trading/docs/market-data/rate-limit/)

### 1. 配額總覽

| 介面類型 | 功能模組 / 項目 | 限制配額 | 超限錯誤碼 / 狀態 | 超限處理方式 | 
| ----- | ----- | ----- | ----- | ----- | 
| **Web API (HTTP)** | 日內行情（Intraday） | 600 次 / 分鐘 | HTTP `429 Too Many Requests` | 暫停請求，等待 1 分鐘後自動恢復 | 
| **Web API (HTTP)** | 行情快照（Snapshot） | 600 次 / 分鐘 | HTTP `429 Too Many Requests` | 暫停請求，等待 1 分鐘後自動恢復 | 
| **Web API (HTTP)** | 歷史行情（Historical） | 60 次 / 分鐘 | HTTP `429 Too Many Requests` | 暫停請求，等待 1 分鐘後自動恢復 | 
| **WebSocket API** | 同時連線數上限 | 最多 2 條連線 | Error Code `1001` | `Maximum number of connections reached`，需關閉多餘連線 | 
| **WebSocket API** | 訂閱頻道總數上限 | 最多 300 個頻道 | 拒絕新增訂閱 | 需先透過 `unsubscribe` 取消不需使用的頻道 | 

## 三、環境準備、安裝與身份驗證

> **官方章節**：[Web API 開始使用](https://www.esunsec.com.tw/trading-platforms/api-trading/docs/market-data/http-api/getting-started)

### 1. 設定檔格式（`config.ini`）

玉山證券新版行情 SDK 統一採用設定檔（`config.ini`）進行憑證、API 金鑰與帳號驗證：

```
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

### 2. SDK 安裝方式

* **Python 安裝**（支援 Python 3.7、3.8、3.9、3.10、3.11、3.12、3.13）：

  ```
  pip install esun_marketdata-<version>-<platform>.whl
  
  ```

* **Node.js 安裝**： 先初始化專案並於 `package.json` 加入本地安裝檔路徑：

  ```
  npm init
  
  ```

  於 `package.json` 新增依賴：

  ```
  {
    "dependencies": {
      "esun-marketdata": "file://<path-to-js-binary>/esun-marketdata-<version>.tgz"
    }
  }
  
  ```

  執行安裝：

  ```
  npm install
  
  ```

### 3. SDK 初始化與登入

* **Python 初始化範例**：

  ```
  from configparser import ConfigParser
  from esun_marketdata import EsunMarketdata
  
  config = ConfigParser()
  config.read('/path/to/config.ini')
  sdk = EsunMarketdata(config)
  
  # 執行登入驗證
  sdk.login()
  
  # 取得 REST API 股票客戶端
  rest_stock = sdk.rest_client.stock
  
  ```

* **Node.js 初始化範例**：

  ```
  const { EsunMarketdata } = require("@esun/marketdata");
  
  const sdk = new EsunMarketdata({
    configPath: "/path/to/config.ini",
  });
  
  await sdk.login();
  
  // 取得 REST API 股票客戶端
  const restClient = sdk.restClient.stock;
  
  ```

## 四、Web API — 日內行情（Intraday）

### 1. Tickers — 取得股票或指數列表（依條件查詢）

* **端點**：`GET /intraday/tickers`

* **官方說明**：[Intraday Tickers](https://www.google.com/search?q=https://www.esunsec.com.tw/trading-platforms/api-trading/docs/market-data/http-api/intraday/tickers/)

#### 請求參數（Parameters）

| 參數名稱 | 型別 | 必填 | 說明 | 
| ----- | ----- | ----- | ----- | 
| `type` | `string` | 是 | Ticker 類型，可選：`EQUITY`（股票）、`INDEX`（指數）、`WARRANT`（權證）、`ODDLOT`（盤中零股） | 
| `exchange` | `string` | 否 | 交易所，可選：`TWSE`（臺灣證券交易所）、`TPEx`（證券櫃檯買賣中心） | 
| `market` | `string` | 否 | 市場別，可選：`TSE`（上市）、`OTC`（上櫃）、`ESB`（興櫃一般板）、`TIB`（臺灣創新板） | 
| `industry` | `string` | 否 | 產業別代碼（參閱下方產業別代碼表） | 
| `isNormal` | `boolean` | 否 | 查詢正常股票（非注意、處置股票）：`true`；帶入時僅查詢 `EQUITY`，`type` 不生效 | 
| `isAttention` | `boolean` | 否 | 查詢注意股票：`true`；帶入時僅查詢 `EQUITY`，`type` 不生效 | 
| `isDisposition` | `boolean` | 否 | 查詢處置股票：`true`；帶入時僅查詢 `EQUITY`，`type` 不生效 | 
| `isHalted` | `boolean` | 否 | 查詢暫停交易股票：`true`；帶入時僅查詢 `EQUITY`，`type` 不生效 | 

#### 回傳欄位（Response）

| 欄位名稱 | 型別 | 必填 | 說明 | 
| ----- | ----- | ----- | ----- | 
| `date` | `string` | 是 | 日期（`yyyy-MM-dd`） | 
| `type` | `string` | 是 | Ticker 類型 | 
| `exchange` | `string` | 是 | 交易所 | 
| `market` | `string` | 否 | 市場別（有帶入 `market` 時回傳） | 
| `industry` | `string` | 否 | 產業別（有帶入 `industry` 時回傳） | 
| `isNormal` | `boolean` | 否 | 查詢正常股票（帶入 `true` 時回傳） | 
| `isAttention` | `boolean` | 否 | 查詢注意股票（帶入 `true` 時回傳） | 
| `isDisposition` | `boolean` | 否 | 查詢處置股票（帶入 `true` 時回傳） | 
| `isHalted` | `boolean` | 否 | 查詢暫停交易股票（帶入 `true` 時回傳） | 
| `data` | `object[]` | 否 | 股票列表 | 
| `data[].symbol` | `string` | 否 | 股票代碼 | 
| `data[].name` | `string` | 否 | 股票簡稱 | 
| `data[].industry` | `string` | 否 | 產業別代碼；`type` 為 `EQUITY`（部分標的無此欄位）、`WARRANT` 時回傳 | 

#### 呼叫範例與回傳格式

```
# Python
rest_stock.intraday.tickers(type="EQUITY", exchange="TWSE", isNormal=True)

```

```
// Node.js
await restClient.intraday.tickers({ type: "EQUITY", exchange: "TWSE", isNormal: true });

```

```
{
  "date": "2026-10-08",
  "type": "EQUITY",
  "exchange": "TWSE",
  "isNormal": true,
  "data": [
    {
      "symbol": "0050",
      "industry": "00",
      "name": "元大台灣50"
    }
  ]
}

```

#### 附表：產業別代碼對照表

> 註：不具備產業屬性的證券如 ETF、可轉換公司債、附認股權公司債、認購（售）權證等衍生性商品，產業別代碼為 `00`。

| 代碼 | 產業別 | 代碼 | 產業別 | 代碼 | 產業別 | 
| ----- | ----- | ----- | ----- | ----- | ----- | 
| `01` | 水泥工業 | `16` | 觀光餐旅 | `29` | 電子通路業 | 
| `02` | 食品工業 | `17` | 金融保險 | `30` | 資訊服務業 | 
| `03` | 塑膠工業 | `18` | 貿易百貨 | `31` | 其他電子業 | 
| `04` | 紡織纖維 | `19` | 綜合 | `32` | 文化創意業 | 
| `05` | 電機機械 | `20` | 其他 | `33` | 農業科技業 | 
| `06` | 電器電纜 | `21` | 化學工業 | `34` | 電子商務 | 
| `08` | 玻璃陶瓷 | `22` | 生技醫療業 | `35` | 綠能環保 | 
| `09` | 造紙工業 | `23` | 油電燃氣業 | `36` | 數位雲端 | 
| `10` | 鋼鐵工業 | `24` | 半導體業 | `37` | 運動休閒 | 
| `11` | 橡膠工業 | `25` | 電腦及週邊設備業 | `38` | 居家生活 | 
| `12` | 汽車工業 | `26` | 光電業 | `80` | 管理股票 | 
| `14` | 建材營造 | `27` | 通信網路業 | `00` | ETF / 衍生性商品 | 
| `15` | 航運業 | `28` | 電子零組件業 |  |  | 

### 2. Ticker — 取得股票基本資料（依代碼查詢）

* **端點**：`GET /intraday/ticker/{symbol}`

* **官方說明**：[Intraday Ticker](https://www.esunsec.com.tw/trading-platforms/api-trading/docs/market-data/http-api/intraday/ticker/)

#### 請求參數（Parameters）

| 參數名稱 | 型別 | 必填 | 說明 | 
| ----- | ----- | ----- | ----- | 
| `symbol` | `string` | 是 | 股票代碼（如 `2330`） | 
| `type` | `string` | 否 | 類型，可選 `oddlot`（盤中零股） | 

#### 回傳欄位（Response）

| 欄位名稱 | 型別 | 必填 | 說明 | 
| ----- | ----- | ----- | ----- | 
| `date` | `string` | 是 | 日期 | 
| `type` | `string` | 是 | Ticker 類型 | 
| `exchange` | `string` | 是 | 交易所 | 
| `market` | `string` | 否 | 市場別 | 
| `symbol` | `string` | 是 | 股票代碼 | 
| `name` | `string` | 是 | 股票簡稱 | 
| `industry` | `string` | 否 | 產業別代碼 | 
| `securityType` | `string` | 否 | 證券別代碼（參閱下方證券別代碼表） | 
| `previousClose` | `number` | 否 | 前一交易日收盤價 | 
| `referencePrice` | `number` | 否 | 今日參考價 | 
| `limitUpPrice` | `number` | 否 | 漲停價（興櫃股不適用） | 
| `limitDownPrice` | `number` | 否 | 跌停價（興櫃股不適用） | 
| `canDayTrade` | `boolean` | 否 | 可買賣現沖（興櫃股不適用） | 
| `canBuyDayTrade` | `boolean` | 否 | 可先買現沖（興櫃股不適用） | 
| `canBelowFlatMarginShortSell` | `boolean` | 否 | 平盤下得融券賣出（興櫃股不適用） | 
| `canBelowFlatSBLShortSell` | `boolean` | 否 | 平盤下得借券賣出（興櫃股不適用） | 
| `isAttention` | `boolean` | 否 | 注意股 | 
| `isDisposition` | `boolean` | 否 | 處置股 | 
| `isUnusuallyRecommended` | `boolean` | 否 | 投資理財節目異常推介個股（興櫃股不適用） | 
| `isSpecificAbnormally` | `boolean` | 否 | 特殊異常個股（興櫃股不適用） | 
| `matchingInterval` | `number` | 否 | 撮合循環秒數（興櫃股不適用） | 
| `securityStatus` | `string` | 否 | 證券狀態：`NORMAL`、`TERMINATED`、`SUSPENDED` | 
| `boardLot` | `number` | 否 | 交易單位（每張股數，如 `1000`） | 
| `tradingCurrency` | `string` | 否 | 交易幣別（如 `TWD`） | 
| `exercisePrice` | `number` | 否 | 履約價格（限權證） | 
| `exercisedVolume` | `number` | 否 | 前一交易日履約數量（限權證） | 
| `cancelledVolume` | `number` | 否 | 前一交易日註銷數量（限權證） | 
| `remainingVolume` | `number` | 否 | 發行餘額量（限權證） | 
| `exerciseRatio` | `number` | 否 | 行使比率（限權證） | 
| `knockInPrice` | `number` | 否 | 上限價格（限權證） | 
| `knockOutPrice` | `number` | 否 | 下限價格（限權證） | 
| `maturityDate` | `string` | 否 | 到期日（限權證） | 
| `openTime` | `string` | 否 | 開盤時間（限指數） | 
| `closeTime` | `string` | 否 | 收盤時間（限指數） | 

#### 呼叫範例與回傳格式

```
# Python
rest_stock.intraday.ticker(symbol="2330")

```

```
// Node.js
await restClient.intraday.ticker({ symbol: "2330" });

```

```
{
  "date": "2023-05-29",
  "type": "EQUITY",
  "exchange": "TWSE",
  "market": "TSE",
  "symbol": "2330",
  "name": "台積電",
  "industry": "24",
  "securityType": "01",
  "previousClose": 566,
  "referencePrice": 566,
  "limitUpPrice": 622,
  "limitDownPrice": 510,
  "canDayTrade": true,
  "canBuyDayTrade": true,
  "canBelowFlatMarginShortSell": true,
  "canBelowFlatSBLShortSell": true,
  "isAttention": false,
  "isDisposition": false,
  "isUnusuallyRecommended": false,
  "isSpecificAbnormally": false,
  "matchingInterval": 0,
  "securityStatus": "NORMAL",
  "boardLot": 1000,
  "tradingCurrency": "TWD"
}

```

#### 附表：證券別代碼對照表

| 代碼 | 證券別 | 代碼 | 證券別 | 
| ----- | ----- | ----- | ----- | 
| `01` | 一般股票 | `25` | ETF（外幣計價） | 
| `02` | 轉換公司債 | `26` | 槓桿型 ETF | 
| `03` | 交換公司債或交換金融債 | `27` | 槓桿型 ETF（外幣計價） | 
| `04` | 一般特別股 | `28` | 反向型 ETF | 
| `05` | 可交換特別股 | `29` | 反向型 ETF（外幣計價） | 
| `06` | 認股權憑證 | `30` | 期信託 ETF | 
| `07` | 附認股權特別股 | `31` | 期信託 ETF（外幣計價） | 
| `08` | 附認股權公司債 | `32` | 債券 ETF | 
| `09` | 附認股權公司債履約或分拆後之公司債 | `33` | 債券 ETF（外幣計價） | 
| `10` | 國內標的認購權證 | `34` | 金融資產證券化受益證券 | 
| `11` | 國內標的認售權證 | `35` | 不動產資產信託受益證券 | 
| `12` | 外國標的認購權證 | `36` | 不動產投資信託受益證券 | 
| `13` | 外國標的認售權證 | `37` | ETN | 
| `14` | 國內標的下限型認購權證 | `38` | 槓桿型 ETN | 
| `15` | 國內標的上限型認售權證 | `39` | 反向型 ETN | 
| `16` | 國內標的可展延下限型認購權證 | `40` | 債券型 ETN | 
| `17` | 國內標的可展延上限型認售權證 | `41` | 期權策略型 ETN | 
| `18` | 受益憑證（封閉式基金） | `42` | 中央登錄公債 | 
| `19` | 存託憑證 | `43` | 外國債券 | 
| `20` | 存託憑證可轉換公司債 | `44` | 黃金現貨 | 
| `21` | 存託憑證附認股權公司債 | `45` | 平衡型 ETF | 
| `22` | 存託憑證附認股權公司債履約或分拆後之公司債 | `46` | 主動型 ETF | 
| `23` | 存託憑證認股權憑證 | `47` | 債券主動式 ETF | 
| `24` | ETF | `00` | 未知或保留代碼 | 

### 3. Quote — 取得股票即時報價與最佳五檔（依代碼查詢）

* **端點**：`GET /intraday/quote/{symbol}`

* **官方說明**：[Intraday Quote](https://www.google.com/search?q=https://www.esunsec.com.tw/trading-platforms/api-trading/docs/market-data/http-api/intraday/quote/)

#### 請求參數（Parameters）

| 參數名稱 | 型別 | 必填 | 說明 | 
| ----- | ----- | ----- | ----- | 
| `symbol` | `string` | 是 | 股票代碼 | 
| `type` | `string` | 否 | 類型，可選 `oddlot`（盤中零股） | 

#### 回傳欄位（Response）

| 欄位名稱 | 型別 | 必填 | 說明 | 
| ----- | ----- | ----- | ----- | 
| `date` | `string` | 是 | 日期 | 
| `type` | `string` | 是 | Ticker 類型 | 
| `exchange` | `string` | 是 | 交易所 | 
| `market` | `string` | 是 | 市場別 | 
| `symbol` | `string` | 是 | 股票代碼 | 
| `name` | `string` | 是 | 股票簡稱 | 
| `referencePrice` | `number` | 否 | 今日參考價 | 
| `previousClose` | `number` | 否 | 昨日收盤價 | 
| `openPrice` | `number` | 否 | 開盤價 | 
| `openTime` | `number` | 否 | 開盤價成交時間（微秒時間戳） | 
| `highPrice` | `number` | 否 | 最高價 | 
| `highTime` | `number` | 否 | 最高價成交時間 | 
| `lowPrice` | `number` | 否 | 最低價 | 
| `lowTime` | `number` | 否 | 最低價成交時間 | 
| `closePrice` | `number` | 否 | 收盤價（最後成交價） | 
| `closeTime` | `number` | 否 | 收盤價（最後成交價）成交時間 | 
| `avgPrice` | `number` | 否 | 當日成交均價 | 
| `change` | `number` | 否 | 最後一筆成交漲跌（含試撮） | 
| `changePercent` | `number` | 否 | 最後一筆成交漲跌幅（含試撮） | 
| `amplitude` | `number` | 否 | 當日振幅 | 
| `lastPrice` | `number` | 否 | 最後一筆成交價（含試撮） | 
| `lastSize` | `number` | 否 | 最後一筆成交數量（含試撮） | 
| `bids` | `object[]` | 否 | 最佳五檔委買列表（`price` 價格、`size` 數量） | 
| `asks` | `object[]` | 否 | 最佳五檔委賣列表（`price` 價格、`size` 數量） | 
| `total` | `object` | 否 | 統計資訊物件 | 
| `total.tradeValue` | `number` | 否 | 累計成交金額 | 
| `total.tradeVolume` | `number` | 否 | 累計成交量 | 
| `total.tradeVolumeAtBid` | `number` | 否 | 累計內盤成交量（指數無此欄位） | 
| `total.tradeVolumeAtAsk` | `number` | 否 | 累計外盤成交量（指數無此欄位） | 
| `total.transaction` | `number` | 否 | 累計成交筆數 | 
| `total.bidOrders` | `number` | 否 | 累計委買筆數（僅指數） | 
| `total.askOrders` | `number` | 否 | 累計委賣筆數（僅指數） | 
| `total.bidVolume` | `number` | 否 | 累計委買數量（僅指數） | 
| `total.askVolume` | `number` | 否 | 累計委賣數量（僅指數） | 
| `total.time` | `number` | 否 | 統計時間 | 
| `lastTrade` | `object` | 否 | 最後一筆正式成交資訊（含 `bid`, `ask`, `price`, `size`, `time`, `serial`） | 
| `lastTrial` | `object` | 否 | 最後一筆試撮資訊（含 `bid`, `ask`, `price`, `size`, `time`, `serial`） | 
| `tradingHalt` | `object` | 否 | 暫停交易狀態（`isHalted` 布林值、`time` 暫停/恢復時間） | 
| `isLimitDownPrice` | `boolean` | 否 | 最後成交價為跌停價：`true` | 
| `isLimitUpPrice` | `boolean` | 否 | 最後成交價為漲停價：`true` | 
| `isLimitDownBid` | `boolean` | 否 | 最佳一檔委買跌停價：`true` | 
| `isLimitUpBid` | `boolean` | 否 | 最佳一檔委買漲停價：`true` | 
| `isLimitDownAsk` | `boolean` | 否 | 最佳一檔委賣跌停價：`true` | 
| `isLimitUpAsk` | `boolean` | 否 | 最佳一檔委賣漲停價：`true` | 
| `isLimitDownHalt` | `boolean` | 否 | 暫緩撮合且瞬間趨跌：`true` | 
| `isLimitUpHalt` | `boolean` | 否 | 暫緩撮合且瞬間趨漲：`true` | 
| `isTrial` | `boolean` | 否 | 試撮階段：`true` | 
| `isDelayedOpen` | `boolean` | 否 | 延後開盤信號：`true` | 
| `isDelayedClose` | `boolean` | 否 | 延後收盤信號：`true` | 
| `isContinuous` | `boolean` | 否 | 最後成交為逐筆交易：`true` | 
| `isOpen` | `boolean` | 否 | 開盤信號：`true` | 
| `isClose` | `boolean` | 否 | 收盤信號：`true` | 
| `lastUpdated` | `number` | 否 | 最後更新時間 | 
| `serial` | `number` | 否 | 流水號 | 

#### 呼叫範例與回傳格式

```
# Python
rest_stock.intraday.quote(symbol="2330")

```

```
// Node.js
await restClient.intraday.quote({ symbol: "2330" });

```

```
{
  "date": "2023-05-29",
  "type": "EQUITY",
  "exchange": "TWSE",
  "market": "TSE",
  "symbol": "2330",
  "name": "台積電",
  "referencePrice": 566,
  "previousClose": 566,
  "openPrice": 574,
  "openTime": 1685322000049353,
  "highPrice": 574,
  "highTime": 1685322000049353,
  "lowPrice": 564,
  "lowTime": 1685327142152580,
  "closePrice": 568,
  "closeTime": 1685338200000000,
  "avgPrice": 568.77,
  "change": 2,
  "changePercent": 0.35,
  "amplitude": 1.77,
  "lastPrice": 568,
  "lastSize": 4778,
  "bids": [
    { "price": 567, "size": 87 },
    { "price": 566, "size": 2454 },
    { "price": 565, "size": 611 },
    { "price": 564, "size": 609 },
    { "price": 563, "size": 636 }
  ],
  "asks": [
    { "price": 568, "size": 800 },
    { "price": 569, "size": 806 },
    { "price": 570, "size": 3643 },
    { "price": 571, "size": 1041 },
    { "price": 572, "size": 2052 }
  ],
  "total": {
    "tradeValue": 31019803000,
    "tradeVolume": 54538,
    "tradeVolumeAtBid": 19853,
    "tradeVolumeAtAsk": 27900,
    "transaction": 9530,
    "time": 1685338200000000
  },
  "lastTrade": {
    "bid": 567,
    "ask": 568,
    "price": 568,
    "size": 4778,
    "time": 1685338200000000,
    "serial": 6652422
  },
  "lastTrial": {
    "bid": 567,
    "ask": 568,
    "price": 568,
    "size": 4772,
    "time": 1685338196400347,
    "serial": 6651941
  },
  "isClose": true,
  "serial": 6652422,
  "lastUpdated": 1685338200000000
}

```

### 4. Candles — 取得股票盤中價格 K 線（依代碼查詢）

* **端點**：`GET /intraday/candles/{symbol}`

* **官方說明**：[Intraday Candles](https://www.google.com/search?q=https://www.esunsec.com.tw/trading-platforms/api-trading/docs/market-data/http-api/intraday/candles/)

#### 請求參數（Parameters）

| 參數名稱 | 型別 | 必填 | 說明 | 
| ----- | ----- | ----- | ----- | 
| `symbol` | `string` | 是 | 股票代碼 | 
| `type` | `string` | 否 | Ticker 類型，可選 `oddlot`（盤中零股） | 
| `timeframe` | `string` | 否 | K 線週期，可選：`1`（1分K）、`3`（3分K）、`5`（5分K）、`10`（10分K）、`15`（15分K）、`30`（30分K）、`60`（60分K） | 
| `sort` | `string` | 否 | 時間排序，預設為 `asc`（升冪），可選 `desc`（降冪） | 

#### 回傳欄位（Response）

| 欄位名稱 | 型別 | 必填 | 說明 | 
| ----- | ----- | ----- | ----- | 
| `date` | `string` | 是 | 日期 | 
| `type` | `string` | 是 | Ticker 類型 | 
| `exchange` | `string` | 是 | 交易所 | 
| `market` | `string` | 否 | 市場別 | 
| `symbol` | `string` | 是 | 股票代號 | 
| `timeframe` | `string` | 是 | K 線週期 | 
| `data` | `object[]` | 是 | K 線資料陣列 | 
| `data[].date` | `string` | 否 | K 線時間（ISO 8601 格式） | 
| `data[].open` | `number` | 否 | K 線開盤價 | 
| `data[].high` | `number` | 否 | K 線最高價 | 
| `data[].low` | `number` | 否 | K 線最低價 | 
| `data[].close` | `number` | 否 | K 線收盤價 | 
| `data[].volume` | `number` | 否 | K 線成交量（整股：成交張數；興櫃股票及盤中零股：成交股數；指數：成交金額） | 
| `data[].average` | `number` | 否 | 成交均價 | 

#### 呼叫範例與回傳格式

```
# Python
rest_stock.intraday.candles(symbol="2330", timeframe="1")

```

```
// Node.js
await restClient.intraday.candles({ symbol: "2330", timeframe: "1" });

```

```
{
  "date": "2023-05-29",
  "type": "EQUITY",
  "exchange": "TWSE",
  "market": "TSE",
  "symbol": "2330",
  "data": [
    {
      "date": "2023-05-29T09:00:00.000+08:00",
      "open": 574,
      "high": 574,
      "low": 572,
      "close": 572,
      "volume": 8450,
      "average": 573.82
    }
  ]
}

```

### 5. Trades — 取得股票逐筆成交明細（含盤前/盤後試撮）

* **端點**：`GET /intraday/trades/{symbol}`

* **官方說明**：[Intraday Trades](https://www.google.com/search?q=https://www.esunsec.com.tw/trading-platforms/api-trading/docs/market-data/http-api/intraday/trades/)

#### 請求參數（Parameters）

| 參數名稱 | 型別 | 必填 | 說明 | 
| ----- | ----- | ----- | ----- | 
| `symbol` | `string` | 是 | 股票代碼 | 
| `type` | `string` | 否 | Ticker 類型，可選 `oddlot`（盤中零股） | 
| `offset` | `number` | 否 | 分頁偏移量 | 
| `limit` | `number` | 否 | 單次回傳筆數限制 | 
| `sort` | `string` | 否 | 時間排序，預設為 `desc`（降冪），可選 `asc`（升冪） | 
| `isTrial` | `boolean` | 否 | 查詢試撮明細（如 08:30～09:00 盤前試撮）：設為 `true` | 

#### 回傳欄位（Response）

| 欄位名稱 | 型別 | 必填 | 說明 | 
| ----- | ----- | ----- | ----- | 
| `date` | `string` | 是 | 日期 | 
| `type` | `string` | 是 | Ticker 類型 | 
| `exchange` | `string` | 是 | 交易所 | 
| `market` | `string` | 否 | 市場別 | 
| `symbol` | `string` | 是 | 股票代號 | 
| `data` | `object[]` | 是 | 成交明細陣列 | 
| `data[].bid` | `number` | 否 | 成交買價 | 
| `data[].ask` | `number` | 否 | 成交賣價 | 
| `data[].price` | `number` | 否 | 成交價格 | 
| `data[].size` | `number` | 否 | 成交單量 | 
| `data[].volume` | `number` | 否 | 累計成交總量 | 
| `data[].time` | `number` | 否 | 成交時間（微秒時間戳） | 
| `data[].serial` | `number` | 否 | 成交流水號 | 

#### 呼叫範例與回傳格式

```
# Python（查詢一般逐筆成交）
rest_stock.intraday.trades(symbol="2330")

# Python（專門查詢盤前/盤後試撮明細）
rest_stock.intraday.trades(symbol="2330", isTrial=True)

```

```
// Node.js
await restClient.intraday.trades({ symbol: "2330", isTrial: true });

```

```
{
  "date": "2023-05-29",
  "type": "EQUITY",
  "exchange": "TWSE",
  "market": "TSE",
  "symbol": "2330",
  "data": [
    {
      "bid": 567,
      "ask": 568,
      "price": 568,
      "size": 4778,
      "volume": 54538,
      "time": 1685338200000000,
      "serial": 6652422
    }
  ]
}

```

### 6. Volumes — 取得股票分價量表（依代碼查詢）

* **端點**：`GET /intraday/volumes/{symbol}`

* **官方說明**：[Intraday Volumes](https://www.google.com/search?q=https://www.esunsec.com.tw/trading-platforms/api-trading/docs/market-data/http-api/intraday/volumes/)

#### 請求參數（Parameters）

| 參數名稱 | 型別 | 必填 | 說明 | 
| ----- | ----- | ----- | ----- | 
| `symbol` | `string` | 是 | 股票代碼 | 
| `type` | `string` | 否 | 類型，可選 `oddlot`（盤中零股） | 

#### 回傳欄位（Response）

| 欄位名稱 | 型別 | 必填 | 說明 | 
| ----- | ----- | ----- | ----- | 
| `date` | `string` | 是 | 日期 | 
| `type` | `string` | 是 | Ticker 類型 | 
| `exchange` | `string` | 是 | 交易所 | 
| `market` | `string` | 否 | 市場別 | 
| `symbol` | `string` | 是 | 股票代號 | 
| `data` | `object[]` | 否 | 分價量表陣列 | 
| `data[].price` | `number` | 否 | 成交價 | 
| `data[].volume` | `number` | 否 | 該成交價之累計成交量 | 
| `data[].volumeAtBid` | `number` | 否 | 該成交價之內盤累計成交量 | 
| `data[].volumeAtAsk` | `number` | 否 | 該成交價之外盤累計成交量 | 

> **內外盤計算說明**：`volumeAtAsk + volumeAtBid` 可能不等於 `volume`，原因為計算內外盤比時扣除了開盤第一筆由電腦集中撮合的成交量，以更真實反映盤中買賣盤力道。

#### 呼叫範例與回傳格式

```
# Python
rest_stock.intraday.volumes(symbol="2330")

```

```
// Node.js
await restClient.intraday.volumes({ symbol: "2330" });

```

```
{
  "date": "2023-05-29",
  "type": "EQUITY",
  "exchange": "TWSE",
  "market": "TSE",
  "symbol": "2330",
  "data": [
    {
      "price": 574,
      "volume": 7309,
      "volumeAtBid": 0,
      "volumeAtAsk": 524
    },
    {
      "price": 573,
      "volume": 771,
      "volumeAtBid": 657,
      "volumeAtAsk": 114
    }
  ]
}

```

## 五、Web API — 行情快照（Snapshot）

> **更新頻率**：快照系列 API 系統更新頻率為每 5 秒更新一次。

### 1. Quotes — 取得全市場股票行情快照（依市場別）

* **端點**：`GET /snapshot/quotes/{market}`

* **官方說明**：[Snapshot Quotes](https://www.esunsec.com.tw/trading-platforms/api-trading/docs/market-data/http-api/snapshot/quotes/)

#### 請求參數（Parameters）

| 參數名稱 | 型別 | 必填 | 說明 | 
| ----- | ----- | ----- | ----- | 
| `market` | `string` | 是 | 市場別，可選：`TSE`（上市）、`OTC`（上櫃）、`ESB`（興櫃一般板）、`TIB`（臺灣創新板） | 
| `type` | `string` | 否 | 標的類型，可選：`ALLBUT0999`（包含一般股票、特別股及 ETF）、`COMMONSTOCK`（一般股票） | 

#### 回傳欄位（Response）

| 欄位名稱 | 型別 | 必填 | 說明 | 
| ----- | ----- | ----- | ----- | 
| `date` | `string` | 是 | 日期 | 
| `time` | `string` | 是 | 時間 | 
| `market` | `string` | 是 | 市場別 | 
| `data` | `object[]` | 是 | 快照資料陣列 | 
| `data[].type` | `string` | 否 | Ticker 類型 | 
| `data[].symbol` | `string` | 否 | 股票代碼 | 
| `data[].name` | `string` | 否 | 股票簡稱 | 
| `data[].openPrice` | `number` | 否 | 開盤價 | 
| `data[].highPrice` | `number` | 否 | 最高價 | 
| `data[].lowPrice` | `number` | 否 | 最低價 | 
| `data[].closePrice` | `number` | 否 | 收盤價（最新價） | 
| `data[].change` | `number` | 否 | 漲跌 | 
| `data[].changePercent` | `number` | 否 | 漲跌幅 | 
| `data[].tradeVolume` | `number` | 否 | 成交量 | 
| `data[].tradeValue` | `number` | 否 | 成交金額 | 
| `data[].lastUpdated` | `number` | 否 | 快照時間（微秒時間戳） | 

#### 呼叫範例

```
# Python
rest_stock.snapshot.quotes(market="TSE")

```

```
// Node.js
await restClient.snapshot.quotes({ market: "TSE" });

```

### 2. Movers — 取得股票漲跌幅排行榜（依市場別）

* **端點**：`GET /snapshot/movers/{market}`

* **官方說明**：[Snapshot Movers](https://www.esunsec.com.tw/trading-platforms/api-trading/docs/market-data/http-api/snapshot/movers/)

#### 請求參數（Parameters）

| 參數名稱 | 型別 | 必填 | 說明 | 
| ----- | ----- | ----- | ----- | 
| `market` | `string` | 是 | 市場別，可選：`TSE`、`OTC`、`ESB`、`TIB` | 
| `direction` | `string` | 是 | 漲跌方向，可選：`up`（上漲）、`down`（下跌） | 
| `change` | `string` | 是 | 排序依據，可選：`percent`（漲跌幅）、`value`（漲跌價差） | 
| `type` | `string` | 否 | 標的類型，可選：`ALLBUT0999`、`COMMONSTOCK` | 
| `gt` | `number` | 否 | 篩選大於指定漲跌／漲跌幅的股票 | 
| `gte` | `number` | 否 | 篩選大於或等於指定漲跌／漲跌幅的股票 | 
| `lt` | `number` | 否 | 篩選小於指定漲跌／漲跌幅的股票 | 
| `lte` | `number` | 否 | 篩選小於或等於指定漲跌／漲跌幅的股票 | 
| `eq` | `number` | 否 | 篩選等於指定漲跌／漲跌幅的股票 | 

#### 回傳欄位（Response）

與 `Snapshot Quotes` 相同，根層級額外包含 `"change": "percent" | "value"` 欄位。

#### 呼叫範例

```
# Python
rest_stock.snapshot.movers(market="TSE", direction="up", change="percent")

```

```
// Node.js
await restClient.snapshot.movers({ market: "TSE", direction: "up", change: "percent" });

```

### 3. Actives — 取得股票成交量值排行榜（依市場別）

* **端點**：`GET /snapshot/actives/{market}`

* **官方說明**：[Snapshot Actives](https://www.google.com/search?q=https://www.esunsec.com.tw/trading-platforms/api-trading/docs/market-data/http-api/snapshot/actives/)

#### 請求參數（Parameters）

| 參數名稱 | 型別 | 必填 | 說明 | 
| ----- | ----- | ----- | ----- | 
| `market` | `string` | 是 | 市場別，可選：`TSE`、`OTC`、`ESB`、`TIB` | 
| `trade` | `string` | 是 | 排行依據，可選：`volume`（成交量）、`value`（成交值） | 
| `type` | `string` | 否 | 標的類型，可選：`ALLBUT0999`、`COMMONSTOCK` | 

#### 回傳欄位（Response）

與 `Snapshot Quotes` 相同，根層級額外包含 `"trade": "volume" | "value"` 欄位。

#### 呼叫範例

```
# Python
rest_stock.snapshot.actives(market="TSE", trade="value")

```

```
// Node.js
await restClient.snapshot.actives({ market: "TSE", trade: "value" });

```

## 六、Web API — 歷史行情（Historical）

### 1. Candles — 取得歷史股價 K 線（依代碼查詢）

* **端點**：`GET /historical/candles/{symbol}`

* **官方說明**：[Historical Candles](https://www.esunsec.com.tw/trading-platforms/api-trading/docs/market-data/http-api/historical/candles/)

* **資料回溯與更新規範**：

  * 歷史資料於每交易日盤後 **16:30 前** 完成更新。

  * **日 K 資料涵蓋範圍**：上市櫃個股自 2010 年起、指數自 2015 年起、興櫃自 2024 年起。

  * **分 K 資料涵蓋範圍**：含興櫃自 2023-05-23 起提供。

  * **單次查詢限制**：查詢區間（`from` \~ `to`）單次須 **小於 1 年**，恰好或超過 1 年會回傳 `400 Bad Request`。

#### 請求參數（Parameters）

| 參數名稱 | 型別 | 必填 | 說明 | 
| ----- | ----- | ----- | ----- | 
| `symbol` | `string` | 是 | 股票代碼 | 
| `from` | `string` | 否 | 開始日期（`yyyy-MM-dd`），未帶時預設為 1 個月前 | 
| `to` | `string` | 否 | 結束日期（`yyyy-MM-dd`），未帶時預設為今日 | 
| `timeframe` | `string` | 否 | K 線週期，預設為 `D`（日K）；可選：`1`、`3`、`5`、`10`、`15`、`30`、`60`（分K）、`D`（日K）、`W`（週K）、`M`（月K） | 
| `adjusted` | `string` | 否 | 還原股價啟用，可選 `true`、`false`（僅日／週／月K 有效） | 
| `fields` | `string` | 否 | 欄位選擇，預設為 `open,high,low,close,volume,average`；可額外指定 `turnover`、`change` | 
| `sort` | `string` | 否 | 時間排序，預設為 `desc`（降冪），可選 `asc`（升冪） | 

#### 回傳欄位（Response）

| 欄位名稱 | 型別 | 適用 Timeframe | 說明 | 
| ----- | ----- | ----- | ----- | 
| `symbol` | `string` | — | 股票代碼 | 
| `type` | `string` | — | 證券類型 | 
| `market` | `string` | — | 市場別 | 
| `exchange` | `string` | — | 交易所 | 
| `timeframe` | `string` | — | K 線週期 | 
| `sort` | `string` | — | 排序方向（`desc` 或 `asc`） | 
| `adjusted` | `boolean` | 僅日／週／月K | 是否為還原股價（帶 `adjusted=true` 時回傳） | 
| `data[].date` | `string` | 全部 | 日期（日/週/月K 為 `yyyy-MM-dd`；分K 為 ISO 8601 含時區） | 
| `data[].open` | `number` | 全部 | 開盤價 | 
| `data[].high` | `number` | 全部 | 最高價 | 
| `data[].low` | `number` | 全部 | 最低價 | 
| `data[].close` | `number` | 全部 | 收盤價 | 
| `data[].volume` | `number` | 全部 | 成交量（整股分K 為「張」，整股日/週/月K 為「股」；興櫃皆為「股」；指數分K 為成交金額、日/週/月K 為成交股數） | 
| `data[].average` | `number` | 僅分K | 成交均價（自開盤累計） | 
| `data[].turnover` | `number` | 僅日／週／月K | 成交金額（元） | 
| `data[].change` | `number` | 僅日／週／月K | 漲跌價差 | 

#### 呼叫範例與回傳格式

```
# Python
rest_stock.historical.candles(
    symbol="0050",
    **{"from": "2023-02-06", "to": "2023-02-08", "fields": "open,high,low,close,volume,change"}
)

```

```
// Node.js
await restClient.historical.candles({
  symbol: "0050",
  from: "2023-02-06",
  to: "2023-02-08",
  fields: "open,high,low,close,volume,change"
});

```

```
{
  "symbol": "0050",
  "type": "EQUITY",
  "exchange": "TWSE",
  "market": "TSE",
  "timeframe": "D",
  "data": [
    {
      "date": "2023-02-08",
      "open": 120.1,
      "high": 120.95,
      "low": 120,
      "close": 120.85,
      "volume": 9239321,
      "change": 1.85
    }
  ],
  "sort": "desc"
}

```

### 2. Stats — 取得近 52 週股價統計數據（依代碼查詢）

* **端點**：`GET /historical/stats/{symbol}`

* **官方說明**：[Historical Stats](https://www.esunsec.com.tw/trading-platforms/api-trading/docs/market-data/http-api/historical/stats/)

#### 請求參數（Parameters）

| 參數名稱 | 型別 | 必填 | 說明 | 
| ----- | ----- | ----- | ----- | 
| `symbol` | `string` | 是 | 股票代碼 | 

#### 回傳欄位（Response）

| 欄位名稱 | 型別 | 必填 | 說明 | 
| ----- | ----- | ----- | ----- | 
| `date` | `string` | 是 | 日期 | 
| `type` | `string` | 是 | Ticker 類型 | 
| `exchange` | `string` | 是 | 交易所 | 
| `market` | `string` | 是 | 市場別 | 
| `symbol` | `string` | 是 | 股票代碼 | 
| `name` | `string` | 是 | 股票簡稱 | 
| `openPrice` | `number` | 是 | 最後交易日開盤價 | 
| `highPrice` | `number` | 是 | 最後交易日最高價 | 
| `lowPrice` | `number` | 是 | 最後交易日最低價 | 
| `closePrice` | `number` | 是 | 最後交易日收盤價 | 
| `change` | `number` | 是 | 最後交易日漲跌 | 
| `changePercent` | `number` | 是 | 最後交易日漲跌幅 | 
| `tradeVolume` | `number` | 是 | 最後交易日成交量（股） | 
| `tradeValue` | `number` | 是 | 最後交易日成交金額（元） | 
| `previousClose` | `number` | 是 | 前一交易日收盤價 | 
| `week52High` | `number` | 是 | 近 52 週最高價 | 
| `week52Low` | `number` | 是 | 近 52 週最低價 | 

#### 呼叫範例與回傳格式

```
# Python
rest_stock.historical.stats(symbol="0050")

```

```
// Node.js
await restClient.historical.stats({ symbol: "0050" });

```

```
{
  "date": "2023-02-09",
  "type": "EQUITY",
  "exchange": "TWSE",
  "market": "TSE",
  "symbol": "0050",
  "name": "元大台灣50",
  "openPrice": 120.5,
  "highPrice": 121,
  "lowPrice": 120.3,
  "closePrice": 120.9,
  "change": 0.05,
  "changePercent": 0.04,
  "tradeVolume": 5032245,
  "tradeValue": 607543546,
  "previousClose": 120.85,
  "week52High": 145.05,
  "week52Low": 96.5
}

```

## 七、WebSocket API — 即時行情串流

> **官方章節**：[WebSocket 開始使用](https://www.esunsec.com.tw/trading-platforms/api-trading/docs/market-data/websocket-api/getting-started)

### 1. 連線初始化、訂閱與取消訂閱

* **Python 完整連線與訂閱範例**：

  ```
  from configparser import ConfigParser
  from esun_marketdata import EsunMarketdata
  
  config = ConfigParser()
  config.read('/path/to/config.ini')
  sdk = EsunMarketdata(config)
  sdk.login()
  
  stock = sdk.websocket_client.stock
  
  def handle_message(message):
      print(message)
  
  stock.on("message", handle_message)
  stock.connect()
  
  # 訂閱頻道（如欲訂閱盤中零股可加入 "intradayOddLot": True）
  stock.subscribe({
      "channel": "trades",
      "symbol": "2330"
  })
  
  # 取消訂閱頻道
  stock.unsubscribe({
      "id": "<CHANNEL_ID>"
  })
  
  ```

* **Node.js 完整連線與訂閱範例**：

  ```
  const { EsunMarketdata } = require("@esun/marketdata");
  
  const sdk = new EsunMarketdata({
    configPath: "/path/to/config.ini",
  });
  
  await sdk.login();
  
  const stock = sdk.websocketClient.stock;
  
  stock.on("message", (message) => {
    const data = JSON.parse(message);
    console.log(data);
  });
  
  await stock.connect();
  
  // 訂閱頻道
  stock.subscribe({
    channel: "trades",
    symbol: "2330",
    // intradayOddLot: true // 若要訂閱盤中零股可加入此參數
  });
  
  ```

### 2. 共用訂閱參數（Subscribe Parameters）

| 參數名稱 | 型別 | 必填 | 說明 | 
| ----- | ----- | ----- | ----- | 
| `channel` | `string` | 是 | 訂閱頻道名稱：`trades`、`candles`、`books`、`aggregates`、`indices` | 
| `symbol` | `string` | 是 | 股票或指數代碼（如 `2330`、`IR0001`） | 
| `intradayOddLot` | `boolean` | 否 | `true`：盤中零股；`false`：整股（預設為 `false`） | 

### 3. 各頻道推播規格（Channels）

#### (1) `trades` — 接收最新逐筆成交與試撮資訊

* **官方說明**：[WebSocket Trades](https://www.esunsec.com.tw/trading-platforms/api-trading/docs/market-data/websocket-api/market-data-channels/trades/)

* **推播欄位（`data` 物件）**：

| 欄位名稱 | 型別 | 說明 | 
| ----- | ----- | ----- | 
| `symbol` | `string` | 股票代號 | 
| `type` | `string` | Ticker 類型 | 
| `exchange` | `string` | 交易所 | 
| `market` | `string` | 市場別 | 
| `time` | `number` | 成交時間（微秒時間戳） | 
| `serial` | `number` | 成交流水號 | 
| `bid` | `number` | 成交買價 | 
| `ask` | `number` | 成交賣價 | 
| `price` | `number` | 成交價格 | 
| `size` | `number` | 成交單量 | 
| `volume` | `number` | 累計成交總量 | 
| `isLimitDownPrice` | `boolean` | 最後成交價為跌停價：`true` | 
| `isLimitUpPrice` | `boolean` | 最後成交價為漲停價：`true` | 
| `isLimitDownBid` | `boolean` | 最佳一檔委買跌停價：`true` | 
| `isLimitUpBid` | `boolean` | 最佳一檔委買漲停價：`true` | 
| `isLimitDownAsk` | `boolean` | 最佳一檔委賣跌停價：`true` | 
| `isLimitUpAsk` | `boolean` | 最佳一檔委賣漲停價：`true` | 
| `isLimitDownHalt` | `boolean` | 暫緩撮合且瞬間趨跌：`true` | 
| `isLimitUpHalt` | `boolean` | 暫緩撮合且瞬間趨漲：`true` | 
| `isTrial` | `boolean` | 試撮階段（如 08:30～09:00 盤前試撮）：`true` | 
| `isDelayedOpen` | `boolean` | 延後開盤信號：`true` | 
| `isDelayedClose` | `boolean` | 延後收盤信號：`true` | 
| `isContinuous` | `boolean` | 最後成交為逐筆交易：`true` | 
| `isOpen` | `boolean` | 開盤信號：`true` | 
| `isClose` | `boolean` | 收盤信號：`true` | 

#### (2) `candles` — 接收最新分鐘 K 線

* **官方說明**：[WebSocket Candles](https://www.esunsec.com.tw/trading-platforms/api-trading/docs/market-data/websocket-api/market-data-channels/candles/)

* **推播欄位（`data` 物件）**：

| 欄位名稱 | 型別 | 說明 | 
| ----- | ----- | ----- | 
| `date` | `string` | K 線時間（ISO 8601 格式） | 
| `type` | `string` | Ticker 類型 | 
| `exchange` | `string` | 交易所 | 
| `market` | `string` | 市場別 | 
| `symbol` | `string` | 股票代號 | 
| `open` | `number` | K 線開盤價 | 
| `high` | `number` | K 線最高價 | 
| `low` | `number` | K 線最低價 | 
| `close` | `number` | K 線收盤價 | 
| `volume` | `number` | K 線成交量（整股：張；興櫃及盤中零股：股；指數：金額） | 
| `average` | `number` | 成交均價 | 

#### (3) `books` — 接收最佳五檔委託簿變動

* **官方說明**：[WebSocket Books](https://www.google.com/search?q=https://www.esunsec.com.tw/trading-platforms/api-trading/docs/market-data/websocket-api/market-data-channels/books/)

* **推播欄位（`data` 物件）**：

| 欄位名稱 | 型別 | 說明 | 
| ----- | ----- | ----- | 
| `symbol` | `string` | 股票代號 | 
| `type` | `string` | Ticker 類型 | 
| `exchange` | `string` | 交易所 | 
| `market` | `string` | 市場別 | 
| `bids` | `object[]` | 最佳五檔委買陣列（`bids[].price` 委買價、`bids[].size` 委買量） | 
| `asks` | `object[]` | 最佳五檔委賣陣列（`asks[].price` 委賣價、`asks[].size` 委賣量） | 
| `isTrial` | `boolean` | 試撮階段標記：`true` | 
| `time` | `number` | 更新時間（微秒時間戳） | 

#### (4) `aggregates` — 接收聚合數據與完整統計資訊

* **官方說明**：[WebSocket Aggregates](https://www.esunsec.com.tw/trading-platforms/api-trading/docs/market-data/websocket-api/market-data-channels/aggregates/)

* **推播欄位（`data` 物件）**：
  結構與 REST API `GET /intraday/quote/{symbol}` 完全相同，包含開高低收、均價、漲跌幅、`bids`、`asks`、`total`（累計量值與內外盤）、`lastTrade`、`lastTrial` 以及所有狀態旗標（`isTrial`、`isOpen`、`isClose` 等）。

#### (5) `indices` — 接收最新指數行情資料

* **官方說明**：[WebSocket Indices](https://www.esunsec.com.tw/trading-platforms/api-trading/docs/market-data/websocket-api/market-data-channels/indices/)

* **推播範例**：

  ```
  {
    "event": "data",
    "data": {
      "symbol": "IR0001",
      "type": "INDEX",
      "exchange": "TWSE",
      "index": 35276.44,
      "time": 1686114510000000
    },
    "id": "<CHANNEL_ID>",
    "channel": "indices"
  }
  
  ```

### 4. WebSocket 錯誤處理與事件監聽

> **官方章節**：[WebSocket 錯誤處理](https://www.esunsec.com.tw/trading-platforms/api-trading/docs/market-data/websocket-api/error-handling)

支援監聽 `connect`（連線成功）、`disconnect`（斷線）與 `error`（錯誤）三大事件：

* **Python 事件監聽範例**：

  ```
  def handle_connect():
      print('market data connected')
  
  def handle_disconnect(code, message):
      print(f'market data disconnect: {code}, {message}')
  
  def handle_error(error):
      print(f'market data error: {error}')
  
  stock.on("connect", handle_connect)
  stock.on("disconnect", handle_disconnect)
  stock.on("error", handle_error)
  
  ```

* **Node.js 事件監聽範例**：

  ```
  stock.on("connect", (message) => {
    const connect_msg = JSON.parse(message);
    console.log(connect_msg);
  });
  
  stock.on("disconnect", (message) => {
    console.log(message);
  });
  
  stock.on("error", (message) => {
    const err_msg = JSON.parse(message);
    console.log(err_msg);
  });
  
  ```

## 八、行情 SDK 遷移指南（Migration Guide）

> **官方章節**：[遷移指南](https://www.esunsec.com.tw/trading-platforms/api-trading/docs/market-data/migration_guide)

新版玉山行情 SDK（`esun_marketdata` / `@esun/marketdata`）與舊版 Fugle 行情 SDK（`fugle_marketdata` / `@fugle/marketdata`）的核心差異在於 **身份驗證機制**：

* **舊版（`fugle_marketdata`）**：直接傳入 `api_key` 字串進行驗證。

* **新版（`esun_marketdata`）**：讀取 `config.ini` 設定檔並呼叫 `sdk.login()` 進行驗證。

### 1. Python 遷移對照

```
# --- 舊版 (fugle_marketdata) ---
from fugle_marketdata import RestClient

client = RestClient(api_key='YOUR_API_KEY')
stock = client.stock
stock.intraday.quote(symbol='2330')

# --- 新版 (esun_marketdata) ---
from configparser import ConfigParser
from esun_marketdata import EsunMarketdata

config = ConfigParser()
config.read('/path/to/config.ini')
sdk = EsunMarketdata(config)
sdk.login()

stock = sdk.rest_client.stock
stock.intraday.quote(symbol='2330')

```

### 2. Node.js 遷移對照

```
// --- 舊版 (@fugle/marketdata) ---
const { RestClient } = require('@fugle/marketdata');

const client = new RestClient({ apiKey: 'YOUR_API_KEY' });
client.stock.intraday.quote({ symbol: '2330' })
  .then(data => console.log(data));

// --- 新版 (@esun/marketdata) ---
const { EsunMarketdata } = require('@esun/marketdata');

(async () => {
  const sdk = new EsunMarketdata({
    configPath: './config.ini',
  });

  await sdk.login();

  const stock = sdk.restClient.stock;
  const result = await stock.intraday.quote({ symbol: '2330' });
  console.log(result);
})();

```