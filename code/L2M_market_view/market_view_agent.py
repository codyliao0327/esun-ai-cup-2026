"""【L2M】整體市場判斷鏈 Agent (market_view)。

依據 D-Plan Schema v4.3 與 D-Plan 撰寫指南 v4.3 規範：
1. 從 data/D-Paln_Output/l1_observations/ 讀取今日 topic == "tw_market" 之大盤觀察資料。
2. 從 data/Datapack/Processed/ 讀取今日 DataPack Processed 快照 (帳戶現金、淨值、部位與合規狀態)。
3. 組裝包含「自訂大盤分析邏輯區塊」之提示詞，呼叫 Gemini Interaction API 生成結構化 JSON。
4. 驗證 schema (Pydantic / Structured Outputs) 並確保 basis_refs 引用合法。
5. 產出成果儲存至 data/D-Paln_Output/l2m_market_view/l2m_market_view_YYYYMMDD.json。

用法::

    python market_view_agent.py                  # 執行今日分析 (預設串流生成與啟用 Code Execution)
    python market_view_agent.py --dry-run        # 僅組裝 Prompt 並存成 txt，不呼叫 API
    python market_view_agent.py --no-stream      # 關閉串流印出，改用單次等待
    python market_view_agent.py --no-code-exec   # 關閉 Code Execution 功能
    python market_view_agent.py --date 20261027  # 指定特定日期
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# 設定 code/ 為匯入路徑 (支援直接以腳本路徑單獨執行)
CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from configs.date_utils import prompt_trade_date  # noqa: E402
from configs.gemini_client import GeminiClient  # noqa: E402
from schemas.dplan_models import (  # noqa: E402
    MarketView,
    MarketViewDraft,
    MarketViewResponse,
    draft_to_market_view,
)

ROOT = CODE_DIR.parent
DATA_ROOT = ROOT / "data"
L1_OBS_DIRS = [
    DATA_ROOT / "D-Paln_Output" / "l1_observations",
    DATA_ROOT / "D-Paln_Output" / "1_observations",
]
DATAPACK_PROCESSED_DIR = DATA_ROOT / "Datapack" / "Processed"
OUTPUT_DIR = DATA_ROOT / "D-Paln_Output" / "l2m_market_view"
OUTPUT_PREFIX = "l2m_market_view"
TW_TZ = timezone(timedelta(hours=8))


# =============================================================================
# 【自訂大盤分析邏輯專區 / Custom Market Analysis Logic Section】
# -----------------------------------------------------------------------------
# 整合市場趨勢、下行風險、法人資金動向、市場廣度、融資籌碼、產業相對強弱、持股與部位風險空間。
# 本區塊內容會直接作為 Prompt 的核心分析準則提供給 Gemini。
# =============================================================================
CUSTOM_MARKET_ANALYSIS_LOGIC = """\
### 一、市場趨勢與下行風險（走向研判核心）
1. 均線乖離與短中期趨勢結構：
   - 短中期均線乖離率：
     * taiex_vs_ma10_pct（加權指數相對 10 日雙週線乖離率 %）：反映極短線強弱與乖離程度。
     * taiex_vs_ma20_pct（加權指數相對 20 日月線乖離率 %）：反映波段強弱，正值代表指數站穩月線之上，負值代表跌破月線轉弱。
   - 價格區間位置：
     * taiex_range_pos_10d（加權指數 10 日價格區間位置 0%~100%）：0% 位於近 10 日最低點，100% 位於最高點；>80% 代表強勢逼近或刷新高點，<20% 代表弱勢瀕臨破底。
2. 生命線動能與價格表現：
   - 檢視加權報酬指數相對均線之乖離率 (index_vs_ma5_pct, index_vs_ma20_pct)：正值代表指數站在均線之上，負值代表跌破均線。
   - 檢視均線斜率變化率 (ma5_change_3d_pct, ma20_change_5d_pct)：正值代表均線上揚助漲，負值代表均線下彎形成下壓阻力。
   - 搭配近 5 日報酬率 (taiex_return_5d)，評估短線價格動能是否支持均線反映的趨勢。
3. 櫃買指數 (OTC) vs 加權相對強弱（中小型飆股與內資風向球 - 極重要）：
   - otc_vs_taiex_return_5d（櫃買近 5 日報酬率 － 加權近 5 日報酬率，百分點 pp）：
     * 數值 > 0：代表櫃買比大盤強，內資與本土主力積極拉抬中小型題材股，市場熱度高，動能策略勝率極高。
     * 數值 < 0：代表櫃買走勢疲弱落後大盤，中小型股面臨殺盤修正，操作應提高警覺，慎防中小型股補跌。
