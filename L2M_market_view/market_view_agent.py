"""【L2M】整體市場判斷鏈 Agent (market_view)。

依據 D-Plan Schema v4.3 與 D-Plan 撰寫指南 v4.3 規範：
1. 從 data/D-Paln_Output/l1_observations/ 讀取今日 topic == "tw_market" 之大盤觀察資料。
2. 從 data/Datapack/Processed/ 讀取今日 DataPack Processed 快照 (帳戶現金、淨值、部位與合規狀態)。
3. 組裝包含「自訂大盤分析邏輯區塊」之提示詞，呼叫 Gemini Interaction API 生成結構化 JSON。
4. 驗證 schema (Pydantic / Structured Outputs) 並確保 basis_refs 引用合法。
5. 產出成果儲存至 data/D-Paln_Output/l2m_market_view/l2m_market_view_YYYYMMDD.json。

用法::

    python market_view_agent.py                  # 執行今日分析 (預設串流生成)
    python market_view_agent.py --dry-run        # 僅組裝 Prompt 並存成 txt，不呼叫 API
    python market_view_agent.py --no-stream      # 關閉串流印出，改用單次等待
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
# 整合市場趨勢、下行風險、法人資金動向、市場廣度、融資籌碼、持股與部位風險空間。
# 本區塊內容會直接作為 Prompt 的核心分析準則提供給 Gemini。
# =============================================================================
CUSTOM_MARKET_ANALYSIS_LOGIC = """\
### 一、市場趨勢與下行風險（走向研判核心）
1. 趨勢結構：根據收盤價與均線位置辨識市場狀態：
   - 多頭排列 (收盤價 > 20MA > 60MA)：代表短中期價格結構偏強，走向偏向 `risk_on`。
   - 多頭結構短期回檔 (60MA < 收盤價 < 20MA，且 20MA > 60MA)：多頭結構下的修正訊號，走向偏向 `neutral`。
   - 中期結構轉弱 (收盤價 < 60MA)：短中期均線破線下彎，價格結構轉弱，走向偏向 `risk_off`。
   - 其他排列：依實際均線位置客觀判讀，不強行歸類。
2. 價格動能：結合近 20 日報酬率 (taiex_return_20d)，評估價格表現是否支持均線所反映的趨勢。
3. 下行風險：透過近 20 日最大回撤 (taiex_max_drawdown_20d)，評估近期市場已發生的下跌壓力。若報酬為正但期間回撤較深，應注意市場上漲過程可能伴隨較大波動。
4. 綜合判斷：評估價格位置、近期動能與歷史回撤是否一致，辨識市場屬於趨勢延續 (`risk_on`)、短期回檔 (`neutral`) 或轉弱風險 (`risk_off`)。

### 二、法人資金動向（資金面檢視）
1. 同步買超：外資與投信皆為淨買超，視為法人資金方向一致的正向訊號；若價格趨勢與市場廣度也偏強，可提高對市場偏多研判的信心。
2. 同步賣超：外資與投信皆為淨賣超，視為法人資金方向一致的負向訊號；若同時伴隨價格轉弱，應提高對下行風險的關注。
3. 多空分歧：外資與投信資金方向相反時 (例如外資賣超但投信逢低買超)，分析其分歧程度，並結合價格趨勢與市場廣度判斷。
4. 資金與價格背離：當法人資金方向與指數趨勢相反時，評估此現象是否削弱目前市場趨勢的可信度，並將其列為關鍵反向觀察指標。

### 三、市場廣度與融資籌碼（籌碼與結構檢視）
1. 指數廣度背離：若指數近期趨勢偏強，但當日市場漲跌家數比 (market_advance_decline_ratio) 小於 1，應注意市場結構可能失衡、漲勢不夠全面。
2. 籌碼風險警戒：若指數低於 20MA、近期價格動能偏弱，且融資餘額仍增加，應提高對下跌環境中槓桿部位擴張及潛在多殺多賣壓的關注。
3. 交叉驗證：綜合指數趨勢、當日市場廣度與融資變化 (listed_margin_balance_change_5d)，辨識市場是否存在價格、參與程度及槓桿籌碼之間的矛盾訊號。

### 四、持股與整體市場風險（結合 DataPack 部位現狀）
結合目前市場研判及 DataPack 所揭露的現有部位與持股明細：
1. 現有持股是否可能共同受到大盤趨勢轉弱影響。
2. 市場資金撤出、下行壓力或融資籌碼風險，是否可能同時波及多檔持股。
3. 檢視現有持股組合是否存在看似分散，但實質承擔高度相似市場系統性風險的情況。

### 五、現有部位與風險承擔空間（操作姿態評估）
分析目前帳戶部位是否適合當前市場環境：
1. 市場偏多時，現有股票曝險是否已有較高水位？
2. 市場轉弱時，目前現金水位是否已提供足夠的風險緩衝？
3. 若市場訊號分歧，維持現有曝險是否比積極調整更合理？
4. 若持股共同風險升高，是否需要降低整體風險承擔？

