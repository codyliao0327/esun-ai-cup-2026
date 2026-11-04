"""【L2】個股推論層 Agent (inferences)。

依據 D-Plan Schema v4.3 與 D-Plan 撰寫指南 v4.3 規範：
1. 從 data/D-Paln_Output/l1_observations/ 讀取今日所有事實觀察資料 (O1 大盤 + 各個股 O2..On)。
2. 若存在，同時讀入今日 L2M 市場研判 (regime, stance, posture) 與 DataPack 部位快照作為總體背景。
3. 組裝包含「自訂個股分析邏輯區塊」之提示詞，呼叫 Gemini Interaction API 生成結構化推論 JSON。
4. 驗證 schema (Pydantic / Structured Outputs) 並確保 premise_refs 引用合法。
5. 產出成果儲存至 data/D-Paln_Output/l2_inferences/l2_inferences_YYYYMMDD.json。

用法::

    python stock_inference_agent.py                  # 執行今日分析 (預設串流生成與啟用 Code Execution)
    python stock_inference_agent.py --dry-run        # 僅組裝 Prompt 並存成 txt，不呼叫 API
    python stock_inference_agent.py --no-stream      # 關閉串流印出，改用單次等待
    python stock_inference_agent.py --no-code-exec   # 關閉 Code Execution 功能
    python stock_inference_agent.py --date 20261027  # 指定特定日期
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
    Inference,
    InferenceDraft,
    InferencesResponse,
    drafts_to_inferences,
)

ROOT = CODE_DIR.parent
DATA_ROOT = ROOT / "data"
L1_OBS_DIRS = [
    DATA_ROOT / "D-Paln_Output" / "l1_observations",
    DATA_ROOT / "D-Paln_Output" / "1_observations",
]
L2M_VIEW_DIR = DATA_ROOT / "D-Paln_Output" / "l2m_market_view"
DATAPACK_PROCESSED_DIR = DATA_ROOT / "Datapack" / "Processed"
OUTPUT_DIR = DATA_ROOT / "D-Paln_Output" / "l2_inferences"
OUTPUT_PREFIX = "l2_inferences"
ETF_STRATEGY_FILE = DATA_ROOT / "ETF_Strategy" / "etf_strategy.md"
TW_TZ = timezone(timedelta(hours=8))


# =============================================================================
# 【自訂個股分析邏輯專區 / Custom Stock Inference Logic Section】
# -----------------------------------------------------------------------------
# 依據主動式 ETF 基金投資理念「兼顧企業品質、營運改善與潛在成長動能」，
# 全面整合個股多維度分析（企業營運、價格趨勢、籌碼量能、市場情緒）與選股組合決策。
# 本區塊內容會直接作為 Prompt 的核心分析準則提供給 Gemini。
# =============================================================================
CUSTOM_STOCK_ANALYSIS_LOGIC = """\
### 【第一階段：個股多維度深入分析】
請依序從下列面向客觀分析各檔股票，整理支持與不利證據，並辨識可能影響短期的機會、風險及不確定性：

1. 企業營運與成長（基本面品質）
   - 獲利能力：檢視最新 ROE (roe_latest)。若 ROE 偏低或為負，應特別關注獲利能力較弱或可能存在虧損之風險；高 ROE 則代表股東權益報酬良好、具備長線護城河。
   - 營收成長：評估最新月營收年增率 (revenue_yoy_latest) 與月增率 (revenue_mom_latest) 的變化，雙成長為營運向上訊號，動能放緩需提防營運轉折。

