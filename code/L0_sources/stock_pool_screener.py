"""【L0】150 檔上市櫃股票池量化初篩 + LLM Agent 補充篩選模組 (stock_pool_screener.py)。

流程：
  1. 量化指標計算 (Compact Array JSON)：
     - 透過 FinLab API 取得 150 檔（上市 100 + 上櫃 50）截至目標交易日之價量、集保籌碼、融資與本益比／產業資料。
     - 依各指標最大視窗需求（11 共同交易日、2 期集保週資料）回推 35 日曆日，保留各類資料源原始日期且不補值。
     - 輸出 Compact Array JSON 快照至 `data/Stock_Pool/metrics/stock_pool_metrics_<YYYYMMDD>.json`。
  2. 規則一量化初篩：
     - 計算個股與對應市場指數（TAIEX / 上櫃櫃買指數，均不含息）近 5 日、近 10 日相對市場報酬（百分點）。
     - 兩項相對市場報酬皆 > 0 者直接鎖定納入股票池（rule1_selected = true）。
  3. LLM Agent 補充篩選（預設路由 `stage-l0` -> `gemini-4-carbon`，預設啟用 Code Execution）：
     - 將 150 檔完整 Compact Array JSON 輸入給補充篩選 Agent，僅從 `rule1_selected == false` 的候選股中，
       綜合規則一差距、集保大戶／散戶籌碼、融資餘額與槓桿位置、同產業本益比百分位寬鬆補撈遺珠。
  4. 防呆校驗與分層存檔（`data/Stock_Pool/`）：
     - 過濾非法代碼、排除重複規則一標的、去重並校正名稱／市場別後合併為最終股票池。
     - `data/Stock_Pool/stock_list_<YYYYMMDD>.json`：獨立精簡清單（供下游模組直接讀取）。
     - `data/Stock_Pool/screening_result_<YYYYMMDD>.json`：完整篩選結果與量化理由（供後續整合至每日回顧報告）。
     - `data/Stock_Pool/usage/l0_usage_<YYYYMMDD>.json`：LiteLLM 用量紀錄（同步結算至 `usage_history.json`）。

用法::

    python stock_pool_screener.py                          # 執行今日完整篩選（預設串流 + Code Execution）
    python stock_pool_screener.py --date 20261123          # 指定基準日期
    python stock_pool_screener.py --date 20261118 --dry-run # 僅計算 FinLab 指標並產出 Prompt 預覽，不呼叫 LLM
    python stock_pool_screener.py --date 20261123 --use-cached-metrics  # 重讀已算好的指標重跑 LLM
    python stock_pool_screener.py --skip-llm               # 僅輸出規則一篩選結果，不呼叫 LLM
    python stock_pool_screener.py --no-code-exec           # 關閉 Gemini Code Execution
    python stock_pool_screener.py --no-stream              # 關閉串流印出
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

import pandas as pd
from pydantic import BaseModel, Field

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 設定 code/ 為匯入路徑 (支援直接以腳本執行)
CURRENT_DIR = Path(__file__).resolve().parent
CODE_DIR = CURRENT_DIR.parent
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from configs.date_utils import clean_date_str, format_iso_trade_date, prompt_trade_date  # noqa: E402
from configs.gemini_client import GeminiClient  # noqa: E402
from configs.json_utils import format_metric_value, to_compact_json  # noqa: E402

ROOT = CODE_DIR.parent
DATA_ROOT = ROOT / "data"
STOCK_POOL_DIR = DATA_ROOT / "Stock_Pool"
METRICS_DIR = STOCK_POOL_DIR / "metrics"
PROMPTS_DIR = STOCK_POOL_DIR / "prompts"
TW_TZ = timezone(timedelta(hours=8))

# 視窗回推天數：本模組最大需求為「11 個共同交易日（近10日報酬／融資百分位）」與「2 期集保週資料」，
# 加上連假緩衝回推 35 個日曆日（5 週）即可穩定覆蓋 >= 15 個交易日與 >= 3 期週資料，並節省 FinLab 流量。
LOOKBACK_CALENDAR_DAYS = 35


# =============================================================================
# 150 檔上市櫃股票池母體定義 (上市 100 檔 + 上櫃 50 檔)
# =============================================================================
TWSE_STOCKS: Dict[str, str] = {
    "2330": "台積電",     "2454": "聯發科",     "2308": "台達電",
    "2317": "鴻海",       "3711": "日月光投控", "2881": "富邦金",
    "2383": "台光電",     "2303": "聯電",       "2882": "國泰金",
    "3037": "欣興",       "2891": "中信金",     "1303": "南亞",
    "2345": "智邦",       "2382": "廣達",       "2408": "南亞科",
    "7769": "鴻勁",       "2412": "中華電",     "2327": "國巨",
    "6669": "緯穎",       "3017": "奇鋐",       "2885": "元大金",
    "2887": "台新新光金", "2360": "致茂",       "2886": "兆豐金",
    "2059": "川湖",       "6505": "台塑化",     "2884": "玉山金",
    "2880": "華南金",     "2357": "華碩",       "2890": "永豐金",
    "8046": "南電",       "2344": "華邦電",     "3231": "緯創",
    "2892": "第一金",     "3008": "大立光",     "2356": "英業達",
    "2404": "漢唐",       "6515": "穎崴",       "3533": "嘉澤",
    "2313": "華通",       "2337": "旺宏",       "5871": "中租-KY",
    "3044": "健鼎",       "3702": "大聯大",     "1101": "台泥",
    "2409": "友達",       "6239": "力成",       "2609": "陽明",
    "2834": "臺企銀",     "6139": "亞翔",       "2883": "凱基金",
    "3443": "創意",       "3653": "健策",       "2395": "研華",
    "2301": "光寶科",     "6446": "藥華藥",     "4958": "臻鼎-KY",
    "2603": "長榮",       "5880": "合庫金",     "1216": "統一",
    "3045": "台灣大",     "2368": "金像電",     "3665": "貿聯-KY",
    "4904": "遠傳",       "3481": "群創",       "2379": "瑞昱",
    "1301": "台塑",       "1326": "台化",       "3189": "景碩",
    "3034": "聯詠",       "2207": "和泰車",     "2002": "中鋼",
    "2801": "彰銀",       "2449": "京元電子",   "1590": "亞德客-KY",
    "3661": "世芯-KY",    "6770": "力積電",     "3036": "文曄",
    "2615": "萬海",       "2618": "長榮航",     "2912": "統一超",
    "4938": "和碩",       "2376": "技嘉",       "5876": "上海商銀",
    "1519": "華城",       "6415": "矽力-KY",    "6919": "康霈",
    "2324": "仁寶",       "2347": "聯強",       "1504": "東元",
    "7750": "新代",       "1402": "遠東新",     "1605": "華新",
    "2610": "華航",       "6789": "采鈺",       "1802": "台玻",
    "8210": "勤誠",       "2451": "創見",       "2812": "台中銀",
    "2377": "微星",
}

OTC_STOCKS: Dict[str, str] = {
    "5274": "信驊",       "6223": "旺矽",       "6488": "環球晶",
    "8299": "群聯",       "6274": "台燿",       "5347": "世界",
    "3293": "鈊象",       "8069": "元太",       "3529": "力旺",
    "3081": "聯亞",       "3260": "威剛",       "3105": "穩懋",
    "5289": "宜鼎",       "5536": "聖暉",       "5483": "中美晶",
    "6147": "頎邦",       "7734": "印能科技",   "6187": "萬潤",
    "3264": "欣銓",       "3324": "雙鴻",       "6510": "精測",
    "8358": "金居",       "3374": "精材",       "3131": "弘塑",
    "4749": "新應材",     "3491": "昇達科",     "6121": "新普",
    "6548": "長科",       "1785": "光洋科",     "3363": "上詮",
    "7828": "創新服務",   "4979": "華星光",     "6182": "合晶",
    "3163": "波若威",     "3211": "順達",       "4966": "譜瑞-KY",
    "4991": "環宇-KY",    "5903": "全家",       "1815": "富喬",
    "3680": "家登",       "8415": "大國鋼",     "6290": "良維",
    "7751": "竑騰",       "6023": "元大期",     "4772": "台特化",
    "8932": "智通",       "6584": "南俊國際",   "3227": "原相",
    "4123": "晟德",       "3718": "中光電投控",
}


def build_universe_df() -> pd.DataFrame:
    """建構 150 檔上市櫃股票池基礎 DataFrame (stock_id, stock, market)。"""
    twse_df = pd.DataFrame(TWSE_STOCKS.items(), columns=["stock_id", "stock"])
    twse_df["market"] = "twse"
    otc_df = pd.DataFrame(OTC_STOCKS.items(), columns=["stock_id", "stock"])
    otc_df["market"] = "otc"
    df = pd.concat([twse_df, otc_df], ignore_index=True)
    assert len(df) == 150 and df["stock_id"].nunique() == 150, "股票池母體必須為 150 檔不重複個股"
    return df


UNIVERSE_META: Dict[str, Dict[str, str]] = {
    **{sid: {"stock": name, "market": "twse"} for sid, name in TWSE_STOCKS.items()},
    **{sid: {"stock": name, "market": "otc"} for sid, name in OTC_STOCKS.items()},
}


# =============================================================================
# Pydantic Structured Output Schema (Agent 補充篩選輸出結構)
# =============================================================================
class SupplementaryPick(BaseModel):
    """單一檔由 Agent 額外撈回之候選標的。"""

    stock_id: str = Field(description="4碼台股代號（必須嚴格來自 rule1_selected=false 的候選名單）")
    stock: str = Field(description="股票名稱")
    market: Literal["twse", "otc"] = Field(description="市場別 ('twse' 或 'otc')")
    priority_rank: int = Field(ge=1, description="優先關注排序，1 表示最優先")
    primary_angles: List[str] = Field(
        default_factory=list,
        description="主要觸發觀察面向標籤，例如 ['集保籌碼集中', '同業低估值', '融資減肥', '相對報酬逼近翻正']",
    )
    reason: str = Field(
        description="引用具體指標數值與日期背景，簡要說明為何值得額外納入股票池"
    )


class StockPoolScreeningResponse(BaseModel):
    """L0 股票池補充篩選 Agent 完整結構化回覆。"""

    market_context_summary: str = Field(
        description="簡要概述當前大盤與櫃買近5日/10日報酬環境、規則一入選概況與150檔籌碼/估值結構"
    )
    supplementary_picks: List[SupplementaryPick] = Field(
        default_factory=list,
        description="依優先關注程度由高至低排列之額外入選名單；僅包含 rule1_selected=false 之標的；若無合適標的則回傳空陣列",
    )


# =============================================================================
# Step 1 & 2: FinLab 指標計算與規則一初篩 (Compact Array JSON)
# =============================================================================
def _format_date_str(ts: Any) -> str:
    """將 Timestamp / datetime 轉為 YYYY-MM-DD 字串。"""
    s = str(ts).strip()
    return s.split()[0] if " " in s else s[:10]


def _round_metric(val: Any, digits: int = 2) -> Any:
    """將數值四捨五入後轉為標準 int/float，缺值回傳 None。"""
    if val is None or pd.isna(val):
        return None
    try:
        return format_metric_value(round(float(val), digits))
    except (ValueError, TypeError):
        return None


def _calc_return_series(prices: pd.DataFrame, days: int) -> pd.Series:
    """計算截至最後一筆交易日之近 N 個交易日報酬率（%）。"""
    end_price = prices.iloc[-1]
    start_price = prices.iloc[-(days + 1)]
    return (end_price / start_price.replace(0, float("nan")) - 1.0) * 100.0


def fetch_and_compute_metrics(target_date: str) -> Dict[str, Any]:
    """透過 FinLab API 抓取 150 檔資料、計算規則一與三組補充指標，回傳 Compact Array JSON 字典。"""
    import finlab
    from finlab import data

    c_date = clean_date_str(target_date)
    end_iso = format_iso_trade_date(c_date)
    end_ts = pd.Timestamp(end_iso)
    start_iso = (end_ts - timedelta(days=LOOKBACK_CALENDAR_DAYS)).strftime("%Y-%m-%d")

    finlab_api_key = os.getenv("FINLAB_API_KEY", "").strip()
    if finlab_api_key:
        finlab.login(finlab_api_key)
    else:
        finlab.login()

    stocks_df = build_universe_df()
    stock_ids = stocks_df["stock_id"].tolist()

    print(f"[FinLab] 抓取 150 檔資料區間: {start_iso} ~ {end_iso} (回推 {LOOKBACK_CALENDAR_DAYS} 日曆日)...")

    with data.universe(None):
        # 1. 價量與大盤不含息指數 (規則一)
        close_raw = data.get("price:收盤價", start=start_iso, end=end_iso)
        index_close = data.get("stock_index_price:收盤指數", start=start_iso, end=end_iso)
        taiex_series = data.get("taiex_total_index:收盤指數", start=start_iso, end=end_iso)["TAIEX"]
        otc_series = index_close["上櫃櫃買指數:指數"]

        market_price_index = pd.concat({"twse": taiex_series, "otc": otc_series}, axis=1)
        common_dates = close_raw.index.intersection(market_price_index.index).sort_values()
        common_dates = common_dates[common_dates <= end_ts]
        if len(common_dates) < 11:
            raise RuntimeError(
                f"共同交易日不足 11 日（實際僅 {len(common_dates)} 日，區間 {start_iso} ~ {end_iso}），無法計算近 10 日報酬！"
            )

        close = close_raw.reindex(index=common_dates, columns=stock_ids)
        market_price_index = market_price_index.reindex(index=common_dates)
        price_date_str = _format_date_str(common_dates[-1])

        stock_ret_5d = _calc_return_series(close, 5)
        stock_ret_10d = _calc_return_series(close, 10)
        mkt_ret_5d = _calc_return_series(market_price_index, 5)
        mkt_ret_10d = _calc_return_series(market_price_index, 10)

        # 2. 集保持股指標 (週資料)
        holding_over_1000 = data.get("etl:inventory:大於一千張佔比", start=start_iso, end=end_iso)
        holding_under_50 = data.get("etl:inventory:小於五十張佔比", start=start_iso, end=end_iso)
        holder_count = data.get("etl:inventory:全部人數", start=start_iso, end=end_iso)

        holding_over_1000 = holding_over_1000.loc[holding_over_1000.index <= end_ts].reindex(columns=stock_ids)
        holding_under_50 = holding_under_50.loc[holding_under_50.index <= end_ts].reindex(columns=stock_ids)
        holder_count = holder_count.loc[holder_count.index <= end_ts].reindex(columns=stock_ids)

        if not (
            holding_over_1000.index.equals(holding_under_50.index)
            and holding_over_1000.index.equals(holder_count.index)
        ):
            raise RuntimeError("集保三項資料源日期索引不一致！")
        if len(holding_over_1000) < 2:
            raise RuntimeError(f"集保週資料不足 2 期（實際 {len(holding_over_1000)} 期），無法計算近 1 期變化！")

        chip_date_str = _format_date_str(holding_over_1000.index[-1])
        chip_over_1000_chg = holding_over_1000.diff(1).iloc[-1]
        chip_under_50_chg = holding_under_50.diff(1).iloc[-1]
        chip_holders_chg = (
            (holder_count / holder_count.shift(1).replace(0, float("nan")) - 1.0) * 100.0
        ).iloc[-1]

        # 3. 融資指標 (日資料)
        margin_balance = data.get("margin_transactions:融資今日餘額", start=start_iso, end=end_iso)
        margin_balance = margin_balance.loc[margin_balance.index <= end_ts].reindex(columns=stock_ids)
        if len(margin_balance) < 10:
            raise RuntimeError(f"融資日資料不足 10 個交易日（實際 {len(margin_balance)} 日）！")

        margin_date_str = _format_date_str(margin_balance.index[-1])
        margin_latest = margin_balance.iloc[-1]
        margin_chg_5d = (
            (margin_balance / margin_balance.shift(5).replace(0, float("nan")) - 1.0) * 100.0
        ).iloc[-1]
        margin_pct_10d = (margin_balance.rolling(10).rank(pct=True) * 100.0).iloc[-1]

        # 4. 本益比與產業分類 (日資料)
        pe_df = data.get("price_earning_ratio:本益比", start=start_iso, end=end_iso).sort_index()
        pe_df = pe_df.loc[pe_df.index <= end_ts].reindex(columns=stock_ids)
        if pe_df.empty:
            raise RuntimeError(f"截至 {end_iso} 查無本益比資料！")

        pe_date_str = _format_date_str(pe_df.index[-1])
        categories_df = data.get("security_categories")[["stock_id", "category"]].drop_duplicates("stock_id")

    # 計算完整 150 檔同產業本益比百分位（非正值不參與排名，保留 NaN；單一家數保留 NaN）
    pe_table = stocks_df[["stock_id"]].copy()
    pe_table["pe"] = pe_table["stock_id"].map(pe_df.iloc[-1])
    pe_table["pe"] = pe_table["pe"].where(pe_table["pe"] > 0)
    pe_table = pe_table.merge(categories_df, on="stock_id", how="left")

    pe_group = pe_table.groupby("category")["pe"]
    pe_rank = pe_group.rank(method="average")
    pe_count = pe_group.transform("count")
    pe_table["pe_industry_pct"] = (pe_rank - 1.0) / (pe_count - 1.0).replace(0, float("nan")) * 100.0
    pe_table = pe_table.set_index("stock_id")

    # 組裝 Compact Array JSON 結構
    stocks_payload: Dict[str, Dict[str, Any]] = {}
    rule1_count = 0

    for row in stocks_df.itertuples(index=False):
        sid = row.stock_id
        mkt = row.market

        r5 = stock_ret_5d.get(sid)
        r10 = stock_ret_10d.get(sid)
        m5 = mkt_ret_5d.get(mkt)
        m10 = mkt_ret_10d.get(mkt)

        rel5 = (r5 - m5) if (pd.notna(r5) and pd.notna(m5)) else float("nan")
        rel10 = (r10 - m10) if (pd.notna(r10) and pd.notna(m10)) else float("nan")

        # 以未四捨五入原值精準判斷規則一，避免邊界進位誤差
        rule1_ok = bool(pd.notna(rel5) and pd.notna(rel10) and rel5 > 0 and rel10 > 0)
        if rule1_ok:
            rule1_count += 1

        industry_val = pe_table.at[sid, "category"]
        industry_str = str(industry_val).strip() if pd.notna(industry_val) else None

        entry: Dict[str, Any] = {
            "stock": row.stock,
            "market": mkt,
            "industry": industry_str,
            "rule1_selected": rule1_ok,
        }

        metric_specs: List[Tuple[str, Any, str, int]] = [
            ("ret_5d_pct", r5, price_date_str, 2),
            ("ret_10d_pct", r10, price_date_str, 2),
            ("rel_ret_5d_pp", rel5, price_date_str, 2),
            ("rel_ret_10d_pp", rel10, price_date_str, 2),
            ("chip_over_1000_chg_pp", chip_over_1000_chg.get(sid), chip_date_str, 2),
            ("chip_under_50_chg_pp", chip_under_50_chg.get(sid), chip_date_str, 2),
            ("chip_holders_chg_pct", chip_holders_chg.get(sid), chip_date_str, 2),
            ("margin_balance_lots", margin_latest.get(sid), margin_date_str, 0),
            ("margin_chg_5d_pct", margin_chg_5d.get(sid), margin_date_str, 2),
            ("margin_pct_10d", margin_pct_10d.get(sid), margin_date_str, 1),
            ("pe_ratio", pe_table.at[sid, "pe"], pe_date_str, 2),
            ("pe_industry_pct", pe_table.at[sid, "pe_industry_pct"], pe_date_str, 2),
        ]

        for key, raw_val, dt_str, digits in metric_specs:
            norm_val = _round_metric(raw_val, digits=digits)
            if norm_val is not None:
                entry[key] = [norm_val, dt_str]

        stocks_payload[sid] = entry

    metrics_payload: Dict[str, Any] = {
        "_format": "[value, date]",
        "target_date": c_date,
        "generated_at": datetime.now(TW_TZ).isoformat(timespec="seconds"),
        "data_dates": {
            "price": price_date_str,
            "chip": chip_date_str,
            "margin": margin_date_str,
            "pe": pe_date_str,
        },
        "market_returns": {
            "twse": {
                "ret_5d_pct": [_round_metric(mkt_ret_5d.get("twse"), 2), price_date_str],
                "ret_10d_pct": [_round_metric(mkt_ret_10d.get("twse"), 2), price_date_str],
            },
            "otc": {
                "ret_5d_pct": [_round_metric(mkt_ret_5d.get("otc"), 2), price_date_str],
                "ret_10d_pct": [_round_metric(mkt_ret_10d.get("otc"), 2), price_date_str],
            },
        },
        "universe_summary": {
            "total_stocks": len(stocks_payload),
            "rule1_selected_count": rule1_count,
            "candidate_pool_count": len(stocks_payload) - rule1_count,
        },
        "stocks": stocks_payload,
    }

    print(
        f"[量化指標完成] 價量/融資/PE日={price_date_str} | 集保週={chip_date_str} | "
        f"規則一入選 {rule1_count} 檔 / 待補充評估 {len(stocks_payload) - rule1_count} 檔"
    )
    return metrics_payload


# =============================================================================
# 供下游模組讀取當日動態股票池之共用函式
# =============================================================================
def load_stock_pool_ids(
    target_date: Optional[str] = None,
    fallback: Optional[List[str]] = None,
) -> List[str]:
    """讀取指定日期（或最新）之 `data/Stock_Pool/stock_list_<YYYYMMDD>.json` 股票代碼清單。

    優先順序：
    1. 若指定 target_date 且存在 `stock_list_<YYYYMMDD>.json`，直接回傳該日清單。
    2. 否則搜尋 `data/Stock_Pool/stock_list_*.json` 中日期最新的一份。
    3. 若目錄尚無任何 stock_list 檔案，回傳 fallback 清單（或空陣列）。
    """
    chosen_path: Optional[Path] = None
    if STOCK_POOL_DIR.is_dir():
        if target_date:
            c_date = clean_date_str(target_date)
            exact_path = STOCK_POOL_DIR / f"stock_list_{c_date}.json"
            if exact_path.is_file():
                chosen_path = exact_path
        if chosen_path is None:
            candidates = sorted(STOCK_POOL_DIR.glob("stock_list_*.json"), reverse=True)
            if candidates:
                chosen_path = candidates[0]

    if chosen_path is not None:
        try:
            payload = json.loads(chosen_path.read_text(encoding="utf-8"))
            ids = [str(x).strip() for x in (payload.get("stock_ids") or []) if str(x).strip()]
            if ids:
                print(f"[StockPool] 已載入動態股票池 {chosen_path.name} (共 {len(ids)} 檔)")
                return ids
        except Exception as exc:
            print(f"[StockPool][警告] 讀取 {chosen_path} 失敗: {exc}")

    if fallback is not None:
        print(f"[StockPool][提示] 查無動態股票池檔案，沿用預設清單 (共 {len(fallback)} 檔)")
        return list(fallback)
    return []


# =============================================================================
# 讀取當日 DataPack 目前持股清單 (確保持股必定保留於最終股票池)
# =============================================================================
def load_current_holdings(target_date: str) -> Tuple[List[str], Optional[str]]:
    """從當日官方 DataPack Raw JSON 讀取目前持股代碼 (shares > 0)。

    回傳: (sorted_holding_ids, datapack_filename)；若當日查無 DataPack 則回傳 ([], None)。
    """
    from L0_sources.datapack_loader import find_datapack_raw

    try:
        dp_path = find_datapack_raw(target_date)
    except FileNotFoundError as exc:
        print(f"[目前持股] 查無當日 DataPack，略過持股強制保留 ({exc})")
        return [], None

    dp = json.loads(dp_path.read_text(encoding="utf-8"))
    raw_holdings = dp.get("holdings") or []
    holding_ids: List[str] = []
    for item in raw_holdings:
        if int(item.get("shares") or 0) > 0:
            code = str(item.get("code") or "").strip()
            if code:
                holding_ids.append(code)

    holding_ids = sorted(set(holding_ids))
    print(f"[目前持股] 已讀取 {dp_path.name} -> 共 {len(holding_ids)} 檔目前持股將強制保留於股票池")
    return holding_ids, dp_path.name


# =============================================================================
# Step 3: Prompt 組裝與 LLM Agent 補充篩選
# =============================================================================
SYSTEM_INSTRUCTION = """\
你是台股量化與籌碼研究團隊的「L0 股票池補充篩選 Agent」。
你的任務是檢視指定 150 檔上市櫃股票的完整量化指標（Compact Array JSON 格式），從「未被規則一選中（rule1_selected = false）」的股票中，發掘被單純動能規則忽略、但具備潛力值得額外納入股票池的標的。

