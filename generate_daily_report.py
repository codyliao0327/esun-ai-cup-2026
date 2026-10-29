"""每日投資決策與投資組合回顧報告生成器 (generate_daily_report.py)。

依據今日 D-Plan JSON 檔與 DataPack (Raw/Processed) 資料：
1. 提取 DataPack 現有帳戶資產現況 (NAV、現有現金、現金比、持股檔數、合規狀態)。
2. 提取 L2M 市場整體判斷、操作姿態、淨曝險意圖、推論邏輯與目標現金承諾區間。
3. 統計原本持股部位 (按權重由高至低排序、股數、張數、收盤價、現值)。
4. 匯總今日買賣部位增減明細 (BUY/SELL、張數、股數、金額、目標權重，以及「為什麼增減」的決策理由)。
5. 匯總今日續抱部位 (HOLD / 0委託理由)。
6. 試算交割財務收支 (買進總額、賣出總額、淨花費/淨賺金額、執行後預估現金與現金比)。
7. 與 L2M 承諾的現金區間、淨曝險意圖、官方持股檔數限制進行全方位對照檢驗。
8. 輸出高品質 Markdown 報告至 data/D-Paln_Output/reports/。

用法::
    python generate_daily_report.py                      # 處理最新日期的 D-Plan
    python generate_daily_report.py --date 20261028     # 指定特定交易日
    python generate_daily_report.py --dplan-path <path> # 直接指定 D-Plan JSON 檔案
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 設定 code/ 為匯入路徑
CODE_DIR = Path(__file__).resolve().parent
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from configs.date_utils import clean_date_str, format_iso_trade_date, prompt_trade_date

ROOT = CODE_DIR.parent
DATA_ROOT = ROOT / "data"
DPLAN_DIR = DATA_ROOT / "D-Paln_Output" / "final_dplan"
DATAPACK_RAW_DIR = DATA_ROOT / "Datapack" / "Raw"
REPORT_DIR = DATA_ROOT / "D-Paln_Output" / "reports"
TW_TZ = timezone(timedelta(hours=8))


def _clean_date(date_str: str) -> str:
    return clean_date_str(date_str)


def find_dplan_file(target_date: Optional[str] = None, custom_path: Optional[Path] = None) -> Path:
    """尋找指定日期的 D-Plan JSON 檔案。"""
    if custom_path and custom_path.exists():
        return custom_path

    if not DPLAN_DIR.exists():
        raise FileNotFoundError(f"找不到 D-Plan 輸出目錄: {DPLAN_DIR}")

    c_date = _clean_date(target_date) if target_date else ""
    iso_date = format_iso_trade_date(c_date) if c_date else ""

    files = sorted(DPLAN_DIR.glob("D-Plan_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError(f"在 {DPLAN_DIR} 找不到任何 D-Plan JSON 檔案！")

    if c_date:
        for p in files:
            if c_date in p.name or iso_date in p.name:
                return p
        raise FileNotFoundError(f"在 {DPLAN_DIR} 找不到日期為 {c_date} (或 {iso_date}) 的 D-Plan JSON 檔案！")

    # 預設回傳最新修改的一個
    return files[0]


def find_datapack_raw_file(target_date: Optional[str] = None, custom_path: Optional[Path] = None) -> Optional[Path]:
    """尋找指定日期的 DataPack Raw JSON 檔案。"""
    if custom_path and custom_path.exists():
        return custom_path

    if not DATAPACK_RAW_DIR.exists():
        return None

    c_date = _clean_date(target_date) if target_date else ""
    iso_date = format_iso_trade_date(c_date) if c_date else ""

    files = sorted(DATAPACK_RAW_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None

    if c_date:
        for p in files:
            if p.stem.endswith(f"_{c_date}") or p.stem.endswith(f"_{iso_date}"):
                return p
        return None

    return files[0]


def load_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_daily_report(
    target_date: Optional[str] = None,
    dplan_path: Optional[Path] = None,
    datapack_path: Optional[Path] = None,
) -> Tuple[str, Path]:
    """組裝每日 Markdown 回顧報告並輸出存檔。"""
    dplan_file = find_dplan_file(target_date=target_date, custom_path=dplan_path)
    dplan_data = load_json(dplan_file)

    trade_date = dplan_data.get("trade_date", "")
    team_id = dplan_data.get("team_id", "TEAM_11402")
    c_date = _clean_date(trade_date) or _clean_date(target_date or "")

    dp_file = find_datapack_raw_file(target_date=c_date, custom_path=datapack_path)
    dp_data = load_json(dp_file) if dp_file else {}

    # 1. 帳戶現況 (DataPack)
    account = dp_data.get("account") or {}
    holdings_raw = dp_data.get("holdings") or []
    compliance = dp_data.get("compliance") or {}

    nav_tradable = float(account.get("nav_tradable", 1000000000.0) or 1000000000.0)
    current_cash = float(account.get("cash", 1000000000.0) or 1000000000.0)
    cash_ratio = (
        float(account.get("cash_ratio_tradable"))
        if account.get("cash_ratio_tradable") is not None
        else (current_cash / nav_tradable if nav_tradable > 0 else 1.0)
    )
    aum = float(account.get("aum", nav_tradable) or nav_tradable)
    holdings_count = int(account.get("holdings_count", len([h for h in holdings_raw if (h.get("shares") or 0) > 0])))
    violations = compliance.get("violations", 0)
    notices = compliance.get("notices", 0)

    # 2. L2M 市場觀點與承諾
    mv = dplan_data.get("market_view") or {}
    regime = mv.get("regime", "neutral")
    stance = mv.get("stance", "neutral")
    posture = mv.get("posture") or {}
    net_exposure_intent = posture.get("net_exposure_intent", "hold")
    target_cash_range = posture.get("target_cash_pct_range", [0.0, 0.25])
    mv_logic = mv.get("logic", "無推論邏輯說明")
    mv_counter = mv.get("counter_evidence")

    # 3. 股票收盤價字典 (從 Observations 取得最新價)
    observations = dplan_data.get("observations") or []
    obs_prices: Dict[str, float] = {}
    for obs in observations:
        vals = obs.get("values", {})
        topic = obs.get("topic", "")
        code = ""
        if topic.startswith("stock_"):
            code = topic.replace("stock_", "").strip()
        elif "ticker" in vals:
            code = str(vals["ticker"]).strip()

        if "close_latest" in vals and code:
            try:
                obs_prices[code] = float(vals["close_latest"])
            except (ValueError, TypeError):
                pass

    # 4. 原有部位清單整理 (依目前權重或市值由大到小排序)
    holdings_list = []
    for h in holdings_raw:
        shares = int(h.get("shares") or 0)
        code = str(h.get("code") or "")
        close_p = float(h.get("close_price") or obs_prices.get(code, 0.0))
        weight = h.get("tradable_weight")
        weight_val = float(weight) if weight is not None else (shares * close_p / nav_tradable if nav_tradable > 0 else 0.0)
        market_val = shares * close_p
        lots = shares / 1000.0

        if shares > 0:
            holdings_list.append({
                "code": code,
                "shares": shares,
                "lots": lots,
                "close_price": close_p,
                "market_value": market_val,
                "weight": weight_val,
            })

    # 權重由高到低排序
    holdings_list.sort(key=lambda x: x["weight"], reverse=True)
    total_holdings_val = sum(h["market_value"] for h in holdings_list)

    # 5. 決策與委託明細 (Decisions & Orders)
    decisions = dplan_data.get("decisions") or []
    no_trade_decisions = dplan_data.get("no_trade_decisions") or []
    orders = dplan_data.get("orders") or []

    # 建立 decision_ref 對照字典
    decision_map = {d.get("decision_id"): d for d in decisions if d.get("decision_id")}

    order_details = []
    total_buy_amt = 0.0
    total_sell_amt = 0.0

    for ord_item in orders:
        ticker = str(ord_item.get("ticker"))
        side = ord_item.get("side", "").upper()
        shares = int(ord_item.get("shares") or 0)
        d_ref = ord_item.get("decision_ref", "")
        derivation = ord_item.get("derivation_detail", "")
        lots = shares // 1000

        # 取得參考價格 (優先由 observations 取得，或持股收盤價)
        ref_price = obs_prices.get(ticker, 0.0)
        if ref_price == 0.0:
            for h in holdings_list:
                if h["code"] == ticker:
                    ref_price = h["close_price"]
                    break

        est_amount = shares * ref_price

        # 取得決策理由與目標權重
        d_info = decision_map.get(d_ref, {})
        target_weight = d_info.get("target_weight", 0.0)
        rationale = d_info.get("decision_rationale", derivation or "無提供決策理由")

        if side == "BUY":
            total_buy_amt += est_amount
        elif side == "SELL":
            total_sell_amt += est_amount

        order_details.append({
            "ticker": ticker,
            "side": side,
            "shares": shares,
            "lots": lots,
            "ref_price": ref_price,
            "est_amount": est_amount,
            "target_weight": target_weight,
            "decision_ref": d_ref,
            "rationale": rationale,
            "derivation": derivation,
        })

    # 6. 財務試算與現金水位計算
    net_cash_flow = total_buy_amt - total_sell_amt  # 正數代表淨花費 (現金減少)
    est_final_cash = current_cash - net_cash_flow
    est_final_cash_ratio = est_final_cash / nav_tradable if nav_tradable > 0 else 0.0

    # 7. L2M 承諾區間與意圖對照檢驗
    min_cash_pct, max_cash_pct = target_cash_range[0], target_cash_range[1]
    is_cash_in_range = (min_cash_pct - 1e-4) <= est_final_cash_ratio <= (max_cash_pct + 1e-4)

    # 淨曝險意圖檢驗
    # increase: 淨買超 (total_buy_amt > total_sell_amt)
    # reduce: 淨賣超 (total_sell_amt > total_buy_amt)
    # hold: 差距在 NAV 2% 容差內
    net_flow_pct_of_nav = (total_buy_amt - total_sell_amt) / nav_tradable if nav_tradable > 0 else 0.0
    intent_check_pass = True
    intent_check_note = ""

    if net_exposure_intent == "increase":
        if total_buy_amt >= total_sell_amt:
            intent_check_note = f"符合承諾：今日淨買入 NT$ {total_buy_amt - total_sell_amt:,.0f} 元 (+{net_flow_pct_of_nav*100:.2f}% NAV)"
        else:
            intent_check_pass = False
            intent_check_note = f"⚠️ 警告：承諾 increase 但今日為淨賣出 NT$ {total_sell_amt - total_buy_amt:,.0f} 元"
    elif net_exposure_intent == "reduce":
        if total_sell_amt >= total_buy_amt:
            intent_check_note = f"符合承諾：今日淨賣出 NT$ {total_sell_amt - total_buy_amt:,.0f} 元 (-{abs(net_flow_pct_of_nav)*100:.2f}% NAV)"
        else:
            intent_check_pass = False
            intent_check_note = f"⚠️ 警告：承諾 reduce 但今日為淨買入 NT$ {total_buy_amt - total_sell_amt:,.0f} 元"
    elif net_exposure_intent == "hold":
        if abs(net_flow_pct_of_nav) <= 0.02 + 1e-4:
            intent_check_note = f"符合承諾：淨異動比例 {net_flow_pct_of_nav*100:+.2f}% 在 NAV 2% 容差範圍內"
        else:
            intent_check_pass = False
            intent_check_note = f"⚠️ 警告：承諾 hold 但淨異動比例 {net_flow_pct_of_nav*100:+.2f}% 超出 2% 容差"

    # 預估持股檔數
    # 現有持股中未全賣出者 + 今日新買進者
    held_codes = {h["code"] for h in holdings_list}
    sold_out_codes = {o["ticker"] for o in order_details if o["side"] == "SELL" and o["target_weight"] == 0.0}
    new_buy_codes = {o["ticker"] for o in order_details if o["side"] == "BUY" and o["ticker"] not in held_codes}
    est_final_holdings_count = len(held_codes - sold_out_codes) + len(new_buy_codes)
    is_holdings_count_valid = 20 <= est_final_holdings_count <= 30

    # 8. 組裝 Markdown 報告內容
    now_str = datetime.now(TW_TZ).strftime("%Y-%m-%d %H:%M:%S")
    agent_meta = dplan_data.get("agent_metadata") or {}
    model_version = agent_meta.get("model_version", "Google Gemini")
    code_version = agent_meta.get("code_version", "main")

    md_lines = []
    md_lines.append(f"# 📊 每日投資決策與投資組合回顧報告 ({trade_date})")
    md_lines.append("")
    md_lines.append(f"> **報告生成時間**：`{now_str}` (台北時間)  ")
    md_lines.append(f"> **隊伍編號**：`{team_id}` ｜ **模型版本**：`{model_version}` ｜ **程式版本**：`{code_version}`  ")
    md_lines.append(f"> **D-Plan 檔案**：`{dplan_file.name}`")
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")

    # 一、帳戶資產與現況快照
    md_lines.append("## 一、 官方帳戶現況快照 (DataPack 現有資訊)")
    md_lines.append("")
    md_lines.append("| 項目 | 數值 | 說明 |")
    md_lines.append("| :--- | :--- | :--- |")
    md_lines.append(f"| **可交易淨值 (NAV Tradable)** | **NT$ {nav_tradable:,.0f} 元** | 個股權重與現金比計算基準 |")
    md_lines.append(f"| **目前可動用現金 (Cash)** | **NT$ {current_cash:,.0f} 元** | 未執行今日委託前現金水位 |")
    md_lines.append(f"| **目前現金比例** | **{cash_ratio * 100:.2f}%** | 現金佔 NAV 比例 |")
    md_lines.append(f"| **總資產 (AUM)** | **NT$ {aum:,.0f} 元** | 含應收配息與市值 |")
    md_lines.append(f"| **現有持股檔數** | **{holdings_count} 檔** | 官方規範要求持股 20 ~ 30 檔 |")
    md_lines.append(f"| **合規狀態** | **違規 {violations} 次 / 警告 {notices} 次** | 累計違規狀態 |")
    md_lines.append("")

    # 二、L2M 大盤分析與承諾
    md_lines.append("## 二、 L2M 大盤分析、操作方向與水位承諾")
    md_lines.append("")
    regime_emoji = "🟢" if regime == "risk_on" else ("🔴" if regime == "risk_off" else "🟡")
    stance_emoji = "🚀" if stance == "aggressive" else ("🛡️" if stance == "defensive" else "⚖️")
    intent_emoji = "📈" if net_exposure_intent == "increase" else ("📉" if net_exposure_intent == "reduce" else "⏸️")

    md_lines.append("| 決策維度 | 研判宣告 | 意義解讀 |")
    md_lines.append("| :--- | :--- | :--- |")
    md_lines.append(f"| **市場體制 (Regime)** | {regime_emoji} `{regime}` | 市場環境偏向風險偏好 / 中性 / 風險規避 |")
    md_lines.append(f"| **操作姿態 (Stance)** | {stance_emoji} `{stance}` | 策略採取積極進攻 / 中性配置 / 保守防禦 |")
    md_lines.append(f"| **淨曝險意圖 (Intent)** | {intent_emoji} `{net_exposure_intent}` | 預計進行淨買超 / 維持曝險 / 淨賣超 |")
    md_lines.append(f"| **目標現金承諾區間** | 🎯 **[{min_cash_pct*100:.2f}%, {max_cash_pct*100:.2f}%]** | 今日委託執行後現金比例必須落在此區間內 |")
    md_lines.append("")
    md_lines.append("### 🧠 大盤核心推論邏輯 (Logic)")
    md_lines.append(f"> {mv_logic}")
    md_lines.append("")
    if mv_counter:
        md_lines.append("### ⚠️ 反向證據與風險提示 (Counter Evidence)")
        md_lines.append(f"> {mv_counter}")
        md_lines.append("")

    # 三、原本持有部位明細
    md_lines.append("## 三、 原有持股部位明細 (依目前權重由高至低排序)")
    md_lines.append("")
    if holdings_list:
        md_lines.append(f"共有 **{len(holdings_list)}** 檔持股，持股市值合計 **NT$ {total_holdings_val:,.0f} 元**：")
        md_lines.append("")
        md_lines.append("| 排名 | 證券代號 | 持有股數 | 持有張數 | 昨日收盤價 (元) | 目前現值 (元) | 目前權重 (%) |")
        md_lines.append("| :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
        for i, h in enumerate(holdings_list, 1):
            md_lines.append(
                f"| {i} | `{h['code']}` | {h['shares']:,} | {h['lots']:.1f} 張 | "
                f"{h['close_price']:,.2f} | {h['market_value']:,.0f} | {h['weight']*100:.2f}% |"
            )
        md_lines.append("")
    else:
        md_lines.append("*(帳戶目前為空手全現金狀態，尚無昨日留倉部位)*\n")

    # 四、今日部位增減明細與決策理由
    md_lines.append("## 四、 今日部位增減決策與委託執行明細")
    md_lines.append("")
    if order_details:
        md_lines.append(f"今日共產生 **{len(order_details)}** 筆交易委託單：")
        md_lines.append("")
        md_lines.append("| 決策ID | 股票代號 | 買賣動作 | 委託張數 | 委託股數 | 參考市價 | 預估交易金額 | 目標權重 | 為什麼調整部位？(決策理由) |")
        md_lines.append("| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |")
        for o in order_details:
            side_badge = "🟢 **BUY (買進)**" if o["side"] == "BUY" else "🔴 **SELL (賣出)**"
            md_lines.append(
                f"| `{o['decision_ref']}` | `{o['ticker']}` | {side_badge} | {o['lots']} 張 | "
                f"{o['shares']:,} | {o['ref_price']:,.2f} | NT$ {o['est_amount']:,.0f} | "
                f"{o['target_weight']*100:.2f}% | {o['rationale']} |"
            )
        md_lines.append("")
    else:
        md_lines.append("*(今日無任何部位買賣異動委託)*\n")

    # 續抱清單
    if no_trade_decisions:
        md_lines.append("### 📌 續抱無異動部位 (Hold / No Trade)")
        md_lines.append("")
        md_lines.append("| 股票代號 | 維持目標權重 | 續抱原因說明 |")
        md_lines.append("| :---: | :---: | :--- |")
        for nt in no_trade_decisions:
            md_lines.append(f"| `{nt.get('ticker')}` | {float(nt.get('target_weight', 0.0))*100:.2f}% | {nt.get('decision_rationale', '維持原部位續抱')} |")
        md_lines.append("")

    # 五、財務收支試算與 L2M 承諾對照檢驗
    md_lines.append("## 五、 財務試算與 L2M 承諾對照檢驗")
    md_lines.append("")
    md_lines.append("### 💰 資金收支與執行後現金試算")
    md_lines.append("")
    md_lines.append("| 財務項目 | 金額 (新台幣) | 佔 NAV 比例 | 備註說明 |")
    md_lines.append("| :--- | :--- | :--- | :--- |")
    md_lines.append(f"| **買進總金額 (Gross Buy)** | NT$ {total_buy_amt:,.0f} 元 | {total_buy_amt/nav_tradable*100:.2f}% | 今日預估買單資金需求 |")
    md_lines.append(f"| **賣出總金額 (Gross Sell)** | NT$ {total_sell_amt:,.0f} 元 | {total_sell_amt/nav_tradable*100:.2f}% | 今日預估賣單回籠現金 |")
    net_flow_str = f"淨花費 NT$ {net_cash_flow:,.0f} 元 (流出)" if net_cash_flow >= 0 else f"淨套現 NT$ {abs(net_cash_flow):,.0f} 元 (流入)"
    md_lines.append(f"| **淨交易收支 (Net Cash Flow)** | **{net_flow_str}** | **{abs(net_cash_flow)/nav_tradable*100:.2f}%** | 買賣互抵交割款 |")
    md_lines.append(f"| **目前現有現金** | NT$ {current_cash:,.0f} 元 | {cash_ratio*100:.2f}% | 交易前帳戶可動用現金 |")
    md_lines.append(f"| **執行後預估剩餘現金** | **NT$ {est_final_cash:,.0f} 元** | **{est_final_cash_ratio*100:.2f}%** | 預估結算後留存現金 |")
    md_lines.append("")

    md_lines.append("### 🎯 風控與 L2M 承諾全方位對照檢驗")
    md_lines.append("")
    cash_check_badge = "🟢 **PASS (達標)**" if is_cash_in_range else "🔴 **FAIL (偏離)**"
    intent_check_badge = "🟢 **PASS (符合)**" if intent_check_pass else "⚠️ **ALERT (警示)**"
    holdings_check_badge = "🟢 **PASS (合規)**" if is_holdings_count_valid else "🔴 **FAIL (違規)**"

    md_lines.append("| 檢驗項目 | 承諾與規範標準 | 今日執行試算結果 | 合規判定 | 說明與對照 |")
    md_lines.append("| :--- | :--- | :--- | :---: | :--- |")
    md_lines.append(
        f"| **目標現金水位區間** | **[{min_cash_pct*100:.2f}%, {max_cash_pct*100:.2f}%]** | "
        f"**{est_final_cash_ratio*100:.2f}%** (NT$ {est_final_cash:,.0f}) | {cash_check_badge} | "
        f"{'預估現金比例精準落於 L2M 承諾目標區間內' if is_cash_in_range else '⚠️ 預估現金比超出承諾區間，需複查算單'} |"
    )
    md_lines.append(
        f"| **淨曝險方向意圖** | `{net_exposure_intent}` | "
        f"{'淨買超' if net_cash_flow > 0 else ('淨賣超' if net_cash_flow < 0 else '淨持平')} {abs(net_cash_flow)/nav_tradable*100:.2f}% NAV | "
        f"{intent_check_badge} | {intent_check_note} |"
    )
    md_lines.append(
        f"| **投資組合持股檔數** | 20 ~ 30 檔 | 預估結算後 **{est_final_holdings_count} 檔** | {holdings_check_badge} | "
        f"{'符合官方 20~30 檔要求' if is_holdings_count_valid else '⚠️ 持股檔數未達或超過官方上限'} |"
    )
    md_lines.append("")

    # 結論與經理人覆核摘要
    md_lines.append("## 六、 投資經理人覆核結論")
    md_lines.append("")
    if is_cash_in_range and intent_check_pass and is_holdings_count_valid:
        md_lines.append("✅ **系統自動覆核結果：全數通過**。")
        md_lines.append("- 現金承諾、曝險意圖、持股檔數皆符合 L2M 與玉山競賽合規規範。")
        md_lines.append("- 本 D-Plan 已完成全量因果鏈審查與格式校驗，可安心上傳競賽系統。")
    else:
        md_lines.append("⚠️ **系統自動覆核結果：存在風控或承諾偏差警示**！")
        if not is_cash_in_range:
            md_lines.append(f"- 預估現金比例 `{est_final_cash_ratio*100:.2f}%` 偏離 L2M 承諾區間 `[{min_cash_pct*100:.2f}%, {max_cash_pct*100:.2f}%]`。")
        if not intent_check_pass:
            md_lines.append(f"- {intent_check_note}。")
        if not is_holdings_count_valid:
            md_lines.append(f"- 預估持股檔數 `{est_final_holdings_count}` 檔不符合官方規定 (20~30 檔)。")
    md_lines.append("")

    report_content = "\n".join(md_lines) + "\n"

    # 輸出至檔案
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_file = REPORT_DIR / f"Daily_Decision_Report_{c_date}.md"
    report_file.write_text(report_content, encoding="utf-8")
    return report_content, report_file


def main():
    parser = argparse.ArgumentParser(description="產生每日投資決策與投資組合回顧 Markdown 報告")
    parser.add_argument("--date", type=str, default=None, help="目標交易日期 (格式 YYYYMMDD 或 YYYY-MM-DD)")
    parser.add_argument("--dplan-path", type=Path, default=None, help="手動指定 D-Plan JSON 檔案路徑")
    parser.add_argument("--datapack-path", type=Path, default=None, help="手動指定 DataPack Raw JSON 檔案路徑")
    args = parser.parse_args()

    t_date = prompt_trade_date(args.date, prompt_text="決策回顧報告 - 交易日期")
    c_date = _clean_date(t_date)

    content, out_path = build_daily_report(
        target_date=c_date,
        dplan_path=args.dplan_path,
        datapack_path=args.datapack_path,
    )
    print(f"\n[DailyReport] 成功產出每日決策回顧報告：\n -> {out_path}\n")


if __name__ == "__main__":
    main()