2. 價格趨勢與相對強弱（技術動能與結構）
   - 報酬表現：比較近 5 日報酬 (return_5d) 與近 20 日報酬 (return_20d)，觀察短期及較長期間的價格方向。
   - 相對大盤：檢視近 20 日相對大盤超額報酬 (excess_return_20d)。若個股絕對報酬為負，但相對報酬為正，可客觀判斷為該期間相對大盤抗跌。
   - 均線結構與動能：結合價格相對 20 日均線位置 (price_vs_ma20) 以及 20 日均線近 5 日升降變化 (ma20_change_5d) 研判價格結構；搭配 14 日 RSI (rsi_14) 與近 10 日報酬波動率 (volatility_10d)，評估近期動能、超買超賣與波動風險。
   - KD 動能與短線轉折 (5, 3, 3)：檢視最新 K 值 (k_5) 與 D 值 (d_5)、K 值近 3 日增減點數 (k_change_3d)、連續高於/低於天數 (kd_above_d_days, kd_below_d_days) 與交叉距今天數 (kd_cross_days_ago_20d)。>80 留意高檔鈍化或過熱拉回，<20 留意超賣低檔轉折或弱勢破底，剛黃金交叉 (kd_cross_days_ago_20d 為 0 或 1 且 K>D) 為關鍵短線轉折訊號。
   - MACD 中期趨勢與強弱 (6, 13, 5)：檢視快慢線差 (macd_dif)、柱狀體 (macd_hist)、柱狀體近 3 日增減 (macd_hist_change_3d)、連續遞增/遞減天數 (macd_hist_increasing_days, macd_hist_decreasing_days) 與交叉距今天數 (macd_cross_days_ago_20d)。柱狀體負值若開始由負轉正或負差距大幅縮小 (macd_hist_change_3d > 0)，代表中期下跌動能衰竭、買盤轉強跡象；柱狀體由正翻負或連續遞減則提示趨勢轉弱。
   - 布林通道波動與軌道型態 (10日, 1.9標準差)：檢視價格在軌道內之相對位置百分比 (bollinger_position_pct)、帶寬 (bollinger_bandwidth_pct)、帶寬近 3 日變化 (bollinger_bandwidth_change_3d_pp)、連續收斂/擴張天數 (bollinger_contraction_days, bollinger_expansion_days)，以及近 60 日帶寬歷史百分位 (bollinger_bandwidth_percentile_60d)。帶寬極度收斂 (歷史百分位低) 往往預示即將發生方向性大波動；價格突破上軌 (bollinger_position_pct > 100) 伴隨通道擴張代表強勢噴出，跌破下軌 (bollinger_position_pct < 0) 則提示加速破底或極度超賣。
   - 交叉判斷：比較上述訊號是否一致，釐清價格表現、相對強弱及技術訊號之間的一致性或分歧。

3. 交易活躍度與法人籌碼（籌碼與流動性）
   - 量價配合：比較近 5 日與近 20 日均量比 (volume_ma5_to_ma20) 及 20 日日均成交值 (amount_ma20)，結合價格方向與成交量變化，觀察量價是否配合（如價漲量增、量縮價穩），並評估其對短期走勢的流動性與延續性意義。
   - 法人動向：觀察外資 (foreign_net_buy_1d, foreign_net_buy_intensity_5d) 與投信 (trust_net_buy_1d, trust_net_buy_intensity_5d) 買賣超方向是否一致；若法人資金流向與價格走勢出現分歧（例如股價跌但法人連續逆勢買超，或股價漲但法人大幅調節），應明確說明該分歧可能影響短期動能之機制。

4. 情緒與討論風向（市場心理與預期）
   - 情緒參考性：依據 CMoney 情緒分數與分布評估市場討論氛圍。樣本數偏低時應適度降低情緒訊號之採信權重。
   - 預期落差：將市場情緒與價格、量能及法人方向交叉比對。討論樂觀不等於實際買盤；若無客觀事件佐證，不得自行推斷存在利多，應留意市場過度期待與實際表現脫鉤的風險。

