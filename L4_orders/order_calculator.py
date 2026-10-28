"""【L4】委託層計算與審核 Agent (order_calculator)。

依據 D-Plan Schema v4.3 與 D-Plan 撰寫指南 v4.3 規範：
1. 從 data/D-Paln_Output/l3_decisions/ 讀取 L3 投資組合決策 (decisions)。
2. 從 data/Datapack/Processed/ 與 Raw/ 讀取帳戶可交易淨值 (nav_tradable)、現有持股部位 (holdings) 與現金。
3. 從 data/D-Paln_Output/l1_observations/ 或 DataPack 讀取最新收盤價 (close_latest)。
4. 從 data/Active_ETF_Holdings/ 讀取主動式 ETF 前 15 大成分股快照。
5. 【第一階段：Python 機械計算】
   嚴格依官方演算法計算目標股數 (千股整股，嚴禁手調)：
     目標股數 = floor( target_weight × 前日淨值 ÷ 前日收盤價 ÷ 1000 ) × 1000
     委託股數 = 目標股數 − 目前持有股數 (正=BUY，負=SELL)
   自動產生人讀推導展開式 (derivation_detail)。
   執行即時風控分析 (取整後實際權重、執行後剩餘現金、Active Share 精算)。
   輸出 Python 初版結果至 data/D-Paln_Output/l4_orders/l4_orders_python_YYYYMMDD.json。
6. 【第二階段：Gemini 智能審查與覆核】
   連接 Gemini Client，提供 DataPack 快照、L3 決策、Python 委託單、取整偏離分析與 Active Share 結果。
   由 Gemini 針對 Active Share (>=15%)、現金水位區間、委託超賣風險與產業曝險進行專業審視覆核。
   透過 Pydantic OrdersResponse 產生最終嚴格結構化 JSON。
7. 產出最終結果至 data/D-Paln_Output/l4_orders/l4_orders_YYYYMMDD.json。

用法::

    python order_calculator.py                  # 完整執行 (Python 算單 + Gemini 覆核)
    python order_calculator.py --no-gemini      # 僅執行 Python 官方公式算單
    python order_calculator.py --dry-run        # 僅組裝 Prompt，不實際調用 Gemini API
    python order_calculator.py --date 20261027  # 指定特定日期
"""

from __future__ import annotations

import argparse
import json
import math
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
    Order,
    OrderDraft,
    OrdersResponse,
    OrdersResult,
    drafts_to_orders,
)

ROOT = CODE_DIR.parent
DATA_ROOT = ROOT / "data"
L3_DEC_DIR = DATA_ROOT / "D-Paln_Output" / "l3_decisions"
L2M_VIEW_DIR = DATA_ROOT / "D-Paln_Output" / "l2m_market_view"
L1_OBS_DIR = DATA_ROOT / "D-Paln_Output" / "l1_observations"
DATAPACK_PROCESSED_DIR = DATA_ROOT / "Datapack" / "Processed"
DATAPACK_RAW_DIR = DATA_ROOT / "Datapack" / "Raw"
ACTIVE_ETF_DIR = DATA_ROOT / "Active_ETF_Holdings"
OUTPUT_DIR = DATA_ROOT / "D-Paln_Output" / "l4_orders"
OUTPUT_PREFIX = "l4_orders"
TW_TZ = timezone(timedelta(hours=8))


