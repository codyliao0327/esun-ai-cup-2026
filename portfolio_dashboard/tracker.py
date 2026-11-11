"""
Portfolio Tracker for 2026 玉山人工智慧挑戰賽
解析 data/backend_reports/*.htm 與 data/Datapack/Raw/*.json
計算帳戶真實成交成本、損益、歷史資產曲線與個股部位
"""
import re
import json
import sys
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


def parse_backend_reports() -> List[Dict[str, Any]]:
    """解析 data/backend_reports/*.htm 抓取所有真實成交明細"""
    if not BACKEND_REPORTS_DIR.exists():
        return []

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
                    t_amount_wan = float(cells[6].replace(",", ""))
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


def calculate_portfolio_costs(backend_reports: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """依據後台歷史成交明細，計算每檔股票的移動加權平均成本與已實現損益"""
    portfolio_state: Dict[str, Dict[str, Any]] = {}
    # {code: {"shares": 0, "total_cost": 0.0, "avg_cost": 0.0, "realized_pnl": 0.0, "name": ""}}

    for rep in backend_reports:
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
                }

            item = portfolio_state[code]
            item["name"] = name

            if action == "買進":
                # 加碼或建倉：移動加權平均成本
                new_shares = item["shares"] + shares
                new_cost = item["total_cost"] + (shares * price)
                item["shares"] = new_shares
                item["total_cost"] = new_cost
                item["avg_cost"] = (new_cost / new_shares) if new_shares > 0 else 0.0
            elif action == "賣出":
                # 減碼或出清：依目前成本認列已實現損益
                sell_shares = min(shares, item["shares"])
                cost_of_sold = sell_shares * item["avg_cost"]
                sell_revenue = sell_shares * price
                item["realized_pnl"] += (sell_revenue - cost_of_sold)
                
                new_shares = item["shares"] - sell_shares
                item["shares"] = new_shares
                item["total_cost"] = new_shares * item["avg_cost"]
                if new_shares <= 0:
                    item["shares"] = 0
                    item["total_cost"] = 0.0

    return portfolio_state


def load_datapack_history() -> List[Dict[str, Any]]:
    """讀取 data/Datapack/Raw/ 下所有歷史 DataPack，建立資產歷史時間序列"""
    if not DATAPACK_RAW_DIR.exists():
        return []

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
            
            nav = float(acc.get("nav_tradable", 0.0))
            cash = float(acc.get("cash", 0.0))
            aum = float(acc.get("aum", nav))
            cash_ratio = float(acc.get("cash_ratio_tradable", 0.0)) if acc.get("cash_ratio_tradable") is not None else (cash / nav if nav > 0 else 0.0)
            holdings_count = int(acc.get("holdings_count", 0))

            # 計算累計報酬率 (相較初始資金 1,000,000,000)
            cum_return_pct = ((nav - 1_000_000_000.0) / 1_000_000_000.0) * 100.0

            history.append({
                "date": dt,
                "trade_date": trade_dt,
                "nav": nav,
                "cash": cash,
                "aum": aum,
                "stock_value": nav - cash,
                "cash_ratio_pct": round(cash_ratio * 100.0, 2),
                "holdings_count": holdings_count,
                "cum_return_pct": round(cum_return_pct, 2),
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
    cash = latest_dp["cash"]
    stock_value = latest_dp["stock_value"]
    cum_pnl = nav - 1_000_000_000.0
    cum_return_pct = (cum_pnl / 1_000_000_000.0) * 100.0

    # 今日持股部位
    raw_holdings = latest_dp["holdings"]
    held_positions = []
    total_unrealized_pnl = 0.0

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

        # 成本均價：優先自後台成交明細計算，若無則以當日 close_price 作為 baseline
        cost_info = costs_by_code.get(code)
        if cost_info and cost_info["shares"] > 0:
            avg_cost = cost_info["avg_cost"]
        else:
            avg_cost = close_price  # fallback

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
        })

    # 依權重由大至小排序
    held_positions.sort(key=lambda x: x["weight_pct"], reverse=True)

    return {
        "as_of_date": latest_dp["date"],
        "trade_date": latest_dp["trade_date"],
        "account": {
            "nav": round(nav, 0),
            "aum": round(latest_dp["aum"], 0),
            "cash": round(cash, 0),
            "stock_value": round(stock_value, 0),
            "cash_ratio_pct": latest_dp["cash_ratio_pct"],
            "cum_pnl": round(cum_pnl, 0),
            "cum_return_pct": round(cum_return_pct, 2),
            "unrealized_pnl": round(total_unrealized_pnl, 0),
            "holdings_count": len(held_positions),
            "violations": latest_dp["compliance"].get("violations", 0),
            "notices": latest_dp["compliance"].get("notices", 0),
        },
        "held_positions": held_positions,
        "history": [{
            "date": h["date"],
            "nav": round(h["nav"], 0),
            "cash": round(h["cash"], 0),
            "stock_value": round(h["stock_value"], 0),
            "cash_ratio_pct": h["cash_ratio_pct"],
            "cum_return_pct": h["cum_return_pct"]
        } for h in dp_history],
        "stocks_150": stocks_150
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
