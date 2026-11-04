"""【L3】投資組合決策層 Agent (portfolio_decision_agent)。

依據 D-Plan Schema v4.3 與 D-Plan 撰寫指南 v4.3 規範：
1. 從 data/D-Paln_Output/l2_inferences/ 讀取今日所有個股推論 (I1..In)。
2. 從 data/Datapack/Processed/ 讀取 DataPack 快照並解析昨日既有持股清單與現金比率。
3. 從 data/ETF_Strategy/ 讀取 ETF 投資策略與理念。
4. 從 data/Active_ETF_Holdings/ 讀取主動式 ETF 前 15 大成分股快照作為 Active Share 標竿參考。
5. 從 data/D-Paln_Output/l2m_market_view/ 讀取市場走向 (regime)、操作姿態 (stance) 與目標現金區間。
6. 組裝提示詞，呼叫 Gemini Interaction API 生成 decisions 與 no_trade_decisions 結構化 JSON。
7. 嚴格檢核昨日持股覆蓋度、持股檔數 (20~30檔)、個股權重上限 (個股10%、台積電25%)、現金水位平衡。
8. 產出成果儲存至 data/D-Paln_Output/l3_decisions/l3_decisions_YYYYMMDD.json。

用法::

    python portfolio_decision_agent.py                  # 執行今日決策 (預設串流生成與啟用 Code Execution)
    python portfolio_decision_agent.py --dry-run        # 僅組裝 Prompt 並存成 txt，不呼叫 API
    python portfolio_decision_agent.py --no-stream      # 關閉串流印出，改用單次等待
    python portfolio_decision_agent.py --no-code-exec   # 關閉 Code Execution 功能
    python portfolio_decision_agent.py --date 20261027  # 指定特定日期
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

# 設定 code/ 為匯入路徑 (支援直接以腳本路徑單獨執行)
CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from configs.date_utils import prompt_trade_date  # noqa: E402
from configs.gemini_client import GeminiClient  # noqa: E402
from schemas.dplan_models import (  # noqa: E402
    Decision,
    DecisionsResponse,
    DecisionsResult,
    NoTradeDecision,
    drafts_to_decisions,
)

ROOT = CODE_DIR.parent
DATA_ROOT = ROOT / "data"
L2_INF_DIR = DATA_ROOT / "D-Paln_Output" / "l2_inferences"
L2M_VIEW_DIR = DATA_ROOT / "D-Paln_Output" / "l2m_market_view"
DATAPACK_PROCESSED_DIR = DATA_ROOT / "Datapack" / "Processed"
DATAPACK_RAW_DIR = DATA_ROOT / "Datapack" / "Raw"
ETF_STRATEGY_FILE = DATA_ROOT / "ETF_Strategy" / "etf_strategy.md"
ACTIVE_ETF_DIR = DATA_ROOT / "Active_ETF_Holdings"
OUTPUT_DIR = DATA_ROOT / "D-Paln_Output" / "l3_decisions"
OUTPUT_PREFIX = "l3_decisions"
TW_TZ = timezone(timedelta(hours=8))


# =============================================================================
# 【自訂投資組合決策分析邏輯專區 / Custom Portfolio Decision Logic Section】
# -----------------------------------------------------------------------------
# 依據主動式 ETF 投資理念與競賽合規規範，將 L2 個股推論落實為具體投資組合配置決策。
# 本區塊內容會直接作為 Prompt 的核心分析準則提供給 Gemini。
# =============================================================================
CUSTOM_PORTFOLIO_DECISION_LOGIC = """\
你身為基金決策主管，負責根據已提供的投資推論 (L2 Inferences) 與 DataPack 中的帳戶狀況，判斷當日各檔股票的交易動作、目標配置、資金調度需求，並嚴格遵循主動式 ETF 競賽法規。

請依照下列步驟進行投資組合決策與檢核：