5. 個股綜合評估
   - 機會與風險：統整有資料支持的企業成長、營運改善、相對強勢或短期動能線索；同時檢視是否出現多個不利訊號並評估其嚴重性。
   - 訊號分歧：各面向結果不一致時，應於 logic 中分別說明支持與不利依據，以及尚待確認的風險。
   - 反面證據與不確定性：評估反面證據、訊號分歧及資料缺漏對該股票判斷的影響，並如實呈現在 counter_evidence 中。

### 【第二階段：選股與組合決策推論】
完成個股分析後，請綜合比較各檔股票，決定哪些股票納入目標投資組合，以及各自的配置比重規劃：

1. 證據導向與綜合取捨
   - 衡量各檔股票在一個月競賽期間內的潛在機會與風險，評估支持與不利證據的相對強度。
   - 不因單一面向做出決定，依據整體分析進行客觀取捨，比較各檔股票的投資吸引力。
   - 評估反面證據與不確定性是否影響選股或配置，說明其如何影響決策的判斷。

2. 比較與取捨（組合角色）
   - 當多檔股票都具備投資機會，而目標投資組合檔數（20～30 檔）有限時，應比較其機會、風險及對整體組合的貢獻。
   - 對建議納入或保留的股票，說明其主要投資機會、風險、組合角色及目標比重的主要考量；對建議避開或調節的股票，說明讓位理由。

3. 產業配置與風險控管
   - 參考股票產業分類，比較同產業內各檔標的之投資機會、風險及組合需求，選擇相對符合投資理念及組合需求的股票。
   - 產業配置不必刻意平均分配；不為了填補產業類別或追求產業分散，而納入缺乏足夠數據支持的股票。

4. 目標權重與資金調度（引導 L3 決策與 L4 委託）
   - 目標比重以 DataPack 中前一日結算淨值 account.nav_tradable 為基準。
   - 目標投資組合須包含 20～30 檔股票，各股目標比重加總與現金目標比重應為 100%（單一個股上限 10%，台積電上限 25%）。
   - 【重大合規警示：嚴防市場下跌導致現金比率被動飆升破 25.0% 天花板】：
     * 每日收盤結算後現金比率不得高於 25.0%（超過記一次警告，交易整批作廢；累計 3 次取消資格）。
     * 當股市下跌時，持股市值縮水導致總 NAV 變小，未動用現金金額固定不變，使現金比率在盤後「被動飆升」！例如現金比 23.8% 時，NAV 僅需下跌 4.8%（持股市值修正約 6.26%）就會被動突破 25.0% 造成違規。
     * 因此當帳戶現金水位超過 20% (cash_ratio_tradable > 0.20) 時，個股推論必須配合大盤 increase 姿態，在結論 (conclusion) 中積極提出建倉或加碼之目標權重，促使現金比率降至 22% 以下（台股單日跌幅上限 10%，現金維持在 22% 以下即便持股跌停盤後現金比亦在 23.86% 內），拉開與 25% 天花板的安全距離。
   - 結論 (conclusion) 中明確提出操作方向與建議權重（例如：「新建倉 2330 作為核心權值，目標權重 5.0%」、「2891 具殖利率與防禦特性，建議納入目標權重 4.5%」等）。

### 【第三階段：D-Plan v4.3 規格要求】
1. premise_refs 引用規範：
   - 每筆推論必須精確引用對應該個股的事實 ID (例如 2330 對應 O8、1301 對應 O2)，必要時可同時引用大盤 O1。
   - 嚴格禁止引用不存在於事實清單中的 ID。
2. 推導過程 (logic)：
   - 必須明確引用實際數據數值 (如收盤價、近20日報酬率、營收年增率、ROE、法人買賣超、均線位置等)，禁止空泛陳述。
   - 推論鏈條須完整：「客觀數據事證」 -> 「多維度分析與分歧檢視」 -> 「走勢與風險研判」 -> 「組合角色與目標權重意向」。
   - 長度規範：20 ~ 1000 字元。
3. 人讀結論 (conclusion)：
   - 簡明總結該個股之操作建議、組合角色與目標權重 (300 字內)。