### 六、整體操作方向與部位承諾（D-Plan 規範落實）
結合市場研判、DataPack 現有股票曝險、現金水位及持股共同風險，明確宣告當日操作方向與姿態：
1. 本日操作姿態 (stance)：
   - `aggressive` (積極)：偏多環境、勝率高且有充足風險承受空間時採取。
   - `neutral` (中性)：市場訊號分歧、方向不明、維持既有配置或進行板塊輪動再平衡時採取。
   - `defensive` (保守)：市場趨勢轉弱、下行壓力升高或持股面臨共同風險時採取。
2. 淨曝險意圖 (posture.net_exposure_intent)：
   - `increase` (淨買超)：市場趨勢偏強，資金與市場廣度提供支持，且主要風險可控。
     * **特別注意**：若目前帳戶處於競賽第一天全現金狀態 (cash_ratio_tradable = 1.0)，為達成官方合規要求 (持股 20 至 30 檔且現金 <= 25%)，首日必須宣告 `increase` 進行建倉。
   - `hold` (維持曝險/大致持平)：市場訊號分歧、方向不明，或現有部位已符合當前風險環境（淨買賣金額差距在 NAV 2% 容差內）。
   - `reduce` (降低曝險/淨賣超)：市場趨勢轉弱，並有資金、廣度或籌碼的負向訊號支持，尤其既有持股面臨共同風險時。
3. 目標現金比例區間 (posture.target_cash_pct_range)：
   - 必須為 [下限, 上限] 陣列，數值介於 0.0 ~ 0.25 (即 0% ~ 25%) 之間，且下限 <= 上限。
   - 第一天全現金建倉者：建議設為 [0.03, 0.10] 或 [0.05, 0.15]；已建倉者依防禦或再平衡需求設定。

### 七、推論邏輯 (logic) 與反向證據 (counter_evidence) 規範
1. 邏輯過程 (logic)：
   - 必須明確引用 basis_refs 中的事實 ID (例如 O1)，並對應其具體數據 (如指數收盤點位、MA20/MA60 均線、近20日報酬率、最大回撤、法人買賣超、騰落比、融資變化等)。
   - 必須涵蓋從「趨勢與風險結構」->「資金與籌碼」->「DataPack 現有部位與風險空間」->「最終 regime / stance / posture」的完整推論過程。
   - 長度規範：20 ~ 1000 字元。
2. 反向訊號 (counter_evidence)：
   - 綜合各項面向，檢驗是否存在背離訊號 (如資金與價格背離、外資投信多空分歧、指數與市場廣度背離等)，評估主要反向證據對市場判斷的影響。
   - 長度上限 500 字元；若客觀數據全盤檢視後確實無反向訊號，請明確填 null。
"""


# -----------------------------------------------------------------------------
# Prompt 樣板
# -----------------------------------------------------------------------------
PROMPT_TEMPLATE = """\
你是台股專業基金經理人與總體量化策略研究員。
你的主要任務是根據客觀市場觀察，從整體市場趨勢、下行風險、法人資金、市場廣度及籌碼變化等面向，
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

可引用的事實 ID 清單：{available_obs_ids_str}
(注意：basis_refs 必須至少包含大盤事實 ID「{market_obs_id}」，且引用的 ID 必須存在於可用清單內)