### 一、確認投資推論與帳戶狀況
1. 整理個股推論中提及的股票，辨識：
   - 個股及其目標權重建議。
   - 建議調整的方向與核心原因（成長、轉機、價值、防禦或避險）。
   - 明確建議退出或維持不動的股票。
   - 支持各項判斷的推論 ID (如 I1, I2, ...)。
2. 逐檔交叉比對推論結論與目前持股狀況（DataPack）：
   - 建議持有的股票，目前是否已有部位（前期持股清單）。
   - 目標配置與目前部位之間的差距（計算需加碼或減碼之幅度）。
   - 既有持股是否有明確的調整（異動）或續抱（維持不動）結論。

### 二、判斷當日交易動作與覆蓋原則
依照投資推論與前一交易日的實際持股狀況，逐檔判斷：
1. 建倉 (BUY)：未持有該股票（前期部位為 0），且推論明確建議納入目標組合時，建立全新部位。
   - 注意：若為競賽首日建倉（帳戶為全現金、昨日持股為 0 檔），必須一口氣宣告 20 至 30 檔股票之 BUY 決策，迅速完成建倉合規，此時 no_trade_decisions 必須為空陣列 []。
2. 加碼 (ADD)：已有持股，且需要增加部位以接近推論中的目標配置時，判斷加碼。
3. 減碼 (TRIM)：已有持股，且需要降低部位以接近推論中的目標配置，但仍保留該股票時，判斷減碼。
4. 出清 (SELL_ALL)：前一交易日已有持股，且推論明確建議不再持有該股票時，判斷全數出清（目標權重 target_weight 填 0.0）。
5. 維持不動 (續抱)：前一交易日已有持股，推論建議維持不動或偏離度在無交易帶內，填入 no_trade_decisions。
6. 全覆蓋與互斥原則（非首日適用）：
   - 昨日持有的每一檔股票，在本日規劃中必須恰好分配至 decisions 或 no_trade_decisions 之一，不可遺漏、不可重複、不可兩邊皆填。

### 三、確認目標權重與競賽合規限制
1. 目標權重設定原則：
   - 建倉、加碼及減碼時，應使用投資推論與策略提供的目標權重。
   - 交易動作應與投資推論、目前持股狀況及目標配置完全一致。
2. 投資組合持股檔數限制：
   - 目標投資組合最終持有之股票總檔數（不含全數出清 target_weight=0 者），必須嚴格落在 20 至 30 檔 之間！
3. 單一持股權重上限：
   - 台積電 (2330) 之目標權重不得超過 0.25 (25%)，建議配置 0.05 ~ 0.10 作為核心基石，保留彈性。
   - 除台積電外，其餘任何單一個股之目標權重上限一律為 0.10 (10%)，建議單檔分散在 0.03 ~ 0.05 (3%~5%) 之間。
4. 現金比例、總權重平衡與被動違規防範：
   - 最終所有持有個股之目標權重 target_weight 總和，加上預估剩餘現金比例，必須嚴格等於 1.0 (100%)。
   - 預估剩餘現金比例必須落在今日 L2M market_view 所規範之 target_cash_pct_range 區間內（例如 [0.05, 0.15]，即 5%~15%）。
   - 【重大合規天花板警示：防範市場下跌導致現金比率被動飆升破 25.0%】：
     * 官方合規嚴格限制：每日收盤結算後，現金比率不得高於 25.0%（恰好 25.0% 合規，超過 25.0% 記一次警告，交易整批作廢；累計 3 次警告取消參賽資格）。
     * 被動違規成因：當股市下跌時，庫存持股市值縮水，導致總淨值 NAV 變小（NAV = 現金 + 持股市值）。然而未動用的現金金額 (cash) 是固定不變的，因此現金比率會在盤後結算時「被動飆升」！
     * 具體實例：若目前現金比高達 23.8%，只要整體 NAV 下跌超過 4.8%（或持股市值修正約 6.26%），現金比率就會在盤後被動突破 25.0% 天花板而觸發違規整批作廢！
     * 強制決策防禦指引：
       a. 當昨日 DataPack 顯示現金水位超過 20% (cash_ratio_tradable > 0.20) 時，本日決策必須執行淨買超（買進總額 > 賣出總額），主動降低現金比，拉開與 25% 天花板的安全距離！
       b. 預估剩餘現金 (1.0 - sum(target_weight)) 上限設定在 22% (0.22) 以下即可。因每日皆會重新檢視與交易，且台股單日最大跌幅為 10%，只要現金比控制在 22% 以下，即便遭遇持股全數跌停的極端情況，結算現金比亦在 23.86% 左右，能確保安全避開 25.0% 違規天花板，毋須過度壓縮現金，保留良好操作彈性。