4. 反向證據 (counter_evidence)：
   - 誠實揭露不利數據、訊號背離、潛在風險或不確定性 (500 字內)；若無反向訊號則明確填 null。
5. 筆數要求：產生所有個股的個股推論，涵蓋投資組合核心關注與欲納入/調整之標的。
"""


# -----------------------------------------------------------------------------
# Prompt 樣板
# -----------------------------------------------------------------------------
PROMPT_TEMPLATE = """\
你是一位主動式 ETF 基金經理人與量化選股策略研究員。
你的主要任務是根據 DataPack、個股客觀事實 (L1 observations) 及市場大盤環境 (L2M market_view)，
基於「兼顧企業品質、營運改善與潛在成長動能」的投資理念，
綜合評估個股在一個月競賽期間的投資機會與風險，
並依據玉山人工智慧公開賽 D-Plan v4.3 規範，
為建立包含 20～30 檔股票及現金的目標投資組合產生嚴格結構化的『L2 個股推論層 (inferences)』。

## 今日日期與執行時間
- 交易日基準：{target_date}
- 系統時間：{now}

## ETF 基金投資主題與理念 (ETF Strategy)
{etf_strategy_content}

## 今日市場大盤背景與姿態 (L2M Market View)
{market_view_context}

## 目前官方帳戶部位與快照 (DataPack 快照)
{datapack_context}

## 今日所有客觀事實觀察資料 (Observations 清單)
以下為從今日 L1 資訊層擷取的全部客觀事實清單 (共 {obs_count} 筆，包含大盤與各個股指標)：
{observations_formatted}

可用事實 ID 清單：{available_obs_ids_str}
(注意：每筆推論的 premise_refs 必須至少包含 1 個上述可用 ID，且引用之事實必須與該個股直接對應)

## 技術指標定義與數值含意指引 (供精準解讀與引用)
### 1. 個股技術面指標
- **KD (5, 3, 3)**：
  - `k_5` / `d_5`：最新 K 值與 D 值 (0~100)。>80 為高檔超買、<20 為低檔超賣。
  - `k_change_3d`：K 值近 3 日增減點數 (正代表快速走高、負代表轉折下彎)。
  - `kd_above_d_days` / `kd_below_d_days`：K 連續高於 / 低於 D 的天數 (>0 代表兩線多/空領先優勢持續天數)。
  - `kd_cross_days_ago_20d`：近 20 日內最近一次交叉距今天數 (0＝今日、1＝前一交易日、-1＝近 20 日未交叉；可配合連續天數確認是黃金交叉或死亡交叉)。
- **MACD (6, 13, 5)**：
  - `macd_dif`：快慢線差 (6EMA － 13EMA)。正值代表短期均線強於中天期均線，負值代表偏弱。
  - `macd_hist`：最新柱狀體 (DIF － Signal)。正值代表 DIF 高於訊號線、負值代表低於訊號線。
  - `macd_hist_change_3d`：柱狀體近 3 日增減。負值變得較不負 (正增加) 代表負差距縮小、動能改善；正值縮小則代表多頭動能減退。
  - `macd_hist_increasing_days` / `macd_hist_decreasing_days`：柱狀體連續遞增 / 連續遞減天數。
  - `macd_cross_days_ago_20d`：近 20 日內 DIF 與 Signal 最近一次交叉距今天數 (0＝今日、-1＝近 20 日未交叉)。