### 一、任務邊界與鐵律
1. **規則一與目前持股皆已鎖定**：凡 `rule1_selected == true`（近 5 日與近 10 日相對市場報酬皆 > 0）之股票已確定納入最終股票池，**嚴禁重新審核、剔除，也不得重複列入你的 `supplementary_picks` 名單中**；此外，若輸入摘要列出目前帳上持股（`current_holding_ids`），這些持股亦會由系統強制保留於最終股票池，無須重複挑選。
2. **嚴格候選範圍**：你的 `supplementary_picks` **只能挑選 `rule1_selected == false`、且非目前帳上持股、且存在於輸入清單內的股票**；你可以參考全部 150 檔的整體橫斷面分布進行比較。
3. **NVIDIA 相關概念股強制納入清單（共 35 檔）**：
   - 以下 35 檔為 **NVIDIA 相關個股**：`["2059", "2301", "2308", "2313", "2317", "2330", "2357", "2368", "2376", "2377", "2382", "2383", "2449", "3017", "3037", "3131", "3189", "3231", "3324", "3374", "3533", "3653", "3665", "3680", "3711", "4958", "6187", "6239", "6274", "6415", "6515", "6584", "6669", "8046", "8210"]`。
   - 凡此清單中屬於 `rule1_selected == false` 且非目前帳上持股者，**必須全數強制納入 `supplementary_picks`**（不得因動能、籌碼或估值未達標而略過），並在 `primary_angles` 標註 `"NVIDIA概念股強制納入"`、`reason` 中註明為 NVIDIA 相關個股強制納入並簡附其關鍵指標數值。
   - 若該代碼已在 `rule1_selected == true` 或 `current_holding_ids` 內，系統已鎖定保留於股票池，無須重複列入 `supplementary_picks`。