### 四、資金與調度需求 (Funding Logic)
1. 資金調度宣告 (funding_for) 判定規範：
   - 概念定義：只有當賣出股票是為了「補足買進股票的資金缺口」時，才能宣告資金調度；若賣出單純是因看壞、停損或避險，屬於策略型賣出，不得宣告調度。
   - 步驟一：真實資金缺口檢查（前置條件）
     * 請先試算：若完全「不安排該筆賣出」，僅執行預計的買進決策後，帳戶預估現金比率是否會「低於」market_view 所宣告的目標現金區間下限（target_cash_pct_range[0]）？
     * 若預估現金比率 ≥ 下限：代表手頭現金充裕，【資金缺口不存在】。此時所有減碼 (TRIM) 或出清 (SELL_ALL) 決策之 funding_for 欄位【必須強制填寫為 null】，絕不可填寫任何買進決策 ID，否則會觸發系統警示矛盾！
   - 步驟二：資金調度對應（僅在【資金缺口真實存在】時執行）
     * 若預估現金比率 < 下限（資金不足）：代表必須透過賣出股票來籌措買進資金。
     * 請確認哪一項賣出 (TRIM / SELL_ALL) 提供資金，對應支應哪一項買進或加碼 (BUY / ADD) 決策。
     * 在該筆賣出決策之 funding_for 欄位中，填入受支應之買進決策 ID 陣列（例如 ["D2"]）。
     * 若為買進決策（BUY / ADD），funding_for 欄位一律填寫 null。

### 五、主動投資比率（Active Share）嚴格檢查
為確保本投資組合具備鮮明的主動管理超額報酬能力，避免成為被動跟隨指數或複製市售 ETF 的「隱形指數基金」，必須進行 Active Share 檢驗：
1. 將本投資組合的前 15 大持股（依目標權重由大至小排序），分別與市面上的各檔指定主動型 ETF 前 15 大持股進行比較，確認本組合與其他 ETF 不會過於相似。
2. 逐檔計算兩個組合的持股權重差異，並依公式計算 Active Share：
   Active Share = 1/2 × Σ ｜本組合中該股票的權重 − 比較 ETF 中該股票的權重｜
3. 嚴格門檻：與每一檔指定主動型 ETF 比較的 Active Share，都「絕對不得小於 15% (0.15)」！
4. 權重調配指引：
   - 核心權值股（如台積電 2330、聯發科 2454 等）可適度配置，但切忌與市售主動 ETF 之權重配置過於接近。
   - 應積極納入具備獨立基本面轉機、營收高增長、高 ROE、以及非同業重倉的潛力利基股與各產業龍頭，拉開主動權重差距，確保 Active Share 充分高於 15% 門檻。

### 六、決策依據與風險自述 (risk_check) 規範
1. 引用推論支持：
   - 每一項異動決策 (decisions) 都必須在 inference_refs 引用至少 1 筆 L2 個股推論 ID (如 ["I1"])，且推論內容須與股票、交易動作一致。
   - 每一項續抱決策 (no_trade_decisions) 都必須在 reason_refs 引用推論 ID，並於 reason 說明維持不動的原因。