- **布林通道 (10日, 1.9個標準差)**：
  - `bollinger_position_pct`：價格在軌道內之相對位置 (%)。0＝下軌、50＝中軌(10MA)、100＝上軌；>100 代表突破上軌、<0 代表跌破下軌。
  - `bollinger_bandwidth_pct`：標準化帶寬 (%)，數值代表目前相對波動幅度。
  - `bollinger_bandwidth_change_3d_pp`：帶寬近 3 日變化 (百分點 pp，正值代表通道擴張、負值代表通道收斂)。
  - `bollinger_contraction_days` / `bollinger_expansion_days`：帶寬連續收斂 (縮小) / 連續擴張 (放大) 天數。
  - `bollinger_bandwidth_percentile_60d`：目前帶寬在近 60 日的歷史百分位 (0~100%，數值越低代表相較近 60 日波動越極致壓縮、醞釀大變盤)。
- **均線、趨勢與動能指標**：
  - `price_vs_ma20`：最新價相對 20MA (月線) 乖離率 (%)，正值為站上月線、負值為跌破月線。
  - `ma20_change_5d`：20MA (月線) 近 5 日斜率變化率 (%)，反映月線趨勢走向。
  - `return_5d` / `return_20d`：近 5 日 / 近 20 日漲跌幅 (%)。
  - `excess_return_20d`：近 20 日相對大盤超額報酬 (pp，正值代表強於大盤/抗跌領漲，負值代表弱於大盤)。
  - `volume_ma5_to_ma20`：5 日均量 / 20 日均量比值 (倍，>1 代表短線出量轉熱、<1 代表短線量縮整理)。
  - `amount_ma20`：近 20 日日均成交金額 (元)，評估市場流動性。
  - `rsi_14`：14 日相對強弱指標 (0~100)。
  - `volatility_10d`：近 10 日報酬波動率 (%)。

### 2. 個股基本面與籌碼面指標
- `roe_latest`：最新季度股東權益報酬率 (%)。
- `revenue_yoy_latest` / `revenue_mom_latest`：最新月營收年增率 / 月增率 (%)。
- `foreign_net_buy_intensity_5d` / `trust_net_buy_intensity_5d`：外資 / 投信近 5 日買賣超強度 (%) ＝ 5日法人淨買賣超 / 5日總成交量。正值代表法人積極加碼吸籌、負值代表法人持續減碼調節。
- `foreign_net_buy_1d` / `trust_net_buy_1d`：最新交易日外資 / 投信單日買賣超股數 (股)。

### 3. 市場大盤背景指標 (引用 O1 大盤事實時參考)
- `market_alignment_diff`：全市場均線多空排列家數差 (家，>0 多頭佔優，<0 空頭佔優)。
- `index_vs_ma20_pct`：加權報酬指數相對生命線 (20MA) 乖離率 (%)。
- `ma20_change_5d_pct`：生命線 (20MA) 近 5 日斜率變化率 (%)。
- `market_advance_decline_ratio`：全市場漲跌家數比。

## 個股分析邏輯與選股決策準則
{stock_analysis_guidelines}

## 輸出格式要求 (嚴格遵循 D-Plan v4.3 JSON 結構)
請產生符合下列結構的 JSON 回應：
{{
  "inferences": [
    {{
      "inf_id": "I1",
      "premise_refs": ["O2"],
      "logic": "推導過程：引用事實數據 (包含具體數值)、分析多面向表現與分歧、為何成立操作結論 (20~1000字)",
      "conclusion": "簡明結論，明確說明投資機會、組合角色與建議目標權重 (300字內)",
      "counter_evidence": "與本推論相反的客觀反向訊號、背離或不確定性 (500字內)；若無則填 null",
      "confidence": 0.75
    }},
    ...
  ]
}}