4. 下行風險：透過近 5 日最大回撤 (taiex_max_drawdown_5d)，評估近期市場已發生的下跌壓力。若短期回撤較深，應注意市場可能伴隨高波動。
5. 綜合判斷：評估均線乖離、區間位置、生命線動能、OTC 相對強弱與歷史回撤，辨識市場走向：趨勢延續 (`risk_on`)、短期回檔 (`neutral`) 或轉弱風險 (`risk_off`)。

### 二、法人資金動向（資金面檢視）
1. 觀察指標：
   - market_foreign_net_buy_5d / market_foreign_net_buy_1d：外資近 5 日累計及昨日淨買賣超金額 (元)。
   - market_trust_net_buy_5d / market_trust_net_buy_1d：投信近 5 日累計及昨日淨買賣超金額 (元)。
2. 同步買超：外資與投信皆為淨買超（特別是昨日與近 5 日方向一致），視為法人資金方向一致的正向訊號；若價格趨勢與市場廣度也偏強，可提高對市場偏多研判的信心。
3. 同步賣超：外資與投信皆為淨賣超，視為法人資金方向一致的負向訊號；若同時伴隨價格轉弱，應提高對下行風險的關注。
4. 多空分歧：外資與投信資金方向相反時 (例如外資賣超但投信逢低買超)，分析其分歧程度，並結合價格趨勢、OTC 內資動能與市場廣度判斷。
5. 資金與價格背離：當法人資金方向與指數趨勢相反時，評估此現象是否削弱目前市場趨勢的可信度，並將其列為關鍵反向觀察指標。

### 三、市場廣度與融資籌碼（籌碼與結構檢視）
1. 全市場均線多空排列家數差 (market_alignment_diff)：
   - (5MA≥10MA≥30MA多頭家數) － (5MA<10MA<30MA空頭家數)。
   - 正值代表多頭排列佔優，負值代表空頭排列佔優；若指數上漲但家數差大幅為負，反映僅權值股拉抬，市場內部廣度其實偏弱；若家數差由負大幅收斂轉正，代表廣泛個股開始落底回升。
2. 指數廣度背離：若指數近期趨勢偏強，但當日市場漲跌家數比 (market_advance_decline_ratio) 小於 1，應注意市場結構可能失衡、漲勢不夠全面。
3. 籌碼風險警戒：若指數低於 20MA、近期價格動能偏弱，且融資餘額仍增加 (listed_margin_balance_change_5d > 0)，應提高對下跌環境中槓桿部位擴張及潛在多殺多賣壓的關注；若融資餘額顯著縮減則為去槓桿融資減肥訊號。
4. 交叉驗證：綜合指數趨勢、全市場多空排列家數差、當日市場廣度與融資變化，辨識市場是否存在價格、參與程度及槓桿籌碼之間的矛盾訊號。

### 四、產業相對強弱（產業結構觀察）
透過各產業 RS 指標觀察盤面結構（詳細指標定義見下方指引）：
1. 自身漲跌與相對強弱：對照產業當日漲跌 (`_return_1d`) 與 RS 變化，區分「實質上漲領漲」、「大盤回檔時的相對抗跌」與「弱勢落後」。
2. 跨期間強弱與動能轉折：比較近 1、3、5 日 RS 變化，辨識趨勢延續或「短線轉強 / 近期仍弱」等分歧；搭配 `_rs_momentum_change` 觀察原領先產業優勢是否維持、原落後產業是否出現改善訊號。
3. 集中度、分化與輪動：結合大盤趨勢與市場廣度，評估強勢是否集中於少數產業或呈現明顯分化，並追蹤領先產業與強弱排名變化作為族群交替輪動線索。

### 五、持股與整體市場風險（結合 DataPack 部位現狀）
結合目前市場研判及 DataPack 所揭露的現有部位與持股明細：
1. 現有持股是否可能共同受到大盤趨勢轉弱影響。
2. 市場資金撤出、下行壓力或融資籌碼風險，是否可能同時波及多檔持股。
3. 檢視現有持股組合是否存在看似分散，但實質承擔高度相似市場系統性風險的情況。
4. 產業強弱曝險：在產業對應資料足夠時，結合現有持股權重，檢視組合是否集中於近期落後大盤或相對優勢減弱的產業，評估風險與輪動機會。

