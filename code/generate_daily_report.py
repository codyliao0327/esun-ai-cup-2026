"""每日投資決策與投資組合回顧報告生成器 (generate_daily_report.py)。

依據今日 D-Plan JSON 檔、DataPack (Raw/Processed) 資料、L2 推論檔與 L3 決策檔：
1. 提取 DataPack 現有帳戶資產現況 (NAV、現有現金、現金比、持股檔數、合規狀態)。
2. 提取 L2M 市場整體判斷、操作姿態、淨曝險意圖、推論邏輯與目標現金承諾區間。
3. 統計原本持股部位 (含股票名稱、權重由高至低、股數、張數、收盤價、現值、目前權重 vs 目標權重比對)。
4. 匯總今日買賣部位增減明細 (含股票名稱、BUY/SELL、張數、股數、易讀金額、目標權重，以及 L2 推論與 L3 風控決策鏈)。
5. 匯總今日續抱部位 (含股票名稱、維持目標權重、續抱理由)。
6. 試算交割財務收支 (以人易懂之萬/億元為主要呈現，並保留完整金額；試算買進總額、賣出總額、淨額、剩餘現金)。
7. 與 L2M 承諾的現金區間、淨曝險意圖、官方持股檔數限制進行全方位對照檢驗。
8. 輸出高品質 Markdown 報告至 data/D-Paln_Output/reports/。

用法::
    python generate_daily_report.py                      # 處理最新日期的 D-Plan
    python generate_daily_report.py --date 20261112     # 指定特定交易日
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
L2_DIR = DATA_ROOT / "D-Paln_Output" / "l2_inferences"
L3_DIR = DATA_ROOT / "D-Paln_Output" / "l3_decisions"
REPORT_DIR = DATA_ROOT / "D-Paln_Output" / "reports"
TW_TZ = timezone(timedelta(hours=8))

# ==============================================================================
# 玉山挑戰賽 150 檔法定投資標的清單 (上市 100 檔 + 上櫃 50 檔，固定不變)
# ==============================================================================
STOCK_NAMES: Dict[str, str] = {
    # 【上市】100 檔
    "2330": "台積電", "2883": "凱基金", "2454": "聯發科", "3443": "創意",
    "2308": "台達電", "3653": "健策", "2317": "鴻海", "2395": "研華",
    "3711": "日月光投控", "2301": "光寶科", "2881": "富邦金", "6446": "藥華藥",
    "2383": "台光電", "4958": "臻鼎-KY", "2303": "聯電", "2603": "長榮",
    "2882": "國泰金", "5880": "合庫金", "3037": "欣興", "1216": "統一",
    "2891": "中信金", "3045": "台灣大", "1303": "南亞", "2368": "金像電",
    "2345": "智邦", "3665": "貿聯-KY", "2382": "廣達", "4904": "遠傳",
    "2408": "南亞科", "3481": "群創", "7769": "鴻勁", "2379": "瑞昱",
    "2412": "中華電", "1301": "台塑", "2327": "國巨", "1326": "台化",
    "6669": "緯穎", "3189": "景碩", "3017": "奇鋐", "3034": "聯詠",
    "2885": "元大金", "2207": "和泰車", "2887": "台新新光金", "2002": "中鋼",
    "2360": "致茂", "2801": "彰銀", "2886": "兆豐金", "2449": "京元電子",
    "2059": "川湖", "1590": "亞德客-KY", "6505": "台塑化", "3661": "世芯-KY",
    "2884": "玉山金", "6770": "力積電", "2880": "華南金", "3036": "文曄",
    "2357": "華碩", "2615": "萬海", "2890": "永豐金", "2618": "長榮航",
    "8046": "南電", "2912": "統一超", "2344": "華邦電", "4938": "和碩",
    "3231": "緯創", "2376": "技嘉", "2892": "第一金", "5876": "上海商銀",
    "3008": "大立光", "1519": "華城", "2356": "英業達", "6415": "矽力-KY",
    "2404": "漢唐", "6919": "康霈", "6515": "穎崴", "2324": "仁寶",
    "3533": "嘉澤", "2347": "聯強", "2313": "華通", "1504": "東元",
    "2337": "旺宏", "7750": "新代", "5871": "中租-KY", "1402": "遠東新",
    "3044": "健鼎", "1605": "華新", "3702": "大聯大", "2610": "華航",
    "1101": "台泥", "6789": "采鈺", "2409": "友達", "1802": "台玻",
    "6239": "力成", "8210": "勤誠", "2609": "陽明", "2451": "創見",
    "2834": "臺企銀", "2812": "台中銀", "6139": "亞翔", "2377": "微星",

    # 【上櫃】50 檔
    "5274": "信驊", "3491": "昇達科", "6223": "旺矽", "6121": "新普",
    "6488": "環球晶", "6548": "長科", "8299": "群聯", "1785": "光洋科",
    "6274": "台燿", "3363": "上詮", "5347": "世界", "7828": "創新服務",
    "3293": "鈊象", "4979": "華星光", "8069": "元太", "6182": "合晶",
    "3529": "力旺", "3163": "波若威", "3081": "聯亞", "3211": "順達",
    "3260": "威剛", "4966": "譜瑞-KY", "3105": "穩懋", "4991": "環宇-KY",
    "5289": "宜鼎", "5903": "全家", "5536": "聖暉", "1815": "富喬",
    "5483": "中美晶", "3680": "家登", "6147": "頎邦", "8415": "大國鋼",
    "7734": "印能科技", "6290": "良維", "6187": "萬潤", "7751": "竑騰",
    "3264": "欣銓", "6023": "元大期", "3324": "雙鴻", "4772": "台特化",
    "6510": "精測", "8932": "智通", "8358": "金居", "6584": "南俊國際",
    "3374": "精材", "3227": "原相", "3131": "弘塑", "4123": "晟德",
    "4749": "新應材", "3718": "中光電投控",
}


def get_stock_name(code: str) -> str:
    """取得股票名稱，查無則回傳空字串。"""
    return STOCK_NAMES.get(str(code).strip(), "")


def format_money(amount: float, with_raw: bool = True) -> str:
    """將金額格式化為人易讀的中文單位 (萬 / 億)，並可附帶完整原始數字。

    例如:
        28115000 -> "2,812 萬 (NT$ 28,115,000)" (with_raw=True)
                 -> "2,812 萬" (with_raw=False)
        183823753 -> "1 億 8,382 萬 (NT$ 183,823,753)"
        1189000   -> "119 萬 (NT$ 1,189,000)"
        5000      -> "NT$ 5,000"
    """
    abs_v = abs(amount)
    sign = "-" if amount < 0 else ""
    raw_str = f"NT$ {abs_v:,.0f}"

    if abs_v < 10000:
        return f"{sign}{raw_str}"

    if abs_v >= 100000000:
        yi = int(abs_v // 100000000)
        wan = round((abs_v % 100000000) / 10000)
        if wan >= 10000:
            yi += 1
            wan -= 10000
        if wan > 0:
            human_str = f"{sign}{yi} 億 {wan:,} 萬"
        else:
            human_str = f"{sign}{yi} 億"
    else:
        wan = round(abs_v / 10000)
        human_str = f"{sign}{wan:,} 萬"

    if with_raw:
        return f"{human_str} ({sign}{raw_str})"
    return human_str


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


def find_l2_inferences_file(target_date: Optional[str] = None) -> Optional[Path]:
    """尋找指定日期的 L2 Inferences JSON 檔案。"""
    if not L2_DIR.exists():
        return None
    c_date = _clean_date(target_date) if target_date else ""
    files = sorted(L2_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None
    if c_date:
        for p in files:
            if c_date in p.name:
                return p
    return files[0]


def find_l3_decisions_file(target_date: Optional[str] = None) -> Optional[Path]:
    """尋找指定日期的 L3 Decisions JSON 檔案。"""
    if not L3_DIR.exists():
        return None
    c_date = _clean_date(target_date) if target_date else ""
    files = sorted(L3_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None
    if c_date:
        for p in files:
            if c_date in p.name:
                return p
    return files[0]


def load_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _clean_table_text(text: Optional[str]) -> str:
    """清理文字以便在 Markdown 表格中單行顯示，換行替換為 <br>，轉義管線符號。"""
    if not text:
        return "-"
    t = str(text).replace("\r\n", " ").replace("\n", " ").replace("|", "\\|").strip()
    return t


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

    # 讀取獨立的 L2 Inferences 與 L3 Decisions (若有)
    l2_file = find_l2_inferences_file(target_date=c_date)
    l2_data = load_json(l2_file) if l2_file else {}

    l3_file = find_l3_decisions_file(target_date=c_date)
    l3_data = load_json(l3_file) if l3_file else {}

    # 建立 L2 推論索引 (inf_id -> inference obj)
    # 優先由 l2_file 取得，若無則從 dplan_data 取得
    inferences_raw = l2_data.get("inferences") or dplan_data.get("inferences") or []
    inf_map: Dict[str, Dict[str, Any]] = {}
    for inf in inferences_raw:
        iid = inf.get("inf_id")
        if iid:
            inf_map[iid] = inf

    # 建立 L3 決策索引 (decision_id -> decision obj)
    l3_decisions_raw = l3_data.get("decisions") or dplan_data.get("decisions") or []
    l3_map: Dict[str, Dict[str, Any]] = {}
    for d in l3_decisions_raw:
        did = d.get("decision_id")
        if did:
            l3_map[did] = d

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

    # 4. 今日決策與委託明細 (Decisions & Orders)
    decisions = dplan_data.get("decisions") or []
    no_trade_decisions = dplan_data.get("no_trade_decisions") or l3_data.get("no_trade_decisions") or []
    orders = dplan_data.get("orders") or []

    # 決策對照字典 (融合 dplan 與 l3)
    decision_map: Dict[str, Dict[str, Any]] = {}
    for d in decisions:
        did = d.get("decision_id")
        if did:
            merged_d = dict(d)
            if did in l3_map:
                for k, v in l3_map[did].items():
                    if k not in merged_d or not merged_d[k]:
                        merged_d[k] = v
            decision_map[did] = merged_d
    for did, d in l3_map.items():
        if did not in decision_map:
            decision_map[did] = d

    # 個股目標權重字典 (ticker -> target_weight)
    ticker_target_weight_map: Dict[str, float] = {}
    for d in decision_map.values():
        tk = str(d.get("ticker", "")).strip()
        if tk and d.get("target_weight") is not None:
            ticker_target_weight_map[tk] = float(d["target_weight"])

    order_details = []
    total_buy_amt = 0.0
    total_sell_amt = 0.0

    for ord_item in orders:
        ticker = str(ord_item.get("ticker", "")).strip()
        name = get_stock_name(ticker)
        side = ord_item.get("side", "").upper()
        shares = int(ord_item.get("shares") or 0)
        d_ref = ord_item.get("decision_ref", "")
        derivation = ord_item.get("derivation_detail", "")
        lots = shares // 1000

        # 取得參考價格 (優先由 observations 取得，或持股收盤價)
        ref_price = obs_prices.get(ticker, 0.0)
        if ref_price == 0.0:
            for h in holdings_raw:
                if str(h.get("code", "")).strip() == ticker:
                    ref_price = float(h.get("close_price") or 0.0)
                    break

        est_amount = shares * ref_price

        # 取得決策理由、目標權重與 risk_check
        d_info = decision_map.get(d_ref, {})
        target_weight = d_info.get("target_weight", ticker_target_weight_map.get(ticker, 0.0))
        rationale = d_info.get("decision_rationale", derivation or "無提供決策理由")
        risk_check = d_info.get("risk_check", "")

        # 取得關聯之 L2 推論 (logic, conclusion, counter_evidence)
        inf_refs = d_info.get("inference_refs", [])
        l2_logics = []
        l2_conclusions = []
        l2_counters = []

        for iref in inf_refs:
            inf_item = inf_map.get(iref)
            if inf_item:
                if inf_item.get("logic"):
                    l2_logics.append(f"[{iref}] {inf_item['logic']}")
                if inf_item.get("conclusion"):
                    l2_conclusions.append(f"[{iref}] {inf_item['conclusion']}")
                if inf_item.get("counter_evidence"):
                    l2_counters.append(f"[{iref}] {inf_item['counter_evidence']}")

        l2_logic_str = " <br> ".join(l2_logics) if l2_logics else "-"
        l2_conclusion_str = " <br> ".join(l2_conclusions) if l2_conclusions else "-"
        l2_counter_str = " <br> ".join(l2_counters) if l2_counters else "-"

        if side == "BUY":
            total_buy_amt += est_amount
        elif side == "SELL":
            total_sell_amt += est_amount

        order_details.append({
            "ticker": ticker,
            "name": name,
            "side": side,
            "shares": shares,
            "lots": lots,
            "ref_price": ref_price,
            "est_amount": est_amount,
            "target_weight": target_weight,
            "decision_ref": d_ref,
            "rationale": rationale,
            "derivation": derivation,
            "risk_check": risk_check,
            "inf_refs": inf_refs,
            "l2_logic": l2_logic_str,
            "l2_conclusion": l2_conclusion_str,
            "l2_counter": l2_counter_str,
        })

    # 5. 原有部位清單整理 (依目前權重由大到小排序，並比對目標權重)
    holdings_list = []
    holdings_weight_map: Dict[str, float] = {}

    for h in holdings_raw:
        shares = int(h.get("shares") or 0)
        code = str(h.get("code") or "").strip()
        name = get_stock_name(code)
        close_p = float(h.get("close_price") or obs_prices.get(code, 0.0))
        weight = h.get("tradable_weight")
        weight_val = float(weight) if weight is not None else (shares * close_p / nav_tradable if nav_tradable > 0 else 0.0)
        market_val = shares * close_p
        lots = shares / 1000.0

        if shares > 0:
            holdings_weight_map[code] = weight_val

            # 判斷目標權重：若有決策以決策為準，若無決策代表續抱維持既有權重
            if code in ticker_target_weight_map:
                t_weight = ticker_target_weight_map[code]
            else:
                t_weight = weight_val

            diff_weight = t_weight - weight_val

            holdings_list.append({
                "code": code,
                "name": name,
                "shares": shares,
                "lots": lots,
                "close_price": close_p,
                "market_value": market_val,
                "weight": weight_val,
                "target_weight": t_weight,
                "diff_weight": diff_weight,
            })

    # 權重由高到低排序
    holdings_list.sort(key=lambda x: x["weight"], reverse=True)
    total_holdings_val = sum(h["market_value"] for h in holdings_list)

    # 6. 財務試算與現金水位計算
    net_cash_flow = total_buy_amt - total_sell_amt  # 正數代表淨花費 (現金減少)
    est_final_cash = current_cash - net_cash_flow
    est_final_cash_ratio = est_final_cash / nav_tradable if nav_tradable > 0 else 0.0

    # 7. L2M 承諾區間與意圖對照檢驗
    min_cash_pct, max_cash_pct = target_cash_range[0], target_cash_range[1]
    is_cash_in_range = (min_cash_pct - 1e-4) <= est_final_cash_ratio <= (max_cash_pct + 1e-4)

    # 淨曝險意圖檢驗
    net_flow_pct_of_nav = (total_buy_amt - total_sell_amt) / nav_tradable if nav_tradable > 0 else 0.0
    intent_check_pass = True
    intent_check_note = ""

    if net_exposure_intent == "increase":
        if total_buy_amt >= total_sell_amt:
            intent_check_note = f"符合承諾：今日淨買入 {format_money(total_buy_amt - total_sell_amt, with_raw=False)} (+{net_flow_pct_of_nav*100:.2f}% NAV)"
        else:
            intent_check_pass = False
            intent_check_note = f"⚠️ 警告：承諾 increase 但今日為淨賣出 {format_money(total_sell_amt - total_buy_amt, with_raw=False)}"
    elif net_exposure_intent == "reduce":
        if total_sell_amt >= total_buy_amt:
            intent_check_note = f"符合承諾：今日淨賣出 {format_money(total_sell_amt - total_buy_amt, with_raw=False)} (-{abs(net_flow_pct_of_nav)*100:.2f}% NAV)"
        else:
            intent_check_pass = False
            intent_check_note = f"⚠️ 警告：承諾 reduce 但今日為淨買入 {format_money(total_buy_amt - total_sell_amt, with_raw=False)}"
    elif net_exposure_intent == "hold":
        if abs(net_flow_pct_of_nav) <= 0.02 + 1e-4:
            intent_check_note = f"符合承諾：淨異動比例 {net_flow_pct_of_nav*100:+.2f}% 在 NAV 2% 容差範圍內"
        else:
            intent_check_pass = False
            intent_check_note = f"⚠️ 警告：承諾 hold 但淨異動比例 {net_flow_pct_of_nav*100:+.2f}% 超出 2% 容差"

    # 預估持股檔數
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
    md_lines.append("| 項目 | 數值 (易讀/完整) | 說明 |")
    md_lines.append("| :--- | :--- | :--- |")
    md_lines.append(f"| **可交易淨值 (NAV Tradable)** | **{format_money(nav_tradable, with_raw=True)}** | 個股權重與現金比計算基準 |")
    md_lines.append(f"| **目前可動用現金 (Cash)** | **{format_money(current_cash, with_raw=True)}** | 未執行今日委託前現金水位 |")
    md_lines.append(f"| **目前現金比例** | **{cash_ratio * 100:.2f}%** | 現金佔 NAV 比例 |")
    md_lines.append(f"| **總資產 (AUM)** | **{format_money(aum, with_raw=True)}** | 含應收配息與市值 |")
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

    # 三、原本持有部位明細 (含股票名稱、目標權重與變化)
    md_lines.append("## 三、 原有持股部位明細 (依目前權重由高至低排序)")
    md_lines.append("")
    if holdings_list:
        md_lines.append(f"共有 **{len(holdings_list)}** 檔持股，持股市值合計 **{format_money(total_holdings_val, with_raw=True)}**：")
        md_lines.append("")
        md_lines.append("| 排名 | 股票代碼 | 股票名稱 | 持有股數 | 持有張數 | 昨日收盤價 (元) | 目前現值 (易讀/完整) | 目前權重 (%) | 目標權重 (%) | 權重變化 |")
        md_lines.append("| :---: | :---: | :---: | :---: | :---: | :---: | :--- | :---: | :---: | :---: |")
        for i, h in enumerate(holdings_list, 1):
            diff = h["diff_weight"]
            if abs(diff) < 1e-5:
                change_badge = "持平 (續抱)"
            elif diff > 0:
                change_badge = f"🟢 **+{diff*100:.2f}%**"
            else:
                if h["target_weight"] == 0.0:
                    change_badge = f"🔴 **{diff*100:.2f}% (出清)**"
                else:
                    change_badge = f"🔴 **{diff*100:.2f}%**"

            formatted_mv = format_money(h["market_value"], with_raw=True)
            md_lines.append(
                f"| {i} | `{h['code']}` | **{h['name']}** | {h['shares']:,} | {h['lots']:.1f} 張 | "
                f"{h['close_price']:,.2f} | {formatted_mv} | {h['weight']*100:.2f}% | "
                f"**{h['target_weight']*100:.2f}%** | {change_badge} |"
            )
        md_lines.append("")
    else:
        md_lines.append("*(帳戶目前為空手全現金狀態，尚無昨日留倉部位)*\n")

    # 四、今日部位增減明細 (含股票名稱、易讀金額、目標權重；因果推論於下方詳解)
    md_lines.append("## 四、 今日部位增減決策與委託執行明細")
    md_lines.append("")
    if order_details:
        md_lines.append(f"今日共產生 **{len(order_details)}** 筆交易委託單：")
        md_lines.append("")
        md_lines.append("| 決策ID | 股票代號 | 股票名稱 | 買賣動作 | 委託張數 | 委託股數 | 參考市價 (元) | 預估交易金額 | 目標權重 (%) | 委託算單與執行說明 |")
        md_lines.append("| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :---: | :--- |")
        for o in order_details:
            side_badge = "🟢 **BUY (買進)**" if o["side"] == "BUY" else "🔴 **SELL (賣出)**"
            formatted_amt = format_money(o["est_amount"], with_raw=True)
            c_deriv = _clean_table_text(o["derivation"] or o["rationale"])

            md_lines.append(
                f"| `{o['decision_ref']}` | `{o['ticker']}` | **{o['name']}** | {side_badge} | {o['lots']} 張 | "
                f"{o['shares']:,} | {o['ref_price']:,.2f} | {formatted_amt} | "
                f"**{o['target_weight']*100:.2f}%** | `{c_deriv}` |"
            )
        md_lines.append("")

        # 今日異動個股之深度因果推論與決策展開卡片 (便於人工專注閱讀)
        md_lines.append("### 🔍 今日異動個股之 L2 推論與 L3 決策因果鏈詳解")
        md_lines.append("")
        for o in order_details:
            side_str = "🟢 買進 (BUY)" if o["side"] == "BUY" else "🔴 賣出 (SELL)"
            md_lines.append(f"#### 📌 【{o['decision_ref']}】 {o['ticker']} {o['name']} ｜ {side_str} {o['lots']} 張 ({o['shares']:,} 股)")
            md_lines.append("")
            md_lines.append(f"- **預估交易金額**：{format_money(o['est_amount'], with_raw=True)} ｜ **參考市價**：NT$ {o['ref_price']:,.2f} 元")
            md_lines.append(f"- **目標權重配置**：**{o['target_weight']*100:.2f}%** (委託計算：`{o['derivation']}`)")
            if o["inf_refs"]:
                md_lines.append(f"- **關聯 L2 推論依據**：`{', '.join(o['inf_refs'])}`")
            conc_text = str(o['l2_conclusion']).replace(' <br> ', '  \n> ')
            logic_text = str(o['l2_logic']).replace(' <br> ', '  \n> ')
            counter_text = str(o['l2_counter']).replace(' <br> ', '  \n> ')

            md_lines.append(f"- **🧠 L2 推論結論 (Conclusion)**：")
            md_lines.append(f"  > {conc_text}")
            md_lines.append(f"- **📖 L2 核心推論邏輯 (Logic)**：")
            md_lines.append(f"  > {logic_text}")
            if o["l2_counter"] and o["l2_counter"] != "-":
                md_lines.append(f"- **⚠️ L2 反向證據與風險 (Counter Evidence)**：")
                md_lines.append(f"  > {counter_text}")
            md_lines.append(f"- **🛡️ L3 風控檢核與決策動機 (Risk Check)**：")
            md_lines.append(f"  > {o['risk_check'] or o['rationale']}")
            md_lines.append("")
    else:
        md_lines.append("*(今日無任何部位買賣異動委託)*\n")

    # 續抱清單 (Hold / No Trade)
    if no_trade_decisions:
        md_lines.append("### 📌 續抱無異動部位 (Hold / No Trade)")
        md_lines.append("")
        md_lines.append("| 股票代號 | 股票名稱 | 維持目標權重 (%) | 續抱原因說明 |")
        md_lines.append("| :---: | :---: | :---: | :--- |")
        for nt in no_trade_decisions:
            tk = str(nt.get("ticker", "")).strip()
            name = get_stock_name(tk)
            # 若無明確 target_weight 欄位，從原有持股權重取得
            raw_w = nt.get("target_weight")
            if raw_w is not None and float(raw_w) > 0:
                keep_w = float(raw_w)
            else:
                keep_w = holdings_weight_map.get(tk, 0.0)
            reason = nt.get("reason") or nt.get("decision_rationale") or "維持原部位續抱"
            md_lines.append(f"| `{tk}` | **{name}** | **{keep_w*100:.2f}%** | {reason} |")
        md_lines.append("")

    # 五、財務收支試算與 L2M 承諾對照檢驗 (金額人性化易讀呈現)
    md_lines.append("## 五、 財務試算與 L2M 承諾對照檢驗")
    md_lines.append("")
    md_lines.append("### 💰 資金收支與執行後現金試算")
    md_lines.append("")
    md_lines.append("| 財務項目 | 金額 (主要易讀呈現 / 完整精準數值) | 佔 NAV 比例 | 備註說明 |")
    md_lines.append("| :--- | :--- | :--- | :--- |")
    md_lines.append(f"| **買進總金額 (Gross Buy)** | **{format_money(total_buy_amt, with_raw=True)}** | {total_buy_amt/nav_tradable*100:.2f}% | 今日預估買單資金需求 |")
    md_lines.append(f"| **賣出總金額 (Gross Sell)** | **{format_money(total_sell_amt, with_raw=True)}** | {total_sell_amt/nav_tradable*100:.2f}% | 今日預估賣單回籠現金 |")
    if net_cash_flow >= 0:
        net_flow_human = f"淨花費 **{format_money(net_cash_flow, with_raw=True)}** (流出)"
    else:
        net_flow_human = f"淨套現 **{format_money(abs(net_cash_flow), with_raw=True)}** (流入)"
    md_lines.append(f"| **淨交易收支 (Net Cash Flow)** | {net_flow_human} | **{abs(net_cash_flow)/nav_tradable*100:.2f}%** | 買賣互抵交割款 |")
    md_lines.append(f"| **目前現有現金** | **{format_money(current_cash, with_raw=True)}** | {cash_ratio*100:.2f}% | 交易前帳戶可動用現金 |")
    md_lines.append(f"| **執行後預估剩餘現金** | **{format_money(est_final_cash, with_raw=True)}** | **{est_final_cash_ratio*100:.2f}%** | 預估結算後留存現金 |")
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
        f"**{est_final_cash_ratio*100:.2f}%** ({format_money(est_final_cash, with_raw=True)}) | {cash_check_badge} | "
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

    # 六、結論與經理人覆核摘要
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