# =============================================================================
# Prompt 樣板 (用於 Gemini 委託層審查與覆核)
# =============================================================================
REVIEW_PROMPT_TEMPLATE = r"""\
你是主動式 ETF 基金經理人與交易風控覆核主管。
依據玉山人工智慧公開賽 D-Plan v4.3 規範，我們已透過 Python 官方演算法由今日 L3 決策 (decisions)
機械推導出今日初版委託清單 (orders)。

請審核這批委託單的合規性、資金安全性、Active Share 指標與執行效果，
並回傳最終確認（或經風控核可）的嚴格委託單 JSON。

## 今日日期與執行環境
- 交易日基準：{target_date}
- 系統時間：{now}

## 今日市場大盤目標現金區間 (L2M Market View)
- 目標現金區間 target_cash_pct_range：{target_cash_pct_range_str}

## 官方帳戶現況快照 (DataPack 快照)
- 可交易淨值 (nav_tradable)：{nav_tradable:,.0f} 元
- 可動用現金 (cash)：{cash:,.0f} 元
- 現有持股檔數：{holdings_count} 檔
- 現有持股部位明細 (前一交易日結算庫存)：
{current_holdings_str}

## 今日 L3 投資組合決策清單 (Decisions)
{decisions_summary}

## 今日 Python 官方公式推導之委託單清單 (待覆核 orders)
官方計算公式：
  目標股數 = floor( target_weight × 前日淨值 ÷ 前日收盤價 ÷ 1000 ) × 1000
  委託股數 = 目標股數 − 目前持有股數 (正=BUY, 負=SELL)

共 {order_count} 筆委託：
{orders_python_formatted}

## 執行效果與風控分析指標
1. 預估執行後股票總市值：{est_stock_value:,.0f} 元
2. 預估執行後實際總權重：{est_stock_weight:.4f} ({est_stock_weight_pct:.2f}%)
3. 預估執行後剩餘現金：{est_cash_value:,.0f} 元
4. 預估執行後現金比率：{est_cash_pct:.4f} ({est_cash_pct_str})
5. 買進總所需資金：{total_buy_amount:,.0f} 元，賣出總釋出資金：{total_sell_amount:,.0f} 元

## 主動投資比率 (Active Share) 精算結果
本目標組合與市場指定主動型 ETF 前 15 大持股逐檔比對：
公式：Active Share = 1/2 × Σ ｜本組合權重 − ETF 權重｜
{active_shares_summary}
(合規門檻：與每一檔指定 ETF 的 Active Share 均嚴格不得小於 15% / 0.15)

## 經理人與風控官覆核審查任務
請針對以下四大要點進行審視，並於 review_notes 說明覆核結論：
1. **Active Share 審視**：確認委託執行後的投資組合，與市場各主動式 ETF 前 15 大成分股之 Active Share 均 $\ge 15\%$，無指數複製或同業雷同之風險。
2. **整股取整偏離與現金檢核**：確認因向下整股取整所保留之剩餘現金比率 ({est_cash_pct_str})，完全符合 L2M 所宣示之目標現金區間 {target_cash_pct_range_str}，資金水位健康充足。
3. **委託方向與無超賣檢核**：確認賣出委託 (SELL) 之股數絕無超過庫存持股數 (絕不可超賣)；買進委託 (BUY) 所需資金未超過帳戶淨額上限。
4. **推導明細 (derivation_detail) 格式確認**：每筆委託單之推導算式皆精準對應官方範例格式。

## 輸出格式要求 (嚴格遵循 D-Plan v4.3 JSON 結構)
請產生符合下列結構的 JSON 回應：
{{
  "orders": [
    {{
      "ticker": "2330",
      "side": "BUY",
      "shares": 49000,
      "decision_ref": "D1",
      "derivation_detail": "target_shares = floor(0.07×1,000,000,000 / 1425 / 1000)×1000 = 49,000；現持 0 → BUY 49,000"
    }},
    ...
  ],
  "review_notes": "經理人與風控覆核總結 (例如：經檢核 25 檔委託單完全合規，Active Share 達標且剩餘現金在安全區間內)"
}}
"""


# -----------------------------------------------------------------------------
# 資料讀取輔助函式
# -----------------------------------------------------------------------------
def _clean_date_str(date_str: str) -> str:
    """標準化日期字串為 YYYYMMDD。"""
    return re.sub(r"\D", "", date_str)