### 六、現有部位與風險承擔空間（操作姿態評估）
分析目前帳戶部位是否適合當前市場環境，並結合 DataPack 的「賽期進度」與「帳戶淨值演變」：
1. 市場偏多時，現有股票曝險是否已有較高水位？
2. 市場轉弱時，目前現金水位是否已提供足夠的風險緩衝？
3. 若市場訊號分歧，維持現有曝險是否比積極調整更合理？
4. 若持股共同風險升高，是否需要降低整體風險承擔？
5. 賽期進度與帳戶節奏檢視：參考 `remaining_trading_days` / `phase`、`cum_return_pct`、`drawdown_from_peak_pct` (MDD)、`nav_return_3d_pct` 與 `consecutive_loss_days`，判斷近期策略是否踩對節奏；若連續虧損天數擴大或接近賽期衝刺期，應於 `logic` 中說明其對今日 `stance` 與 `target_cash_pct_range` 的影響。

### 七、整體操作方向與部位承諾（D-Plan 規範落實）
結合市場研判、DataPack 現有股票曝險、現金水位及持股共同風險，明確宣告當日操作方向與姿態：
1. 【重大合規警戒：市場下跌導致現金比率被動飆升違規】：
   - 官方合規嚴格規定：每日收盤結算後，現金比率不得高於 25.0%（恰好 25.0% 合規，超過 25.0% 記一次警告，交易整批作廢；累計 3 次警告取消參賽資格）。
   - 被動違規機制：當股市下跌時，庫存持股市值縮水，導致總淨值 NAV 變小（NAV = 現金 + 持股市值）。然而未動用的現金金額 (cash) 是固定不變的，因此現金比率會在盤後結算時「被動飆升」！
   - 具體實例：若目前現金比高達 23.8%，只要整體 NAV 下跌超過 4.8%（或持股市值修正約 6.26%），現金比率就會被動突破 25.0% 天花板而觸發違規整批作廢！
   - 強制防禦規則：
     * 當 DataPack 顯示現金水位超過 20% (即 cash_ratio_tradable > 0.20，包含競賽首日全現金 1.0) 時，**必須強制將淨曝險意圖宣告為 `increase`（淨買超）**，主動買進股票降低現金比，拉開與 25% 天花板的安全距離！
     * 在現金水位超過 20% 時，**嚴禁宣告 `hold` 或 `reduce`**！
2. 本日操作姿態 (stance)：
   - `aggressive` (積極)：偏多環境、勝率高且有充足風險承受空間時採取。
   - `neutral` (中性)：市場訊號分歧、方向不明、維持既有配置或進行板塊輪動再平衡時採取。
   - `defensive` (保守)：市場趨勢轉弱、下行壓力升高或持股面臨共同風險時採取。
3. 淨曝險意圖 (posture.net_exposure_intent)：
   - `increase` (淨買超)：市場趨勢偏強，資金與市場廣度提供支持，且主要風險可控。
     * **特別注意**：當目前帳戶現金水位超過 20%（cash_ratio_tradable > 0.20，含首日全現金 1.0），為避免市場回檔造成現金比率被動飆升突破 25% 天花板，無論市場多空，**必須強制宣告 `increase`** 進行積極建倉或加碼。
   - `hold` (維持曝險/大致持平)：市場訊號分歧、方向不明，且現金水位安全 (<= 20%)，或現有部位已符合當前風險環境（淨買賣金額差距在 NAV 2% 容差內），NAV = (Σ 各持股張數 × 1,000 × 當日收盤價) + 現金部位。
   - `reduce` (降低曝險/淨賣超)：市場趨勢轉弱，並有資金、廣度或籌碼的負向訊號支持，且現金水位在安全範圍內（減碼後預估現金比絕不能超過 20%）。
4. 目標現金比例區間 (posture.target_cash_pct_range)：
   - 必須為 [下限, 上限] 陣列，數值介於 0.0 ~ 0.25 (即 0% ~ 25%) 之間，且下限 <= 上限。
   - 【現金上限 22% 安全線】：因每日皆有交易檢視，且台股單日最大跌幅上限為 10%，只要現金比率維持在 22% (0.22) 以下，即便當日持股全部跌停（持股市值縮水 10%），結算時現金比率約為 23.86%，依然完全在 25.0% 合規天花板之內！因此目標現金區間上限建議設定在 0.22 以下（例如 [0.05, 0.20] 或 [0.03, 0.15] 等），不必過度壓低現金，保留操作彈性即可。

### 八、推論邏輯 (logic) 與反向證據 (counter_evidence) 規範
1. 邏輯過程 (logic)：
   - 必須明確引用 basis_refs 中的事實 ID (例如 O1)，並對應其具體數據 (如指數收盤點位、均線乖離率、10日區間位置、OTC 相對強弱、近5日報酬率、最大回撤、法人近5日與昨日買賣超、騰落比、融資變化、關鍵產業 RS 等)。
   - 必須涵蓋「趨勢與風險」->「資金與籌碼」->「產業相對強弱」->「現有部位與風險」->「最終 regime / stance / posture」的完整推論過程；產業部分應說明其支持或削弱目前的大盤判斷，僅挑選最具影響力、變化最明顯的產業說明，不必逐一重述所有產業。
   - 長度規範：20 ~ 1000 字元。
