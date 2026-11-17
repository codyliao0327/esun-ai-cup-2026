"""
Portfolio Tracker for 2026 玉山人工智慧挑戰賽
解析 data/backend_reports/*.htm 與 data/Datapack/Raw/*.json
計算帳戶真實成交成本、損益、歷史資產曲線與個股部位
"""
import re
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 設定路徑 (以 code/portfolio_dashboard 為起點)
DASHBOARD_DIR = Path(__file__).resolve().parent
CODE_DIR = DASHBOARD_DIR.parent
PROJECT_ROOT = CODE_DIR.parent

BACKEND_REPORTS_DIR = PROJECT_ROOT / "data" / "backend_reports"
DATAPACK_RAW_DIR = PROJECT_ROOT / "data" / "Datapack" / "Raw"
STOCKS_150_FILE = PROJECT_ROOT / "docs" / "官方參考文件" / "玉山挑戰賽_投資組合及交易標的_150檔清單_v1.md"


def get_stocks_150_file() -> Optional[Path]:
    """多路徑自動尋找 150 檔標的清單檔案"""
    candidates = [
        STOCKS_150_FILE,
        PROJECT_ROOT / "玉山挑戰賽_投資組合及交易標的_150檔清單_v1.md",
        *list(PROJECT_ROOT.glob("**/玉山挑戰賽_投資組合及交易標的_150檔清單*.md"))
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def load_150_stocks() -> Dict[str, Dict[str, str]]:
    """讀取 150 檔官方競賽標的清單 (上市 100 檔、上櫃 50 檔)，具備快取回退防呆"""
    stocks = {}
    target_file = get_stocks_150_file()
    if not target_file:
        print("[警告] 找不到 150 檔標的清單 markdown 檔案！嘗試自快取恢復...")
        cache_file = DASHBOARD_DIR / "market_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cdata = json.load(f)
                cached = cdata.get("stocks", {})
                for code, item in cached.items():
                    stocks[code] = {
                        "code": code,
                        "name": item.get("name", code),
                        "market": item.get("market", "上市")
                    }
                if stocks:
                    print(f"[提示] 已自快取成功恢復 {len(stocks)} 檔標的清單！")
                    return stocks
            except Exception:
                pass
        return stocks

    content = target_file.read_text(encoding="utf-8", errors="ignore")
    current_market = "上市"
    for line in content.splitlines():
        line = line.strip()
        if "【上櫃】" in line:
            current_market = "上櫃"
        elif "【上市】" in line:
            current_market = "上市"
        
        # 匹配表格格式 | 2330 | 台積電 | 2883 | 凱基金 |
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if len(parts) >= 2:
            for i in range(0, len(parts) - 1, 2):
                code = parts[i]
                name = parts[i+1]
                if code.isdigit() and len(code) == 4 and not name.startswith("證券"):
                    stocks[code] = {
                        "code": code,
                        "name": name,
                        "market": current_market
                    }
    return stocks


_SIDE_MAP = {
    "buy": "買進",
    "sell": "賣出",
    "買進": "買進",
    "賣出": "賣出",
}


def load_backend_ranking() -> Optional[Dict[str, Any]]:
    """讀取 backend_ranking_latest.json 官方競賽全體排行榜快照。"""
    ranking_json = BACKEND_REPORTS_DIR / "backend_ranking_latest.json"
    if not ranking_json.exists():
        return None
    try:
        data = json.loads(ranking_json.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("results"), list):
            return data
        return None
    except Exception as e:
        print(f"[警告] 讀取 backend_ranking_latest.json 失敗: {e}")
        return None


def load_backend_history_all() -> List[Dict[str, Any]]:
    """讀取 backend_all_history.json 完整每日紀錄（含 ranking、portfolio、trade_summary、trades）。"""
    history_json = BACKEND_REPORTS_DIR / "backend_all_history.json"
    if not history_json.exists():
        return []
    try:
        records = json.loads(history_json.read_text(encoding="utf-8"))
        records.sort(key=lambda x: str(x.get("date") or ""))
        return records
    except Exception as e:
        print(f"[警告] 讀取 backend_all_history.json 失敗: {e}")
        return []


def _parse_backend_history_json(json_path: Path) -> List[Dict[str, Any]]:
    """從 backend_all_history.json 解析所有真實成交明細（保留小數 4 位成交價與精確金額）。"""
    records = json.loads(json_path.read_text(encoding="utf-8"))
    reports: List[Dict[str, Any]] = []
    for day_entry in records:
        real_date = str(day_entry.get("date") or "").strip()
        if not real_date:
            continue
        summary = day_entry.get("trade_summary") or {}
        fee = float(summary.get("fee", 0.0))
        tax = float(summary.get("tax", 0.0))

        trades: List[Dict[str, Any]] = []
        for tr in day_entry.get("trades") or []:
            outcome = str(tr.get("outcome", "")).strip().lower()
            if outcome and outcome != "filled":
                continue
            t_action = _SIDE_MAP.get(str(tr.get("side", "")).strip().lower())
            t_code = str(tr.get("code", "")).strip()
            t_name = str(tr.get("name", "")).strip()
            shares = int(tr.get("shares", 0))
            if not t_action or not t_code or shares <= 0:
                continue
            t_price = float(tr.get("price", 0.0))
            t_amount = float(tr.get("amount", t_price * shares))
            trades.append({
                "id": tr.get("id"),
                "date": real_date,
                "action": t_action,
                "code": t_code,
                "name": t_name,
                "lots": shares / 1000.0,
                "shares": shares,
                "price": t_price,
                "amount": t_amount,
                "fee": float(tr.get("fee", 0.0)),
                "tax": float(tr.get("tax", 0.0)),
            })

        if trades:
            reports.append({
                "file": json_path.name,
                "date": real_date,
                "fee": fee,
                "tax": tax,
                "trades": trades,
            })

    reports.sort(key=lambda x: x["date"])
    return reports


def _parse_backend_htm_files() -> List[Dict[str, Any]]:
    """備援：解析 data/backend_reports/*.htm* 抓取所有真實成交明細"""
    reports = []
    htm_files = sorted(BACKEND_REPORTS_DIR.glob("*.htm*"))
    for f in htm_files:
        if not f.is_file():
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
            # 提取手續費與證交稅
            fee_m = re.search(r"手續費\s*([0-9,]+)\s*元", content)
            tax_m = re.search(r"證交稅\s*([0-9,]+)\s*元", content)
            fee = int(fee_m.group(1).replace(",", "")) if fee_m else 0
            tax = int(tax_m.group(1).replace(",", "")) if tax_m else 0

            # 提取表格每列
            rows = re.findall(r"<tr[^>]*>(.*?)</tr>", content, re.DOTALL)
            trades = []
            for r in rows:
                cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.DOTALL)]
                if len(cells) >= 7 and cells[1] in ["買進", "賣出"]:
                    t_date = cells[0]
                    t_action = cells[1] # 買進 / 賣出
                    t_code = cells[2]
                    t_name = cells[3]
                    t_lots = float(cells[4].replace(",", ""))
                    t_price = float(cells[5].replace(",", ""))
                    trades.append({
                        "date": t_date,
                        "action": t_action,
                        "code": t_code,
                        "name": t_name,
                        "lots": t_lots,
                        "shares": int(t_lots * 1000),
                        "price": t_price,
                        "amount": t_price * t_lots * 1000
                    })

            # 優先從表格第一筆成交交易日，或頂部下拉選單 option value 提取精確日期
            m_opt = re.search(r'option\s+value="(\d{4}-\d{2}-\d{2})"', content)
            real_date = trades[0]["date"] if trades else (m_opt.group(1) if m_opt else None)
            if not real_date:
                m_date = re.search(r"(\d{4}-\d{2}-\d{2})", content)
                real_date = m_date.group(1) if m_date else None
            if trades and real_date:
                reports.append({
                    "file": f.name,
                    "date": real_date,
                    "fee": fee,
                    "tax": tax,
                    "trades": trades
                })
        except Exception as e:
            print(f"[警告] 解析後台檔案 {f.name} 失敗: {e}")

    # 依真實交易日期排序，並以交易日去重防呆 (若有同日多檔，保留最新/完整的一份)
    reports.sort(key=lambda x: x["date"])
    dedup_reports = {}
    for rep in reports:
        dedup_reports[rep["date"]] = rep
    return list(dedup_reports.values())