請特別注意：
1. 【防範現金比被動飆升破 25% 天花板】：每日結算後現金比率不得超過 25.0%（超過記警告、整批作廢，累計 3 次取消資格）。股市下跌時持股市值縮水會使固定現金比率在盤後「被動飆升」！因每日皆會交易且台股單日跌幅上限為 10%，現金維持在 22% 以下即可確保即便遭遇極端跌幅，盤後現金比仍安全落在 23.86% 內。因此當 DataPack 現金水位超過 20% (cash_ratio_tradable > 0.20) 時，個股推論請積極提出加碼/建倉之目標權重建議，促使現金比維持在 22% 以下安全線，拉開與 25% 天花板的緩衝空間。
2. premise_refs 內引用的每個 ID 必須真實存在於上方事實清單中，未通過檢核將整份退回。
3. logic 內必須提及引用的事實 ID (如 O2, O8) 並列出實際數據對照。
4. 產生所有個股的個股推論，涵蓋投資組合核心關注標的。
5. 若無反向訊號，counter_evidence 請填 null。
6. 程式碼執行功能 (Code Execution)：系統已為你開啟 Python Code Execution 工具。如需計算個股指標、綜合得分、權重試算或對帳驗證或其他計算時，請主動撰寫並執行 Python 程式碼，確保所有數據與結論精確無誤。
"""


# -----------------------------------------------------------------------------
# 資料讀取輔助函式
# -----------------------------------------------------------------------------
def _clean_date_str(date_str: str) -> str:
    """標準化日期字串為 YYYYMMDD。"""
    return re.sub(r"\D", "", date_str)


def load_all_observations(
    target_date: str,
    custom_path: Optional[Path] = None,
) -> Tuple[List[Dict[str, Any]], Set[str], Path]:
    """讀取 L1 observations JSON 中所有事實觀察資料。

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

    print(f"[StockInferenceAgent] 載入 L1 observations: {file_path}")
    raw_content = file_path.read_text(encoding="utf-8")
    data = json.loads(raw_content)

    if not isinstance(data, list):
        raise ValueError(f"L1 observations 檔案格式錯誤，預期為 list，實得: {type(data)}")

    all_obs_ids: Set[str] = set()
    for item in data:
        obs_id = item.get("obs_id")
        if obs_id:
            all_obs_ids.add(obs_id)

    return data, all_obs_ids, file_path


def load_optional_market_view(target_date: str) -> str:
    """嘗試載入特定日期的 L2M market_view 作為總體環境參考 (嚴格比對 _YYYYMMDD.json)。"""
    clean_date = _clean_date_str(target_date)
    cand = L2M_VIEW_DIR / f"l2m_market_view_{clean_date}.json"
    file_path = cand if cand.exists() else None

    if file_path and file_path.exists():
        try:
            content = json.loads(file_path.read_text(encoding="utf-8"))
            mv = content.get("market_view", content)
            return (
                f"- 市場走向 (regime): {mv.get('regime')}\n"
                f"- 操作姿態 (stance): {mv.get('stance')}\n"
                f"- 淨曝險意圖 (net_exposure_intent): {mv.get('posture', {}).get('net_exposure_intent')}\n"
                f"- 目標現金比例區間: {mv.get('posture', {}).get('target_cash_pct_range')}\n"
                f"- 市場研判邏輯摘要: {mv.get('logic')}"
            )
        except Exception:
            pass
    return f"  (日期 {clean_date} 尚未產生 L2M market_view 或略過載入)"


def load_optional_datapack(target_date: str) -> str:
    """嘗試載入特定日期的 DataPack Processed 作為帳戶背景 (嚴格比對 _YYYYMMDD.md)。"""
    clean_date = _clean_date_str(target_date)
    cand = DATAPACK_PROCESSED_DIR / f"DataPack_Processed_{clean_date}.md"
    file_path = cand if cand.exists() else None

    if file_path and file_path.exists():
        try:
            text = file_path.read_text(encoding="utf-8")
            # 擷取關鍵摘要部分避免過長
            lines = text.splitlines()
            # 取前 60 行
            return "\n".join(lines[:60])
        except Exception:
            pass
    return f"  (日期 {clean_date} 無可用之 DataPack 快照)"