## 目前官方帳戶部位與快照 (DataPack Processed)
{datapack_content}

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
1. target_cash_pct_range 的兩個數值必須在 0.0 到 0.25 之間，且下限 <= 上限。
2. logic 內必須提及 {market_obs_id} 並對照實際數值。
3. 若無反向訊號，counter_evidence 請填 null。
"""


# -----------------------------------------------------------------------------
# 資料讀取輔助函式
# -----------------------------------------------------------------------------
def _clean_date_str(date_str: str) -> str:
    """標準化日期字串為 YYYYMMDD。"""
    return re.sub(r"\D", "", date_str)


def find_latest_file(directory: Path, pattern: str) -> Optional[Path]:
    """在指定目錄尋找符合條件且檔名日期最新的一個檔案。"""
    if not directory.exists():
        return None
    matched = list(directory.glob(pattern))
    if not matched:
        return None

    def _extract_date(p: Path) -> str:
        m = re.findall(r"\d{8}", p.name)
        if m:
            return m[-1]
        m2 = re.findall(r"\d{4}-\d{2}-\d{2}", p.name)
        if m2:
            return m2[-1].replace("-", "")
        return ""

    matched.sort(key=lambda p: (_extract_date(p), p.stat().st_mtime), reverse=True)
    return matched[0]


def load_l1_market_observation(
    target_date: str,
    custom_path: Optional[Path] = None,
) -> Tuple[Dict[str, Any], Set[str], Path]:
    """讀取 L1 observations JSON 並擷取 topic == 'tw_market' 之資料。

    Returns:
        (tw_market_item, all_obs_ids, resolved_file_path)
    """
    file_path: Optional[Path] = custom_path
    clean_date = _clean_date_str(target_date)

    if file_path is None:
        # 依序在各 L1 目錄尋找
        for l1_dir in L1_OBS_DIRS:
            if not l1_dir.exists():
                continue
            # 優先找符合指定日期的檔案
            candidates = [
                l1_dir / f"l1_observations_{clean_date}.json",
                l1_dir / f"l1_observations_{target_date}.json",
                l1_dir / f"1_observations_{clean_date}.json",
            ]
            for cand in candidates:
                if cand.exists():
                    file_path = cand
                    break
            if file_path:
                break

            # 若特定日期不存在，找該目錄下最新的 l1_observations_*.json
            latest = find_latest_file(l1_dir, "*observations_*.json")
            if latest:
                file_path = latest
                break

    if file_path is None or not file_path.exists():
        raise FileNotFoundError(
            f"找不到 L1 observations 檔案！搜尋目錄：{[str(d) for d in L1_OBS_DIRS]}，目標日期：{target_date}"
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

    Returns:
        (text_content, resolved_file_path)
    """
    file_path: Optional[Path] = custom_path
    clean_date = _clean_date_str(target_date)

    if file_path is None:
        candidates = [
            DATAPACK_PROCESSED_DIR / f"DataPack_Processed_{clean_date}.md",
            DATAPACK_PROCESSED_DIR / f"DataPack_Processed_{target_date}.md",
        ]
        for cand in candidates:
            if cand.exists():
                file_path = cand
                break

        if file_path is None:
            latest = find_latest_file(DATAPACK_PROCESSED_DIR, "DataPack_Processed_*.md")
            if latest:
                file_path = latest

    if file_path is None or not file_path.exists():
        raise FileNotFoundError(
            f"找不到 DataPack Processed 檔案！搜尋目錄：{DATAPACK_PROCESSED_DIR}，目標日期：{target_date}"
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
    stream: bool = True,
) -> MarketView:
    """呼叫 Gemini Client 進行結構化生成與嚴格檢核。"""
    client = GeminiClient()

    if stream:
        print("\n" + "=" * 65)
        print(" [Gemini 串流模式啟動] 正在即時生成 L2M market_view...")
        print(" (提示：若生成方向有偏離，可隨時按 Ctrl + C 中斷以節省 Token)")
        print("=" * 65 + "\n")

    resp: MarketViewResponse = client.generate_structured(
        prompt=prompt,
        response_model=MarketViewResponse,
        stream=stream,
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
        help="目標日期 (預設為今日台北時間，例如 20261027 或 2026-10-27)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="僅組合提示詞並輸出 txt，不實際呼叫 Gemini API",
    )
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="關閉串流印出，改用一次性等待回傳",
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

    # 決定基準日期
    today = datetime.now(TW_TZ)
    target_date = args.date or today.strftime("%Y%m%d")

    # 1. 讀入資料
    market_obs, all_obs_ids, l1_path = load_l1_market_observation(
        target_date=target_date,
        custom_path=args.l1_path,
    )
    datapack_text, dp_path = load_datapack_processed(
        target_date=target_date,
        custom_path=args.datapack_path,
    )

    # 2. 組裝 Prompt
    prompt = build_prompt(
        target_date=target_date,
        market_obs=market_obs,
        all_obs_ids=all_obs_ids,
        datapack_text=datapack_text,
    )

    print(
        f"[MarketViewAgent] 準備就緒 | "
        f"大盤依據 ID: {market_obs.get('obs_id')} | "
        f"指標數: {len(market_obs.get('values', {}))} | "
        f"Prompt 長度: {len(prompt):,} 字元"
    )

    # 3. Dry-run 模式：只存 Prompt
    if args.dry_run:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        clean_date = _clean_date_str(target_date)
        prompt_file = OUTPUT_DIR / f"{OUTPUT_PREFIX}_prompt_{clean_date}.txt"
        prompt_file.write_text(prompt, encoding="utf-8")
        print(f"[MarketViewAgent] --dry-run 已啟用：Prompt 已輸出至 {prompt_file}")
        return 0

    # 4. 呼叫 Gemini 進行結構化生成
    market_view = generate_market_view(
        prompt=prompt,
        valid_obs_ids=all_obs_ids,
        stream=not args.no_stream,
    )

    # 5. 輸出存檔
    saved_path = save_market_view(market_view, target_date_str=target_date)
    print(f"\n[MarketViewAgent] 成功產出 L2M market_view：{saved_path}")
    print("產出內容預覽：")
    print(json.dumps({"market_view": market_view.model_dump(exclude_none=False)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