4. **寬鬆初選原則**：這一步是「股票池初選」，目的是把值得後續深入研究（L1/L2）的潛力標的補撈回來，**不要求所有面向同時有利，也不必套用死板門檻**，且**沒有固定家數上下限**（除了上述強制納入之 NVIDIA 相關個股外，其餘標的若確實無合適者可不額外補撈）。
5. **善用 Python Code Execution（附防爆 Token 紀律）**：你可以選擇使用 Python 進行數值驗算、分數排序或交叉比對，但**嚴禁在 Python 程式碼中逐字重抄整個 150 檔原始 JSON 資料**（否則會耗盡輸出 Token 上限）；若要動用 Python，請先閱讀 JSON 篩出 10~30 檔感興趣的候選股，僅將這少數候選股的關鍵數值帶入程式碼運算，或直接以推理完成分析並輸出最終 JSON。

### 二、資料格式與指標定義
輸入 JSON 採 Compact Array JSON 格式，數值欄位皆為 `[value, date]`（保留各類資料源原始日期；省略欄位代表該項為缺值、虧損無正本益比或單一家數無同業百分位，請勿自行補 0）：
- **規則一價格動能（日資料）**：
  - `ret_5d_pct` / `ret_10d_pct`：個股近 5 日 / 近 10 日收盤報酬率（%）。
  - `rel_ret_5d_pp` / `rel_ret_10d_pp`：個股相對對應市場（上市比 TAIEX、上櫃比櫃買指數，均不含息）之近 5 日 / 近 10 日超額報酬（百分點 pp）。
  - `rule1_selected`：兩項相對報酬同時 > 0 時為 `true`，否則為 `false`。