def load_etf_strategy() -> str:
    """載入公開說明書宣告之 ETF 投資策略與理念 (若存在)。"""
    if ETF_STRATEGY_FILE.exists():
        try:
            return ETF_STRATEGY_FILE.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    return (
        "| 項目 | 內容 |\n"
        "| :--- | :--- |\n"
        "| **ETF 名稱** | 主動台灣多面向動態配置 |\n"
        "| **ETF 投資主題** | 結合企業基本面、市場趨勢與事件動向的主動式台股配置策略。 |\n"
        "| **ETF 投資理念** | 本基金採取主動式多面向資訊分析策略，綜合評估企業基本面、市場趨勢、資金動向與重要事件等多元構面，審慎發掘台灣上市櫃股票中具備相對投資吸引力的標的。兼顧營運穩健企業與潛在改善機會，在控制風險前提下追求長期資本增值。 |"
    )


def format_single_observation(obs: Dict[str, Any]) -> str:
    """將單筆 observation 格式化為精簡明瞭的文字區塊。"""
    obs_id = obs.get("obs_id", "")
    topic = obs.get("topic", "")
    statement = obs.get("statement", "")
    values = obs.get("values", {})

    # 將數值精簡為單行或多個鍵值
    val_strs = []
    for k, v in values.items():
        if isinstance(v, float):
            val_strs.append(f"{k}={v:,.2f}" if abs(v) >= 1000 else f"{k}={v}")
        else:
            val_strs.append(f"{k}={v}")
    values_line = ", ".join(val_strs) if val_strs else "(無具體數值)"

    return f"### [{obs_id}] {topic}\n- 事實摘要: {statement}\n- 指標數據: {values_line}"


def format_all_observations(observations: List[Dict[str, Any]]) -> str:
    """將所有 observations 格式化為清單文字。"""
    blocks = [format_single_observation(obs) for obs in observations]
    return "\n\n".join(blocks)


# -----------------------------------------------------------------------------
# 主生成邏輯
# -----------------------------------------------------------------------------
def build_prompt(
    target_date: str,
    observations: List[Dict[str, Any]],
    all_obs_ids: Set[str],
    etf_strategy_content: str,
    market_view_context: str,
    datapack_context: str,
    custom_logic: str = CUSTOM_STOCK_ANALYSIS_LOGIC,
) -> str:
    """組裝送入 Gemini 的完整個股推論提示詞。"""
    now_str = datetime.now(TW_TZ).strftime("%Y-%m-%d %H:%M:%S (%Z)")
    available_ids_str = ", ".join(sorted(all_obs_ids))
    obs_formatted = format_all_observations(observations)

    return PROMPT_TEMPLATE.format(
        target_date=target_date,
        now=now_str,
        etf_strategy_content=etf_strategy_content.strip(),
        market_view_context=market_view_context.strip(),
        datapack_context=datapack_context.strip(),
        obs_count=len(observations),
        observations_formatted=obs_formatted,
        available_obs_ids_str=available_ids_str,
        stock_analysis_guidelines=custom_logic.strip(),
    )


def generate_inferences(
    prompt: str,
    valid_obs_ids: Optional[Set[str]] = None,
    target_date: Optional[str] = None,
    stream: bool = False,
    code_execution: bool = True,
) -> List[Inference]:
    """呼叫 Gemini Client 進行結構化生成與嚴格檢核。"""
    client = GeminiClient()

    print("\n" + "=" * 65)
    if stream:
        print(" [Gemini 串流模式啟動] 正在即時生成 L2 inferences (個股推論)...")
    else:
        print(" [Gemini 批次模式啟動] 正在生成 L2 inferences (啟用完整 Steps 與 Code Execution 監聽)...")
    if code_execution:
        print(" (已啟用 Code Execution 程式碼自動執行工具)")
    print("=" * 65 + "\n")

    resp: InferencesResponse = client.generate_structured(
        prompt=prompt,
        response_model=InferencesResponse,
        stream=stream,
        enable_code_execution=code_execution,
    )

    # 輸出 Gemini Usage 統計至 OUTPUT_DIR / "usage" / "l2_usage_YYYYMMDD.json"
    if target_date:
        client.save_usage_metadata(
            output_dir=OUTPUT_DIR,
            stage_prefix="l2",
            target_date=target_date,
        )

    if stream:
        print("\n" + "=" * 65)
        print(" [Gemini 串流完成] 已接收結構化輸出，正在進行 D-Plan v4.3 規格驗證...")
        print("=" * 65 + "\n")

    # 驗證並轉換為最終嚴格 Inference 清單 (依序重編 I1..In)
    final_inferences = drafts_to_inferences(resp, valid_obs_ids=valid_obs_ids)
    return final_inferences