2. 風險檢核 (risk_check) 撰寫要求：
   - 必須以具體、簡短的人讀自述檢核：該股權重是否符合上限（<=10% 或 2330<=25%）、調整後整體組合持股檔數是否落在 [20, 30] 檔、預留現金是否控制在 22% 安全線以下（拉開與 25.0% 天花板的安全距離）等風險指標。
"""


# -----------------------------------------------------------------------------
# Prompt 樣板
# -----------------------------------------------------------------------------
PROMPT_TEMPLATE = """\
你是主動式 ETF 基金經理人與投資組合配置決策主管。
請依據玉山人工智慧公開賽 D-Plan v4.3 規範，結合今日 L2 個股推論 (inferences)、官方帳戶現狀 (DataPack)、
市場大盤姿態 (L2M market_view) 以及主動式 ETF 投資理念，
為今日投資組合產生嚴格結構化的『L3 決策層 (decisions 與 no_trade_decisions)』。

## 今日日期與執行時間
- 交易日基準：{target_date}
- 系統時間：{now}

## ETF 基金投資主題與理念 (ETF Strategy)
{etf_strategy_content}

## 今日市場大盤背景與姿態承諾 (L2M Market View)
{market_view_context}

## 目前官方帳戶部位與昨日持股快照 (DataPack 快照)
{datapack_context}
- 昨日持股代碼清單：{prev_holdings_codes_str}
- 昨日持股檔數：{prev_holdings_count} 檔

## 同業主動式 ETF 前 15 大成分股標竿參考 (Active Share 參考)
以下為市場同業主動式 ETF 重點持股統計：
{active_etf_holdings_summary}

## 今日可用之 L2 個股推論清單 (Inferences 清單)
以下為今日產出的全部個股推論 (共 {inf_count} 筆)：
{inferences_formatted}

可用推論 ID 清單：{available_inf_ids_str}
(注意：每筆決策的 inference_refs / reason_refs 必須至少包含 1 個上述可用 ID，且引用之推論必須直接支持該個股操作)

## 投資組合決策分析邏輯與建置準則
{portfolio_decision_guidelines}

## 輸出格式要求 (嚴格遵循 D-Plan v4.3 JSON 結構)
請產生符合下列結構的 JSON 回應：
{{
  "decisions": [
    {{
      "decision_id": "D1",
      "ticker": "2330",
      "action": "BUY",
      "target_weight": 0.08,
      "inference_refs": ["I1"],
      "risk_check": "新建核心持股 8.0% <= 25% 上限；新增後整體持股 24 檔 ∈ [20, 30]，剩餘現金在 [0.05, 0.15] 區間內",
      "funding_for": null
    }},
    ...
  ],
  "no_trade_decisions": [
    ...
  ]
}}

請特別注意：
1. 【最高合規限制：嚴防市場下跌導致現金比率被動飆升破 25.0% 天花板】：
   - 每日收盤結算後現金比率不得超過 25.0%（超過記一次警告，交易整批作廢；累計 3 次取消資格）。
   - 當股市下跌時持股市值縮水導致總 NAV 變小，固定現金會使現金比率「被動飆升」！例如現金比若為 23.8%，只要整體 NAV 下跌超過 4.8%，現金比率就會被動突破 25.0% 造成整批作廢！
   - 當昨日 DataPack 顯示現金水位超過 20% (cash_ratio_tradable > 0.20) 時，本日決策必須執行淨買超（買進總額 > 賣出總額），主動降低現金比！
   - 預估剩餘現金 (1.0 - sum(target_weight)) 上限控制在 22% (0.22) 以下即可（不必過度壓縮現金至極低水位），台股單日跌幅上限 10%，現金維持在 22% 以下即便遭遇極端跌幅盤後現金比亦在 23.86% 安全線內。