2. 反向訊號 (counter_evidence)：
   - 綜合各項面向，檢驗是否存在背離訊號 (如資金與價格背離、外資投信多空分歧、指數與市場廣度或產業強弱背離等)，評估主要反向證據對市場判斷的影響。
   - 長度上限 500 字元；若客觀數據全盤檢視後確實無反向訊號，請明確填 null。

### 九、最後交易日 (11/27) 績效最佳化原則
- 11/27 為競賽最後一個交易日，交易以當日均價成交，最終 NAV 以收盤價計算。因此，應以預期收盤價與均價的價差作為主要交易依據，而非僅判斷個股漲跌方向。
- 積極買入或加碼預期收盤價高於均價的標的，減碼或退出預期收盤價低於均價的持股。既有持股須評估獲利延續性與回吐風險，所有交易均須考量交易成本，避免無效調倉。
- 在符合競賽規範的前提下，充分運用現金，優先配置於預期淨效益較高的標的，無須為後續交易保留額外現金（設定 `target_cash_pct_range` 與 `net_exposure_intent` 時應賦予充分運用現金之空間，避免不必要地保留過高現金水位），以最大化最終 NAV 為目標。
- 本原則優先於一般投資配置及停利停損邏輯，但不得違反競賽規範。
"""


# -----------------------------------------------------------------------------
# Prompt 樣板
# -----------------------------------------------------------------------------
PROMPT_TEMPLATE = """\
你是台股專業基金經理人與總體量化策略研究員。
你的主要任務是根據客觀市場觀察，從整體市場趨勢、下行風險、法人資金、市場廣度、籌碼變化及產業相對強弱等面向，
研判目前台股的上市股市票場環境與主要風險，並依據玉山人工智慧公開賽 D-Plan v4.3 規範，
為投資組合產生今日嚴格結構化的『L2M 整體市場判斷鏈 (market_view)』。

## 今日日期與執行時間
- 交易日基準：{target_date}
- 系統時間：{now}

## 可引用的市場級事實依據 (Observations)
以下為從今日 L1 資訊層擷取的「大盤數據事實 (tw_market)」：
- 事實 ID: {market_obs_id}
- 標題分類: {market_topic}
- 事實陳述 (Statement): {market_statement}
- 詳細數值清單 (Values):
{market_values_formatted}

【補充行情資料】
以下為2026/11/23至2026/11/26的海外市場與期貨行情紀錄。
11/23～11/25採用歷史收盤行情，11/26採用截至台灣時間23:15的最新盤中行情。
### 1. 市場行情與漲跌幅
| 商品 | 11/23 收盤點位 | 11/24 收盤點位 | 11/24 漲跌幅 | 11/25 收盤點位 | 11/25 漲跌幅 | 11/26 盤中點位 | 11/26 漲跌幅 | 補充資訊 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| 費城半導體指數 | 9,588.05 | 8,832.50 | -7.88% | 8,774.86 | -0.65% | 休市 | — | 11/25盤中一度大幅下跌，後續明顯反彈，收盤跌幅大幅收斂 |
| 那斯達克綜合指數 | 24,089.56 | 23,733.54 | -1.48% | 23,585.80 | -0.62% | 休市 | — | 11/25跳空低開後明顯回升，收盤接近當日最高點 |
| 小那斯達克期貨 | 26,845.00 | 26,866.00 | +0.08% | 26,000.50 | -3.22% | 26,295.00 | +1.13% | 11/25明顯下跌，11/26盤中出現反彈，但尚未收復前一日跌幅 |
| 台指期夜盤 | 39,829 | 38,482 | -3.38% | 38,397 | -0.22% | 39,306 | +2.37% | 相較前兩日夜盤收盤點位有所回升，但最新畫面漲跌幅為-0.47% |
### 2. 各期間點位變化率
| 商品 | 11/23→11/24 | 11/24→11/25 | 11/25→11/26 | 11/23→11/25 累積變化率 | 11/23→最新點位累積變化率 |
|---|---:|---:|---:|---:|---:|
| 費城半導體指數 | -7.88% | -0.65% | 休市 | -8.48% | -8.48% |
| 那斯達克綜合指數 | -1.48% | -0.62% | 休市 | -2.09% | -2.09% |
| 小那斯達克期貨 | +0.08% | -3.22% | +1.13% | -3.15% | -2.05% |
| 台指期夜盤 | -3.38% | -0.22% | +2.37% | -3.60% | -1.31% |
註：
- 11/23～11/25採用歷史收盤點位。
- 11/26採用截至台灣時間23:15左右的最新盤中點位。
- 11/26為美國感恩節，費城半導體指數及那斯達克綜合指數休市，最新累積變化率計算至11/25收盤。
- 點位變化率＝（最新點位／基準點位－1）×100%。