def save_inferences(
    inferences: List[Inference],
    target_date_str: str,
) -> Path:
    """將 inferences 依照 D-Plan 規格輸出至 JSON 檔。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    clean_date = _clean_date_str(target_date_str)
    out_path = OUTPUT_DIR / f"{OUTPUT_PREFIX}_{clean_date}.json"

    payload = {
        "inferences": [inf.model_dump(exclude_none=False) for inf in inferences]
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
    parser = argparse.ArgumentParser(description="執行 D-Plan L2 inferences 個股推論 Agent")
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="目標日期 (格式如 20261027 或 2026-10-27)",
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
    args = parser.parse_args(argv)

    # 取得交易日期 (若無命令列參數則在終端機提示輸入)
    target_date = prompt_trade_date(args.date, prompt_text="L2 個股推論 - 交易日期")
    clean_date = _clean_date_str(target_date)

    # 1. 讀入資料
    observations, all_obs_ids, l1_path = load_all_observations(
        target_date=clean_date,
        custom_path=args.l1_path,
    )
    etf_strategy_content = load_etf_strategy()
    market_view_context = load_optional_market_view(clean_date)
    datapack_context = load_optional_datapack(clean_date)

    # 2. 組裝 Prompt
    prompt = build_prompt(
        target_date=clean_date,
        observations=observations,
        all_obs_ids=all_obs_ids,
        etf_strategy_content=etf_strategy_content,
        market_view_context=market_view_context,
        datapack_context=datapack_context,
    )

    print(
        f"[StockInferenceAgent] 準備就緒 | 交易日: {clean_date} | "
        f"L1 觀察事實筆數: {len(observations)} | "
        f"Prompt 長度: {len(prompt):,} 字元"
    )

    # 3. 儲存 Prompt (供排查與回溯)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prompt_file = OUTPUT_DIR / f"{OUTPUT_PREFIX}_prompt_{clean_date}.txt"
    prompt_file.write_text(prompt, encoding="utf-8")
    print(f"[StockInferenceAgent] Prompt 已保存至: {prompt_file}")

    if args.dry_run:
        print(f"[StockInferenceAgent] --dry-run 已啟用：Prompt 已輸出至 {prompt_file}，不呼叫 API。")
        return 0

    # 決定串流模式：若有明確傳入 --stream / --no-stream 則遵照；否則 Code Execution 預設為批次 (False)
    if args.stream:
        use_stream = True
    elif args.no_stream:
        use_stream = False
    else:
        use_stream = False if not args.no_code_exec else True

    # 4. 呼叫 Gemini 進行結構化生成
    inferences = generate_inferences(
        prompt=prompt,
        valid_obs_ids=all_obs_ids,
        target_date=clean_date,
        stream=use_stream,
        code_execution=not args.no_code_exec,
    )

    # 5. 輸出存檔
    saved_path = save_inferences(inferences, target_date_str=clean_date)
    print(f"\n[StockInferenceAgent] 成功產出 {len(inferences)} 筆 L2 inferences：{saved_path}")
    print(f"前 2 筆推論預覽：")
    preview = {"inferences": [inf.model_dump(exclude_none=False) for inf in inferences[:2]]}
    print(json.dumps(preview, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