2. 投資組合持股檔數必須落在 20 至 30 檔之間。
3. 首日建倉（昨日持股為 0 檔）：no_trade_decisions 必須為空陣列 []，所有新買進股票全部列在 decisions 且 action 填 "BUY"。
4. 非首日建倉：昨日持有的每檔股票 ({prev_holdings_codes_str}) 必須恰好出現在 decisions 或 no_trade_decisions 之一。
5. 各股 target_weight 之總和加上剩餘現金必須為 1.0 (100%)，且單一股票 <= 0.10 (台積電 2330 <= 0.25)。
6. 每筆決策的 inference_refs 必須真實存在於上方推論 ID 清單中。
7. 程式碼執行功能 (Code Execution)：系統已為你開啟 Python Code Execution 工具。你在決定各檔目標權重 (target_weight)、計算持股總權重、預估剩餘現金 (1.0 - sum(target_weight)) 以及檢核權重上限 (個股<=10%、台積電<=25%) 與持股檔數 (20~30檔) 或其他計算時，請務必主動撰寫並執行 Python 程式碼進行驗證與試算，確保投資組合數據完全合規。
"""


# -----------------------------------------------------------------------------
# 資料讀取輔助函式
# -----------------------------------------------------------------------------
def _clean_date_str(date_str: str) -> str:
    """標準化日期字串為 YYYYMMDD。"""
    return re.sub(r"\D", "", date_str)


def load_l2_inferences(
    target_date: str,
    custom_path: Optional[Path] = None,
) -> Tuple[List[Dict[str, Any]], Set[str], Path]:
    """讀取 L2 inferences JSON 中所有個股推論資料。

    嚴格比對檔名結尾為 _YYYYMMDD.json，若不存在直接報錯。
    """
    clean_date = _clean_date_str(target_date)
    if not clean_date or len(clean_date) != 8:
        raise ValueError(f"target_date 必須為 8 碼 YYYYMMDD 格式: '{target_date}'")

    file_path: Optional[Path] = custom_path
    if file_path is None:
        cand = L2_INF_DIR / f"l2_inferences_{clean_date}.json"
        if cand.exists():
            file_path = cand

    if file_path is None or not file_path.exists():
        raise FileNotFoundError(f"找不到日期為 {clean_date} 的 L2 inferences 檔案！搜尋目錄：{L2_INF_DIR}")

    print(f"[PortfolioDecisionAgent] 載入 L2 inferences: {file_path}")
    raw_content = file_path.read_text(encoding="utf-8")
    data = json.loads(raw_content)

    items = data.get("inferences", data) if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError(f"L2 inferences 格式錯誤，預期為 list，實得: {type(items)}")

    all_inf_ids: Set[str] = set()
    for item in items:
        inf_id = item.get("inf_id")
        if inf_id:
            all_inf_ids.add(inf_id)

    return items, all_inf_ids, file_path


def load_datapack_info(target_date: str) -> Tuple[str, Set[str], int]:
    """讀取 DataPack Processed md 與 Raw json，提取昨日既有持股代碼與檔數。

    嚴格比對檔名日期完全等於 target_date。
    """
    clean_date = _clean_date_str(target_date)
    if not clean_date or len(clean_date) != 8:
        raise ValueError(f"target_date 必須為 8 碼 YYYYMMDD 格式: '{target_date}'")
    iso_date = f"{clean_date[:4]}-{clean_date[4:6]}-{clean_date[6:]}"

    proc_file = DATAPACK_PROCESSED_DIR / f"DataPack_Processed_{clean_date}.md"
    if not proc_file.exists():
        raise FileNotFoundError(f"找不到日期為 {clean_date} 的 DataPack Processed 檔案！{proc_file}")
    datapack_text = proc_file.read_text(encoding="utf-8")

    # 從 Raw JSON 讀取精準 holdings 陣列
    raw_file = None
    if DATAPACK_RAW_DIR.exists():
        for p in DATAPACK_RAW_DIR.glob("*.json"):
            if p.stem.endswith(f"_{clean_date}") or p.stem.endswith(f"_{iso_date}"):
                raw_file = p
                break

    if raw_file is None or not raw_file.exists():
        raise FileNotFoundError(
            f"找不到日期結尾為 {clean_date} (或 {iso_date}) 的 DataPack Raw JSON 檔案！目錄：{DATAPACK_RAW_DIR}"
        )

    prev_holdings_codes: Set[str] = set()
    raw_data = json.loads(raw_file.read_text(encoding="utf-8"))
    holdings = raw_data.get("holdings") or []
    for h in holdings:
        code = str(h.get("code", "")).strip()
        shares = int(h.get("shares", 0))
        if code and shares > 0:
            prev_holdings_codes.add(code)

    return datapack_text, prev_holdings_codes, len(prev_holdings_codes)


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


def load_active_etf_holdings(target_date: str) -> str:
    """讀取同業主動式 ETF 前 15 大成分股快照 (嚴格比對 _YYYYMMDD.parquet)。"""
    clean_date = _clean_date_str(target_date)
    if not clean_date or len(clean_date) != 8:
        raise ValueError(f"target_date 必須為 8 碼 YYYYMMDD 格式: '{target_date}'")

    file_path = ACTIVE_ETF_DIR / f"top_15_constituents_{clean_date}.parquet"
    if not file_path.exists():
        raise FileNotFoundError(f"找不到日期為 {clean_date} 的主動式 ETF 成分股檔案！{file_path}")

    try:
        df = pd.read_parquet(file_path)
        # 篩選 4 位數台股代碼
        tw = df[df["constituent_id"].astype(str).str.match(r"^\d{4}$")].copy()
        if not tw.empty:
            top = (
                tw.groupby(["constituent_id", "constituent_name"])["weight"]
                .agg(["count", "mean"])
                .sort_values("mean", ascending=False)
                .head(15)
            )
            lines = ["| 代號 | 名稱 | 被納入檔數 | 平均權重(%) |", "| :--- | :--- | :--- | :--- |"]
            for (cid, cname), row in top.iterrows():
                lines.append(f"| {cid} | {cname} | {int(row['count'])} 檔 | {row['mean']:.2f}% |")
            return "\n".join(lines)
    except Exception as e:
        print(f"[警告] 解析主動式 ETF 成分股失敗: {e}")
        raise

    return "  (無可用之主動式 ETF 成分股標竿資料)"


def load_optional_market_view(target_date: str) -> str:
    """嘗試載入特定日期的 L2M market_view 作為大盤姿態承諾背景 (嚴格比對 _YYYYMMDD.json)。"""
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
                f"- 目標現金比例區間 [下限, 上限]: {mv.get('posture', {}).get('target_cash_pct_range')}\n"
                f"- 大盤邏輯摘要: {mv.get('logic')}"
            )
        except Exception:
            pass
    return f"  (日期 {clean_date} 尚未產生 L2M market_view 或略過載入)"


def format_inferences_for_prompt(inferences: List[Dict[str, Any]]) -> str:
    """將 L2 inferences 格式化為精簡明瞭的文字清單。"""
    lines = []
    for inf in inferences:
        inf_id = inf.get("inf_id", "")
        prefs = ", ".join(inf.get("premise_refs", []))
        conclusion = inf.get("conclusion", "")
        logic = inf.get("logic", "")
        counter = inf.get("counter_evidence") or "無"
        conf = inf.get("confidence")
        conf_str = f" | 信心度: {conf}" if conf is not None else ""
        lines.append(
            f"### [{inf_id}] 引用: {prefs}{conf_str}\n"
            f"- 結論: {conclusion}\n"
            f"- 邏輯: {logic}\n"
            f"- 反向訊號: {counter}"
        )
    return "\n\n".join(lines)


# -----------------------------------------------------------------------------
# 主生成邏輯
# -----------------------------------------------------------------------------
def build_prompt(
    target_date: str,
    inferences: List[Dict[str, Any]],
    all_inf_ids: Set[str],
    datapack_text: str,
    prev_holdings_codes: Set[str],
    prev_holdings_count: int,
    etf_strategy_content: str,
    active_etf_holdings_summary: str,
    market_view_context: str,
    custom_logic: str = CUSTOM_PORTFOLIO_DECISION_LOGIC,
) -> str:
    """組裝送入 Gemini 的完整投資組合決策提示詞。"""
    now_str = datetime.now(TW_TZ).strftime("%Y-%m-%d %H:%M:%S (%Z)")
    available_inf_ids_str = ", ".join(sorted(all_inf_ids))
    prev_codes_str = ", ".join(sorted(prev_holdings_codes)) if prev_holdings_codes else "無 (首日建倉全現金)"
    inf_formatted = format_inferences_for_prompt(inferences)

    return PROMPT_TEMPLATE.format(
        target_date=target_date,
        now=now_str,
        etf_strategy_content=etf_strategy_content.strip(),
        market_view_context=market_view_context.strip(),
        datapack_context=datapack_text.strip() if datapack_text else "(無可用快照)",
        prev_holdings_codes_str=prev_codes_str,
        prev_holdings_count=prev_holdings_count,
        active_etf_holdings_summary=active_etf_holdings_summary.strip(),
        inf_count=len(inferences),
        inferences_formatted=inf_formatted,
        available_inf_ids_str=available_inf_ids_str,
        portfolio_decision_guidelines=custom_logic.strip(),
    )


def generate_decisions(
    prompt: str,
    valid_inf_ids: Optional[Set[str]] = None,
    prev_holdings_codes: Optional[Set[str]] = None,
    target_date: Optional[str] = None,
    stream: bool = False,
    code_execution: bool = True,
) -> DecisionsResult:
    """呼叫 Gemini Client 進行結構化生成與嚴格檢核。"""
    client = GeminiClient()

    print("\n" + "=" * 65)
    if stream:
        print(" [Gemini 串流模式啟動] 正在即時生成 L3 decisions (投資組合決策)...")
    else:
        print(" [Gemini 批次模式啟動] 正在生成 L3 decisions (啟用完整 Steps 與 Code Execution 監聽)...")
    if code_execution:
        print(" (已啟用 Code Execution 程式碼自動執行工具)")
    print("=" * 65 + "\n")

    resp: DecisionsResponse = client.generate_structured(
        prompt=prompt,
        response_model=DecisionsResponse,
        stream=stream,
        enable_code_execution=code_execution,
    )

    # 輸出 Gemini Usage 統計至 OUTPUT_DIR / "usage" / "l3_usage_YYYYMMDD.json"
    if target_date:
        client.save_usage_metadata(
            output_dir=OUTPUT_DIR,
            stage_prefix="l3",
            target_date=target_date,
        )

    if stream:
        print("\n" + "=" * 65)
        print(" [Gemini 串流完成] 已接收結構化輸出，正在進行 D-Plan v4.3 規格驗證...")
        print("=" * 65 + "\n")

    # 驗證並轉換為最終嚴格 DecisionsResult
    final_result = drafts_to_decisions(
        resp,
        valid_inf_ids=valid_inf_ids,
        prev_holdings_codes=prev_holdings_codes,
    )
    return final_result


def save_decisions(
    decisions_result: DecisionsResult,
    target_date_str: str,
) -> Path:
    """將 decisions 與 no_trade_decisions 依照 D-Plan 規格輸出至 JSON 檔。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    clean_date = _clean_date_str(target_date_str)
    out_path = OUTPUT_DIR / f"{OUTPUT_PREFIX}_{clean_date}.json"

    payload = decisions_result.model_dump(exclude_none=True)

    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out_path