【穩市政策補充資訊｜截至2026-11-24】
- 自11/23起，原則上禁止平盤以下放空，特定避險需求除外。
- 借券賣出委託數量上限降至規定基準的1%，最低融券保證金提高至150%。
- 暫停受理認售權證新發行申請，並鼓勵出借人暫停借券。
- 自11/24起，信用交易整戶擔保維持率最低標準由130%降至120%，依公告取消先前相關追繳紀錄且不處分擔保品。

可引用的事實 ID 清單：{available_obs_ids_str}
(注意：basis_refs 必須至少包含大盤事實 ID「{market_obs_id}」，且引用的 ID 必須存在於可用清單內)

## 目前官方帳戶部位與快照 (DataPack Processed)
{datapack_content}

## 技術指標定義與數值含意指引 (供精準解讀與引用)
- `market_alignment_diff`：全市場均線多空排列家數差 (家) ＝ (5MA≥10MA≥30MA多頭家數) － (5MA<10MA<30MA空頭家數)。正值代表多頭排列佔優，負值代表空頭排列佔優 (例如 -1304 代表全市場空頭比多頭多 1304 家)。
- `index_vs_ma5_pct` / `index_vs_ma20_pct`：加權報酬指數相對 5MA / 20MA (生命線) 之乖離率 (%)。正值代表指數站在均線之上，負值代表跌破均線走弱。
- `ma5_change_3d_pct` / `ma20_change_5d_pct`：5MA 近 3 日 / 20MA 近 5 日斜率變化率 (%)。正值代表均線上揚助漲，負值代表均線下彎形成下行壓力。
- `taiex_vs_ma10_pct` / `taiex_vs_ma20_pct`：加權指數相對 10MA / 20MA 之乖離率 (%)。
- `taiex_range_pos_10d`：加權指數近 10 日價格區間位置 (0% ~ 100%)。0% 位於區間最低點，100% 位於最高點。
- `otc_vs_taiex_return_5d`：櫃買指數 (OTC) 近 5 日報酬 － 加權近 5 日報酬 (百分點 pp)。>0 代表內資主力拉抬中小型題材股勝率高；<0 代表中小型股走弱。
- `market_advance_decline_ratio`：全市場股票漲跌家數比 (倍)。>1 代表上漲家數多於下跌家數，<1 代表下跌家數偏多。
- `taiex_return_5d`：加權指數近 5 日報酬率 (%)。
- `taiex_max_drawdown_5d`：加權指數近 5 日最大回撤 (%)，負值表示近期波段高點至低點的最大跌幅。
- `listed_margin_balance_change_5d`：上市融資餘額近 5 日變化率 (%)，負值代表融資減肥去槓桿，正值代表融資持續增加。
- `market_foreign_net_buy_5d` / `market_foreign_net_buy_1d`：市場外資近 5 日累計與昨日單日淨買賣超金額 (元)。
- `market_trust_net_buy_5d` / `market_trust_net_buy_1d`：市場投信近 5 日累計與昨日單日淨買賣超金額 (元)。
- `taiex_close_latest`：最新加權指數收盤點位。
- **上市各產業相對強弱 (RS，其中 RS ＝ 產業收盤點數 ÷ 大盤收盤點數)**：
  - `<產業指數>_return_1d`：該產業指數當日漲跌幅 (%)。
  - `<產業指數>_rs_change_1d` / `<產業指數>_rs_change_3d` / `<產業指數>_rs_change_5d`：該產業近 1 日 / 近 3 日 / 近 5 日 RS 相對大盤強弱變化率 (%)。正值代表該期間表現強於大盤、負值代表弱於大盤。
  - `<產業指數>_rs_momentum_change`：該產業近 3 日 RS 變化率較昨日增減 (百分點 pp ＝ 今日近 3 日 RS 變化率 － 昨日近 3 日 RS 變化率)。正值代表相對強弱動能加速轉強、負值代表動能轉弱。

## 大盤分析邏輯與決策準則
{market_analysis_guidelines}