- **集保持股籌碼（週資料）**：
  - `chip_over_1000_chg_pp`：大於 1000 張大戶持股占比近 1 期變化（百分點 pp，正值代表大戶加碼吸籌）。
  - `chip_under_50_chg_pp`：小於 50 張散戶持股占比近 1 期變化（百分點 pp，負值代表散戶退場）。
  - `chip_holders_chg_pct`：全部持有人數近 1 期變化率（%，負值代表籌碼集中度提升）。
- **融資槓桿（日資料）**：
  - `margin_balance_lots`：最新融資餘額（張）。
  - `margin_chg_5d_pct`：融資餘額近 5 日變化率（%，負值代表融資減肥／去槓桿）。
  - `margin_pct_10d`：最新融資餘額在近 10 個交易日中的升冪百分位（0~100，越低代表融資處於近期低水位、籌碼較輕；越高代表槓桿水位偏高）。
- **本益比估值（日資料）**：
  - `industry`：產業分類。
  - `pe_ratio`：最新本益比（倍；非正值已省略）。
  - `pe_industry_pct`：同產業本益比升冪百分位（0~100，以完整 150 檔同業計算，**越低代表在同產業中估值相對越便宜**）。

### 三、多面向觀察與發掘方向
請從以下單一強訊號或跨面向組合中，挑選具備實質吸引力的遺珠：
1. **規則一臨門一腳 / 結構轉強**：例如其中一期相對市場報酬顯著優於大盤、另一期僅微幅落後（如短線剛止跌轉強或僅因單日拉回而差一點落選），且籌碼或估值面給予支撐。
2. **籌碼顯著集中（大戶進、散戶退）**：`chip_over_1000_chg_pp` 明顯增加，且伴隨 `chip_under_50_chg_pp` 下降或 `chip_holders_chg_pct` 負成長，顯示主力趁股價未明顯領先大盤前先行佈局。
3. **融資健康去槓桿**：融資餘額顯著縮減（`margin_chg_5d_pct < 0`）或位於近 10 日低百分位（`margin_pct_10d` 偏低），代表籌碼清洗乾淨、潛在賣壓輕。**重要判讀紀律：解讀 `margin_chg_5d_pct` 時必須一併檢視 `margin_balance_lots` 張數，避免因融資基期過低造成百分比劇烈波動而誤判。**
4. **同產業低估值安全邊際**：`pe_industry_pct` 處於同業偏低位置（如前 20%~30% 低估值區），且未出現籌碼嚴重潰散或高檔融資爆增風險。