# -----------------------------------------------------------------------------
# CLI 介面
# -----------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="執行 D-Plan L3 投資組合決策 Agent")
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
        "--l2-path",
        type=Path,
        default=None,
        help="手動指定 L2 inferences JSON 檔案路徑",
    )
    args = parser.parse_args(argv)

    # 取得交易日期 (若無命令列參數則在終端機提示輸入)
    target_date = prompt_trade_date(args.date, prompt_text="L3 投資決策 - 交易日期")
    clean_date = _clean_date_str(target_date)

    # 1. 讀入所有資料
    inferences, all_inf_ids, l2_path = load_l2_inferences(
        target_date=clean_date,
        custom_path=args.l2_path,
    )
    datapack_text, prev_holdings_codes, prev_holdings_count = load_datapack_info(clean_date)
    etf_strategy_content = load_etf_strategy()
    active_etf_holdings_summary = load_active_etf_holdings(clean_date)
    market_view_context = load_optional_market_view(clean_date)

    # 2. 組裝 Prompt
    prompt = build_prompt(
        target_date=clean_date,
        inferences=inferences,
        all_inf_ids=all_inf_ids,
        datapack_text=datapack_text,
        prev_holdings_codes=prev_holdings_codes,
        prev_holdings_count=prev_holdings_count,
        etf_strategy_content=etf_strategy_content,
        active_etf_holdings_summary=active_etf_holdings_summary,
        market_view_context=market_view_context,
    )

    print(
        f"[PortfolioDecisionAgent] 準備就緒 | 交易日: {clean_date} | "
        f"L2 推論筆數: {len(inferences)} | "
        f"昨日持股數: {prev_holdings_count} | "
        f"Prompt 長度: {len(prompt):,} 字元"
    )

    # 3. 儲存 Prompt (供排查與回溯)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prompt_file = OUTPUT_DIR / f"{OUTPUT_PREFIX}_prompt_{clean_date}.txt"
    prompt_file.write_text(prompt, encoding="utf-8")
    print(f"[PortfolioDecisionAgent] Prompt 已保存至: {prompt_file}")

    if args.dry_run:
        print(f"[PortfolioDecisionAgent] --dry-run 已啟用：Prompt 已輸出至 {prompt_file}，不呼叫 API。")
        return 0

    # 決定串流模式：若有明確傳入 --stream / --no-stream 則遵照；否則 Code Execution 預設為批次 (False)
    if args.stream:
        use_stream = True
    elif args.no_stream:
        use_stream = False
    else:
        use_stream = False if not args.no_code_exec else True

    # 4. 呼叫 Gemini 進行結構化生成
    decisions_result = generate_decisions(
        prompt=prompt,
        valid_inf_ids=all_inf_ids,
        prev_holdings_codes=prev_holdings_codes,
        target_date=clean_date,
        stream=use_stream,
        code_execution=not args.no_code_exec,
    )

    # 5. 輸出存檔
    saved_path = save_decisions(decisions_result, target_date_str=clean_date)
    print(
        f"\n[PortfolioDecisionAgent] 成功產出 L3 決策：{saved_path} | "
        f"異動決策: {len(decisions_result.decisions)} 筆, 續抱決策: {len(decisions_result.no_trade_decisions)} 筆"
    )
    total_weight = sum(d.target_weight for d in decisions_result.decisions)
    print(f"總目標持股權重: {total_weight:.4f} ({total_weight * 100:.2f}%)，預估剩餘現金: {1.0 - total_weight:.4f} ({(1.0 - total_weight) * 100:.2f}%)")
    print(f"前 2 筆決策預覽：")
    preview = {
        "decisions": [d.model_dump(exclude_none=True) for d in decisions_result.decisions[:2]],
        "no_trade_decisions": [nt.model_dump(exclude_none=True) for nt in decisions_result.no_trade_decisions[:2]],
    }
    print(json.dumps(preview, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