## 輸出格式要求 (嚴格遵循 D-Plan v4.3 JSON 結構)
請產生符合下列結構的 JSON 回應：
{{
  "market_view": {{
    "basis_refs": ["{market_obs_id}"],
    "logic": "從引用之事實推導到市場走向、操作姿態與部位意圖的推論說明 (20~1000字)",
    "regime": "risk_on" | "neutral" | "risk_off",
    "stance": "aggressive" | "neutral" | "defensive",
    "posture": {{
      "net_exposure_intent": "increase" | "hold" | "reduce",
      "target_cash_pct_range": [0.03, 0.10]
    }},
    "counter_evidence": "與走向研判相反的客觀反向訊號或背離證據 (500字內)；若無則填 null",
    "confidence": 0.0 ~ 1.0 (選填數字)
  }}
}}

請特別注意：
1. 【最高合規天花板防禦】：每日收盤結算後現金比率不得超過 25.0%（超過記一次警告，交易整批作廢；累計 3 次取消資格）。股市下跌時持股市值縮水導致總 NAV 變小，固定現金會使現金比率「被動飆升」！因每日皆會交易且台股單日跌幅上限為 10%，現金維持在 22% 以下即可確保即便遭遇極端跌幅，盤後現金比仍安全落在 23.86% 內。因此：
   - 當 DataPack 顯示現金水位超過 20% (cash_ratio_tradable > 0.20) 時，**必須強制將 net_exposure_intent 宣告為 "increase"（淨買超）**，主動降低現金比率拉開安全距離，**嚴禁宣告 hold 或 reduce**！
   - target_cash_pct_range 上限設定在 0.22 (22%) 以下即可（例如 [0.05, 0.20] 等），不必過度限制現金保留比例，兼顧合規安全與配置彈性。