### 四、輸出要求
- `supplementary_picks` 請依「最值得優先納入關注」的程度由高至低排列（`priority_rank` 從 1 開始遞增）。
- 每檔股票的 `reason` 必須引用輸入資料中的具體數字（例如相對報酬 pp、千張大戶變化 pp、融資張數與變化率、同業本益比百分位），精簡扼要、有理有據。
"""


def _to_prompt_compact_json(metrics_payload: Dict[str, Any]) -> str:
    """將 150 檔 Compact Array JSON 壓縮為「每檔股票一行」的精簡 JSON，大幅節省 Prompt Token 並保持可讀性。"""
    header_obj = {
        "_format": metrics_payload.get("_format", "[value, date]"),
        "target_date": metrics_payload.get("target_date"),
        "data_dates": metrics_payload.get("data_dates"),
        "market_returns": metrics_payload.get("market_returns"),
        "universe_summary": metrics_payload.get("universe_summary"),
    }
    lines = ["{"]
    for k, v in header_obj.items():
        lines.append(f'  "{k}": {json.dumps(v, ensure_ascii=False, separators=(",", ":"))},')
    lines.append('  "stocks": {')
    stocks_items = list((metrics_payload.get("stocks") or {}).items())
    for idx, (sid, info) in enumerate(stocks_items):
        comma = "," if idx < len(stocks_items) - 1 else ""
        lines.append(f'    "{sid}": {json.dumps(info, ensure_ascii=False, separators=(",", ":"))}{comma}')
    lines.append("  }")
    lines.append("}")
    return "\n".join(lines)


def build_user_prompt(
    metrics_payload: Dict[str, Any],
    holding_ids: Optional[List[str]] = None,
) -> str:
    """組裝餵給 L0 補充篩選 Agent 的 User Prompt（嵌入每檔單行之 Compact Array JSON）。"""
    d_dates = metrics_payload.get("data_dates", {})
    mkt = metrics_payload.get("market_returns", {})
    usum = metrics_payload.get("universe_summary", {})
    compact_json_str = _to_prompt_compact_json(metrics_payload)
    h_list = sorted(set(holding_ids or []))
    holding_line = (
        f"- 目前帳上持股（系統將強制保留於最終股票池，共 {len(h_list)} 檔，無須重複挑選）：{json.dumps(h_list, ensure_ascii=False)}\n"
        if h_list
        else "- 目前帳上持股：無（空手或未載入 DataPack）\n"
    )

    return (
        f"## 基準日期與市場環境摘要\n"
        f"- 目標基準日：{metrics_payload.get('target_date')}\n"
        f"- 各類資料最新日期：價量={d_dates.get('price')}｜集保週={d_dates.get('chip')}｜"
        f"融資={d_dates.get('margin')}｜本益比={d_dates.get('pe')}\n"
        f"- 上市大盤 (TAIEX) 報酬：近5日 {mkt.get('twse', {}).get('ret_5d_pct')}、近10日 {mkt.get('twse', {}).get('ret_10d_pct')}\n"
        f"- 上櫃指數 (OTC) 報酬：近5日 {mkt.get('otc', {}).get('ret_5d_pct')}、近10日 {mkt.get('otc', {}).get('ret_10d_pct')}\n"
        f"- 股票池概況：總計 {usum.get('total_stocks')} 檔，規則一已確定入選 {usum.get('rule1_selected_count')} 檔，"
        f"規則一未入選候選池（`rule1_selected: false`）共 {usum.get('candidate_pool_count')} 檔。\n"
        f"{holding_line}\n"
        f"## 150 檔股票完整指標資料（Compact Array JSON）\n"
        f"```json\n{compact_json_str}\n```\n\n"
        f"請嚴格從 `rule1_selected == false`（且非目前帳上持股）的股票中，挑選值得額外納入股票池的標的並依優先順序輸出結構化 JSON。"
    )


# =============================================================================
# Step 4: 防呆校驗、合併股票池與報告渲染
# =============================================================================
def validate_and_merge_pool(
    metrics_payload: Dict[str, Any],
    agent_response: Optional[StockPoolScreeningResponse],
    holding_ids: Optional[List[str]] = None,
    datapack_file: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """對 Agent 輸出進行程式端防呆校驗，並強制聯集目前持股，產出 (stock_list_payload, screening_result_payload)。"""
    stocks_map: Dict[str, Dict[str, Any]] = metrics_payload["stocks"]
    c_date = metrics_payload["target_date"]
    holding_id_set: set[str] = set(holding_ids or [])

    rule1_stocks: List[Dict[str, Any]] = []
    rule1_id_set: set[str] = set()
    for sid, info in stocks_map.items():
        if info.get("rule1_selected"):
            rule1_id_set.add(sid)
            rule1_stocks.append(
                {
                    "stock_id": sid,
                    "stock": info["stock"],
                    "market": info["market"],
                    "industry": info.get("industry"),
                    "is_holding": sid in holding_id_set,
                    "rel_ret_5d_pp": (info.get("rel_ret_5d_pp") or [None])[0],
                    "rel_ret_10d_pp": (info.get("rel_ret_10d_pp") or [None])[0],
                }
            )

    # 規則一名單依近 5 日相對報酬由高至低排序，便於檢視
    rule1_stocks.sort(key=lambda x: (x["rel_ret_5d_pp"] is not None, x["rel_ret_5d_pp"] or -9999), reverse=True)

    valid_picks: List[Dict[str, Any]] = []
    seen_extra: set[str] = set()
    dropped_warnings: List[str] = []

    if agent_response is not None:
        sorted_raw = sorted(agent_response.supplementary_picks, key=lambda p: p.priority_rank)
        for pick in sorted_raw:
            sid = str(pick.stock_id).strip()
            if sid not in stocks_map:
                dropped_warnings.append(f"濾除不在 150 檔清單內之代碼: {sid}")
                continue
            if sid in rule1_id_set:
                dropped_warnings.append(f"濾除已屬規則一入選之重複代碼: {sid} ({stocks_map[sid]['stock']})")
                continue
            if sid in seen_extra:
                dropped_warnings.append(f"濾除 Agent 重複列舉之代碼: {sid}")
                continue

            seen_extra.add(sid)
            auth_info = stocks_map[sid]
            valid_picks.append(
                {
                    "priority_rank": len(valid_picks) + 1,
                    "stock_id": sid,
                    "stock": auth_info["stock"],
                    "market": auth_info["market"],
                    "industry": auth_info.get("industry"),
                    "is_holding": sid in holding_id_set,
                    "primary_angles": list(pick.primary_angles),
                    "reason": pick.reason.strip(),
                    "key_metrics": {
                        k: auth_info[k]
                        for k in (
                            "rel_ret_5d_pp",
                            "rel_ret_10d_pp",
                            "chip_over_1000_chg_pp",
                            "chip_under_50_chg_pp",
                            "chip_holders_chg_pct",
                            "margin_balance_lots",
                            "margin_chg_5d_pct",
                            "margin_pct_10d",
                            "pe_ratio",
                            "pe_industry_pct",
                        )
                        if k in auth_info
                    },
                }
            )

    if dropped_warnings:
        print("[防呆校驗提示]")
        for w in dropped_warnings:
            print(f"  - {w}")

    rule1_ids = sorted(rule1_id_set)
    agent_extra_ids = sorted(seen_extra)
    holding_sorted_ids = sorted(holding_id_set)
    holding_forced_ids = sorted(holding_id_set - rule1_id_set - seen_extra)
    final_stock_ids = sorted(rule1_id_set | seen_extra | holding_id_set)

    holding_forced_stocks: List[Dict[str, Any]] = []
    for sid in holding_forced_ids:
        info = stocks_map.get(sid)
        holding_forced_stocks.append(
            {
                "stock_id": sid,
                "stock": info["stock"] if info else sid,
                "market": info["market"] if info else "unknown",
                "industry": info.get("industry") if info else None,
                "in_universe_150": info is not None,
                "rel_ret_5d_pp": (info.get("rel_ret_5d_pp") or [None])[0] if info else None,
                "rel_ret_10d_pp": (info.get("rel_ret_10d_pp") or [None])[0] if info else None,
            }
        )

    generated_at = datetime.now(TW_TZ).isoformat(timespec="seconds")

    def _stock_source_tags(sid: str) -> Tuple[str, List[str]]:
        tags: List[str] = []
        if sid in rule1_id_set:
            tags.append("rule1")
        if sid in seen_extra:
            tags.append("agent_supplementary")
        if sid in holding_id_set:
            tags.append("holding")
        primary = (
            "rule1"
            if sid in rule1_id_set
            else ("agent_supplementary" if sid in seen_extra else "holding_forced")
        )
        return primary, tags

    # 1. 獨立精簡 Stock List（專供下游 finlab_market_loader / cmoney_sentiment_crawler 無縫讀取）
    stock_list_payload: Dict[str, Any] = {
        "date": c_date,
        "generated_at": generated_at,
        "datapack_file": datapack_file,
        "data_dates": metrics_payload.get("data_dates", {}),
        "count": len(final_stock_ids),
        "rule1_count": len(rule1_ids),
        "agent_extra_count": len(agent_extra_ids),
        "holding_count": len(holding_sorted_ids),
        "holding_forced_count": len(holding_forced_ids),
        "stock_ids": final_stock_ids,
        "rule1_stock_ids": rule1_ids,
        "agent_extra_stock_ids": agent_extra_ids,
        "holding_stock_ids": holding_sorted_ids,
        "holding_forced_stock_ids": holding_forced_ids,
        "stocks": [
            {
                "stock_id": sid,
                "stock": stocks_map[sid]["stock"] if sid in stocks_map else sid,
                "market": stocks_map[sid]["market"] if sid in stocks_map else "unknown",
                "industry": stocks_map[sid].get("industry") if sid in stocks_map else None,
                "is_holding": sid in holding_id_set,
                "source": _stock_source_tags(sid)[0],
                "sources": _stock_source_tags(sid)[1],
            }
            for sid in final_stock_ids
        ],
    }

    # 2. 完整篩選報告 JSON（供人類檢視與後續整合至 data/D-Paln_Output/reports/）
    screening_result_payload: Dict[str, Any] = {
        "date": c_date,
        "generated_at": generated_at,
        "datapack_file": datapack_file,
        "data_dates": metrics_payload.get("data_dates", {}),
        "market_returns": metrics_payload.get("market_returns", {}),
        "summary": {
            "universe_count": len(stocks_map),
            "rule1_count": len(rule1_ids),
            "agent_extra_count": len(agent_extra_ids),
            "holding_count": len(holding_sorted_ids),
            "holding_forced_count": len(holding_forced_ids),
            "final_pool_count": len(final_stock_ids),
        },
        "market_context_summary": (
            agent_response.market_context_summary.strip()
            if agent_response is not None
            else "（本次以 --skip-llm 模式執行，未呼叫補充篩選 Agent）"
        ),
        "final_stock_ids": final_stock_ids,
        "rule1_stocks": rule1_stocks,
        "supplementary_picks": valid_picks,
        "holding_forced_stocks": holding_forced_stocks,
        "validation_warnings": dropped_warnings,
    }

    return stock_list_payload, screening_result_payload


def _fmt_signed(val: Any, suffix: str = "", digits: int = 2) -> str:
    """將數值格式化為帶正負號之人讀字串（如 +5.33pp / -1.58%），缺值回傳 '-'。"""
    if val is None or pd.isna(val):
        return "-"
    try:
        v = float(val)
        return f"{v:+.{digits}f}{suffix}"
    except (ValueError, TypeError):
        return str(val)


def _metric_val(km: Dict[str, Any], key: str) -> Any:
    """從 Compact Array JSON 的 key_metrics 取出數值本體。"""
    item = km.get(key)
    if isinstance(item, (list, tuple)) and len(item) >= 1:
        return item[0]
    return item


def render_stock_pool_markdown(result: Dict[str, Any], section_title: str = "## 七、 L0 動態股票池篩選回顧") -> str:
    """將 screening_result JSON 渲染為高度易讀的人類檢閱 Markdown 報告區塊。"""
    summary = result.get("summary", {})
    d_dates = result.get("data_dates", {})
    mkt = result.get("market_returns", {})
    picks = result.get("supplementary_picks", [])
    rule1 = result.get("rule1_stocks", [])
    forced = result.get("holding_forced_stocks", [])

    twse_5 = _metric_val(mkt.get("twse", {}), "ret_5d_pct")
    twse_10 = _metric_val(mkt.get("twse", {}), "ret_10d_pct")
    otc_5 = _metric_val(mkt.get("otc", {}), "ret_5d_pct")
    otc_10 = _metric_val(mkt.get("otc", {}), "ret_10d_pct")

    lines: List[str] = [
        section_title,
        "",
        "### 📊 篩選漏斗與市場基準總覽",
        "",
        "| 項目 | 內容 / 數值 | 說明 |",
        "| :--- | :--- | :--- |",
        f"| **資料基準日期** | 價量 `{d_dates.get('price', '-')}` ｜ 集保 `{d_dates.get('chip', '-')}` ｜ 融資 `{d_dates.get('margin', '-')}` ｜ PE `{d_dates.get('pe', '-')}` | "
        + (f"對照持股檔：`{result.get('datapack_file')}`" if result.get("datapack_file") else "未對照 DataPack 持股")
        + " |",
        f"| **大盤基準報酬 (不含息)** | 上市 TAIEX：近5日 **{_fmt_signed(twse_5, '%')}** / 近10日 **{_fmt_signed(twse_10, '%')}**<br>上櫃 OTC：近5日 **{_fmt_signed(otc_5, '%')}** / 近10日 **{_fmt_signed(otc_10, '%')}** | 規則一相對強弱比較基準 |",
        f"| **最終股票池規模** | **{summary.get('final_pool_count', 0)} 檔**（自 {summary.get('universe_count', 150)} 檔母體篩出） | 規則一鎖定 **{summary.get('rule1_count', 0)}** 檔 ＋ Agent 補充 **{summary.get('agent_extra_count', 0)}** 檔 ＋ 持股強制保留 **{summary.get('holding_forced_count', 0)}** 檔（帳上總持股 {summary.get('holding_count', 0)} 檔） |",
        "",
        "### 🧠 Agent 盤勢與 150 檔籌碼結構總評",
        "",
        f"> {result.get('market_context_summary', '（無摘要）')}",
        "",
        f"### ✨ Agent 額外補撈遺珠名單（共 {len(picks)} 檔，依優先關注度排序）",
        "",
    ]

    if not picks:
        lines.append("*(本次無額外補充納入之標的)*")
        lines.append("")
    else:
        lines.extend(
            [
                "| 排序 | 股票 | 市場 / 產業 | 近5日 / 10日相對報酬 | 集保 (千張 / <50張 / 人數) | 融資餘額 (5日變 / 10日位階) | 本益比 (同業百分位) | 觸發面向 |",
                "| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :--- |",
            ]
        )
        for p in picks:
            km = p.get("key_metrics") or {}
            mkt_label = "上市" if p.get("market") == "twse" else "上櫃"
            ind_label = p.get("industry") or "-"
            rel_str = f"{_fmt_signed(_metric_val(km, 'rel_ret_5d_pp'), 'pp')} / {_fmt_signed(_metric_val(km, 'rel_ret_10d_pp'), 'pp')}"
            chip_str = (
                f"{_fmt_signed(_metric_val(km, 'chip_over_1000_chg_pp'), 'pp')} / "
                f"{_fmt_signed(_metric_val(km, 'chip_under_50_chg_pp'), 'pp')} / "
                f"{_fmt_signed(_metric_val(km, 'chip_holders_chg_pct'), '%')}"
            )
            m_lots = _metric_val(km, "margin_balance_lots")
            m_lots_str = f"{int(m_lots):,}張" if m_lots is not None else "-"
            m_pct = _metric_val(km, "margin_pct_10d")
            m_pct_str = f"P{int(round(float(m_pct)))}" if m_pct is not None else "-"
            margin_str = f"{m_lots_str} ({_fmt_signed(_metric_val(km, 'margin_chg_5d_pct'), '%')} / {m_pct_str})"

            pe_val = _metric_val(km, "pe_ratio")
            pe_pct = _metric_val(km, "pe_industry_pct")
            pe_str = (
                f"{float(pe_val):.1f}x ({f'P{float(pe_pct):.0f}' if pe_pct is not None else '-'})"
                if pe_val is not None
                else "-"
            )
            angles = "、".join(p.get("primary_angles") or []) or "-"
            lines.append(
                f"| #{p.get('priority_rank')} | `{p.get('stock_id')}` **{p.get('stock')}** | {mkt_label}・{ind_label} | "
                f"{rel_str} | {chip_str} | {margin_str} | {pe_str} | {angles} |"
            )

        lines.extend(["", "#### 💡 逐檔補撈入選理由說明", ""])
        for p in picks:
            angles = "、".join(p.get("primary_angles") or [])
            reason_clean = str(p.get("reason", "")).replace("\n", " ").strip()
            lines.append(
                f"- **#{p.get('priority_rank')} `{p.get('stock_id')}` {p.get('stock')}**（{angles}）：{reason_clean}"
            )
        lines.append("")

    if forced:
        lines.extend(
            [
                f"### 🛡️ 目前持股強制保留名單（未入選規則一／Agent，共 {len(forced)} 檔）",
                "",
                "> 以下為帳上現有持倉，雖未通過規則一或 Agent 補撈，系統仍強制納入股票池以利後續 L2/L3 評估續抱或賣出：",
                "",
                "| 股票代號 | 股票名稱 | 市場 / 產業 | 近5日相對報酬 | 近10日相對報酬 |",
                "| :---: | :--- | :--- | :---: | :---: |",
            ]
        )
        for h in forced:
            mkt_label = "上市" if h.get("market") == "twse" else ("上櫃" if h.get("market") == "otc" else "-")
            lines.append(
                f"| `{h['stock_id']}` | **{h['stock']}** | {mkt_label}・{h.get('industry') or '-'} | "
                f"{_fmt_signed(h.get('rel_ret_5d_pp'), 'pp')} | {_fmt_signed(h.get('rel_ret_10d_pp'), 'pp')} |"
            )
        lines.append("")

    # 規則一已鎖定名單：依產業分組呈現，讓人類一眼看出強勢資金集中族群
    lines.append(f"### ✅ 規則一已鎖定強勢名單（近5日及近10日相對大盤皆 > 0，共 {len(rule1)} 檔）")
    lines.append("")
    if not rule1:
        lines.append("*(今日無標的通過規則一)*")
    else:
        by_industry: Dict[str, List[Dict[str, Any]]] = {}
        for r in rule1:
            ind = r.get("industry") or "未分類"
            by_industry.setdefault(ind, []).append(r)

        sorted_inds = sorted(by_industry.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        lines.extend(
            [
                "| 產業族群 | 檔數 | 入選個股（括號為近5日相對報酬，`★` 表示目前持有） |",
                "| :--- | :---: | :--- |",
            ]
        )
        for ind, items in sorted_inds:
            stock_tags = []
            for r in items:
                star = "★" if r.get("is_holding") else ""
                r5 = _fmt_signed(r.get("rel_ret_5d_pp"), "pp", digits=1)
                stock_tags.append(f"{star}`{r['stock_id']}` {r['stock']} ({r5})")
            lines.append(f"| **{ind}** | {len(items)} | {'、'.join(stock_tags)} |")
    lines.append("")
    return "\n".join(lines)


# =============================================================================
# 主流程入口
# =============================================================================
def run_stock_pool_screening(
    target_date: Optional[str] = None,
    model: Optional[str] = None,
    dry_run: bool = False,
    skip_llm: bool = False,
    use_cached_metrics: bool = False,
    stream: bool = True,
    enable_code_execution: bool = True,
    include_holdings: bool = True,
) -> Dict[str, Any]:
    """執行完整 L0 股票池篩選並將結果存檔至 data/Stock_Pool/。"""
    t_date = prompt_trade_date(target_date, prompt_text="L0 股票池篩選 - 基準日期")

    STOCK_POOL_DIR.mkdir(parents=True, exist_ok=True)
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)

    metrics_path = METRICS_DIR / f"stock_pool_metrics_{t_date}.json"
    prompt_path = PROMPTS_DIR / f"l0_prompt_{t_date}.txt"
    stock_list_path = STOCK_POOL_DIR / f"stock_list_{t_date}.json"
    screening_result_path = STOCK_POOL_DIR / f"screening_result_{t_date}.json"

    # 0. 讀取當日 DataPack 目前持股 (確保目前持股必保留於最終股票池)
    holding_ids: List[str] = []
    datapack_file: Optional[str] = None
    if include_holdings:
        holding_ids, datapack_file = load_current_holdings(t_date)

    # 1. 取得或重讀 150 檔 Compact Array JSON 指標
    if use_cached_metrics:
        if not metrics_path.is_file():
            raise FileNotFoundError(
                f"指定了 --use-cached-metrics，但找不到快取指標檔: {metrics_path}"
            )
        print(f"[快取載入] 讀取既有指標檔: {metrics_path}")
        metrics_payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    else:
        metrics_payload = fetch_and_compute_metrics(t_date)
        metrics_path.write_text(to_compact_json(metrics_payload, indent=2), encoding="utf-8")
        print(f"[指標存檔] 已寫入 Compact Array JSON -> {metrics_path}")

    # 2. 組裝並一律儲存 Prompt (無論是否 dry-run 皆留存稽核紀錄)
    user_prompt = build_user_prompt(metrics_payload, holding_ids=holding_ids)
    prompt_path.write_text(
        f"=== SYSTEM INSTRUCTION ===\n{SYSTEM_INSTRUCTION}\n\n=== USER PROMPT ===\n{user_prompt}\n",
        encoding="utf-8",
    )
    print(f"[Prompt 存檔] 已寫入 -> {prompt_path} (字元數: {len(user_prompt):,})")

    if dry_run:
        print("[Dry-Run] 僅輸出指標與 Prompt，不呼叫 LLM。")
        return {"metrics_path": str(metrics_path), "prompt_path": str(prompt_path)}

    # 3. 呼叫 LLM Agent (或跳過)
    agent_response: Optional[StockPoolScreeningResponse] = None
    if not skip_llm:
        client = GeminiClient(model=model, stage="l0", target_date=t_date)
        print(
            f"[LLM 補充篩選] 啟動 stage-l0 Agent (model={client.default_model}, "
            f"stream={stream}, code_execution={enable_code_execution})..."
        )
        agent_response = client.generate_structured(
            prompt=user_prompt,
            response_model=StockPoolScreeningResponse,
            system_instruction=SYSTEM_INSTRUCTION,
            model=model,
            stream=stream,
            enable_code_execution=enable_code_execution,
            stage="l0",
            target_date=t_date,
        )
        client.save_usage_metadata(
            output_dir=STOCK_POOL_DIR,
            stage_prefix="l0",
            target_date=t_date,
        )
    else:
        print("[跳過 LLM] 以 --skip-llm 模式僅輸出規則一與目前持股結果。")

    # 4. 防呆校驗與合併存檔
    stock_list_payload, screening_result_payload = validate_and_merge_pool(
        metrics_payload=metrics_payload,
        agent_response=agent_response,
        holding_ids=holding_ids,
        datapack_file=datapack_file,
    )

    stock_list_path.write_text(
        json.dumps(stock_list_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    screening_result_path.write_text(
        to_compact_json(screening_result_payload, indent=2),
        encoding="utf-8",
    )

    print("\n" + "=" * 72)
    print(f"[L0 股票池篩選完成] 基準日期: {t_date}")
    print(
        f" -> 規則一鎖定: {stock_list_payload['rule1_count']} 檔 ｜ "
        f"Agent 補充: {stock_list_payload['agent_extra_count']} 檔 ｜ "
        f"持股強制保留: {stock_list_payload['holding_forced_count']} 檔 (總持股 {stock_list_payload['holding_count']} 檔) ｜ "
        f"最終股票池: {stock_list_payload['count']} 檔"
    )
    print(f" -> 獨立 Stock List: {stock_list_path}")
    print(f" -> 完整篩選報告:    {screening_result_path}")
    print("=" * 72)

    return {
        "metrics_path": str(metrics_path),
        "stock_list_path": str(stock_list_path),
        "screening_result_path": str(screening_result_path),
        "stock_list": stock_list_payload,
        "screening_result": screening_result_payload,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="【L0】150 檔上市櫃股票池量化初篩 + LLM Agent 補充篩選"
    )
    parser.add_argument("--date", type=str, default=None, help="指定基準日期 (格式 YYYYMMDD)")
    parser.add_argument("--model", type=str, default=None, help="指定覆寫路由模型或別名 (預設 stage-l0)")
    parser.add_argument("--dry-run", action="store_true", help="僅計算 FinLab 指標並輸出 Prompt 預覽，不呼叫 LLM")
    parser.add_argument("--skip-llm", action="store_true", help="僅執行規則一初篩與目前持股保留，不呼叫 LLM")
    parser.add_argument(
        "--use-cached-metrics",
        action="store_true",
        help="直接讀取當日既有 metrics JSON 重跑 LLM 篩選（省 FinLab 流量）",
    )
    parser.add_argument("--no-stream", action="store_true", help="關閉串流印出，改用單次等待")
    parser.add_argument("--no-code-exec", action="store_true", help="關閉 Gemini Code Execution 沙盒工具")
    parser.add_argument("--no-holdings", action="store_true", help="不從當日 DataPack 載入目前持股強制保留")
    args = parser.parse_args()

    run_stock_pool_screening(
        target_date=args.date,
        model=args.model,
        dry_run=args.dry_run,
        skip_llm=args.skip_llm,
        use_cached_metrics=args.use_cached_metrics,
        stream=not args.no_stream,
        enable_code_execution=not args.no_code_exec,
        include_holdings=not args.no_holdings,
    )


if __name__ == "__main__":
    main()