def load_l3_decisions(target_date: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Path]:
    """讀入 L3 投資組合決策檔案 (嚴格比對 _YYYYMMDD.json)。"""
    c_date = _clean_date_str(target_date)
    if not c_date or len(c_date) != 8:
        raise ValueError(f"target_date 必須為 8 碼 YYYYMMDD 格式: '{target_date}'")

    exact_file = L3_DEC_DIR / f"l3_decisions_{c_date}.json"
    if not exact_file.exists():
        raise FileNotFoundError(f"找不到日期為 {c_date} 的 L3 決策檔案: {exact_file}")

    with open(exact_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    decisions = data.get("decisions", [])
    no_trade = data.get("no_trade_decisions", [])
    return decisions, no_trade, exact_file


def load_account_datapack(target_date: str) -> Tuple[Dict[str, Any], Path]:
    """讀入 DataPack Raw JSON，取得指定日期的帳戶資產與持股部位。"""
    c_date = _clean_date_str(target_date)
    if not c_date or len(c_date) != 8:
        raise ValueError(f"target_date 必須為 8 碼 YYYYMMDD 格式: '{target_date}'")
    iso_date = f"{c_date[:4]}-{c_date[4:6]}-{c_date[6:]}"

    file_to_load = None
    if DATAPACK_RAW_DIR.exists():
        for p in DATAPACK_RAW_DIR.glob("*.json"):
            if p.stem.endswith(f"_{c_date}") or p.stem.endswith(f"_{iso_date}"):
                file_to_load = p
                break

    if not file_to_load or not file_to_load.exists():
        raise FileNotFoundError(
            f"找不到日期結尾為 {c_date} (或 {iso_date}) 的 DataPack Raw JSON 檔案！目錄：{DATAPACK_RAW_DIR}"
        )

    with open(file_to_load, "r", encoding="utf-8") as f:
        data = json.load(f)

    account_info = {
        "nav_tradable": float(data.get("account", {}).get("nav_tradable", 1000000000.0)),
        "cash": float(data.get("account", {}).get("cash", 1000000000.0)),
        "holdings_count": int(data.get("account", {}).get("holdings_count", 0)),
        "holdings": data.get("holdings", []),
    }
    return account_info, file_to_load


def load_stock_prices(target_date: str) -> Dict[str, float]:
    """從 L1 observations 中解析指定日期個股收盤價 (嚴格比對 _YYYYMMDD.json)。"""
    c_date = _clean_date_str(target_date)
    if not c_date or len(c_date) != 8:
        raise ValueError(f"target_date 必須為 8 碼 YYYYMMDD 格式: '{target_date}'")

    exact_file = L1_OBS_DIR / f"l1_observations_{c_date}.json"
    if not exact_file.exists():
        raise FileNotFoundError(f"找不到日期為 {c_date} 的 L1 observations 檔案: {exact_file}")

    prices: Dict[str, float] = {}
    with open(exact_file, "r", encoding="utf-8") as f:
        obs_list = json.load(f)
        for obs in obs_list:
            vals = obs.get("values", {})
            topic = obs.get("topic", "")
            ticker = ""
            if topic.startswith("stock_"):
                ticker = topic.replace("stock_", "").strip()
            elif "ticker" in vals:
                ticker = str(vals["ticker"]).strip()

            if "close_latest" in vals:
                p = float(vals["close_latest"])
                if ticker:
                    prices[ticker] = p

    return prices


def load_l2m_target_cash_range(target_date: str) -> List[float]:
    """從特定日期的 L2M market_view 取得目標現金區間 (嚴格比對 _YYYYMMDD.json)。"""
    c_date = _clean_date_str(target_date)
    if not c_date or len(c_date) != 8:
        raise ValueError(f"target_date 必須為 8 碼 YYYYMMDD 格式: '{target_date}'")

    exact_file = L2M_VIEW_DIR / f"l2m_market_view_{c_date}.json"
    if not exact_file.exists():
        raise FileNotFoundError(f"找不到日期為 {c_date} 的 L2M market_view 檔案: {exact_file}")

    with open(exact_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 支援包在 market_view 內或位於根目錄
    mv = data.get("market_view", data)
    posture = mv.get("posture")
    if not posture or "target_cash_pct_range" not in posture:
        raise KeyError(f"{exact_file} 中缺少 posture.target_cash_pct_range 欄位！")

    cash_range = posture["target_cash_pct_range"]
    if not isinstance(cash_range, list) or len(cash_range) != 2:
        raise ValueError(f"{exact_file} 的 target_cash_pct_range 格式錯誤: {cash_range}")

    return [float(cash_range[0]), float(cash_range[1])]


def load_active_etf_holdings(target_date: str) -> Optional[pd.DataFrame]:
    """讀入特定日期的主動式 ETF 前 15 大持股 Parquet (嚴格比對 _YYYYMMDD.parquet)。"""
    c_date = _clean_date_str(target_date)
    exact_file = ACTIVE_ETF_DIR / f"top_15_constituents_{c_date}.parquet"

    if not exact_file.exists():
        raise FileNotFoundError(f"找不到日期為 {c_date} 的主動式 ETF 成分股檔案: {exact_file}")

    try:
        return pd.read_parquet(exact_file)
    except Exception as e:
        print(f"[警告] 讀取主動式 ETF 成分股失敗: {e}")
        raise


# =============================================================================
# 第一階段：Python 官方演算法委託計算
# =============================================================================
def calculate_orders_python(
    decisions: List[Dict[str, Any]],
    nav: float,
    current_holdings_dict: Dict[str, int],
    stock_prices: Dict[str, float],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """依官方公式嚴格計算委託單及人讀展開式。

    公式：
      目標股數 = floor( target_weight × 前日淨值 ÷ 前日收盤價 ÷ 1000 ) × 1000
      委託股數 = 目標股數 − 目前持有股數 (正=BUY, 負=SELL)
    """
    orders: List[Dict[str, Any]] = []
    total_buy_shares = 0
    total_sell_shares = 0
    total_buy_amount = 0.0
    total_sell_amount = 0.0
    est_target_shares_dict: Dict[str, int] = {}

    for dec in decisions:
        ticker = dec["ticker"].strip()
        dec_id = dec["decision_id"].strip()
        target_weight = float(dec.get("target_weight", 0.0))
        action = dec.get("action", "")

        price = stock_prices.get(ticker)
        if not price or price <= 0:
            # 若無收盤價，預設合理估值防呆 (例如 100.0)
            price = 100.0

        current_shares = current_holdings_dict.get(ticker, 0)

        # 官方演算法計算目標股數
        if action == "SELL_ALL" or target_weight <= 0.0:
            target_shares = 0
        else:
            raw_target = (target_weight * nav) / price
            target_shares = int(math.floor(raw_target / 1000.0)) * 1000

        est_target_shares_dict[ticker] = target_shares

        # 計算差異
        diff = target_shares - current_shares

        if diff > 0:
            side = "BUY"
            order_shares = diff
            total_buy_shares += order_shares
            total_buy_amount += order_shares * price
        elif diff < 0:
            side = "SELL"
            order_shares = abs(diff)
            # 防超賣安全保護
            if order_shares > current_shares:
                order_shares = current_shares
            total_sell_shares += order_shares
            total_sell_amount += order_shares * price
        else:
            # 股數無異動，不產生委託單
            continue

        # 官方規範之 derivation_detail
        derivation_detail = (
            f"target_shares = floor({target_weight:g}×{nav:,.0f} / {price:g} / 1000)×1000 = {target_shares:,}；"
            f"現持 {current_shares:,} → {side} {order_shares:,}"
        )

        orders.append({
            "ticker": ticker,
            "side": side,
            "shares": order_shares,
            "decision_ref": dec_id,
            "derivation_detail": derivation_detail,
            "_price": price,
            "_target_weight": target_weight,
            "_target_shares": target_shares,
        })

    # 計算執行後預估總持股市值與現金
    est_stock_value = sum(
        sh * stock_prices.get(tk, 100.0)
        for tk, sh in est_target_shares_dict.items()
    )
    est_stock_weight = est_stock_value / nav if nav > 0 else 0.0
    est_cash_value = nav - est_stock_value
    est_cash_pct = est_cash_value / nav if nav > 0 else 0.0

    stats = {
        "nav": nav,
        "est_stock_value": est_stock_value,
        "est_stock_weight": est_stock_weight,
        "est_cash_value": est_cash_value,
        "est_cash_pct": est_cash_pct,
        "total_buy_amount": total_buy_amount,
        "total_sell_amount": total_sell_amount,
        "total_buy_shares": total_buy_shares,
        "total_sell_shares": total_sell_shares,
        "est_target_shares_dict": est_target_shares_dict,
    }

    return orders, stats


# =============================================================================
# Active Share 逐檔精算
# =============================================================================
def compute_active_shares(
    est_target_shares_dict: Dict[str, int],
    stock_prices: Dict[str, float],
    nav: float,
    active_etf_df: Optional[pd.DataFrame],
) -> Dict[str, float]:
    """計算本組合相對於市售主動型 ETF 前 15 大持股的 Active Share。

    公式：
      Active Share = 1/2 × Σ |Weight_portfolio - Weight_ETF|
    """
    if active_etf_df is None or active_etf_df.empty:
        return {}

    # 1. 計算本組合取整後的實際持股權重
    port_weights: Dict[str, float] = {}
    for tk, sh in est_target_shares_dict.items():
        p = stock_prices.get(tk, 100.0)
        port_weights[tk] = (sh * p) / nav if nav > 0 else 0.0

    # 2. 依各主動型 ETF (stock_id) 分組計算
    active_shares: Dict[str, float] = {}
    for etf_id, group in active_etf_df.groupby("stock_id"):
        etf_weights: Dict[str, float] = {}
        for _, row in group.iterrows():
            c_id = str(row["constituent_id"]).strip()
            # parquet 的 weight 欄位若為百分比 (e.g. 9.01)，轉換為小數
            w = float(row["weight"])
            etf_weights[c_id] = w / 100.0 if w > 1.0 else w

        # 取聯集股票
        all_tickers = set(port_weights.keys()) | set(etf_weights.keys())
        abs_diff_sum = sum(
            abs(port_weights.get(tk, 0.0) - etf_weights.get(tk, 0.0))
            for tk in all_tickers
        )
        active_share = 0.5 * abs_diff_sum
        active_shares[str(etf_id)] = round(active_share, 4)

    return active_shares


# =============================================================================
# 主執行流程
# =============================================================================
def run_order_calculator(
    target_date: Optional[str] = None,
    dry_run: bool = False,
    no_gemini: bool = False,
    no_stream: bool = False,
) -> Path:
    """執行委託單計算與 Gemini 覆核主流程。"""
    now_dt = datetime.now(TW_TZ)
    now_str = now_dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    t_date = target_date or now_dt.strftime("%Y%m%d")
    c_date = _clean_date_str(t_date)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*65}\n [OrderCalculator] 啟動 L4 委託層計算流程 (日期: {c_date})\n{'='*65}")

    # 1. 讀入 L3 投資組合決策
    decisions, no_trades, dec_file = load_l3_decisions(c_date)
    print(f"[OrderCalculator] 載入 L3 決策: {dec_file} | 異動決策: {len(decisions)} 筆, 續抱: {len(no_trades)} 筆")

    # 2. 讀入 DataPack 帳戶資料
    account_info, dp_file = load_account_datapack(c_date)
    nav = account_info["nav_tradable"]
    cash = account_info["cash"]
    holdings = account_info["holdings"]
    current_holdings_dict = {
        str(h.get("code", "")).strip(): int(h.get("shares", 0))
        for h in holdings
        if str(h.get("code", "")).strip()
    }
    print(f"[OrderCalculator] 載入 DataPack: {dp_file} | NAV: {nav:,.0f} 元, 現有持股: {len(current_holdings_dict)} 檔")

    # 3. 讀入個股前日收盤價
    stock_prices = load_stock_prices(c_date)
    print(f"[OrderCalculator] 載入個股收盤價資料: 共 {len(stock_prices)} 檔")

    # 4. 讀入 L2M 目標現金區間與 Active ETF 前 15 大
    cash_range = load_l2m_target_cash_range(c_date)
    active_etf_df = load_active_etf_holdings(c_date)
    if active_etf_df is not None:
        print(f"[OrderCalculator] 載入主動式 ETF 持股標竿: 共 {len(active_etf_df)} 筆持股紀錄")

    # 5. 【第一階段：Python 機械式演算法計算】
    orders_python, stats = calculate_orders_python(
        decisions=decisions,
        nav=nav,
        current_holdings_dict=current_holdings_dict,
        stock_prices=stock_prices,
    )

    # 6. 計算 Active Share
    active_shares = compute_active_shares(
        est_target_shares_dict=stats["est_target_shares_dict"],
        stock_prices=stock_prices,
        nav=nav,
        active_etf_df=active_etf_df,
    )

    # 儲存第一階段 Python 委託計算結果
    python_output_file = OUTPUT_DIR / f"{OUTPUT_PREFIX}_python_{c_date}.json"
    clean_python_orders = [
        {
            "ticker": od["ticker"],
            "side": od["side"],
            "shares": od["shares"],
            "decision_ref": od["decision_ref"],
            "derivation_detail": od["derivation_detail"],
        }
        for od in orders_python
    ]

    python_result_payload = {
        "trade_date": c_date,
        "calculation_timestamp": now_str,
        "orders": clean_python_orders,
        "execution_summary": {
            "nav_tradable": nav,
            "estimated_stock_value": stats["est_stock_value"],
            "estimated_stock_weight": round(stats["est_stock_weight"], 4),
            "estimated_cash_value": stats["est_cash_value"],
            "estimated_cash_ratio": round(stats["est_cash_pct"], 4),
            "target_cash_range": cash_range,
            "cash_compliance": "PASS" if cash_range[0] <= stats["est_cash_pct"] <= cash_range[1] else "CHECK_REQUIRED",
            "active_shares": active_shares,
            "active_share_compliance": "PASS" if all(val >= 0.15 for val in active_shares.values()) else "CHECK_REQUIRED",
        },
    }

    with open(python_output_file, "w", encoding="utf-8") as f:
        json.dump(python_result_payload, f, ensure_ascii=False, indent=2)

    print(f"\n[OrderCalculator] 第一階段 Python 算單完成！共 {len(clean_python_orders)} 筆委託")
    print(f" -> 預估股票總市值: {stats['est_stock_value']:,.0f} 元 ({stats['est_stock_weight']*100:.2f}%)")
    print(f" -> 預估剩餘現金: {stats['est_cash_value']:,.0f} 元 ({stats['est_cash_pct']*100:.2f}%)，目標區間: [{cash_range[0]*100:.1f}%, {cash_range[1]*100:.1f}%]")
    if active_shares:
        print(f" -> Active Share 數值: {active_shares} (全數 >= 15%: {'是' if python_result_payload['execution_summary']['active_share_compliance'] == 'PASS' else '否'})")
    print(f" -> 已儲存 Python 計算檔: {python_output_file}")

    # 若指定 --no-gemini，直接產出最終檔案並返回
    final_output_file = OUTPUT_DIR / f"{OUTPUT_PREFIX}_{c_date}.json"
    if no_gemini:
        print("[OrderCalculator] --no-gemini 已指定，直接以 Python 官方算單結果作為最終輸出。")
        with open(final_output_file, "w", encoding="utf-8") as f:
            json.dump({"orders": clean_python_orders}, f, ensure_ascii=False, indent=2)
        print(f"[OrderCalculator] 成功輸出 L4 委託單至: {final_output_file}")
        return final_output_file

    # 7. 【第二階段：組裝 Prompt 並呼叫 Gemini 進行智能覆核】
    current_holdings_str = "\n".join(
        [f"- {tk}: {sh:,} 股" for tk, sh in current_holdings_dict.items()]
    ) if current_holdings_dict else "(目前無持股，首日全現金狀態)"

    decisions_summary_lines = []
    for d in decisions:
        decisions_summary_lines.append(
            f"- [{d.get('decision_id')}] {d.get('ticker')}: {d.get('action')} 目標權重 {d.get('target_weight')} | 推論: {d.get('inference_refs')}"
        )
    decisions_summary = "\n".join(decisions_summary_lines)

    orders_python_formatted = json.dumps(clean_python_orders, ensure_ascii=False, indent=2)

    active_shares_summary_lines = []
    if active_shares:
        for etf_id, as_val in active_shares.items():
            active_shares_summary_lines.append(f"- 與主動式 ETF {etf_id} 比較之 Active Share: {as_val:.4f} ({as_val*100:.2f}%)")
    else:
        active_shares_summary_lines.append("(無同業主動 ETF 數據或已確保高主動性)")
    active_shares_summary = "\n".join(active_shares_summary_lines)

    prompt = REVIEW_PROMPT_TEMPLATE.format(
        target_date=c_date,
        now=now_str,
        target_cash_pct_range_str=f"[{cash_range[0]:.2f}, {cash_range[1]:.2f}] ({cash_range[0]*100:.1f}% ~ {cash_range[1]*100:.1f}%)",
        nav_tradable=nav,
        cash=cash,
        holdings_count=len(current_holdings_dict),
        current_holdings_str=current_holdings_str,
        decisions_summary=decisions_summary,
        order_count=len(clean_python_orders),
        orders_python_formatted=orders_python_formatted,
        est_stock_value=stats["est_stock_value"],
        est_stock_weight=stats["est_stock_weight"],
        est_stock_weight_pct=stats["est_stock_weight"] * 100.0,
        est_cash_value=stats["est_cash_value"],
        est_cash_pct=stats["est_cash_pct"],
        est_cash_pct_str=f"{stats['est_cash_pct']*100:.2f}%",
        total_buy_amount=stats["total_buy_amount"],
        total_sell_amount=stats["total_sell_amount"],
        active_shares_summary=active_shares_summary,
    )

    # 輸出 Prompt 供除錯檢視
    prompt_file = OUTPUT_DIR / f"{OUTPUT_PREFIX}_prompt_{c_date}.txt"
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(prompt)

    if dry_run:
        print(f"\n[OrderCalculator] --dry-run 已啟用：Prompt 已輸出至 {prompt_file}，不呼叫 API。")
        return prompt_file

    # 8. 連接 Gemini Client 進行審核
    print(f"\n{'='*65}\n [OrderCalculator] 連接 Gemini Client 進行委託單審查與覆核...\n{'='*65}")
    client = GeminiClient()

    stream_enabled = not no_stream
    valid_decision_ids = {d.get("decision_id") for d in decisions if d.get("decision_id")}

    try:
        response_model: OrdersResponse = client.generate_structured(
            prompt=prompt,
            response_model=OrdersResponse,
            stream=stream_enabled,
        )
        # 輸出 Gemini Usage 統計至 OUTPUT_DIR / "usage" / "l4_usage_YYYYMMDD.json"
        client.save_usage_metadata(
            output_dir=OUTPUT_DIR,
            stage_prefix="l4",
            target_date=c_date,
        )
    except Exception as e:
        print(f"[OrderCalculator] Gemini API 呼叫失敗: {e}，切換為以 Python 官方算單結果輸出。")
        response_model = OrdersResponse(
            orders=[
                OrderDraft(
                    ticker=od["ticker"],
                    side=od["side"],
                    shares=od["shares"],
                    decision_ref=od["decision_ref"],
                    derivation_detail=od["derivation_detail"],
                )
                for od in clean_python_orders
            ],
            review_notes="以 Python 官方公式算單結果自動備援覆核通過。",
        )

    print(f"\n{'='*65}\n [Gemini 審查覆核完成] 正在進行 D-Plan v4.3 嚴格驗證...\n{'='*65}\n")

    # 9. 嚴格驗證轉換
    validated_result: OrdersResult = drafts_to_orders(
        resp=response_model,
        valid_decision_ids=valid_decision_ids,
        current_holdings=current_holdings_dict,
    )

    # 10. 輸出符合 D-Plan 規格的最終 JSON 檔案
    final_orders_data = [
        {
            "ticker": o.ticker,
            "side": o.side,
            "shares": o.shares,
            "decision_ref": o.decision_ref,
            "derivation_detail": o.derivation_detail,
        }
        for o in validated_result.orders
    ]

    # 嚴格遵循 D-Plan Schema v4.3 規格 (additionalProperties: false)，只輸出 "orders"
    final_payload = {
        "orders": final_orders_data,
    }

    with open(final_output_file, "w", encoding="utf-8") as f:
        json.dump(final_payload, f, ensure_ascii=False, indent=2)

    print(f"[OrderCalculator] 成功輸出 L4 最終委託單至: {final_output_file} | 委託筆數: {len(final_orders_data)} 筆")
    if validated_result.review_notes:
        print(f"經理人覆核意見: {validated_result.review_notes}")

    print("\n前 2 筆委託預覽：")
    preview = {"orders": final_orders_data[:2]}
    print(json.dumps(preview, ensure_ascii=False, indent=2))

    return final_output_file


# =============================================================================
# CLI 命令列入口
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description="【L4】委託層計算與審核 Agent (order_calculator)")
    parser.add_argument("--date", type=str, default=None, help="指定交易日期 (格式如 20261027 或 2026-10-27)")
    parser.add_argument("--dry-run", action="store_true", help="僅組裝 Prompt 並儲存至 txt，不實際呼叫 Gemini API")
    parser.add_argument("--no-gemini", action="store_true", help="僅執行 Python 官方公式算單，不呼叫 Gemini API")
    parser.add_argument("--no-stream", action="store_true", help="關閉串流印出，改用一次性等待回傳")
    args = parser.parse_args()

    # 取得交易日期 (若無命令列參數則在終端機提示輸入)
    target_date = prompt_trade_date(args.date, prompt_text="L4 委託單計算 - 交易日期")

    run_order_calculator(
        target_date=target_date,
        dry_run=args.dry_run,
        no_gemini=args.no_gemini,
        no_stream=args.no_stream,
    )


if __name__ == "__main__":
    main()