2. target_cash_pct_range 的兩個數值必須在 0.0 到 0.25 之間，且下限 <= 上限。
3. logic 內必須提及 {market_obs_id} 並對照實際數值。
4. 若無反向訊號，counter_evidence 請填 null。
5. net_exposure_intent 若為 hold，需在 logic 內提及淨買賣金額差距在 NAV 2% 容差內，NAV = (Σ 各持股張數 × 1,000 × 當日收盤價) + 現金部位。
6. 程式碼執行功能 (Code Execution)：系統已為你開啟 Python Code Execution 工具。若需計算均線差距、指數報酬率、融資增減比例或目標現金比率試算或其他計算時，請主動撰寫並執行 Python 程式碼，確保所有數據與結論精確無誤。
"""


# -----------------------------------------------------------------------------
# 資料讀取輔助函式
# -----------------------------------------------------------------------------
def _clean_date_str(date_str: str) -> str:
    """標準化日期字串為 YYYYMMDD。"""
    return re.sub(r"\D", "", date_str)


def load_l1_market_observation(
    target_date: str,
    custom_path: Optional[Path] = None,
) -> Tuple[Dict[str, Any], Set[str], Path]:
    """讀取 L1 observations JSON 並擷取 topic == 'tw_market' 之資料。

    嚴格比對檔名結尾為 _YYYYMMDD.json，若不存在直接報錯。
    """
    clean_date = _clean_date_str(target_date)
    if not clean_date or len(clean_date) != 8:
        raise ValueError(f"target_date 必須為 8 碼 YYYYMMDD 格式: '{target_date}'")

    file_path: Optional[Path] = custom_path

    if file_path is None:
        for l1_dir in L1_OBS_DIRS:
            if not l1_dir.exists():
                continue
            cand = l1_dir / f"l1_observations_{clean_date}.json"
            if cand.exists():
                file_path = cand
                break

    if file_path is None or not file_path.exists():
        raise FileNotFoundError(
            f"找不到日期為 {clean_date} 的 L1 observations 檔案！搜尋目錄：{[str(d) for d in L1_OBS_DIRS]}"
        )

    print(f"[MarketViewAgent] 載入 L1 observations: {file_path}")
    raw_content = file_path.read_text(encoding="utf-8")
    data = json.loads(raw_content)

    if not isinstance(data, list):
        raise ValueError(f"L1 observations 檔案格式錯誤，預期為 list，實得: {type(data)}")

    all_obs_ids: Set[str] = set()
    market_obs: Optional[Dict[str, Any]] = None

    for item in data:
        obs_id = item.get("obs_id")
        if obs_id:
            all_obs_ids.add(obs_id)

        topic = str(item.get("topic", "")).strip().lower()
        if topic in ("tw_market", "market", "market_overview") and market_obs is None:
            market_obs = item

    # 若未標記 topic=tw_market，但首筆包含 taiex 相關數據，亦視為大盤
    if market_obs is None and len(data) > 0:
        first = data[0]
        values = first.get("values", {})
        if any("taiex" in k.lower() or "market" in k.lower() for k in values.keys()):
            market_obs = first

    if market_obs is None:
        raise ValueError(f"在 {file_path} 中找不到 topic 為 'tw_market' 的大盤觀察資料！")

    return market_obs, all_obs_ids, file_path


def load_datapack_processed(
    target_date: str,
    custom_path: Optional[Path] = None,
) -> Tuple[str, Path]:
    """讀取 DataPack Processed markdown 檔案內容。

    嚴格比對檔名結尾為 _YYYYMMDD.md，若不存在直接報錯。
    """
    clean_date = _clean_date_str(target_date)
    if not clean_date or len(clean_date) != 8:
        raise ValueError(f"target_date 必須為 8 碼 YYYYMMDD 格式: '{target_date}'")

    file_path: Optional[Path] = custom_path
    if file_path is None:
        cand = DATAPACK_PROCESSED_DIR / f"DataPack_Processed_{clean_date}.md"
        if cand.exists():
            file_path = cand

    if file_path is None or not file_path.exists():
        raise FileNotFoundError(
            f"找不到日期為 {clean_date} 的 DataPack Processed 檔案！搜尋目錄：{DATAPACK_PROCESSED_DIR}"
        )

    print(f"[MarketViewAgent] 載入 DataPack Processed: {file_path}")
    return file_path.read_text(encoding="utf-8"), file_path


def format_market_values(values: Dict[str, Any]) -> str:
    """將大盤數值字典美化為排版清單。"""
    if not values:
        return "  (無具體數值)"
    lines = []
    for k, v in values.items():
        if isinstance(v, float):
            formatted_val = f"{v:,.2f}" if abs(v) >= 1000 else f"{v}"
        else:
            formatted_val = str(v)
        lines.append(f"  - {k}: {formatted_val}")
    return "\n".join(lines)


# -----------------------------------------------------------------------------
# 主生成邏輯
# -----------------------------------------------------------------------------
def build_prompt(
    target_date: str,
    market_obs: Dict[str, Any],
    all_obs_ids: Set[str],
    datapack_text: str,
    custom_logic: str = CUSTOM_MARKET_ANALYSIS_LOGIC,
) -> str:
    """組裝送入 Gemini 的完整提示詞。"""
    now_str = datetime.now(TW_TZ).strftime("%Y-%m-%d %H:%M:%S (%Z)")
    obs_id = market_obs.get("obs_id", "O1")
    topic = market_obs.get("topic", "tw_market")
    statement = market_obs.get("statement", "")
    values = market_obs.get("values", {})

    available_ids_str = ", ".join(sorted(all_obs_ids)) if all_obs_ids else obs_id
    values_str = format_market_values(values)

    return PROMPT_TEMPLATE.format(
        target_date=target_date,
        now=now_str,
        market_obs_id=obs_id,
        market_topic=topic,
        market_statement=statement,
        market_values_formatted=values_str,
        available_obs_ids_str=available_ids_str,
        datapack_content=datapack_text.strip(),
        market_analysis_guidelines=custom_logic.strip(),
    )


def generate_market_view(
    prompt: str,
    valid_obs_ids: Optional[Set[str]] = None,
    target_date: Optional[str] = None,
    stream: bool = False,
    code_execution: bool = True,
    model: Optional[str] = None,
) -> MarketView:
    """呼叫 Gemini Client (LiteLLM Router / stage-l2m) 進行結構化生成與嚴格檢核。"""
    client = GeminiClient(model=model, stage="l2m", target_date=target_date)

    print("\n" + "=" * 65)
    if stream:
        print(" [LiteLLM Router / stage-l2m 串流模式啟動] 正在即時生成 L2M market_view...")
    else:
        print(" [LiteLLM Router / stage-l2m 批次模式啟動] 正在生成 L2M market_view...")
    if code_execution:
        print(" (已啟用 Gemini 原生 Code Execution 沙盒工具)")
    print("=" * 65 + "\n")

    resp: MarketViewResponse = client.generate_structured(
        prompt=prompt,
        response_model=MarketViewResponse,
        stream=stream,
        enable_code_execution=code_execution,
        stage="l2m",
        target_date=target_date,
    )

    # 輸出 LiteLLM Usage 統計至 OUTPUT_DIR / "usage" / "l2m_usage_YYYYMMDD.json"
    if target_date:
        client.save_usage_metadata(
            output_dir=OUTPUT_DIR,
            stage_prefix="l2m",
            target_date=target_date,
        )

    if stream:
        print("\n" + "=" * 65)
        print(" [Gemini 串流完成] 已接收結構化輸出，正在進行 D-Plan v4.3 規格驗證...")
        print("=" * 65 + "\n")

    # 驗證並轉換為最終嚴格 MarketView 模型
    final_market_view = draft_to_market_view(resp.market_view, valid_obs_ids=valid_obs_ids)
    return final_market_view


def save_market_view(
    market_view: MarketView,
    target_date_str: str,
) -> Path:
    """將 market_view 依照 D-Plan 規格輸出至 JSON 檔。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    clean_date = _clean_date_str(target_date_str)
    out_path = OUTPUT_DIR / f"{OUTPUT_PREFIX}_{clean_date}.json"

    payload = {
        "market_view": market_view.model_dump(exclude_none=False)
    }

    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out_path