def parse_backend_reports() -> List[Dict[str, Any]]:
    """解析後台成交明細。優先使用 backend_all_history.json，無則退回 *.htm*"""
    if not BACKEND_REPORTS_DIR.exists():
        return []

    history_json = BACKEND_REPORTS_DIR / "backend_all_history.json"
    if history_json.exists():
        return _parse_backend_history_json(history_json)
    return _parse_backend_htm_files()


def calculate_portfolio_costs(backend_reports: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """依據後台歷史成交明細，計算每檔股票的移動加權平均成本、已實現損益與 FIFO 分批買進明細"""
    portfolio_state: Dict[str, Dict[str, Any]] = {}
    # {code: {"shares": 0, "total_cost": 0.0, "avg_cost": 0.0, "realized_pnl": 0.0, "name": "", "buy_lots": [...]}}

    for rep in backend_reports:
        rep_date = rep["date"]
        for t in rep["trades"]:
            code = t["code"]
            action = t["action"]
            shares = t["shares"]
            price = t["price"]
            name = t["name"]

            if code not in portfolio_state:
                portfolio_state[code] = {
                    "code": code,
                    "name": name,
                    "shares": 0,
                    "total_cost": 0.0,
                    "avg_cost": 0.0,
                    "realized_pnl": 0.0,
                    "buy_lots": [],
                }

            item = portfolio_state[code]
            item["name"] = name

            if action == "買進":
                # 加碼或建倉：移動加權平均成本 + 記錄該筆買進批次
                new_shares = item["shares"] + shares
                new_cost = item["total_cost"] + (shares * price)
                item["shares"] = new_shares
                item["total_cost"] = new_cost
                item["avg_cost"] = (new_cost / new_shares) if new_shares > 0 else 0.0
                item["buy_lots"].append({
                    "date": rep_date,
                    "shares": shares,
                    "lots": round(shares / 1000.0, 1),
                    "orig_lots": round(t["lots"], 1),
                    "price": round(price, 2),
                })
            elif action == "賣出":
                # 減碼或出清：依目前成本認列已實現損益，並以 FIFO 扣減未平倉買進批次
                sell_shares = min(shares, item["shares"])
                cost_of_sold = sell_shares * item["avg_cost"]
                sell_revenue = sell_shares * price
                item["realized_pnl"] += (sell_revenue - cost_of_sold)

                rem_to_sell = sell_shares
                while rem_to_sell > 0 and item["buy_lots"]:
                    oldest = item["buy_lots"][0]
                    if oldest["shares"] <= rem_to_sell:
                        rem_to_sell -= oldest["shares"]
                        item["buy_lots"].pop(0)
                    else:
                        oldest["shares"] -= rem_to_sell
                        oldest["lots"] = round(oldest["shares"] / 1000.0, 1)
                        rem_to_sell = 0

                new_shares = item["shares"] - sell_shares
                item["shares"] = new_shares
                item["total_cost"] = new_shares * item["avg_cost"]
                if new_shares <= 0:
                    item["shares"] = 0
                    item["total_cost"] = 0.0
                    item["buy_lots"] = []

    return portfolio_state


def load_datapack_history() -> List[Dict[str, Any]]:
    """讀取 data/Datapack/Raw/ 與 backend_all_history.json，建立資產歷史時間序列（優先採用官方後台精確數值）"""
    if not DATAPACK_RAW_DIR.exists():
        return []

    backend_map: Dict[str, Dict[str, Any]] = {
        str(entry.get("date")): entry
        for entry in load_backend_history_all()
        if entry.get("date")
    }

    history = []
    files = sorted(DATAPACK_RAW_DIR.glob("*.json"))
    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as fp:
                d = json.load(fp)
            
            acc = d.get("account")
            if not acc:
                continue

            dt = d.get("as_of_date") or d.get("trade_date")
            trade_dt = d.get("trade_date")

            b_entry = backend_map.get(dt) or {}
            b_port = b_entry.get("portfolio") or {}
            b_break = b_port.get("aum_breakdown") or {}
            b_rank = b_entry.get("ranking") or {}
            b_tsum = b_entry.get("trade_summary") or {}

            nav = float(acc.get("nav_tradable", 0.0))
            if b_port:
                aum = float(b_port.get("aum", nav))
                cash = float(b_break.get("cash", acc.get("cash", 0.0)))
                stock_value = float(b_break.get("holdings_value", aum - cash))
                cash_ratio_pct = float(b_port.get("cash_ratio", 0.0))
                stock_ratio_pct = float(b_port.get("stock_ratio", 0.0))
                holdings_count = int(b_port.get("holdings_count", acc.get("holdings_count", 0)))
                cum_return_pct = float(b_port.get("cum_return", 0.0))
                day_return_pct = float(b_port.get("day_return", 0.0))
                top10_weight = float(b_port.get("top10_weight", 0.0))
            else:
                cash = float(acc.get("cash", 0.0))
                aum = float(acc.get("aum", nav))
                stock_value = nav - cash
                cash_ratio = float(acc.get("cash_ratio_tradable", 0.0)) if acc.get("cash_ratio_tradable") is not None else (cash / nav if nav > 0 else 0.0)
                cash_ratio_pct = round(cash_ratio * 100.0, 2)
                stock_ratio_pct = round(100.0 - cash_ratio_pct, 2)
                holdings_count = int(acc.get("holdings_count", 0))
                cum_return_pct = round(((nav - 1_000_000_000.0) / 1_000_000_000.0) * 100.0, 2)
                day_return_pct = 0.0
                top10_weight = 0.0

            total_teams = int(b_rank.get("total_teams", 0)) if b_rank else 0
            group_total = int(b_rank.get("group_total", 0)) if b_rank else 0
            ranking_info = {
                "rank": b_rank.get("rank"),
                "total_teams": total_teams,
                "group_rank": b_rank.get("group_rank"),
                "group_total": group_total,
                "student_total": max(0, total_teams - group_total),
            } if b_rank else None

            history.append({
                "day": b_entry.get("day"),
                "date": dt,
                "trade_date": trade_dt,
                "nav": nav,
                "cash": cash,
                "aum": aum,
                "stock_value": stock_value,
                "cash_ratio_pct": cash_ratio_pct,
                "stock_ratio_pct": stock_ratio_pct,
                "holdings_count": holdings_count,
                "cum_return_pct": cum_return_pct,
                "day_return_pct": day_return_pct,
                "top10_weight": top10_weight,
                "ranking": ranking_info,
                "fee": float(b_tsum.get("fee", 0.0)),
                "tax": float(b_tsum.get("tax", 0.0)),
                "holdings": d.get("holdings") or [],
                "compliance": d.get("compliance") or {"violations": 0, "notices": 0}
            })
        except Exception as e:
            print(f"[警告] 讀取 DataPack {f.name} 失敗: {e}")

    # 依日期排序並去重 (以 date 為主)
    history.sort(key=lambda x: x["date"])
    dedup = {}
    for h in history:
        dedup[h["date"]] = h
    return list(dedup.values())


def get_latest_portfolio_summary() -> Dict[str, Any]:
    """統整最新帳戶資產、庫存持股、損益計算與歷史曲線"""
    stocks_150 = load_150_stocks()
    backend_reports = parse_backend_reports()
    costs_by_code = calculate_portfolio_costs(backend_reports)
    dp_history = load_datapack_history()

    if not dp_history:
        raise RuntimeError("找不到有效的 DataPack 歷史資料！請確認 data/Datapack/Raw/ 檔案。")

    latest_dp = dp_history[-1]
    prev_dp = dp_history[-2] if len(dp_history) >= 2 else None
    prev_holdings_map = {h["code"]: float(h.get("close_price") or 0.0) for h in (prev_dp.get("holdings") or [])} if prev_dp else {}

    nav = latest_dp["nav"]
    aum = latest_dp["aum"]
    cash = latest_dp["cash"]
    stock_value = latest_dp["stock_value"]
    cum_pnl = aum - 1_000_000_000.0
    cum_return_pct = latest_dp["cum_return_pct"]
    day_return_pct = latest_dp.get("day_return_pct", 0.0)
    top10_weight = latest_dp.get("top10_weight", 0.0)

    # 今日持股部位
    raw_holdings = latest_dp["holdings"]
    held_positions = []
    total_unrealized_pnl = 0.0

    try:
        as_of_dt = datetime.strptime(latest_dp["date"], "%Y-%m-%d")
    except Exception:
        as_of_dt = None

    # 預先計算各股自最新交易日回推的連續持有交易日數
    dp_held_sets = [{str(item.get("code")) for item in (dp.get("holdings") or [])} for dp in dp_history]

    for h in raw_holdings:
        code = str(h.get("code"))
        shares = int(h.get("shares", 0))
        close_price = float(h.get("close_price") or 0.0)
        weight = float(h.get("tradable_weight") or 0.0)
        
        stock_meta = stocks_150.get(code, {})
        name = stock_meta.get("name") or costs_by_code.get(code, {}).get("name") or code
        market = stock_meta.get("market", "上市")

        # 昨收價與今日漲跌
        prev_close = prev_holdings_map.get(code) or close_price
        day_change = round(close_price - prev_close, 2)
        day_change_pct = round((day_change / prev_close * 100), 2) if prev_close else 0.0

        # 成本均價與 FIFO 分批買進明細
        cost_info = costs_by_code.get(code)
        if cost_info and cost_info["shares"] > 0:
            avg_cost = cost_info["avg_cost"]
            raw_lots = cost_info.get("buy_lots", [])
        else:
            avg_cost = close_price  # fallback
            raw_lots = []

        # 連續持有交易日數
        holding_trading_days = 0
        for held_set in reversed(dp_held_sets):
            if code in held_set:
                holding_trading_days += 1
            else:
                break

        # 計算每批買進明細損益與持有天數
        buy_lots_detail = []
        for lot in raw_lots:
            lot_shares = lot["shares"]
            lot_price = lot["price"]
            lot_cost = lot_shares * lot_price
            lot_mkt = lot_shares * close_price
            lot_pnl = lot_mkt - lot_cost
            lot_ret = (lot_pnl / lot_cost * 100.0) if lot_cost > 0 else 0.0
            lot_days = holding_trading_days
            if as_of_dt:
                try:
                    lot_dt = datetime.strptime(lot["date"], "%Y-%m-%d")
                    lot_days = max(1, (as_of_dt - lot_dt).days + 1)
                except Exception:
                    pass
            buy_lots_detail.append({
                "date": lot["date"],
                "lots": lot["lots"],
                "orig_lots": lot["orig_lots"],
                "shares": lot_shares,
                "price": lot_price,
                "cost": round(lot_cost, 0),
                "market_value": round(lot_mkt, 0),
                "unrealized_pnl": round(lot_pnl, 0),
                "return_pct": round(lot_ret, 2),
                "holding_days": lot_days,
            })

        first_buy_date = buy_lots_detail[0]["date"] if buy_lots_detail else latest_dp["date"]
        holding_days = buy_lots_detail[0]["holding_days"] if buy_lots_detail else holding_trading_days

        total_cost = shares * avg_cost
        market_val = shares * close_price
        unrealized_pnl = market_val - total_cost
        unrealized_return_pct = ((market_val - total_cost) / total_cost * 100.0) if total_cost > 0 else 0.0
        total_unrealized_pnl += unrealized_pnl

        held_positions.append({
            "code": code,
            "name": name,
            "market": market,
            "shares": shares,
            "lots": round(shares / 1000.0, 1),
            "avg_cost": round(avg_cost, 2),
            "close_price": close_price,
            "prev_close": prev_close,
            "day_change": day_change,
            "day_change_pct": day_change_pct,
            "market_value": round(market_val, 0),
            "unrealized_pnl": round(unrealized_pnl, 0),
            "unrealized_return_pct": round(unrealized_return_pct, 2),
            "weight_pct": round(weight * 100.0, 2),
            "holding_days": holding_days,
            "holding_trading_days": holding_trading_days,
            "first_buy_date": first_buy_date,
            "buy_lots": buy_lots_detail,
        })

    # 依權重由大至小排序
    held_positions.sort(key=lambda x: x["weight_pct"], reverse=True)

    # 彙整後台完整歷史紀錄（排名、交易摩擦成本、週轉率、歷史每日成交明細）
    backend_all = load_backend_history_all()
    total_fee = 0.0
    total_tax = 0.0
    total_buy_amount = 0.0
    total_sell_amount = 0.0
    total_buy_count = 0
    total_sell_count = 0
    trade_history = []

    for entry in backend_all:
        tsum = entry.get("trade_summary") or {}
        day_fee = float(tsum.get("fee", 0.0))
        day_tax = float(tsum.get("tax", 0.0))
        day_buy_amt = float(tsum.get("buy_amount", 0.0))
        day_sell_amt = float(tsum.get("sell_amount", 0.0))
        day_buy_cnt = int(tsum.get("buy_count", 0))
        day_sell_cnt = int(tsum.get("sell_count", 0))

        total_fee += day_fee
        total_tax += day_tax
        total_buy_amount += day_buy_amt
        total_sell_amount += day_sell_amt
        total_buy_count += day_buy_cnt
        total_sell_count += day_sell_cnt

        day_trades = []
        for tr in entry.get("trades") or []:
            outcome = str(tr.get("outcome", "")).strip().lower()
            if outcome and outcome != "filled":
                continue
            side_cn = _SIDE_MAP.get(str(tr.get("side", "")).strip().lower(), str(tr.get("side", "")))
            shares = int(tr.get("shares", 0))
            day_trades.append({
                "id": tr.get("id"),
                "side": side_cn,
                "code": str(tr.get("code", "")).strip(),
                "name": str(tr.get("name", "")).strip(),
                "shares": shares,
                "lots": round(shares / 1000.0, 1),
                "price": float(tr.get("price", 0.0)),
                "amount": float(tr.get("amount", 0.0)),
                "fee": float(tr.get("fee", 0.0)),
                "tax": float(tr.get("tax", 0.0)),
            })

        b_port = entry.get("portfolio") or {}
        b_rank = entry.get("ranking") or {}
        trade_history.append({
            "day": entry.get("day"),
            "date": entry.get("date"),
            "day_return": float(b_port.get("day_return", 0.0)),
            "cum_return": float(b_port.get("cum_return", 0.0)),
            "rank": b_rank.get("rank"),
            "group_rank": b_rank.get("group_rank"),
            "buy_count": day_buy_cnt,
            "sell_count": day_sell_cnt,
            "buy_amount": day_buy_amt,
            "sell_amount": day_sell_amt,
            "fee": day_fee,
            "tax": day_tax,
            "trades": day_trades,
        })

    # 歷史成交明細預設依日期由新到舊排列
    trade_history.sort(key=lambda x: str(x.get("date") or ""), reverse=True)

    total_friction_cost = total_fee + total_tax
    total_traded_amount = total_buy_amount + total_sell_amount
    avg_aum = (sum(h["aum"] for h in dp_history) / len(dp_history)) if dp_history else aum
    turnover_pct = (total_traded_amount / avg_aum * 100.0) if avg_aum > 0 else 0.0
    gross_realized_pnl = sum(c.get("realized_pnl", 0.0) for c in costs_by_code.values())
    net_realized_pnl = gross_realized_pnl - total_friction_cost

    curr_rank = latest_dp.get("ranking") or {}
    prev_rank = (prev_dp.get("ranking") or {}) if prev_dp else {}
    rank_diff = (prev_rank["rank"] - curr_rank["rank"]) if (curr_rank.get("rank") and prev_rank.get("rank")) else 0
    group_rank_diff = (prev_rank["group_rank"] - curr_rank["group_rank"]) if (curr_rank.get("group_rank") and prev_rank.get("group_rank")) else 0

    return {
        "as_of_date": latest_dp["date"],
        "trade_date": latest_dp["trade_date"],
        "account": {
            "day": latest_dp.get("day"),
            "nav": round(nav, 0),
            "aum": round(aum, 0),
            "cash": round(cash, 0),
            "stock_value": round(stock_value, 0),
            "cash_ratio_pct": latest_dp["cash_ratio_pct"],
            "stock_ratio_pct": latest_dp.get("stock_ratio_pct", round(100.0 - latest_dp["cash_ratio_pct"], 2)),
            "cum_pnl": round(cum_pnl, 0),
            "cum_return_pct": cum_return_pct,
            "day_return_pct": day_return_pct,
            "top10_weight": top10_weight,
            "unrealized_pnl": round(total_unrealized_pnl, 0),
            "holdings_count": latest_dp.get("holdings_count", len(held_positions)),
            "violations": latest_dp["compliance"].get("violations", 0),
            "notices": latest_dp["compliance"].get("notices", 0),
            "rank": curr_rank.get("rank"),
            "total_teams": curr_rank.get("total_teams"),
            "group_rank": curr_rank.get("group_rank"),
            "group_total": curr_rank.get("group_total"),
            "student_total": curr_rank.get("student_total"),
            "rank_diff": rank_diff,
            "group_rank_diff": group_rank_diff,
        },
        "friction": {
            "total_fee": round(total_fee, 2),
            "total_tax": round(total_tax, 2),
            "total_friction_cost": round(total_friction_cost, 2),
            "friction_cost_pct": round((total_friction_cost / 1_000_000_000.0) * 100.0, 4),
            "total_buy_amount": round(total_buy_amount, 0),
            "total_sell_amount": round(total_sell_amount, 0),
            "total_traded_amount": round(total_traded_amount, 0),
            "total_buy_count": total_buy_count,
            "total_sell_count": total_sell_count,
            "turnover_pct": round(turnover_pct, 2),
            "gross_realized_pnl": round(gross_realized_pnl, 0),
            "net_realized_pnl": round(net_realized_pnl, 0),
        },
        "held_positions": held_positions,
        "trade_history": trade_history,
        "history": [{
            "day": h.get("day"),
            "date": h["date"],
            "nav": round(h["nav"], 0),
            "aum": round(h["aum"], 0),
            "cash": round(h["cash"], 0),
            "stock_value": round(h["stock_value"], 0),
            "cash_ratio_pct": h["cash_ratio_pct"],
            "cum_return_pct": h["cum_return_pct"],
            "day_return_pct": h.get("day_return_pct", 0.0),
            "top10_weight": h.get("top10_weight", 0.0),
            "rank": (h.get("ranking") or {}).get("rank"),
            "total_teams": (h.get("ranking") or {}).get("total_teams"),
            "group_rank": (h.get("ranking") or {}).get("group_rank"),
            "group_total": (h.get("ranking") or {}).get("group_total"),
            "student_total": (h.get("ranking") or {}).get("student_total"),
            "fee": h.get("fee", 0.0),
            "tax": h.get("tax", 0.0),
        } for h in dp_history],
        "stocks_150": stocks_150,
        "leaderboard": load_backend_ranking(),
    }


if __name__ == "__main__":
    summary = get_latest_portfolio_summary()
    print("=== 最新帳戶快照 ===")
    print(f"日期: {summary['as_of_date']}")
    print(f"NAV: {summary['account']['nav']:,} 元")
    print(f"現金: {summary['account']['cash']:,} 元 ({summary['account']['cash_ratio_pct']}%)")
    print(f"累計總報酬率: {summary['account']['cum_return_pct']}% (總損益: {summary['account']['cum_pnl']:,} 元)")
    print(f"持股檔數: {summary['account']['holdings_count']} 檔")
    print("\n=== 持股損益前 5 名 ===")
    for p in summary["held_positions"][:5]:
        print(f"{p['code']} {p['name']}: {p['lots']}張 | 成本: {p['avg_cost']} | 現價: {p['close_price']} | 報酬率: {p['unrealized_return_pct']}% | 損益: {p['unrealized_pnl']:,}元")