# -----------------------------------------------------------------------------
# CLI 介面
# -----------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="執行 D-Plan L2M market_view 大盤研判 Agent")
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="目標輸出日期 (格式如 20261027 或 2026-10-27)",
    )
    parser.add_argument(
        "--input-date",
        type=str,
        default=None,
        help="指定讀取輸入資料之日期 (預設同 --date)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="手動指定模型或路由別名 (預設 stage-l2m)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="僅組合提示詞並輸出 txt，不實際呼叫 Gemini API",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="強制開啟串流印出",
    )
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="關閉串流印出，改用一次性等待回傳",
    )
    parser.add_argument(
        "--no-code-exec",
        action="store_true",
        help="關閉 Gemini Python 程式碼自動執行 (Code Execution) 功能 (預設開啟)",
    )
    parser.add_argument(
        "--l1-path",
        type=Path,
        default=None,
        help="手動指定 L1 observations JSON 檔案路徑",
    )
    parser.add_argument(
        "--datapack-path",
        type=Path,
        default=None,
        help="手動指定 DataPack Processed md 檔案路徑",
    )
    args = parser.parse_args(argv)

    # 取得交易日期 (若無命令列參數則在終端機提示輸入)
    target_date = prompt_trade_date(args.date, prompt_text="L2M 市場研判 - 交易日期")
    clean_date = _clean_date_str(target_date)
    input_clean_date = _clean_date_str(args.input_date) if args.input_date else clean_date

    # 1. 讀入資料 (若 target_date 的 L1 檔案存在則優先使用，否則使用 input_clean_date)
    l1_target = clean_date if (L1_OBS_DIRS[0] / f"l1_observations_{clean_date}.json").exists() else input_clean_date
    market_obs, all_obs_ids, l1_path = load_l1_market_observation(
        target_date=l1_target,
        custom_path=args.l1_path,
    )
    datapack_text, dp_path = load_datapack_processed(
        target_date=input_clean_date,
        custom_path=args.datapack_path,
    )

    # 2. 組裝 Prompt
    prompt = build_prompt(
        target_date=clean_date,
        market_obs=market_obs,
        all_obs_ids=all_obs_ids,
        datapack_text=datapack_text,
    )

    print(
        f"[MarketViewAgent] 準備就緒 | 交易日: {clean_date} | "
        f"大盤依據 ID: {market_obs.get('obs_id')} | "
        f"指標數: {len(market_obs.get('values', {}))} | "
        f"Prompt 長度: {len(prompt):,} 字元"
    )

    # 3. 儲存 Prompt (供排查與回溯)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prompt_file = OUTPUT_DIR / f"{OUTPUT_PREFIX}_prompt_{clean_date}.txt"
    prompt_file.write_text(prompt, encoding="utf-8")
    print(f"[MarketViewAgent] Prompt 已保存至: {prompt_file}")

    if args.dry_run:
        print(f"[MarketViewAgent] --dry-run 已啟用：Prompt 已輸出至 {prompt_file}，不呼叫 API。")
        return 0

    # 決定串流模式：若有明確傳入 --stream / --no-stream 則遵照；否則預設為串流 (True)
    if args.stream:
        use_stream = True
    elif args.no_stream:
        use_stream = False
    else:
        use_stream = False if not args.no_code_exec else True

    # 4. 呼叫 LiteLLM Router 進行結構化生成
    market_view = generate_market_view(
        prompt=prompt,
        valid_obs_ids=all_obs_ids,
        target_date=clean_date,
        stream=use_stream,
        code_execution=not args.no_code_exec,
        model=args.model,
    )

    # 5. 輸出存檔
    saved_path = save_market_view(market_view, target_date_str=clean_date)
    print(f"\n[MarketViewAgent] 成功產出 L2M market_view：{saved_path}")
    print("產出內容預覽：")
    print(json.dumps({"market_view": market_view.model_dump(exclude_none=False)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
