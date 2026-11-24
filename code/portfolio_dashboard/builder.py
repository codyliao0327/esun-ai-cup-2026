"""
Dashboard HTML Builder for 2026 玉山人工智慧挑戰賽
風格：富果 Fugle 專業版面 + Apple iOS 液態毛玻璃 (Liquid Glass)
功能：
  - 帳戶總覽卡片、歷史 NAV 走勢圖、庫存損益明細表 (可排序)
  - 自選觀察群組 (我的持股 25 檔 vs 其餘 125 檔 vs 全部 150 檔)
  - 漲跌幅排序、即時搜尋、10-27 起股價趨勢微圖 (Sparkline)
  - 淺色 / 深色主題切換、完全響應式 (RWD) 手機與電腦極致優化
"""
import ast
import html as html_lib
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

DASHBOARD_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = DASHBOARD_DIR.parent.parent
REPORTS_DIR = PROJECT_ROOT / "data" / "D-Paln_Output" / "reports"
ETF_STRATEGY_FILE = PROJECT_ROOT / "data" / "ETF_Strategy" / "etf_strategy.md"
FINLAB_MARKET_LOADER_FILE = PROJECT_ROOT / "code" / "L0_sources" / "finlab_market_loader.py"
MARKET_CACHE_FILE = DASHBOARD_DIR / "market_cache.json"
COMPETITION_START_DATE = "2026-10-27"
COMPETITION_END_DATE = "2026-11-27"
DIST_DIR = DASHBOARD_DIR / "dist"
DIST_HTML = DIST_DIR / "index.html"


def _count_weekdays(start_str: str, end_str: str) -> int:
    """計算兩個 YYYY-MM-DD 日期之間（含頭尾）的週一至週五工作日數。"""
    try:
        d0 = date.fromisoformat(start_str[:10])
        d1 = date.fromisoformat(end_str[:10])
    except ValueError:
        return 0
    if d1 < d0:
        return 0
    cnt = 0
    cur = d0
    while cur <= d1:
        if cur.weekday() < 5:
            cnt += 1
        cur += timedelta(days=1)
    return cnt


def compute_competition_progress(as_of_date: str, history: List[Dict[str, Any]]) -> Dict[str, int]:
    """對齊 datapack_loader._build_progress_lines 計算賽期目前第幾天與總天數。"""
    elapsed = len(history) if history else _count_weekdays(COMPETITION_START_DATE, as_of_date)
    remaining = _count_weekdays(as_of_date, COMPETITION_END_DATE)
    total = elapsed + max(remaining - 1, 0)
    return {
        "elapsed": elapsed,
        "remaining": remaining,
        "total": max(total, elapsed),
    }


def load_watchlist_stock_ids() -> List[str]:
    """優先從 data/Stock_Pool/stock_list_*.json 讀取最新動態股票池，查無則退回解析 finlab_market_loader.py。"""
    stock_pool_dir = PROJECT_ROOT / "data" / "Stock_Pool"
    if stock_pool_dir.is_dir():
        pool_files = sorted(stock_pool_dir.glob("stock_list_*.json"), reverse=True)
        for pf in pool_files:
            try:
                payload = json.loads(pf.read_text(encoding="utf-8"))
                ids = [str(x).strip() for x in (payload.get("stock_ids") or []) if str(x).strip()]
                if ids:
                    return ids
            except Exception as exc:
                print(f"[builder] 讀取 {pf.name} 失敗: {exc}")

    if not FINLAB_MARKET_LOADER_FILE.is_file():
        return []
    try:
        tree = ast.parse(FINLAB_MARKET_LOADER_FILE.read_text(encoding="utf-8"))
        for node in tree.body:
            val_node = None
            if isinstance(node, ast.Assign):
                if any(isinstance(t, ast.Name) and t.id in ("STOCK_IDS", "DEFAULT_STOCK_IDS") for t in node.targets):
                    val_node = node.value
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name) and node.target.id in ("STOCK_IDS", "DEFAULT_STOCK_IDS"):
                    val_node = node.value
            if val_node is not None:
                try:
                    parsed = ast.literal_eval(val_node)
                    if isinstance(parsed, (list, tuple)):
                        return [str(x).strip() for x in parsed if str(x).strip()]
                except Exception:
                    continue
    except Exception as exc:
        print(f"[builder] 解析 STOCK_IDS 失敗: {exc}")
    return []


def load_market_updated_at() -> str:
    """讀取 market_cache.json 的行情更新時間（格式化為 YYYY-MM-DD HH:MM）。"""
    if MARKET_CACHE_FILE.is_file():
        try:
            cache_data = json.loads(MARKET_CACHE_FILE.read_text(encoding="utf-8"))
            raw_ts = str(cache_data.get("updated_at") or "").strip()
            if len(raw_ts) >= 16:
                return raw_ts[:16]
            if raw_ts:
                return raw_ts
        except Exception:
            pass
        return datetime.fromtimestamp(MARKET_CACHE_FILE.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def load_etf_strategy() -> Dict[str, str]:
    """讀取 data/ETF_Strategy/etf_strategy.md 中的 ETF 名稱、投資主題與投資理念"""
    strategy = {
        "name": "主動台灣多面向動態配置",
        "theme": "結合企業基本面、市場趨勢與事件動向的主動式台股配置策略。",
        "philosophy": "",
    }
    if not ETF_STRATEGY_FILE.is_file():
        return strategy
    try:
        text = ETF_STRATEGY_FILE.read_text(encoding="utf-8")
        for line in text.splitlines():
            parts = [p.strip() for p in line.strip().strip("|").split("|")]
            if len(parts) < 2:
                continue
            key = parts[0].replace("*", "").strip()
            val = parts[1].strip()
            if "ETF 名稱" in key and val:
                strategy["name"] = val
            elif "ETF 投資主題" in key and val:
                strategy["theme"] = val
            elif "ETF 投資理念" in key and val:
                strategy["philosophy"] = val
    except Exception as exc:
        print(f"[builder] 讀取 ETF 策略失敗: {exc}")
    return strategy


def load_decision_reports() -> List[Dict[str, Any]]:
    """掃描並載入所有歷史與最新每日決策 Markdown 報告（不綁定固定格式，由前端動態渲染）。"""
    if not REPORTS_DIR.is_dir():
        return []

    reports: List[Dict[str, Any]] = []
    for path in REPORTS_DIR.glob("Daily_Decision_Report_*.md"):
        try:
            md_text = path.read_text(encoding="utf-8")
        except Exception as exc:
            print(f"[builder] 讀取報告失敗 ({path.name}): {exc}")
            continue

        m = re.search(r"(\d{8})", path.stem)
        raw_date = m.group(1) if m else path.stem
        iso_date = (
            f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
            if len(raw_date) == 8 and raw_date.isdigit()
            else raw_date
        )

        # 從首個一級標題擷取報告名稱，無則回退檔名
        title = path.stem
        for line in md_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                title = stripped[2:].strip()
                break

        updated_at = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        reports.append({
            "raw_date": raw_date,
            "date": iso_date,
            "filename": path.name,
            "title": title,
            "size_bytes": len(md_text.encode("utf-8")),
            "updated_at": updated_at,
            "markdown": md_text,
        })

    # 依日期由新到舊排序
    reports.sort(key=lambda r: r["raw_date"], reverse=True)
    return reports


def generate_sparkline_svg(trend: List[float], width: int = 100, height: int = 28) -> str:
    """生成微型股價走勢折線圖 (SVG Sparkline)"""
    if not trend or len(trend) < 2:
        return f'<svg width="{width}" height="{height}" class="sparkline"><line x1="0" y1="{height//2}" x2="{width}" y2="{height//2}" stroke="#888" stroke-width="1.5" stroke-dasharray="2,2"/></svg>'
    
    min_v = min(trend)
    max_v = max(trend)
    span = (max_v - min_v) if max_v != min_v else 1.0

    points = []
    step = width / (len(trend) - 1)
    padding = 3
    h_span = height - (padding * 2)

    for i, v in enumerate(trend):
        x = i * step
        # y 軸反轉 (價格高 y 小)
        y = height - padding - ((v - min_v) / span * h_span)
        points.append(f"{x:.1f},{y:.1f}")

    pts_str = " ".join(points)
    is_up = trend[-1] >= trend[0]
    stroke_color = "#f43f5e" if is_up else "#10b981"  # 台股紅漲綠跌
    fill_color = "rgba(244, 63, 94, 0.12)" if is_up else "rgba(16, 185, 129, 0.12)"

    # 封閉區域填充
    area_points = f"0,{height} {pts_str} {width},{height}"

    return (
        f'<svg width="{width}" height="{height}" class="sparkline" viewBox="0 0 {width} {height}">'
        f'<polygon points="{area_points}" fill="{fill_color}" />'
        f'<polyline fill="none" stroke="{stroke_color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" points="{pts_str}" />'
        f'</svg>'
    )


def build_dashboard_html(summary_data: Dict[str, Any], market_quotes: Dict[str, Dict[str, Any]]) -> Path:
    """整合數據並產出自包含的現代化 HTML"""
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    account = summary_data["account"]
    friction = summary_data.get("friction", {})
    history = summary_data["history"]
    held_positions = summary_data["held_positions"]
    trade_history = summary_data.get("trade_history", [])
    stocks_150 = summary_data["stocks_150"]

    held_codes = set(p["code"] for p in held_positions)
    watchlist_ids = load_watchlist_stock_ids()
    watchlist_set = set(watchlist_ids)
    market_updated_at = load_market_updated_at()
    progress = compute_competition_progress(summary_data["as_of_date"], history)

    # 整合 150 檔行情與持股狀態
    all_stocks_list = []
    for code, meta in stocks_150.items():
        q = market_quotes.get(code, {})
        is_held = code in held_codes
        is_watchlist = code in watchlist_set
        held_info = next((p for p in held_positions if p["code"] == code), None)

        # 100% 來自玉山證券行情 API
        close_p = float(q.get("close_price") or (held_info["close_price"] if held_info else 0.0))
        prev_p = float(q.get("prev_close") or close_p)
        change = float(q.get("change") or (close_p - prev_p))
        change_pct = float(q.get("change_pct") or ((change / prev_p * 100) if prev_p else 0.0))
        volume_lots = q.get("volume_lots") or 0
        trend = q.get("trend") or ([close_p] if close_p > 0 else [])

        sparkline_svg = generate_sparkline_svg(trend)

        all_stocks_list.append({
            "code": code,
            "name": meta.get("name", code),
            "market": meta.get("market", "上市"),
            "close_price": round(close_p, 2),
            "prev_close": round(prev_p, 2),
            "change": round(change, 2),
            "change_pct": round(change_pct, 2),
            "volume_lots": volume_lots,
            "is_held": is_held,
            "is_watchlist": is_watchlist,
            "shares": held_info["shares"] if held_info else 0,
            "lots": held_info["lots"] if held_info else 0.0,
            "avg_cost": held_info["avg_cost"] if held_info else 0.0,
            "market_value": held_info["market_value"] if held_info else 0,
            "unrealized_pnl": held_info["unrealized_pnl"] if held_info else 0,
            "unrealized_return_pct": held_info["unrealized_return_pct"] if held_info else 0.0,
            "weight_pct": held_info["weight_pct"] if held_info else 0.0,
            "holding_days": held_info.get("holding_days", 0) if held_info else 0,
            "holding_trading_days": held_info.get("holding_trading_days", 0) if held_info else 0,
            "first_buy_date": held_info.get("first_buy_date", "") if held_info else "",
            "buy_lots": held_info.get("buy_lots", []) if held_info else [],
            "sparkline": sparkline_svg,
            "trend": trend
        })

    # 動態計算觀察標的數量 (不寫死)
    watchlist_count = sum(1 for s in all_stocks_list if s["is_watchlist"])

    # 讀取 LiteLLM Usage 歷史結算資料
    usage_history_path = DASHBOARD_DIR / "usage_history.json"
    usage_data: Dict[str, Any] = {"summary": {}, "daily_summary": {}, "records": []}
    if usage_history_path.exists():
        try:
            usage_data = json.loads(usage_history_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[builder] 讀取 usage_history.json 失敗: {exc}")

    # 讀取所有每日決策報告 (歷史 + 最新) 與 ETF 投資策略
    decision_reports = load_decision_reports()
    etf_strategy = load_etf_strategy()
    etf_name_esc = html_lib.escape(etf_strategy["name"])
    etf_theme_esc = html_lib.escape(etf_strategy["theme"])
    etf_phil_esc = html_lib.escape(etf_strategy["philosophy"])

    # 轉為 JSON 注入前端以利動態排序與篩選
    json_data_payload = {
        "as_of_date": summary_data["as_of_date"],
        "trade_date": summary_data["trade_date"],
        "account": account,
        "friction": friction,
        "history": history,
        "stocks": all_stocks_list,
        "trade_history": trade_history,
        "usage": usage_data,
        "reports": decision_reports,
        "leaderboard": summary_data.get("leaderboard") or {"meta": {}, "count": 0, "results": []},
    }
    safe_json_payload = json.dumps(json_data_payload, ensure_ascii=False).replace("</", "<\\/")

    html_template = f"""<!DOCTYPE html>
<html lang="zh-TW" class="theme-light">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="theme-color" id="themeColorMeta" content="#dce5f0">
  <title>2026 玉山 AI Agent 基金經理人 · TEAM_11402</title>
  <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>📈</text></svg>">
  
  <!-- 字體引入 Inter & SF Pro 質感 -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Noto+Sans+TC:wght@400;500;700;900&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  
  <!-- Chart.js -->
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <!-- Marked.js & DOMPurify (每日決策報告 Markdown 動態渲染與 XSS 防護) -->
  <script src="https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/dompurify@3.1.6/dist/purify.min.js"></script>

  <style>
    :root {{
      --font-sans: 'Plus Jakarta Sans', 'Noto Sans TC', -apple-system, BlinkMacSystemFont, sans-serif;
      --font-mono: 'JetBrains Mono', monospace;
      
      /* 台股習慣色彩：紅漲綠跌 (Apple Liquid Tinted Droplets) */
      --color-up: #ff453a;
      --color-up-bg: linear-gradient(180deg, rgba(255, 69, 58, 0.22) 0%, rgba(239, 68, 68, 0.08) 100%);
      --color-up-border: rgba(255, 110, 100, 0.38);
      --color-up-shadow: inset 0 1px 0.5px rgba(255, 255, 255, 0.35), 0 2px 8px -2px rgba(239, 68, 68, 0.25);

      --color-down: #30d158;
      --color-down-bg: linear-gradient(180deg, rgba(48, 209, 88, 0.22) 0%, rgba(16, 185, 129, 0.08) 100%);
      --color-down-border: rgba(74, 222, 128, 0.38);
      --color-down-shadow: inset 0 1px 0.5px rgba(255, 255, 255, 0.35), 0 2px 8px -2px rgba(16, 185, 129, 0.25);

      --color-flat: #94a3b8;

      --primary-accent: #38bdf8;
      --primary-glow: rgba(56, 189, 248, 0.28);
      --spring-ease: cubic-bezier(0.22, 1, 0.36, 1);
      --glass-alpha-scale: 1;
      --glass-blur-px: 16px;
    }}

    /* 深色主題 (Apple macOS 冷冽藍灰 / 單色系柔和光場) */
    .theme-dark {{
      --bg-solid: #060b14;
      --bg-gradient:
        radial-gradient(ellipse 68% 52% at 14% 10%, rgba(56, 189, 248, 0.14) 0%, transparent 65%),
        radial-gradient(ellipse 62% 54% at 86% 88%, rgba(30, 64, 175, 0.16) 0%, transparent 68%),
        linear-gradient(160deg, #060b14 0%, #0b1322 50%, #070c16 100%);
      --ambient-orb-1:
        radial-gradient(520px circle at 22% 20%, rgba(56, 189, 248, 0.11) 0%, transparent 70%),
        radial-gradient(560px circle at 80% 76%, rgba(148, 163, 184, 0.08) 0%, transparent 70%);

      --text-main: #f8fafc;
      --text-muted: #cbd5e1;
      --text-dim: #94a3b8;
      
      /* 冷冽水晶玻璃：純冰白高光 + 微量冰藍折射（無紫色雜訊） */
      --glass-backdrop: blur(var(--glass-blur-px, 16px)) saturate(155%);
      --glass-bg:
        linear-gradient(145deg, rgba(30, 41, 59, calc(0.62 * var(--glass-alpha-scale, 1))) 0%, rgba(15, 23, 42, calc(0.46 * var(--glass-alpha-scale, 1))) 55%, rgba(22, 34, 54, calc(0.58 * var(--glass-alpha-scale, 1))) 100%);
      --glass-bg-hover:
        linear-gradient(145deg, rgba(38, 52, 74, calc(0.68 * var(--glass-alpha-scale, 1))) 0%, rgba(20, 30, 52, calc(0.52 * var(--glass-alpha-scale, 1))) 55%, rgba(28, 44, 68, calc(0.64 * var(--glass-alpha-scale, 1))) 100%);
      --glass-border: rgba(226, 232, 240, 0.14);
      --glass-border-subtle: rgba(226, 232, 240, 0.09);
      --glass-border-specular: rgba(248, 250, 252, 0.32);
      --glass-shadow:
        0 18px 40px -12px rgba(2, 6, 23, 0.65),
        0 2px 10px -2px rgba(2, 6, 23, 0.40),
        inset 0 1px 0 0 rgba(255, 255, 255, 0.24),
        inset 0 -1px 0 0 rgba(56, 189, 248, 0.10);

      /* 3D 凸透鏡水滴膠囊按鈕 */
      --btn-glass-bg:
        radial-gradient(110% 90% at 50% 8%, rgba(255, 255, 255, 0.20) 0%, rgba(255, 255, 255, 0.04) 55%, transparent 82%),
        linear-gradient(180deg, rgba(255, 255, 255, 0.11) 0%, rgba(15, 23, 42, 0.28) 60%, rgba(56, 189, 248, 0.10) 100%);
      --btn-glass-hover:
        radial-gradient(110% 90% at 50% 8%, rgba(255, 255, 255, 0.28) 0%, rgba(255, 255, 255, 0.08) 55%, transparent 82%),
        linear-gradient(180deg, rgba(255, 255, 255, 0.16) 0%, rgba(15, 23, 42, 0.22) 60%, rgba(56, 189, 248, 0.16) 100%);
      --btn-glass-border: rgba(226, 232, 240, 0.20);
      --btn-glass-shadow:
        0 6px 14px -4px rgba(2, 6, 23, 0.50),
        inset 0 1.25px 0.8px 0 rgba(255, 255, 255, 0.38),
        inset 0 -1px 1.5px 0 rgba(56, 189, 248, 0.16);

      /* 激活態液態寶石膠囊 */
      --btn-active-bg:
        radial-gradient(110% 90% at 50% 6%, rgba(255, 255, 255, 0.42) 0%, transparent 58%),
        linear-gradient(180deg, rgba(56, 189, 248, 0.62) 0%, rgba(2, 132, 199, 0.44) 55%, rgba(14, 165, 233, 0.56) 100%);
      --btn-active-border: rgba(186, 230, 253, 0.70);
      --btn-active-shadow:
        0 8px 20px -4px rgba(14, 165, 233, 0.45),
        inset 0 1.5px 1px 0 rgba(255, 255, 255, 0.72),
        inset 0 -1.5px 2px 0 rgba(2, 132, 199, 0.50);
      --btn-active-text: #ffffff;

      --tab-active-shadow:
        0 6px 18px -4px rgba(2, 6, 23, 0.48),
        0 0 16px -4px var(--primary-glow),
        inset 0 1.5px 1px 0 rgba(255, 255, 255, 0.55),
        inset 0 -1.25px 1.5px 0 rgba(56, 189, 248, 0.24);

      /* 凹槽軌道與輸入框 */
      --well-bg: rgba(6, 11, 20, 0.55);
      --well-border: rgba(226, 232, 240, 0.13);
      --well-shadow:
        inset 0 2px 5px rgba(0, 0, 0, 0.55),
        inset 0 -1px 0.8px rgba(255, 255, 255, 0.14);

      --table-header-bg: linear-gradient(180deg, rgba(255, 255, 255, 0.09) 0%, rgba(255, 255, 255, 0.02) 100%);
      --table-hover: rgba(56, 189, 248, 0.08);
      --pill-bg: rgba(255, 255, 255, 0.07);
      --glass-pill-bg: rgba(255, 255, 255, 0.06);
    }}

    /* 淺色主題 (Apple macOS 冰川銀灰 / 冷冽藍灰柔和光場) */
    .theme-light {{
      --color-up: #dc2626;
      --color-up-bg:
        radial-gradient(100% 80% at 50% 8%, rgba(255, 255, 255, 0.85) 0%, transparent 60%),
        linear-gradient(180deg, rgba(254, 202, 202, 0.72) 0%, rgba(254, 226, 226, 0.38) 100%);
      --color-up-border: rgba(239, 68, 68, 0.42);
      --color-up-shadow: inset 0 1.5px 1px rgba(255, 255, 255, 1), 0 3px 8px -2px rgba(239, 68, 68, 0.20);

      --color-down: #059669;
      --color-down-bg:
        radial-gradient(100% 80% at 50% 8%, rgba(255, 255, 255, 0.85) 0%, transparent 60%),
        linear-gradient(180deg, rgba(167, 243, 208, 0.72) 0%, rgba(209, 250, 229, 0.38) 100%);
      --color-down-border: rgba(16, 185, 129, 0.42);
      --color-down-shadow: inset 0 1.5px 1px rgba(255, 255, 255, 1), 0 3px 8px -2px rgba(16, 185, 129, 0.20);

      --primary-accent: #0284c7;
      --primary-glow: rgba(14, 165, 233, 0.28);

      /* 冰川銀灰 + 冷冽天藍單色系柔和光場：無紫無粉，讓白色玻璃高光邊緣清晰浮現 */
      --bg-solid: #dce5f0;
      --bg-gradient:
        radial-gradient(ellipse 68% 52% at 14% 10%, rgba(186, 230, 253, 0.72) 0%, transparent 64%),
        radial-gradient(ellipse 62% 54% at 88% 88%, rgba(148, 163, 184, 0.42) 0%, transparent 66%),
        linear-gradient(155deg, #dce5f0 0%, #e8eef5 48%, #d6e2ee 100%);
      --ambient-orb-1:
        radial-gradient(520px circle at 24% 22%, rgba(125, 211, 252, 0.32) 0%, transparent 70%),
        radial-gradient(560px circle at 78% 74%, rgba(148, 163, 184, 0.24) 0%, transparent 70%);

      --text-main: #0f172a;
      --text-muted: #1e293b;
      --text-dim: #475569;
      
      /* 淺色冰川水晶玻璃：純淨白高光 + 冷藍微折射（無紫色） */
      --glass-backdrop: blur(var(--glass-blur-px, 16px)) saturate(160%);
      --glass-bg:
        linear-gradient(145deg, rgba(255, 255, 255, calc(0.68 * var(--glass-alpha-scale, 1))) 0%, rgba(248, 250, 252, calc(0.44 * var(--glass-alpha-scale, 1))) 52%, rgba(241, 245, 249, calc(0.58 * var(--glass-alpha-scale, 1))) 100%);
      --glass-bg-hover:
        linear-gradient(145deg, rgba(255, 255, 255, calc(0.78 * var(--glass-alpha-scale, 1))) 0%, rgba(248, 250, 252, calc(0.54 * var(--glass-alpha-scale, 1))) 52%, rgba(241, 245, 249, calc(0.66 * var(--glass-alpha-scale, 1))) 100%);
      --glass-border: rgba(255, 255, 255, 0.85);
      --glass-border-subtle: rgba(15, 23, 42, 0.08);
      --glass-border-specular: rgba(255, 255, 255, 1);
      --glass-shadow:
        0 18px 40px -12px rgba(15, 23, 42, 0.13),
        0 4px 12px -2px rgba(2, 132, 199, 0.07),
        0 0 0 1px rgba(15, 23, 42, 0.06),
        inset 0 1.5px 0 0 rgba(255, 255, 255, 0.96),
        inset 0 -1.5px 0 0 rgba(14, 165, 233, 0.14);

      /* 淺色 3D 凸透鏡水滴按鈕 */
      --btn-glass-bg:
        radial-gradient(110% 95% at 50% 8%, rgba(255, 255, 255, 0.95) 0%, rgba(255, 255, 255, 0.25) 55%, transparent 82%),
        linear-gradient(180deg, rgba(255, 255, 255, 0.64) 0%, rgba(248, 250, 252, 0.34) 55%, rgba(224, 242, 254, 0.50) 100%);
      --btn-glass-hover:
        radial-gradient(110% 95% at 50% 8%, rgba(255, 255, 255, 1) 0%, rgba(255, 255, 255, 0.42) 55%, transparent 82%),
        linear-gradient(180deg, rgba(255, 255, 255, 0.82) 0%, rgba(248, 250, 252, 0.50) 55%, rgba(224, 242, 254, 0.68) 100%);
      --btn-glass-border: rgba(255, 255, 255, 0.95);
      --btn-glass-shadow:
        0 6px 14px -4px rgba(15, 23, 42, 0.12),
        0 0 0 1px rgba(15, 23, 42, 0.07),
        inset 0 1.5px 1px 0 rgba(255, 255, 255, 1),
        inset 0 -1.5px 2px 0 rgba(2, 132, 199, 0.18);

      --btn-active-bg:
        radial-gradient(110% 90% at 50% 6%, rgba(255, 255, 255, 0.60) 0%, transparent 55%),
        linear-gradient(180deg, rgba(56, 189, 248, 0.92) 0%, rgba(2, 132, 199, 0.80) 55%, rgba(3, 105, 161, 0.90) 100%);
      --btn-active-border: rgba(224, 242, 254, 1);
      --btn-active-shadow:
        0 8px 18px -4px rgba(2, 132, 199, 0.38),
        inset 0 1.5px 1px 0 rgba(255, 255, 255, 0.92),
        inset 0 -1.5px 2px 0 rgba(3, 105, 161, 0.45);
      --btn-active-text: #ffffff;

      --tab-active-shadow:
        0 8px 20px -4px rgba(15, 23, 42, 0.14),
        0 2px 6px rgba(2, 132, 199, 0.12),
        0 0 0 1px rgba(15, 23, 42, 0.06),
        inset 0 2px 1px 0 rgba(255, 255, 255, 1),
        inset 0 -1.5px 2px 0 rgba(14, 165, 233, 0.20);

      --well-bg: rgba(15, 23, 42, 0.07);
      --well-border: rgba(255, 255, 255, 0.85);
      --well-shadow:
        inset 0 2px 4px rgba(15, 23, 42, 0.11),
        inset 0 -1px 1px rgba(255, 255, 255, 0.92);

      --table-header-bg: linear-gradient(180deg, rgba(255, 255, 255, 0.62) 0%, rgba(255, 255, 255, 0.24) 100%);
      --table-hover: rgba(14, 165, 233, 0.07);
      --pill-bg: rgba(255, 255, 255, 0.45);
      --glass-pill-bg: rgba(255, 255, 255, 0.52);
    }}

    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
    }}

    html {{
      background-color: var(--bg-solid, #dce5f0);
      overflow-x: clip;
    }}

    body {{
      font-family: var(--font-sans);
      background-color: var(--bg-solid, #dce5f0);
      color: var(--text-main);
      min-height: 100vh;
      max-width: 100%;
      overflow-x: clip;
      padding-bottom: 48px;
      transition: color 0.25s ease;
    }}

    /* 單一靜態固定背景光場（鎖定 GPU 合成層，零捲動重繪負擔、杜絕快速滑動露白） */
    .ambient-glow {{
      position: fixed;
      inset: 0;
      background: var(--ambient-orb-1), var(--bg-gradient);
      transform: translateZ(0);
      pointer-events: none;
      z-index: 0;
    }}

    /* 容器架構 */
    .app-container {{
      max-width: 1360px;
      margin: 0 auto;
      padding: 24px 20px;
      position: relative;
      z-index: 1;
    }}

    /* 懸浮置頂導航區 (Sticky Floating Liquid Glass Dock) */
    .sticky-top-dock-slot {{
      margin-bottom: 24px;
    }}

    .sticky-top-dock {{
      position: relative;
      z-index: 50;
      border-radius: 24px;
      border: 1px solid transparent;
      transform: translateZ(0);
      transition: background 0.25s ease, border-color 0.25s ease, box-shadow 0.25s ease, padding 0.25s var(--spring-ease);
    }}

    .sticky-top-dock.is-scrolled {{
      position: fixed;
      top: 12px;
      left: 50%;
      transform: translateX(-50%);
      width: min(calc(100% - 40px), 1320px);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      background: var(--glass-bg);
      backdrop-filter: var(--glass-backdrop);
      -webkit-backdrop-filter: var(--glass-backdrop);
      border-color: var(--glass-border);
      box-shadow: var(--glass-shadow);
      border-radius: 999px;
      padding: 8px 16px;
    }}

    /* 頂部導航欄 (Header) */
    .app-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 16px;
      padding-bottom: 20px;
      border-bottom: 1px solid var(--glass-border);
      margin-bottom: 18px;
      transition: padding-bottom 0.25s var(--spring-ease), margin-bottom 0.25s var(--spring-ease), gap 0.25s ease;
    }}

    .sticky-top-dock.is-scrolled .app-header {{
      padding-bottom: 0;
      margin-bottom: 0;
      border-bottom-color: transparent;
      flex-wrap: nowrap;
      gap: 10px;
      min-width: 0;
    }}

    .header-branding {{
      display: flex;
      align-items: center;
      min-width: 0;
    }}

    .header-title-box h1 {{
      font-size: 20px;
      font-weight: 800;
      letter-spacing: -0.02em;
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 10px;
      transition: font-size 0.22s var(--spring-ease);
    }}

    .sticky-top-dock.is-scrolled .header-title-box h1 {{
      font-size: 15px;
      flex-wrap: nowrap;
      white-space: nowrap;
      gap: 8px;
    }}

    .header-title-box .team-pill {{
      font-size: 12px;
      padding: 3px 10px;
      border-radius: 999px;
      background: var(--btn-glass-bg);
      color: var(--primary-accent);
      font-weight: 700;
      font-family: var(--font-mono);
      border: 1px solid var(--btn-glass-border);
      box-shadow: var(--btn-glass-shadow);
    }}

    .sticky-top-dock.is-scrolled .header-title-box .team-pill {{
      font-size: 11px;
      padding: 2px 8px;
    }}

    .header-subtitle {{
      font-size: 13px;
      color: var(--text-muted);
      margin-top: 4px;
      transition: opacity 0.2s ease, max-height 0.22s ease, margin-top 0.22s ease;
      max-height: 28px;
      overflow: hidden;
    }}

    .sticky-top-dock.is-scrolled .header-subtitle,
    .sticky-top-dock.is-scrolled .ios27-slider-pill,
    .sticky-top-dock.is-scrolled .theme-cycle-btn {{
      display: none;
    }}

    .sticky-top-dock.is-scrolled .date-pill {{
      padding: 4px 10px;
      font-size: 11.5px;
      white-space: nowrap;
    }}

    .sticky-top-dock.is-scrolled .tab-nav-container {{
      margin-bottom: 0;
      flex-shrink: 0;
    }}

    .sticky-top-dock.is-scrolled .segmented-control {{
      padding: 4px;
      gap: 4px;
      backdrop-filter: none;
      -webkit-backdrop-filter: none;
      box-shadow: var(--well-shadow);
    }}

    .sticky-top-dock.is-scrolled .tab-btn {{
      padding: 6px 11px;
      font-size: 12px;
      white-space: nowrap;
    }}

    @media (max-width: 1280px) {{
      .sticky-top-dock.is-scrolled .date-pill {{
        display: none;
      }}
      .sticky-top-dock.is-scrolled .tab-btn {{
        padding: 5px 9px;
        font-size: 11.5px;
      }}
    }}

    @media (max-width: 1024px) {{
      .sticky-top-dock.is-scrolled {{
        flex-direction: column;
        align-items: stretch;
        gap: 8px;
        border-radius: 22px;
        padding: 10px 12px;
      }}
      .sticky-top-dock.is-scrolled .app-header {{
        justify-content: center;
      }}
    }}

    .header-actions {{
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 10px;
    }}

    /* iOS 27 專屬：液態玻璃通透度調節器 (Liquid Glass Transparency Slider) */
    .ios27-slider-pill {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 14px;
      border-radius: 999px;
      background: var(--btn-glass-bg);
      backdrop-filter: blur(14px) saturate(150%);
      -webkit-backdrop-filter: blur(14px) saturate(150%);
      border: 1px solid var(--btn-glass-border);
      box-shadow: var(--btn-glass-shadow);
      font-size: 12px;
      font-weight: 700;
      color: var(--text-main);
    }}

    .ios27-slider-pill input[type="range"] {{
      -webkit-appearance: none;
      appearance: none;
      width: 72px;
      height: 5px;
      border-radius: 999px;
      background: var(--well-bg);
      box-shadow: var(--well-shadow);
      outline: none;
      cursor: pointer;
    }}

    .ios27-slider-pill input[type="range"]::-webkit-slider-thumb {{
      -webkit-appearance: none;
      appearance: none;
      width: 15px;
      height: 15px;
      border-radius: 50%;
      background: radial-gradient(circle at 35% 30%, #ffffff 0%, #bae6fd 55%, #0284c7 100%);
      border: 1px solid rgba(255, 255, 255, 0.95);
      box-shadow: 0 2px 6px rgba(2, 132, 199, 0.45), inset 0 1px 1px rgba(255, 255, 255, 1);
      transition: transform 0.18s var(--spring-ease);
    }}

    .ios27-slider-pill input[type="range"]::-webkit-slider-thumb:hover {{
      transform: scale(1.18);
    }}

    /* 頂部膠囊狀態標籤與全站統一液態膠囊按鈕 */
    .date-pill {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 16px;
      border-radius: 999px;
      background: var(--btn-glass-bg);
      backdrop-filter: blur(14px) saturate(150%);
      -webkit-backdrop-filter: blur(14px) saturate(150%);
      border: 1px solid var(--btn-glass-border);
      font-size: 13px;
      font-weight: 600;
      font-family: var(--font-mono);
      color: var(--text-main);
      box-shadow: var(--btn-glass-shadow);
    }}

    .date-pill::before {{
      content: '';
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #30d158;
      display: inline-block;
      box-shadow: 0 0 8px #30d158, inset 0 1px 1px rgba(255, 255, 255, 0.8);
    }}

    /* 全站共用液態玻璃膠囊按鈕基礎 (Header / Tab 2 / Tab 4 統一元素) */
    .theme-toggle-btn,
    .filter-btn,
    .report-action-btn {{
      background: var(--btn-glass-bg);
      border: 1px solid var(--btn-glass-border);
      color: var(--text-main);
      border-radius: 999px;
      padding: 8px 16px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 7px;
      font-size: 13px;
      font-weight: 700;
      font-family: var(--font-sans);
      box-shadow: var(--btn-glass-shadow);
      position: relative;
      transition: transform 0.2s var(--spring-ease), background 0.18s ease, color 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
    }}

    /* 三段式主題切換器 (淺色 / 深色 / 跟隨裝置) */
    .theme-cycle-btn {{
      width: 36px;
      height: 36px;
      border-radius: 999px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 16px;
      line-height: 1;
      padding: 0;
      border: 1px solid var(--btn-glass-border);
      background: var(--btn-glass-bg);
      color: var(--text-main);
      box-shadow: var(--btn-glass-shadow);
      cursor: pointer;
      transition: background 0.2s ease, transform 0.2s var(--spring-ease), border-color 0.2s ease;
    }}

    .theme-cycle-btn:hover {{
      background: var(--btn-glass-hover);
      border-color: var(--glass-border-specular);
      transform: translateY(-1px) scale(1.04);
    }}

    .theme-cycle-btn:active {{
      transform: scale(0.94);
    }}

    .theme-toggle-btn:hover,
    .filter-btn:hover,
    .report-action-btn:hover:not(:disabled) {{
      background: var(--btn-glass-hover);
      color: var(--text-main);
      transform: translateY(-1px) scale(1.015);
    }}

    .theme-toggle-btn:active,
    .filter-btn:active,
    .report-action-btn:active:not(:disabled) {{
      transform: translateY(0) scale(0.96);
    }}

    .report-action-btn:disabled {{
      opacity: 0.4;
      cursor: not-allowed;
    }}

    /* 主選單分頁切換 (Tabs) - 液態玻璃膠囊控制器 */
    .tab-nav-container {{
      display: flex;
      justify-content: center;
      margin-bottom: 28px;
    }}

    .segmented-control {{
      display: inline-flex;
      background: var(--well-bg);
      padding: 6px;
      border-radius: 999px;
      border: 1px solid var(--well-border);
      box-shadow: var(--well-shadow), 0 10px 26px -8px rgba(0, 0, 0, 0.18);
      gap: 6px;
      position: relative;
      isolation: isolate;
    }}

    .tab-btn {{
      border: 1px solid transparent;
      background: transparent;
      color: var(--text-muted);
      padding: 10px 20px;
      font-size: 14px;
      font-weight: 700;
      font-family: var(--font-sans);
      border-radius: 999px;
      cursor: pointer;
      transition: background 0.2s ease, color 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s var(--spring-ease);
      display: flex;
      align-items: center;
      gap: 8px;
      position: relative;
      overflow: hidden;
    }}

    .tab-btn:hover:not(.active) {{
      color: var(--text-main);
      background: var(--pill-bg);
    }}

    .tab-btn:active {{
      transform: scale(0.96);
    }}

    .tab-btn.active {{
      background: var(--btn-glass-hover);
      color: var(--text-main);
      border: 1px solid var(--glass-border-specular);
      box-shadow: var(--tab-active-shadow);
    }}

    /* 液態玻璃卡片通用樣式（輕量化單層玻璃，backdrop-filter 僅留給懸浮導航列與目錄以消除長頁面捲動白屏） */
    .glass-card {{
      background: var(--glass-bg);
      border: 1px solid var(--glass-border);
      border-radius: 26px;
      padding: 22px;
      box-shadow: var(--glass-shadow);
      position: relative;
      isolation: isolate;
      transition: transform 0.25s var(--spring-ease), border-color 0.25s ease;
    }}

    /* 頂部 KPI 卡片網格 */
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 16px;
      margin-bottom: 28px;
    }}

    .kpi-card {{
      padding: 20px 22px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }}

    .kpi-card:hover {{
      transform: translateY(-2px);
      border-color: var(--glass-border-specular);
    }}

    .kpi-label {{
      font-size: 13px;
      font-weight: 600;
      color: var(--text-muted);
      display: flex;
      align-items: center;
      gap: 6px;
    }}

    .kpi-value {{
      font-size: 24px;
      font-weight: 800;
      font-family: var(--font-mono);
      letter-spacing: -0.02em;
      margin: 8px 0 4px 0;
    }}

    .kpi-subtext {{
      font-size: 12px;
      font-weight: 600;
      color: var(--text-dim);
      display: flex;
      align-items: center;
      gap: 6px;
    }}

    .kpi-card-interactive {{
      cursor: pointer;
    }}

    .kpi-card-interactive:hover {{
      border-color: var(--primary-accent);
      box-shadow: 0 12px 28px -10px var(--primary-glow), var(--glass-shadow);
    }}

    .kpi-action-pill {{
      font-size: 11px;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 999px;
      background: var(--well-bg);
      border: 1px solid var(--glass-border);
      color: var(--primary-accent);
      white-space: nowrap;
    }}

    .ranking-subview-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
      margin-bottom: 18px;
    }}

    .ranking-my-team-banner {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      flex-wrap: wrap;
      padding: 14px 18px;
      margin-bottom: 18px;
      border-color: rgba(56, 189, 248, 0.30);
    }}

    html.theme-light .ranking-my-team-banner {{
      border-color: rgba(2, 132, 199, 0.24);
    }}

    tr.ranking-my-team-row td {{
      background: rgba(56, 189, 248, 0.12);
      font-weight: 700;
    }}

    html.theme-light tr.ranking-my-team-row td {{
      background: rgba(2, 132, 199, 0.08);
    }}

    tr.ranking-my-team-row td:first-child {{
      box-shadow: inset 3px 0 0 var(--primary-accent);
    }}

    .group-badge {{
      display: inline-flex;
      align-items: center;
      padding: 3px 9px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 700;
      border: 1px solid var(--glass-border);
      background: var(--well-bg);
      color: var(--text-muted);
      white-space: nowrap;
    }}

    .group-badge.society {{
      color: var(--primary-accent);
      background: rgba(56, 189, 248, 0.12);
      border-color: rgba(56, 189, 248, 0.35);
    }}

    html.theme-light .group-badge.society {{
      background: rgba(2, 132, 199, 0.10);
      border-color: rgba(2, 132, 199, 0.30);
    }}

    .ranking-toolbar-controls {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
      max-width: 100%;
    }}

    @media (max-width: 768px) {{
      .ranking-toolbar-controls {{
        width: 100%;
      }}
      .ranking-toolbar-controls .search-box {{
        flex: 1 1 100%;
        min-width: 0;
      }}
      .ranking-toolbar-controls .report-select {{
        flex: 1 1 auto;
      }}
    }}

    /* 歷史圖表區域 (雙欄並排：NAV/現金 + 累計總報酬率) */
    .overview-charts-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 20px;
      margin-bottom: 28px;
    }}

    .overview-charts-grid .glass-card {{
      min-width: 0;
      overflow: hidden;
    }}

    @media (max-width: 960px) {{
      .overview-charts-grid {{
        grid-template-columns: minmax(0, 1fr);
      }}
    }}

    .chart-section {{
      margin-bottom: 28px;
    }}

    .chart-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
    }}

    .chart-title {{
      font-size: 16px;
      font-weight: 700;
      display: flex;
      align-items: center;
      gap: 8px;
    }}

    .chart-wrapper {{
      height: 280px;
      width: 100%;
    }}

    /* 表格控制與搜尋工具列 */
    .table-toolbar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 14px;
      margin-bottom: 18px;
    }}

    .filter-pills {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      padding: 4px;
      border-radius: 999px;
      background: var(--well-bg);
      border: 1px solid var(--well-border);
      box-shadow: var(--well-shadow);
    }}

    /* 液態玻璃膠囊按鈕 active 狀態（基礎樣式已與全站按鈕統一） */
    .filter-btn {{
      color: var(--text-muted);
      padding: 8px 18px;
    }}

    .filter-btn.active {{
      background: var(--btn-active-bg);
      color: var(--btn-active-text);
      border-color: var(--btn-active-border);
      box-shadow: var(--btn-active-shadow);
      text-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
    }}

    .search-box {{
      position: relative;
      display: flex;
      align-items: center;
      min-width: 248px;
    }}

    /* 液態玻璃內凹搜尋框 */
    .search-input {{
      width: 100%;
      background: var(--well-bg);
      border: 1px solid var(--well-border);
      box-shadow: var(--well-shadow);
      padding: 9px 16px 9px 38px;
      border-radius: 999px;
      color: var(--text-main);
      font-size: 13px;
      font-family: var(--font-sans);
      outline: none;
      transition: border-color 0.25s ease, box-shadow 0.25s ease, background 0.25s ease;
    }}

    .search-input::placeholder {{
      color: var(--text-dim);
    }}

    .search-input:focus {{
      border-color: var(--primary-accent);
      background: var(--btn-glass-bg);
      box-shadow:
        0 0 0 3px var(--primary-glow),
        inset 0 1px 1px rgba(255, 255, 255, 0.35);
    }}

    .search-icon {{
      position: absolute;
      left: 14px;
      top: 50%;
      transform: translateY(-50%);
      display: inline-flex;
      align-items: center;
      justify-content: center;
      line-height: 1;
      font-size: 13px;
      color: var(--text-dim);
      pointer-events: none;
    }}

    /* 專業表格樣式 (Table) - 富果高密度 + 液態玻璃質感 */
    .table-container {{
      overflow-x: auto;
      contain: layout style;
      border-radius: 18px;
      border: 1px solid var(--glass-border);
      background: rgba(255, 255, 255, 0.01);
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
    }}

    table.fugle-table tbody tr {{
      content-visibility: auto;
      contain-intrinsic-size: auto 52px;
    }}

    table.fugle-table {{
      width: 100%;
      border-collapse: separate;
      border-spacing: 0;
      font-size: 13px;
    }}

    table.fugle-table th {{
      background: var(--table-header-bg);
      color: var(--text-muted);
      font-weight: 700;
      text-align: right;
      padding: 13px 14px;
      border-bottom: 1px solid var(--glass-border);
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.14);
      white-space: nowrap;
      cursor: pointer;
      user-select: none;
      transition: color 0.18s ease, background 0.18s ease;
    }}

    table.fugle-table th:first-child {{
      text-align: left;
      border-top-left-radius: 16px;
    }}
    table.fugle-table th:nth-child(2) {{
      text-align: left;
    }}
    table.fugle-table th:last-child {{
      border-top-right-radius: 16px;
    }}

    table.fugle-table th:hover {{
      color: var(--text-main);
      background: var(--btn-glass-hover);
    }}

    table.fugle-table th:active {{
      transform: scale(0.98);
    }}

    table.fugle-table th.no-sort {{
      cursor: default;
    }}
    table.fugle-table th.no-sort:hover {{
      color: var(--text-muted);
      background: var(--table-header-bg);
    }}
    table.fugle-table th.no-sort:active {{
      transform: none;
    }}

    table.fugle-table th .sort-icon {{
      margin-left: 4px;
      font-size: 11px;
      opacity: 0.55;
      display: inline-block;
      transition: transform 0.2s ease, opacity 0.2s ease;
    }}
    table.fugle-table th:hover .sort-icon {{
      opacity: 0.9;
    }}
    table.fugle-table th.sorted .sort-icon {{
      opacity: 1;
      color: var(--primary-accent);
    }}

    table.fugle-table td {{
      padding: 14px;
      border-bottom: 1px solid var(--glass-border-subtle);
      text-align: right;
      font-family: var(--font-mono);
      white-space: nowrap;
    }}

    table.fugle-table tbody tr:last-child td {{
      border-bottom: none;
    }}

    table.fugle-table td:first-child,
    table.fugle-table td:nth-child(2) {{
      text-align: left;
    }}

    table.fugle-table tbody tr:not(.usage-stages-row):not(.holdings-drawer-row):hover td {{
      background: var(--table-hover);
    }}

    .holdings-row {{
      cursor: pointer;
    }}

    .holdings-row.expanded .usage-chevron {{
      transform: rotate(90deg);
      color: var(--primary-accent);
    }}

    .holdings-drawer-row td {{
      padding: 0 !important;
      border-bottom: 1px solid var(--glass-border-subtle);
    }}

    .holdings-lot-drawer {{
      padding: 14px 20px;
      background: rgba(0, 0, 0, 0.14);
    }}

    html.theme-light .holdings-lot-drawer {{
      background: rgba(15, 23, 42, 0.03);
    }}

    .holdings-lot-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
      font-family: var(--font-mono);
    }}

    .holdings-lot-table th {{
      background: transparent !important;
      box-shadow: none !important;
      padding: 6px 10px !important;
      font-size: 11px;
      color: var(--text-dim);
      border-bottom: 1px solid var(--glass-border-subtle);
      cursor: default !important;
      text-align: right;
    }}

    .holdings-lot-table th:first-child {{
      text-align: left;
      border-radius: 0 !important;
    }}

    .holdings-lot-table td {{
      padding: 8px 10px !important;
      border-bottom: 1px solid var(--glass-border-subtle);
      text-align: right;
      font-size: 12px;
    }}

    .holdings-lot-table td:first-child {{
      text-align: left;
    }}

    .holdings-lot-table tbody tr:last-child td {{
      border-bottom: none;
    }}

    .lot-count-badge {{
      font-size: 10.5px;
      font-weight: 700;
      font-family: var(--font-mono);
      padding: 2px 7px;
      border-radius: 999px;
      background: var(--glass-pill-bg);
      border: 1px solid var(--glass-border-subtle);
      color: var(--primary-accent);
    }}

    /* 股票標籤 */
    .stock-tag-box {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}

    .stock-code {{
      font-weight: 800;
      font-family: var(--font-mono);
      font-size: 14px;
      color: var(--text-main);
    }}

    .stock-name {{
      font-weight: 700;
      font-family: var(--font-sans);
      font-size: 14px;
      color: var(--text-main);
    }}

    /* 市場微型液態膠囊 */
    .market-badge {{
      font-size: 11px;
      padding: 3px 9px;
      border-radius: 999px;
      background: var(--btn-glass-bg);
      border: 1px solid var(--btn-glass-border);
      box-shadow: inset 0 1px 0.5px rgba(255, 255, 255, 0.25);
      color: var(--text-muted);
      font-family: var(--font-sans);
      font-weight: 600;
    }}

    /* 漲跌與部位液態玻璃徽章 (Liquid Glass Micro-Capsules) */
    .badge-pnl {{
      display: inline-flex;
      align-items: center;
      padding: 3.5px 10px;
      border-radius: 999px;
      font-weight: 700;
      font-size: 12px;
      font-family: var(--font-mono);
    }}

    .badge-pnl.up {{
      background: var(--color-up-bg);
      color: var(--color-up);
      border: 1px solid var(--color-up-border);
      box-shadow: var(--color-up-shadow);
    }}

    .badge-pnl.down {{
      background: var(--color-down-bg);
      color: var(--color-down);
      border: 1px solid var(--color-down-border);
      box-shadow: var(--color-down-shadow);
    }}

    .badge-pnl.flat {{
      color: var(--color-flat);
    }}

    .badge-held {{
      background: var(--btn-active-bg);
      color: var(--btn-active-text);
      border: 1px solid var(--btn-active-border);
      box-shadow:
        inset 0 1px 0.5px rgba(255, 255, 255, 0.6),
        0 2px 8px -2px var(--primary-glow);
    }}

    /* 權重液態光條 */
    .weight-bar-wrapper {{
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 8px;
    }}

    .weight-progress {{
      width: 54px;
      height: 7px;
      border-radius: 999px;
      background: var(--well-bg);
      box-shadow: var(--well-shadow);
      overflow: hidden;
    }}

    .weight-fill {{
      height: 100%;
      background: linear-gradient(90deg, #38bdf8, #0284c7);
      border-radius: 999px;
      box-shadow: inset 0 1px 0.5px rgba(255, 255, 255, 0.65);
    }}

    /* 頁腳 */
    .app-footer {{
      margin-top: 40px;
      text-align: center;
      font-size: 12px;
      color: var(--text-dim);
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}

    /* RWD 適應與動態減敏支援 */
    @media (prefers-reduced-motion: reduce) {{
      *, *::before, *::after {{
        transition-duration: 0.01ms !important;
      }}
    }}

    @media (max-width: 768px) {{
      .app-container {{
        padding: 14px 12px;
      }}
      .sticky-top-dock.is-scrolled {{
        width: calc(100% - 24px);
        top: 8px;
        padding: 8px 10px;
        border-radius: 18px;
      }}
      .sticky-top-dock.is-scrolled .header-title-box h1 {{
        white-space: normal;
        flex-wrap: wrap;
        justify-content: center;
        text-align: center;
        font-size: 14px;
      }}
      .sticky-top-dock.is-scrolled .tab-btn {{
        white-space: normal;
        padding: 6px 8px;
        font-size: 11.5px;
        line-height: 1.25;
      }}
      .app-header {{
        flex-direction: column;
        align-items: flex-start;
      }}
      .header-actions {{
        width: 100%;
        justify-content: space-between;
        gap: 8px;
      }}
      .segmented-control {{
        width: 100%;
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        border-radius: 20px;
      }}
      .tab-btn {{
        justify-content: center;
        padding: 9px 10px;
        font-size: 12.5px;
        min-width: 0;
        text-align: center;
      }}
      .kpi-grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 10px;
      }}
      .kpi-card {{
        padding: 14px;
        min-width: 0;
      }}
      .kpi-value {{
        font-size: 17px;
        word-break: break-word;
      }}
      .glass-card {{
        min-width: 0;
        max-width: 100%;
      }}
      .table-toolbar {{
        flex-direction: column;
        align-items: stretch;
      }}
      .filter-pills {{
        border-radius: 18px;
        justify-content: center;
      }}
      .search-box {{
        min-width: 0;
        width: 100%;
      }}
    }}

    /* ================= AI 模型用量與成本監控 (Tab 3) ================= */
    .usage-charts-grid {{
      display: grid;
      grid-template-columns: minmax(0, 2fr) minmax(0, 1fr);
      gap: 20px;
      margin-bottom: 20px;
    }}

    .usage-chart-card {{
      padding: 20px 24px;
      min-width: 0;
      overflow: hidden;
    }}

    @media (max-width: 960px) {{
      .usage-charts-grid {{
        grid-template-columns: minmax(0, 1fr);
      }}
    }}

    @media (max-width: 768px) {{
      .usage-chart-card {{
        padding: 16px;
      }}
    }}

    .usage-chart-title {{
      font-size: 15px;
      font-weight: 700;
      margin-bottom: 14px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 8px;
      color: var(--text-main);
    }}

    .usage-chart-subtitle {{
      font-size: 12px;
      font-weight: 500;
      color: var(--text-dim);
    }}

    .routing-card {{
      padding: 18px 22px;
      margin-bottom: 24px;
    }}

    .routing-pills-grid {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 12px;
    }}

    .routing-pill {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 14px;
      border-radius: 999px;
      background: var(--glass-pill-bg);
      border: 1px solid var(--glass-border-subtle);
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.16);
      font-size: 12px;
      font-weight: 600;
    }}

    /* 成本監控 Model 標籤與沙盒標籤：與全站一致的液態水滴微膠囊 */
    .model-badge,
    .code-exec-badge {{
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 3.5px 10px;
      border-radius: 999px;
      font-family: var(--font-mono);
      font-size: 11px;
      font-weight: 700;
    }}

    .model-badge.flash {{
      background:
        radial-gradient(100% 80% at 50% 8%, rgba(255, 255, 255, 0.28) 0%, transparent 60%),
        linear-gradient(180deg, rgba(16, 185, 129, 0.24) 0%, rgba(5, 150, 105, 0.10) 100%);
      color: #34d399;
      border: 1px solid rgba(52, 211, 153, 0.40);
      box-shadow: inset 0 1px 0.5px rgba(255, 255, 255, 0.35), 0 2px 6px -2px rgba(16, 185, 129, 0.25);
    }}

    .model-badge.carbon {{
      background:
        radial-gradient(100% 80% at 50% 8%, rgba(255, 255, 255, 0.24) 0%, transparent 60%),
        linear-gradient(180deg, rgba(148, 163, 184, 0.28) 0%, rgba(71, 85, 105, 0.16) 100%);
      color: #f1f5f9;
      border: 1px solid rgba(203, 213, 225, 0.42);
      box-shadow: inset 0 1px 0.5px rgba(255, 255, 255, 0.35), 0 2px 6px -2px rgba(15, 23, 42, 0.35);
    }}

    .model-badge.argon {{
      background:
        radial-gradient(100% 80% at 50% 8%, rgba(255, 255, 255, 0.28) 0%, transparent 60%),
        linear-gradient(180deg, rgba(56, 189, 248, 0.26) 0%, rgba(2, 132, 199, 0.12) 100%);
      color: #38bdf8;
      border: 1px solid rgba(56, 189, 248, 0.42);
      box-shadow: inset 0 1px 0.5px rgba(255, 255, 255, 0.35), 0 2px 6px -2px rgba(56, 189, 248, 0.25);
    }}

    .model-badge.fallback {{
      background:
        radial-gradient(100% 80% at 50% 8%, rgba(255, 255, 255, 0.28) 0%, transparent 60%),
        linear-gradient(180deg, rgba(245, 158, 11, 0.24) 0%, rgba(217, 119, 6, 0.10) 100%);
      color: #fbbf24;
      border: 1px solid rgba(251, 191, 36, 0.40);
      box-shadow: inset 0 1px 0.5px rgba(255, 255, 255, 0.35), 0 2px 6px -2px rgba(245, 158, 11, 0.22);
    }}

    .code-exec-badge {{
      background:
        radial-gradient(100% 80% at 50% 8%, rgba(255, 255, 255, 0.26) 0%, transparent 60%),
        linear-gradient(180deg, rgba(99, 102, 241, 0.24) 0%, rgba(79, 70, 229, 0.10) 100%);
      color: #a5b4fc;
      border: 1px solid rgba(129, 140, 248, 0.40);
      box-shadow: inset 0 1px 0.5px rgba(255, 255, 255, 0.32), 0 2px 6px -2px rgba(99, 102, 241, 0.22);
    }}

    html.theme-light .model-badge.flash {{
      background:
        radial-gradient(100% 80% at 50% 8%, rgba(255, 255, 255, 0.85) 0%, transparent 60%),
        linear-gradient(180deg, rgba(167, 243, 208, 0.72) 0%, rgba(209, 250, 229, 0.38) 100%);
      color: #047857;
      border-color: rgba(16, 185, 129, 0.42);
      box-shadow: inset 0 1.5px 1px rgba(255, 255, 255, 1), 0 2px 6px -2px rgba(16, 185, 129, 0.18);
    }}

    html.theme-light .model-badge.carbon {{
      background:
        radial-gradient(100% 80% at 50% 8%, rgba(255, 255, 255, 0.75) 0%, transparent 60%),
        linear-gradient(180deg, rgba(51, 65, 85, 0.16) 0%, rgba(100, 116, 139, 0.08) 100%);
      color: #1e293b;
      border-color: rgba(71, 85, 105, 0.38);
      box-shadow: inset 0 1.5px 1px rgba(255, 255, 255, 0.9), 0 2px 6px -2px rgba(15, 23, 42, 0.14);
    }}

    html.theme-light .model-badge.argon {{
      background:
        radial-gradient(100% 80% at 50% 8%, rgba(255, 255, 255, 0.85) 0%, transparent 60%),
        linear-gradient(180deg, rgba(186, 230, 253, 0.76) 0%, rgba(224, 242, 254, 0.42) 100%);
      color: #0369a1;
      border-color: rgba(14, 165, 233, 0.42);
      box-shadow: inset 0 1.5px 1px rgba(255, 255, 255, 1), 0 2px 6px -2px rgba(2, 132, 199, 0.18);
    }}

    html.theme-light .model-badge.fallback {{
      background:
        radial-gradient(100% 80% at 50% 8%, rgba(255, 255, 255, 0.85) 0%, transparent 60%),
        linear-gradient(180deg, rgba(253, 230, 138, 0.74) 0%, rgba(254, 243, 199, 0.42) 100%);
      color: #b45309;
      border-color: rgba(245, 158, 11, 0.42);
      box-shadow: inset 0 1.5px 1px rgba(255, 255, 255, 1), 0 2px 6px -2px rgba(245, 158, 11, 0.18);
    }}

    html.theme-light .code-exec-badge {{
      background:
        radial-gradient(100% 80% at 50% 8%, rgba(255, 255, 255, 0.85) 0%, transparent 60%),
        linear-gradient(180deg, rgba(199, 210, 254, 0.74) 0%, rgba(224, 231, 255, 0.42) 100%);
      color: #4338ca;
      border-color: rgba(99, 102, 241, 0.40);
      box-shadow: inset 0 1.5px 1px rgba(255, 255, 255, 1), 0 2px 6px -2px rgba(99, 102, 241, 0.18);
    }}

    .usage-day-row {{
      cursor: pointer;
    }}

    .usage-chevron {{
      display: inline-block;
      transition: transform 0.2s ease;
      font-size: 11px;
      margin-right: 6px;
      color: var(--text-dim);
    }}

    .usage-day-row.expanded .usage-chevron {{
      transform: rotate(90deg);
      color: var(--primary-accent);
    }}

    .usage-stages-row td {{
      padding: 0 !important;
      border-bottom: 1px solid var(--glass-border-subtle);
    }}

    .usage-stages-drawer {{
      padding: 14px 20px;
      background: rgba(0, 0, 0, 0.16);
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
    }}

    html.theme-light .usage-stages-drawer {{
      background: rgba(0, 0, 0, 0.03);
    }}

    .stage-mini-card {{
      padding: 12px 14px;
      border-radius: 14px;
      background: var(--glass-pill-bg);
      border: 1px solid var(--glass-border-subtle);
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}

    .stage-mini-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 12px;
      font-weight: 700;
    }}

    .stage-mini-metrics {{
      display: flex;
      justify-content: space-between;
      font-size: 11px;
      color: var(--text-muted);
      font-family: var(--font-mono);
    }}

    /* ================= 每日決策報告瀏覽器 (Tab 4) ================= */
    .report-toolbar {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 16px 20px;
      margin-bottom: 18px;
    }}

    .report-controls-left {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 10px;
      max-width: 100%;
      min-width: 0;
    }}

    .report-controls-right {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 10px;
      max-width: 100%;
      min-width: 0;
    }}

    .report-select {{
      appearance: none;
      max-width: 100%;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      background: var(--btn-glass-bg);
      color: var(--text-main);
      border: 1px solid var(--btn-glass-border);
      box-shadow: var(--btn-glass-shadow);
      border-radius: 999px;
      padding: 8px 36px 8px 16px;
      font-family: var(--font-sans);
      font-size: 13px;
      font-weight: 700;
      cursor: pointer;
      outline: none;
      background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%2394a3b8' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E");
      background-repeat: no-repeat;
      background-position: right 14px center;
      transition: border-color 0.2s, box-shadow 0.2s, background-color 0.2s;
    }}

    .report-select:hover, .report-select:focus {{
      border-color: var(--primary-accent);
      box-shadow: var(--btn-glass-shadow), 0 0 0 3px var(--primary-glow);
    }}

    .report-select option {{
      background: #0f172a;
      color: #f8fafc;
    }}

    html.theme-light .report-select option {{
      background: #ffffff;
      color: #0f172a;
    }}

    .report-meta-pill {{
      font-size: 12px;
      color: var(--text-dim);
      font-family: var(--font-mono);
      padding: 7px 14px;
      border-radius: 999px;
      background: var(--glass-pill-bg);
      border: 1px solid var(--glass-border-subtle);
      max-width: 100%;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}

    .report-layout {{
      display: grid;
      grid-template-columns: 260px minmax(0, 1fr);
      gap: 18px;
      align-items: start;
    }}

    .report-toc-card {{
      position: sticky;
      top: 86px;
      max-height: calc(100vh - 104px);
      overflow-y: auto;
      padding: 18px 16px;
      backdrop-filter: var(--glass-backdrop);
      -webkit-backdrop-filter: var(--glass-backdrop);
    }}

    .report-toc-title {{
      font-size: 13px;
      font-weight: 700;
      color: var(--text-muted);
      margin-bottom: 10px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}

    .report-toc-list {{
      display: flex;
      flex-direction: column;
      gap: 4px;
    }}

    .report-toc-item {{
      display: block;
      text-align: left;
      width: 100%;
      background: transparent;
      border: none;
      border-radius: 9px;
      padding: 6px 10px;
      color: var(--text-muted);
      font-family: var(--font-sans);
      font-size: 12.5px;
      line-height: 1.4;
      cursor: pointer;
      transition: background 0.15s, color 0.15s;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}

    .report-toc-item:hover {{
      background: var(--glass-pill-bg);
      color: var(--text-main);
    }}

    .report-toc-item.active {{
      background: var(--btn-glass-bg);
      color: var(--primary-accent);
      font-weight: 700;
      box-shadow: inset 2.5px 0 0 var(--primary-accent);
    }}

    .report-toc-item.toc-h3 {{
      padding-left: 22px;
      font-size: 12px;
      color: var(--text-dim);
    }}

    .markdown-body h2,
    .markdown-body h3 {{
      scroll-margin-top: 90px;
    }}

    .report-body-card {{
      padding: 28px 32px;
      min-width: 0;
    }}

    .markdown-body {{
      color: var(--text-main);
      font-size: 14.5px;
      line-height: 1.75;
      word-wrap: break-word;
    }}

    .markdown-body h1 {{
      font-size: 22px;
      font-weight: 800;
      margin: 0 0 16px 0;
      padding-bottom: 12px;
      border-bottom: 1px solid var(--glass-border-subtle);
      letter-spacing: -0.01em;
    }}

    .markdown-body h2 {{
      font-size: 18px;
      font-weight: 700;
      margin: 28px 0 12px 0;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--glass-border-subtle);
      scroll-margin-top: 88px;
    }}

    .markdown-body h3 {{
      font-size: 15.5px;
      font-weight: 700;
      margin: 20px 0 10px 0;
      color: var(--primary-accent);
      scroll-margin-top: 88px;
    }}

    .markdown-body h4 {{
      font-size: 14.5px;
      font-weight: 700;
      margin: 18px 0 8px 0;
      padding: 8px 12px;
      border-radius: 10px;
      background: var(--glass-pill-bg);
      border: 1px solid var(--glass-border-subtle);
    }}

    .markdown-body p {{
      margin: 10px 0;
    }}

    .markdown-body ul, .markdown-body ol {{
      margin: 8px 0;
      padding-left: 22px;
    }}

    .markdown-body li {{
      margin: 4px 0;
    }}

    .markdown-body hr {{
      border: none;
      border-top: 1px solid var(--glass-border-subtle);
      margin: 22px 0;
    }}

    .markdown-body blockquote {{
      margin: 10px 0 14px 0;
      padding: 10px 16px;
      border-left: 3px solid var(--primary-accent);
      border-radius: 0 12px 12px 0;
      background: rgba(56, 189, 248, 0.08);
      color: var(--text-muted);
    }}

    html.theme-light .markdown-body blockquote {{
      background: rgba(14, 165, 233, 0.07);
    }}

    .markdown-body blockquote p {{
      margin: 4px 0;
    }}

    .markdown-body code {{
      font-family: var(--font-mono);
      font-size: 0.86em;
      padding: 2px 6px;
      border-radius: 6px;
      background: rgba(148, 163, 184, 0.16);
      border: 1px solid var(--glass-border-subtle);
    }}

    .markdown-body pre {{
      padding: 14px 16px;
      border-radius: 12px;
      background: rgba(15, 23, 42, 0.65);
      border: 1px solid var(--glass-border-subtle);
      overflow-x: auto;
      margin: 12px 0;
    }}

    html.theme-light .markdown-body pre {{
      background: rgba(241, 245, 249, 0.9);
    }}

    .markdown-body pre code {{
      padding: 0;
      background: transparent;
      border: none;
      font-size: 12.5px;
    }}

    .report-table-wrap {{
      width: 100%;
      overflow-x: auto;
      margin: 14px 0 18px 0;
      border-radius: 14px;
      border: 1px solid var(--glass-border-subtle);
    }}

    /* ================= 專案介紹與技術亮點 (Tab 5) ================= */
    .about-hero-card {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 20px;
      margin-bottom: 24px;
      padding: 26px 28px;
    }}

    .about-hero-text {{
      flex: 1 1 520px;
    }}

    .about-hero-title {{
      font-size: 20px;
      font-weight: 800;
      letter-spacing: -0.02em;
      margin-bottom: 10px;
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 10px;
    }}

    .about-hero-desc {{
      font-size: 14px;
      line-height: 1.75;
      color: var(--text-muted);
    }}

    .github-cta-btn {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 11px 22px;
      border-radius: 999px;
      background: var(--btn-active-bg);
      color: var(--btn-active-text);
      border: 1px solid var(--btn-active-border);
      box-shadow: var(--btn-active-shadow);
      font-size: 13.5px;
      font-weight: 700;
      font-family: var(--font-sans);
      text-decoration: none;
      white-space: nowrap;
      transition: transform 0.2s var(--spring-ease), box-shadow 0.2s ease;
    }}

    .github-cta-btn:hover {{
      transform: translateY(-2px) scale(1.02);
    }}

    .pipeline-flow {{
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 12px;
      margin-top: 16px;
    }}

    @media (max-width: 1100px) {{
      .pipeline-flow {{
        grid-template-columns: repeat(3, minmax(0, 1fr));
      }}
    }}

    @media (max-width: 640px) {{
      .pipeline-flow {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
    }}

    .pipeline-step {{
      padding: 14px;
      border-radius: 16px;
      background: var(--glass-pill-bg);
      border: 1px solid var(--glass-border-subtle);
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}

    .pipeline-step-tag {{
      font-family: var(--font-mono);
      font-size: 11px;
      font-weight: 800;
      color: var(--primary-accent);
    }}

    .pipeline-step-title {{
      font-size: 13.5px;
      font-weight: 700;
      color: var(--text-main);
    }}

    .pipeline-step-desc {{
      font-size: 12px;
      line-height: 1.55;
      color: var(--text-dim);
    }}

    .highlights-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 18px;
      margin-top: 24px;
    }}

    @media (max-width: 960px) {{
      .highlights-grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
    }}

    @media (max-width: 640px) {{
      .highlights-grid {{
        grid-template-columns: minmax(0, 1fr);
      }}
    }}

    .highlight-card {{
      padding: 20px 22px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }}

    .highlight-card-title {{
      font-size: 15px;
      font-weight: 800;
      color: var(--text-main);
      display: flex;
      align-items: center;
      gap: 8px;
    }}

    .highlight-card-desc {{
      font-size: 13px;
      line-height: 1.7;
      color: var(--text-muted);
    }}

    .footer-link {{
      color: var(--primary-accent);
      text-decoration: none;
      font-family: var(--font-mono);
      font-weight: 600;
    }}

    .footer-link:hover {{
      text-decoration: underline;
    }}

    .markdown-body table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}

    .markdown-body th {{
      background: var(--table-header-bg);
      color: var(--text-muted);
      font-weight: 700;
      padding: 10px 12px;
      border-bottom: 1px solid var(--glass-border);
      white-space: nowrap;
    }}

    .markdown-body td {{
      padding: 9px 12px;
      border-bottom: 1px solid var(--glass-border-subtle);
      vertical-align: top;
      min-width: 72px;
    }}

    .markdown-body tbody tr:last-child td {{
      border-bottom: none;
    }}

    .markdown-body tbody tr:hover td {{
      background: var(--table-hover);
    }}

    @media (max-width: 960px) {{
      .report-layout {{
        grid-template-columns: 1fr;
      }}
      .report-toc-card {{
        position: static;
        max-height: 260px;
      }}
      .report-body-card {{
        padding: 18px 16px;
      }}
    }}

    @media (max-width: 768px) {{
      .report-toolbar {{
        padding: 14px;
      }}
      .report-controls-left,
      .report-controls-right {{
        width: 100%;
      }}
      #reportDateSelect {{
        width: 100%;
        flex: 1 1 100%;
        order: -1;
      }}
      .report-controls-left .report-action-btn {{
        flex: 1 1 0;
        justify-content: center;
      }}
    }}
  </style>
</head>
<body>
  <!-- 單一靜態冷冽藍灰／冰川銀柔和光場 -->
  <div class="ambient-glow"></div>

  <div class="app-container">
    <div class="sticky-top-dock-slot" id="stickyTopDockSlot">
      <div class="sticky-top-dock" id="stickyTopDock">
      <!-- 頂部標頭 -->
      <header class="app-header">
        <div class="header-branding">
          <div class="header-title-box">
            <h1>
              <span>2026 玉山 AI Agent 基金經理人</span>
              <span class="team-pill">TEAM_11402</span>
            </h1>
            <div class="header-subtitle">打造你的最佳 ETF 投資組合</div>
          </div>
        </div>
        <div class="header-actions">
          <div class="date-pill" id="dateBadge">基準日: {summary_data['as_of_date']} · 賽期 {progress['elapsed']}/{progress['total']} 天</div>
          <div class="ios27-slider-pill" title="液態玻璃通透度調節 (左：極致冰晶 / 右：溫潤凝霜)">
            <span>💧 通透度</span>
            <input type="range" id="glassAlphaSlider" min="35" max="145" value="100" oninput="setGlassTransparency(this.value)">
          </div>
          <button type="button" class="theme-cycle-btn" id="themeToggleBtn" onclick="toggleTheme()" title="切換深色模式" aria-label="切換深色或淺色模式">🌙</button>
        </div>
      </header>

      <!-- 分頁導航切換 -->
      <div class="tab-nav-container">
        <div class="segmented-control">
          <button class="tab-btn active" id="tabBtn1" onclick="switchTab('tab1')">
            <span>📊</span> 帳戶總覽
          </button>
          <button class="tab-btn" id="tabBtn2" onclick="switchTab('tab2')">
            <span>📈</span> 行情群組
          </button>
          <button class="tab-btn" id="tabBtn6" onclick="switchTab('tab6')">
            <span>🧾</span> 歷史成交明細
          </button>
          <button class="tab-btn" id="tabBtn4" onclick="switchTab('tab4')">
            <span>📄</span> 決策報告
          </button>
          <button class="tab-btn" id="tabBtn3" onclick="switchTab('tab3')">
            <span>🤖</span> AI 模型成本監控
          </button>
          <button class="tab-btn" id="tabBtn5" onclick="switchTab('tab5')">
            <span>💡</span> 專案亮點
          </button>
        </div>
      </div>
      </div>
    </div>

    <!-- ================= 頁籤 1: 帳戶總覽與庫存損益 ================= -->
    <div id="tab1Content">
      <div id="tab1OverviewView">
      <!-- 頂部 KPI 卡片 -->
      <div class="kpi-grid">
        <div class="glass-card kpi-card">
          <div class="kpi-label">可交易淨值 (NAV)</div>
          <div class="kpi-value">${account['nav']:,.0f}</div>
          <div class="kpi-subtext">初始資金 $1,000,000,000</div>
        </div>
        <div class="glass-card kpi-card">
          <div class="kpi-label">可動用現金 (Cash)</div>
          <div class="kpi-value">${account['cash']:,.0f}</div>
          <div class="kpi-subtext">現金比率 {account['cash_ratio_pct']:.2f}%</div>
        </div>
        <div class="glass-card kpi-card">
          <div class="kpi-label">總持股市值</div>
          <div class="kpi-value">${account['stock_value']:,.0f}</div>
          <div class="kpi-subtext">未實現損益 ${account['unrealized_pnl']:,.0f}</div>
        </div>
        <div class="glass-card kpi-card">
          <div class="kpi-label">持股檔數 / 合規</div>
          <div class="kpi-value">{account['holdings_count']} <span style="font-size:14px; color:var(--text-muted);">/ 20~30檔</span></div>
          <div class="kpi-subtext">⚠️ 違規 {account['violations']} 次 · 提示 {account['notices']} 次</div>
        </div>
        <div class="glass-card kpi-card">
          <div class="kpi-label">累計總報酬率 / 當日</div>
          <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
            <div class="kpi-value {'badge-pnl up' if account['cum_return_pct'] >= 0 else 'badge-pnl down'}" style="display:inline-block; font-size:22px;">
              {'+' if account['cum_return_pct'] >= 0 else ''}{account['cum_return_pct']:.2f}%
            </div>
            <span class="badge-pnl {'up' if account.get('day_return_pct', 0) >= 0 else 'down'}" style="font-size:12px;">
              當日 {'+' if account.get('day_return_pct', 0) >= 0 else ''}{account.get('day_return_pct', 0):.2f}%
            </span>
          </div>
          <div class="kpi-subtext">累計損益 ${account['cum_pnl']:,.0f}</div>
        </div>
        <div class="glass-card kpi-card kpi-card-interactive" onclick="openRankingView()" title="點擊查看全體競賽排行榜">
          <div class="kpi-label" style="justify-content:space-between; width:100%;">
            <span>競賽排名 (總 / 社會組)</span>
            <span class="kpi-action-pill">🏆 完整榜單 →</span>
          </div>
          <div class="kpi-value" style="display:flex; align-items:baseline; gap:8px; flex-wrap:wrap;">
            <span>#{account.get('rank') or '--'}</span>
            <span style="font-size:13px; color:var(--text-muted);">/ {account.get('total_teams') or '--'}</span>
            {f"<span class='badge-pnl {'up' if account.get('rank_diff', 0) > 0 else ('down' if account.get('rank_diff', 0) < 0 else '')}' style='font-size:11px;'>{'▲' + str(account['rank_diff']) if account.get('rank_diff', 0) > 0 else ('▼' + str(abs(account['rank_diff'])) if account.get('rank_diff', 0) < 0 else '持平')}</span>" if account.get('rank') else ''}
          </div>
          <div class="kpi-subtext">社會組 #{account.get('group_rank') or '--'}/{account.get('group_total') or '--'} · 學生組 {account.get('student_total') or '--'} 隊</div>
        </div>
      </div>

      <!-- 資產走勢與累計總報酬率雙折線圖 -->
      <div class="overview-charts-grid">
        <div class="glass-card">
          <div class="chart-header">
            <div class="chart-title">
              <span>📈</span> 每日可交易淨值 (NAV) 與現金水位
            </div>
          </div>
          <div class="chart-wrapper">
            <canvas id="assetHistoryChart"></canvas>
          </div>
        </div>
        <div class="glass-card">
          <div class="chart-header">
            <div class="chart-title">
              <span>🚀</span> 累計總報酬率 (%) 趨勢
            </div>
          </div>
          <div class="chart-wrapper">
            <canvas id="cumReturnChart"></canvas>
          </div>
        </div>
      </div>

      <!-- 競賽排名走勢與每日報酬率/集中度雙圖 -->
      <div class="overview-charts-grid">
        <div class="glass-card">
          <div class="chart-header">
            <div class="chart-title">
              <span>🏆</span> 每日競賽排名走勢 (總排名 / 社會組)
            </div>
            <button type="button" class="report-action-btn" onclick="openRankingView()" style="font-size:12px; padding:6px 12px;">🏆 完整榜單 →</button>
          </div>
          <div class="chart-wrapper">
            <canvas id="rankHistoryChart"></canvas>
          </div>
        </div>
        <div class="glass-card">
          <div class="chart-header">
            <div class="chart-title">
              <span>📊</span> 單日報酬率 (%)
            </div>
          </div>
          <div class="chart-wrapper">
            <canvas id="dayReturnChart"></canvas>
          </div>
        </div>
      </div>

      <!-- 目前庫存持股明細表 -->
      <div class="glass-card">
        <div class="table-toolbar">
          <div>
            <div class="chart-title">
              <span>📋</span> 目前庫存部位與未實現損益明細 ({len(held_positions)} 檔)
            </div>
            <div style="font-size:12px; color:var(--text-dim); margin-top:4px;">點擊任一持股列即可展開分批買進明細（建倉日期、張數、成交價與各批損益）</div>
          </div>
          <div style="display:flex; gap:10px; flex-wrap:wrap; align-items:center;">
            <span class="report-meta-pill">行情更新於 {market_updated_at} · 帳戶基準日 {summary_data['as_of_date']}</span>
            <div class="search-box">
              <span class="search-icon">🔍</span>
              <input type="text" class="search-input" id="holdingsSearchInput" placeholder="搜尋代號或名稱..." oninput="filterHoldingsTable()">
            </div>
          </div>
        </div>

        <div class="table-container">
          <table class="fugle-table" id="holdingsTable">
            <thead>
              <tr>
                <th onclick="sortHoldings('code')">代號/名稱 <span class="sort-icon">⇅</span></th>
                <th onclick="sortHoldings('market')">市場 <span class="sort-icon">⇅</span></th>
                <th onclick="sortHoldings('holding_days')">持有天數 <span class="sort-icon">⇅</span></th>
                <th onclick="sortHoldings('lots')">庫存張數 <span class="sort-icon">⇅</span></th>
                <th onclick="sortHoldings('avg_cost')">成本均價 <span class="sort-icon">⇅</span></th>
                <th onclick="sortHoldings('close_price')">最新現價 <span class="sort-icon">⇅</span></th>
                <th onclick="sortHoldings('change_pct')">今日漲跌 <span class="sort-icon">⇅</span></th>
                <th onclick="sortHoldings('market_value')">現值 (元) <span class="sort-icon">⇅</span></th>
                <th onclick="sortHoldings('unrealized_pnl')">未實現損益 <span class="sort-icon">⇅</span></th>
                <th onclick="sortHoldings('unrealized_return_pct')">報酬率 <span class="sort-icon">⇅</span></th>
                <th onclick="sortHoldings('weight_pct')">佔比 <span class="sort-icon">⇅</span></th>
              </tr>
            </thead>
            <tbody id="holdingsTableBody">
              <!-- JS 動態渲染 -->
            </tbody>
          </table>
        </div>
      </div>
      </div> <!-- /#tab1OverviewView -->

      <!-- Tab 1 內嵌子視圖：競賽全體排行榜 -->
      <div id="tab1RankingView" style="display: none;">
        <div class="ranking-subview-header">
          <div style="display:flex; align-items:center; gap:12px; flex-wrap:wrap;">
            <button type="button" class="report-action-btn" onclick="closeRankingView()">← 返回帳戶總覽</button>
            <div class="chart-title" style="font-size:18px;">
              <span>🏆</span> 競賽全體即時排行榜
            </div>
          </div>
        </div>

        <div class="kpi-grid" id="rankingKpiGrid"></div>

        <div class="glass-card ranking-my-team-banner" id="rankingMyTeamBanner" style="display:none;"></div>

        <div class="glass-card">
          <div class="table-toolbar">
            <div>
              <div class="chart-title">
                <span>📋</span> 各隊績效與淨值排行明細
              </div>
              <div style="font-size:12px; color:var(--text-dim); margin-top:4px;">支援組別篩選、隊伍搜尋與點擊表頭排序 · 淨值以億元顯示</div>
            </div>
            <div class="ranking-toolbar-controls">
              <div class="filter-pills">
                <button type="button" class="filter-btn active" id="rankFilterAll" onclick="setRankingGroup('all')">全部</button>
                <button type="button" class="filter-btn" id="rankFilterSociety" onclick="setRankingGroup('society')">社會組</button>
                <button type="button" class="filter-btn" id="rankFilterStudent" onclick="setRankingGroup('student')">學生組</button>
              </div>
              <select class="report-select" id="rankingLimitSelect" onchange="renderRankingTable()">
                <option value="50">顯示前 50 名</option>
                <option value="100" selected>顯示前 100 名</option>
                <option value="0">顯示全部隊伍</option>
              </select>
              <div class="search-box">
                <span class="search-icon">🔍</span>
                <input type="text" class="search-input" id="rankingSearchInput" placeholder="搜尋隊伍 (如 TEAM_11402)..." oninput="renderRankingTable()">
              </div>
            </div>
          </div>

          <div class="table-container">
            <table class="fugle-table" id="rankingTable">
              <thead>
                <tr>
                  <th onclick="sortRankingTable('rank')">總排名 <span class="sort-icon">⇅</span></th>
                  <th onclick="sortRankingTable('team')">隊伍代號 <span class="sort-icon">⇅</span></th>
                  <th onclick="sortRankingTable('group')" style="text-align:left;">組別 <span class="sort-icon">⇅</span></th>
                  <th onclick="sortRankingTable('group_rank')">組別排名 <span class="sort-icon">⇅</span></th>
                  <th onclick="sortRankingTable('rank_diff')" id="rankDiffHeader">總名次變動 <span class="sort-icon">⇅</span></th>
                  <th onclick="sortRankingTable('cum_return')">累計報酬率 <span class="sort-icon">⇅</span></th>
                  <th onclick="sortRankingTable('day_return')">當日報酬率 <span class="sort-icon">⇅</span></th>
                  <th onclick="sortRankingTable('aum')">淨值 (AUM) <span class="sort-icon">⇅</span></th>
                </tr>
              </thead>
              <tbody id="rankingTableBody">
                <!-- JS 動態渲染 -->
              </tbody>
            </table>
          </div>
        </div>
      </div> <!-- /#tab1RankingView -->
    </div>

    <!-- ================= 頁籤 2: 自選行情觀察群組 ================= -->
    <div id="tab2Content" style="display: none;">
      <div class="glass-card">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:14px;">
          <div class="chart-title">
            <span>📈</span> 行情觀察群組 ({len(all_stocks_list)} 檔)
          </div>
          <span class="report-meta-pill">行情更新於 {market_updated_at}</span>
        </div>
        <div class="table-toolbar">
          <div class="filter-pills">
            <button class="filter-btn active" id="btnGroupA" onclick="setWatchGroup('held')">
              我的持股 ({len(held_positions)} 檔)
            </button>
            <button class="filter-btn" id="btnGroupWatch" onclick="setWatchGroup('watchlist')">
              觀察標的 ({watchlist_count} 檔)
            </button>
            <button class="filter-btn" id="btnGroupB" onclick="setWatchGroup('unheld')">
              其餘標的 ({150 - len(held_positions)} 檔)
            </button>
            <button class="filter-btn" id="btnGroupAll" onclick="setWatchGroup('all')">
              全部 {len(all_stocks_list)} 檔
            </button>
          </div>

          <div style="display:flex; gap:10px; flex-wrap:wrap; align-items:center;">
            <div class="filter-pills">
              <button class="filter-btn" id="sortGainBtn" onclick="setSortMode('gain')">📈 漲幅由大到小</button>
              <button class="filter-btn" id="sortLossBtn" onclick="setSortMode('loss')">📉 跌幅由大到小</button>
            </div>
            <div class="search-box">
              <span class="search-icon">🔍</span>
              <input type="text" class="search-input" id="watchSearchInput" placeholder="搜尋 150 檔標的..." oninput="renderWatchTable()">
            </div>
          </div>
        </div>

        <div class="table-container">
          <table class="fugle-table" id="watchTable">
            <thead>
              <tr>
                <th onclick="setSortCol('code')">代號/名稱 <span class="sort-icon">⇅</span></th>
                <th onclick="setSortCol('market')">市場 <span class="sort-icon">⇅</span></th>
                <th onclick="setSortCol('close_price')">最新現價 <span class="sort-icon">⇅</span></th>
                <th onclick="setSortCol('prev_close')">昨日收盤 <span class="sort-icon">⇅</span></th>
                <th onclick="setSortCol('change')">漲跌價差 <span class="sort-icon">⇅</span></th>
                <th onclick="setSortCol('change_pct')">漲跌幅 <span class="sort-icon">⇅</span></th>
                <th onclick="setSortCol('volume_lots')">成交量 (張) <span class="sort-icon">⇅</span></th>
                <th style="text-align: center;">10-27起走勢 (Sparkline)</th>
                <th>持股狀態</th>
              </tr>
            </thead>
            <tbody id="watchTableBody">
              <!-- JS 動態渲染 -->
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ================= 頁籤 3: AI 模型用量與成本監控 ================= -->
    <div id="tab3Content" style="display: none;">
      <!-- 區塊 A: 5 大核心 KPI 卡片 (由 JS 動態渲染) -->
      <div class="kpi-grid" id="usageKpiGrid"></div>

      <!-- 區塊 B: 3 組 Chart.js 互動圖表 -->
      <div class="usage-charts-grid">
        <div class="glass-card usage-chart-card">
          <div class="usage-chart-title">
            <span>📈 每日花費 (USD) 與 Token 消耗雙軸趨勢</span>
            <span class="usage-chart-subtitle" id="usageUpdatedAtBadge"></span>
          </div>
          <div style="height: 290px; position: relative;">
            <canvas id="usageTrendChart"></canvas>
          </div>
        </div>

        <div class="glass-card usage-chart-card">
          <div class="usage-chart-title">
            <span>🍩 各任務階段費用佔比</span>
            <span class="usage-chart-subtitle">L0 ~ L4 算力分佈</span>
          </div>
          <div style="height: 290px; position: relative;">
            <canvas id="usageStageDonutChart"></canvas>
          </div>
        </div>
      </div>

      <div class="glass-card usage-chart-card" style="margin-bottom: 24px;">
        <div class="usage-chart-title">
          <span>📊 每日 Token 細部構成分析 (Prompt / Completion / Code Execution / Thinking)</span>
          <span class="usage-chart-subtitle">單位：Tokens</span>
        </div>
        <div style="height: 260px; position: relative;">
          <canvas id="usageTokenStackChart"></canvas>
        </div>
      </div>

      <!-- 區塊 C: LiteLLM Multi-Model 路由架構速覽 -->
      <div class="glass-card routing-card">
        <div class="usage-chart-title" style="margin-bottom: 4px;">
          <span>🧭 LiteLLM Multi-Model 動態路由與自動降級備援架構</span>
          <span class="usage-chart-subtitle">models_config.yaml</span>
        </div>
        <div class="routing-pills-grid">
          <div class="routing-pill">
            <span>L0 股票池篩選</span>
            <span class="model-badge carbon">gemini-4-carbon</span>
            <span class="code-exec-badge">🐍 Code Exec</span>
            <span style="color:var(--text-dim); font-size:11px;">備援: gemini-4-argon</span>
          </div>
          <div class="routing-pill">
            <span>L1 事實擷取</span>
            <span class="model-badge flash">gemini-3.8-flash</span>
            <span style="color:var(--text-dim); font-size:11px;">備援: gemini-3.6-flash</span>
          </div>
          <div class="routing-pill">
            <span>L2M 市場走向</span>
            <span class="model-badge carbon">gemini-4-carbon</span>
            <span class="code-exec-badge">🐍 Code Exec</span>
            <span style="color:var(--text-dim); font-size:11px;">備援: gemini-4-argon</span>
          </div>
          <div class="routing-pill">
            <span>L2 個股推論</span>
            <span class="model-badge carbon">gemini-4-carbon</span>
            <span class="code-exec-badge">🐍 Code Exec</span>
            <span style="color:var(--text-dim); font-size:11px;">備援: gemini-4-argon</span>
          </div>
          <div class="routing-pill">
            <span>L3 投組決策</span>
            <span class="model-badge carbon">gemini-4-carbon</span>
            <span class="code-exec-badge">🐍 Code Exec</span>
            <span style="color:var(--text-dim); font-size:11px;">備援: gemini-4-argon</span>
          </div>
          <div class="routing-pill">
            <span>L4 委託計算</span>
            <span class="model-badge carbon">gemini-4-carbon</span>
            <span class="code-exec-badge">🐍 Code Exec</span>
            <span style="color:var(--text-dim); font-size:11px;">備援: gemini-4-argon</span>
          </div>
        </div>
      </div>

      <!-- 區塊 D: 每日歷史用量下鑽折疊表 -->
      <div class="glass-card">
        <div class="table-toolbar">
          <div>
            <h3 style="font-size:16px; font-weight:700; margin:0;">📅 每日歷史用量與 6 階段執行明細</h3>
            <div style="font-size:12px; color:var(--text-dim); margin-top:4px;">點擊任一交易日即可展開該日 L0 ～ L4 各階段模型、Token 結構、Code Execution 次數與耗時明細</div>
          </div>
        </div>
        <div class="table-container">
          <table class="fugle-table" id="usageDailyTable">
            <thead>
              <tr>
                <th>交易日期</th>
                <th>呼叫數</th>
                <th>輸入 Prompt</th>
                <th>輸出 Completion</th>
                <th>工具 Code Exec</th>
                <th>思考 Thinking</th>
                <th>總 Tokens</th>
                <th>Python 沙盒</th>
                <th>當日總耗時</th>
                <th>當日花費 (USD)</th>
              </tr>
            </thead>
            <tbody id="usageDailyTableBody">
              <!-- JS 動態渲染 -->
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ================= 頁籤 4: 每日決策報告瀏覽器 ================= -->
    <div id="tab4Content" style="display: none;">
      <div class="glass-card report-toolbar">
        <div class="report-controls-left">
          <button class="report-action-btn" id="reportPrevBtn" onclick="stepReport(1)" title="上一期 (較舊報告)">⬅️ 較舊</button>
          <select class="report-select" id="reportDateSelect" onchange="selectReportByIndex(Number(this.value))"></select>
          <button class="report-action-btn" id="reportNextBtn" onclick="stepReport(-1)" title="下一期 (較新報告)">較新 ➡️</button>
        </div>
        <div class="report-controls-right">
          <span class="report-meta-pill" id="reportMetaPill">--</span>
          <button class="report-action-btn" id="reportCopyBtn" onclick="copyCurrentReportMarkdown()">📋 複製 Markdown</button>
        </div>
      </div>

      <div class="report-layout">
        <aside class="glass-card report-toc-card">
          <div class="report-toc-title">
            <span>📑 報告章節目錄</span>
            <span id="reportTocCount" style="font-size:11px; color:var(--text-dim);"></span>
          </div>
          <nav class="report-toc-list" id="reportTocList">
            <!-- JS 動態從渲染後標題生成 -->
          </nav>
        </aside>
        <article class="glass-card report-body-card">
          <div class="markdown-body" id="reportMarkdownBody">
            <!-- JS 動態渲染 Markdown -->
          </div>
        </article>
      </div>
    </div>

    <!-- ================= 頁籤 5: 專案介紹與技術亮點 ================= -->
    <div id="tab5Content" style="display: none;">
      <div class="glass-card about-hero-card">
        <div class="about-hero-text">
          <div class="about-hero-title">
            <span>🤖 2026 玉山 AI Agent 基金經理人</span>
            <span class="badge-pnl badge-held" style="font-size:11.5px;">TEAM_11402</span>
          </div>
          <div class="about-hero-desc">
            本系統為 <strong>2026 玉山人工智慧公開挑戰賽（AI CUP 2026）</strong> 所建置的「<strong>Multi-Agent 自主量化投資決策產線（D-Plan v4.3）</strong>」與「<strong>即時投資組合監控看板</strong>」雙核心平台。透過分層因果推論、原生 Python 沙盒運算與官方線上預檢核閘門，讓 AI 每日無人值守完成盤後多源數據萃取、市場研判、個股推論、委託算單與自動繳交，並即時同步至本看板進行 FinOps 成本與部位覆核。
          </div>
        </div>
        <a class="github-cta-btn" href="https://github.com/codyliao0327/esun-ai-cup-2026" target="_blank" rel="noopener noreferrer">
          <span>🔗</span> 前往 GitHub Repo
        </a>
      </div>

      <div class="glass-card" style="margin-bottom: 24px;">
        <div class="chart-title" style="margin-bottom: 12px; display:flex; align-items:center; flex-wrap:wrap; gap:10px;">
          <span>🎯</span>
          <span>ETF 投資策略</span>
          <span class="badge-pnl badge-held" style="font-size:12px;">{etf_name_esc}</span>
        </div>
        <div style="padding: 12px 16px; border-radius: 14px; background: var(--glass-pill-bg); border: 1px solid var(--glass-border-subtle); margin-bottom: 12px; font-size: 13.5px; color: var(--text-main);">
          <strong style="color: var(--primary-accent);">投資主題：</strong>{etf_theme_esc}
        </div>
        <div style="font-size: 13.5px; line-height: 1.8; color: var(--text-muted);">
          <strong style="color: var(--text-main);">投資理念：</strong>{etf_phil_esc}
        </div>
      </div>

      <div class="glass-card">
        <div class="chart-title" style="margin-bottom: 4px;">
          <span>🧭</span> 分層因果推論決策架構（L0 ➔ L4 Pipeline）
        </div>
        <div style="font-size:12.5px; color:var(--text-dim);">嚴格遵循單向因果引用鏈與官方 D-Plan Schema v4.3 規範，確保每一筆委託皆具備完整可追溯推論依據</div>
        <div class="pipeline-flow">
          <div class="pipeline-step">
            <span class="pipeline-step-tag">L0 · Pool & Sources</span>
            <span class="pipeline-step-title">動態選股與多源數據</span>
            <span class="pipeline-step-desc">透過 OAuth2 SSO 與 SSR 憑證自動萃取整合多源數據，並結合量化初篩與 LLM 補撈建構動態觀察池。</span>
          </div>
          <div class="pipeline-step">
            <span class="pipeline-step-tag">L1 · Observations</span>
            <span class="pipeline-step-title">客觀事實與數值校準</span>
            <span class="pipeline-step-desc">壓縮為高密度 Compact Array JSON 降低 Token 消耗，並以原始數值程式覆寫防範數值失真。</span>
          </div>
          <div class="pipeline-step">
            <span class="pipeline-step-tag">L2M · Market View</span>
            <span class="pipeline-step-title">市場走向研判</span>
            <span class="pipeline-step-desc">分析宏觀盤勢 Regime、資金水位與整體多空風險立場。</span>
          </div>
          <div class="pipeline-step">
            <span class="pipeline-step-tag">L2 · Inferences</span>
            <span class="pipeline-step-title">個股深度推論</span>
            <span class="pipeline-step-desc">針對精選候選池進行基本面、動能與風險因子因果推論，並強制揭露反面證據。</span>
          </div>
          <div class="pipeline-step">
            <span class="pipeline-step-tag">L3 · Decisions</span>
            <span class="pipeline-step-title">投組權重決策</span>
            <span class="pipeline-step-desc">控管持股檔數、移動停利追蹤與整體部位風險平衡配置。</span>
          </div>
          <div class="pipeline-step">
            <span class="pipeline-step-tag">L4 · Orders & UI</span>
            <span class="pipeline-step-title">委託算單與預檢繳交</span>
            <span class="pipeline-step-desc">千股整股算單與 Active Share 覆核後通過官方預檢閘門繳交，產出稽核報告並同步更新本看板。</span>
          </div>
        </div>
      </div>

      <div class="highlights-grid">
        <div class="glass-card highlight-card">
          <div class="highlight-card-title"><span>🧠</span> 因果引用鏈與雙層 Pydantic Schema</div>
          <div class="highlight-card-desc">落實 L0 ➔ L4 單向無循環 DAG 引用驗證，並分離輕量 <code>Draft</code>（避免結構化輸出 FSM 狀態爆炸）與嚴格 <code>Final</code>（<code>extra='forbid'</code>）模型，杜絕孤兒節點與格式偏差。</div>
        </div>
        <div class="glass-card highlight-card">
          <div class="highlight-card-title"><span>🐍</span> 原生 Python 沙盒與底層原始碼稽核</div>
          <div class="highlight-card-desc">於 L0、L2M、L2、L3、L4 核心階段全面啟用 Gemini 原生 Code Execution 沙盒消除算術幻覺，並透過底層 Hook 攔截串流與非串流 <code>executable_code</code> 留存稽核。</div>
        </div>
        <div class="glass-card highlight-card">
          <div class="highlight-card-title"><span>🧭</span> LiteLLM Multi-Model 動態路由與備援</div>
          <div class="highlight-card-desc">透過 <code>litellm.Router</code> 依任務複雜度分流 <code>gemini-3.8-flash</code>（海量事實擷取）與 <code>gemini-4-carbon</code>（深度推理決策），並配置自動重試與異常降級備援（Fallback）。</div>
        </div>
        <div class="glass-card highlight-card">
          <div class="highlight-card-title"><span>🛡️</span> 三層 JSON 容錯與 L1 原始數值覆寫</div>
          <div class="highlight-card-desc">結合串流模式結構化輸出與 <code>json-repair</code> 三層容錯解析鏈，並於 L1 後處理以程式端原始數據 100% 覆寫 <code>values</code> 與 <code>source_ref</code>，徹底杜絕浮點數幻覺與缺漏。</div>
        </div>
        <div class="glass-card highlight-card">
          <div class="highlight-card-title"><span>⚡</span> 動態遞補與 Compact Array JSON 工程</div>
          <div class="highlight-card-desc">基本面季報／月營收與社群情緒採各股獨立動態遞補最新非空值並保留真實公告時間戳，搭配單行 Compact Array JSON 壓縮，在有限視窗中極大化資訊密度。</div>
        </div>
        <div class="glass-card highlight-card">
          <div class="highlight-card-title"><span>🎯</span> 三階段動態股票池篩選引擎</div>
          <div class="highlight-card-desc">每日自法定上市櫃母體出發，結合量化相對動能初篩、高階 LLM 依籌碼與同業估值補撈遺珠，並強制聯集帳上現有持股，兼顧盤面輪動靈敏度與部位連續性。</div>
        </div>
        <div class="glass-card highlight-card">
          <div class="highlight-card-title"><span>🔐</span> 全自動多源認證與訪客憑證萃取</div>
          <div class="highlight-card-desc">透過 OAuth2 SSO 自動增量同步競賽後台歷史與 DataPack（內建盤後結算就緒守護），並自 CMoney SSR 原始碼自動萃取訪客 JWT 搭配 401 自動重取重試，實現零人工介入。</div>
        </div>
        <div class="glass-card highlight-card">
          <div class="highlight-card-title"><span>🚦</span> 官方線上預檢核閘門與無人值守繳交</div>
          <div class="highlight-card-desc">D-Plan 組裝完成後自動上傳官方 <code>/validate/</code> 端點執行零容忍預檢核（任何異常即中止阻擋），全數通過後才執行正式繳交並驗證官方收據與產出每日回顧報告。</div>
        </div>
        <div class="glass-card highlight-card">
          <div class="highlight-card-title"><span>💎</span> 全鏈路 FinOps 監控與液態玻璃看板</div>
          <div class="highlight-card-desc">實施全階段無條件 Prompt 存檔、19 項 LiteLLM 原生 Usage 成本監控、玉山行情 SDK 開市日曆自校準、FIFO 批次成本追蹤，並支援一鍵更新與 Cloudflare Pages 自動部署。</div>
        </div>
      </div>
    </div>

    <!-- ================= 頁籤 6: 歷史成交明細與摩擦成本 ================= -->
    <div id="tab6Content" style="display: none;">
      <div class="kpi-grid">
        <div class="glass-card kpi-card">
          <div class="kpi-label">累計買進金額 ({friction.get('total_buy_count', 0)} 筆)</div>
          <div class="kpi-value">${friction.get('total_buy_amount', 0):,.0f}</div>
          <div class="kpi-subtext">總成交金額 ${friction.get('total_traded_amount', 0):,.0f}</div>
        </div>
        <div class="glass-card kpi-card">
          <div class="kpi-label">累計賣出金額 ({friction.get('total_sell_count', 0)} 筆)</div>
          <div class="kpi-value">${friction.get('total_sell_amount', 0):,.0f}</div>
          <div class="kpi-subtext">共 {friction.get('total_buy_count', 0) + friction.get('total_sell_count', 0)} 筆成交</div>
        </div>
        <div class="glass-card kpi-card">
          <div class="kpi-label">累計手續費 / 證交稅</div>
          <div class="kpi-value">${friction.get('total_friction_cost', 0):,.2f}</div>
          <div class="kpi-subtext">手續費 ${friction.get('total_fee', 0):,.2f} · 證交稅 ${friction.get('total_tax', 0):,.2f}</div>
        </div>
        <div class="glass-card kpi-card">
          <div class="kpi-label">淨已實現損益 (扣費稅)</div>
          <div class="kpi-value {'badge-pnl up' if friction.get('net_realized_pnl', 0) >= 0 else 'badge-pnl down'}" style="display:inline-block; font-size:22px;">
            {'+' if friction.get('net_realized_pnl', 0) >= 0 else ''}${friction.get('net_realized_pnl', 0):,.0f}
          </div>
          <div class="kpi-subtext">毛已實現 {'+' if friction.get('gross_realized_pnl', 0) >= 0 else ''}${friction.get('gross_realized_pnl', 0):,.0f}</div>
        </div>
      </div>

      <div class="glass-card">
        <div class="table-toolbar">
          <div>
            <div class="chart-title">
              <span>🧾</span> 歷史每日成交明細（來自官方後台 JSON 精確紀錄）
            </div>
            <div style="font-size:12px; color:var(--text-dim); margin-top:4px;" id="tradesFilterSummary">載入中...</div>
          </div>
          <div style="display:flex; gap:10px; flex-wrap:wrap; align-items:center;">
            <select id="tradesDateSelect" class="report-select" onchange="renderTradesTab()">
              <option value="ALL">全部交易日</option>
            </select>
            <select id="tradesSideSelect" class="report-select" onchange="renderTradesTab()">
              <option value="ALL">全部方向</option>
              <option value="買進">買進</option>
              <option value="賣出">賣出</option>
            </select>
            <div class="search-box">
              <span class="search-icon">🔍</span>
              <input type="text" class="search-input" id="tradesSearchInput" placeholder="搜尋代號或名稱..." oninput="renderTradesTab()">
            </div>
          </div>
        </div>

        <div class="table-container">
          <table class="fugle-table" id="tradesHistoryTable">
            <thead>
              <tr>
                <th class="no-sort">交易日</th>
                <th class="no-sort">買/賣</th>
                <th class="no-sort" style="text-align: left;">代號/名稱</th>
                <th class="no-sort">張數 (股數)</th>
                <th class="no-sort">成交均價</th>
                <th class="no-sort">成交金額 (元)</th>
                <th class="no-sort">手續費 (元)</th>
                <th class="no-sort">證交稅 (元)</th>
              </tr>
            </thead>
            <tbody id="tradesHistoryTableBody">
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- 頁尾 -->
    <footer class="app-footer">
      <div>
        AI CUP 2026 玉山人工智慧公開挑戰賽 · 隊伍 TEAM_11402 專用看板 ·
        <a class="footer-link" href="https://github.com/codyliao0327/esun-ai-cup-2026" target="_blank" rel="noopener noreferrer">GitHub Repo</a>
      </div>
      <div>數據更新自官方 DataPack 與玉山證券行情 SDK · 僅供研究與競賽內部覆核使用</div>
    </footer>
  </div>

  <!-- 資料 Payload 注入 -->
  <script>
    const DASHBOARD_DATA = {safe_json_payload};
  </script>

  <!-- 核心互動邏輯腳本 -->
  <script>
    let currentTab = 'tab1';
    let currentWatchGroup = 'held';
    let currentSortMode = 'none'; // 'gain', 'loss', 'col'
    let watchSortCol = 'change_pct';
    let watchSortAsc = false;

    let holdingsSortCol = 'weight_pct';
    let holdingsSortAsc = false;

    // 主題切換 (循環單鍵：淺色 ⇄ 深色，預設淺色；淺色顯示 🌙、深色顯示 ☀️)
    let currentThemeMode = 'light';

    function applyResolvedTheme(mode) {{
      const html = document.documentElement;
      const useDark = (mode === 'dark');
      html.classList.toggle('theme-dark', useDark);
      html.classList.toggle('theme-light', !useDark);
      const themeMeta = document.getElementById('themeColorMeta');
      if (themeMeta) themeMeta.setAttribute('content', useDark ? '#060b14' : '#dce5f0');
      const toggleBtn = document.getElementById('themeToggleBtn');
      if (toggleBtn) {{
        toggleBtn.textContent = useDark ? '☀️' : '🌙';
        toggleBtn.title = useDark ? '切換淺色模式' : '切換深色模式';
      }}
      if (window.assetChart) {{
        updateChartTheme();
      }}
    }}

    function toggleTheme() {{
      const nextMode = (currentThemeMode === 'dark') ? 'light' : 'dark';
      currentThemeMode = nextMode;
      localStorage.setItem('esun_dashboard_theme', nextMode);
      applyResolvedTheme(nextMode);
    }}

    // 初始化主題與輕量化液態玻璃通透度滑桿
    function setGlassTransparency(val) {{
      const scale = (Number(val) / 100).toFixed(2);
      const blurPx = Math.round(6 + (Number(val) / 100) * 10);
      document.documentElement.style.setProperty('--glass-alpha-scale', scale);
      document.documentElement.style.setProperty('--glass-blur-px', blurPx + 'px');
      localStorage.setItem('esun_dashboard_glass_alpha', val);
    }}

    (function initTheme() {{
      const saved = localStorage.getItem('esun_dashboard_theme');
      const initialMode = (saved === 'dark') ? 'dark' : 'light';
      currentThemeMode = initialMode;
      applyResolvedTheme(initialMode);

      const savedAlpha = localStorage.getItem('esun_dashboard_glass_alpha');
      if (savedAlpha !== null) {{
        const slider = document.getElementById('glassAlphaSlider');
        if (slider) slider.value = savedAlpha;
        setGlassTransparency(savedAlpha);
      }}
    }})();

    // 分頁切換
    function switchTab(tabId) {{
      currentTab = tabId;
      document.getElementById('tabBtn1').classList.toggle('active', tabId === 'tab1');
      document.getElementById('tabBtn2').classList.toggle('active', tabId === 'tab2');
      document.getElementById('tabBtn3').classList.toggle('active', tabId === 'tab3');
      document.getElementById('tabBtn4').classList.toggle('active', tabId === 'tab4');
      document.getElementById('tabBtn5').classList.toggle('active', tabId === 'tab5');
      document.getElementById('tabBtn6').classList.toggle('active', tabId === 'tab6');
      document.getElementById('tab1Content').style.display = tabId === 'tab1' ? 'block' : 'none';
      document.getElementById('tab2Content').style.display = tabId === 'tab2' ? 'block' : 'none';
      document.getElementById('tab3Content').style.display = tabId === 'tab3' ? 'block' : 'none';
      document.getElementById('tab4Content').style.display = tabId === 'tab4' ? 'block' : 'none';
      document.getElementById('tab5Content').style.display = tabId === 'tab5' ? 'block' : 'none';
      document.getElementById('tab6Content').style.display = tabId === 'tab6' ? 'block' : 'none';
      if (tabId === 'tab1') {{
        closeRankingView(false);
      }} else if (tabId === 'tab2') {{
        renderWatchTable();
      }} else if (tabId === 'tab3') {{
        renderUsageTab();
      }} else if (tabId === 'tab4') {{
        renderReportsTab();
      }} else if (tabId === 'tab6') {{
        renderTradesTab();
      }}
    }}

    // 格式化數字
    function fmtNum(n, d = 2) {{
      if (n === null || n === undefined || isNaN(n)) return '--';
      return Number(n).toLocaleString('en-US', {{ minimumFractionDigits: d, maximumFractionDigits: d }});
    }}

    // 渲染庫存表格
    function renderHoldingsTable() {{
      const query = (document.getElementById('holdingsSearchInput').value || '').trim().toLowerCase();
      let list = DASHBOARD_DATA.stocks.filter(s => s.is_held);

      if (query) {{
        list = list.filter(s => s.code.includes(query) || s.name.toLowerCase().includes(query));
      }}

      list.sort((a, b) => {{
        let v1 = a[holdingsSortCol];
        let v2 = b[holdingsSortCol];
        if (typeof v1 === 'string') return holdingsSortAsc ? v1.localeCompare(v2) : v2.localeCompare(v1);
        return holdingsSortAsc ? (v1 - v2) : (v2 - v1);
      }});

      const tbody = document.getElementById('holdingsTableBody');
      tbody.innerHTML = list.map(item => {{
        const isUp = item.unrealized_return_pct >= 0;
        const changeUp = item.change >= 0;
        const lotsList = item.buy_lots || [];
        const batchBadge = lotsList.length > 1 ? `<span class="lot-count-badge">${{lotsList.length}} 批</span>` : '';
        const daysTitle = item.first_buy_date ? `建倉日: ${{item.first_buy_date}} · ${{item.holding_trading_days || 0}} 交易日` : '';

        const lotsRowsHtml = lotsList.length > 0
          ? lotsList.map(lot => {{
              const lotUp = lot.unrealized_pnl >= 0;
              const origNote = (lot.orig_lots && lot.orig_lots > lot.lots) ? ` <span style="color:var(--text-dim); font-size:11px;">(原 ${{fmtNum(lot.orig_lots, 1)}} 張)</span>` : '';
              return `
                <tr>
                  <td>${{lot.date}}</td>
                  <td><strong>${{fmtNum(lot.lots, 1)}}</strong> 張${{origNote}}</td>
                  <td>$${{fmtNum(lot.price, 2)}}</td>
                  <td>$${{fmtNum(lot.cost, 0)}}</td>
                  <td>$${{fmtNum(lot.market_value, 0)}}</td>
                  <td style="color:${{lotUp ? 'var(--color-up)' : 'var(--color-down)'}}; font-weight:700;">
                    ${{lotUp ? '+' : ''}}${{fmtNum(lot.unrealized_pnl, 0)}}
                  </td>
                  <td>
                    <span class="badge-pnl ${{lotUp ? 'up' : 'down'}}" style="padding:2px 8px; font-size:11px;">
                      ${{lotUp ? '+' : ''}}${{fmtNum(lot.return_pct, 2)}}%
                    </span>
                  </td>
                  <td>${{lot.holding_days}} 天</td>
                </tr>
              `;
            }}).join('')
          : `<tr><td colspan="8" style="text-align:center; color:var(--text-dim);">尚無後台成交買進明細</td></tr>`;

        return `
          <tr class="holdings-row" id="holdingsRow_${{item.code}}" onclick="toggleHoldingsLot('${{item.code}}')">
            <td>
              <div class="stock-tag-box">
                <span class="usage-chevron">▶</span>
                <span class="stock-code">${{item.code}}</span>
                <span class="stock-name">${{item.name}}</span>
                ${{batchBadge}}
              </div>
            </td>
            <td><span class="market-badge">${{item.market}}</span></td>
            <td title="${{daysTitle}}"><strong>${{item.holding_days || 0}}</strong> 天</td>
            <td><strong>${{fmtNum(item.lots, 1)}}</strong> 張</td>
            <td>$${{fmtNum(item.avg_cost, 2)}}</td>
            <td><strong>$${{fmtNum(item.close_price, 2)}}</strong></td>
            <td>
              <span class="badge-pnl ${{changeUp ? 'up' : 'down'}}">
                ${{changeUp ? '+' : ''}}${{fmtNum(item.change_pct, 2)}}%
              </span>
            </td>
            <td>$${{fmtNum(item.market_value, 0)}}</td>
            <td>
              <span style="color: ${{isUp ? 'var(--color-up)' : 'var(--color-down)'}}; font-weight:700;">
                ${{isUp ? '+' : ''}}${{fmtNum(item.unrealized_pnl, 0)}}
              </span>
            </td>
            <td>
              <span class="badge-pnl ${{isUp ? 'up' : 'down'}}">
                ${{isUp ? '+' : ''}}${{fmtNum(item.unrealized_return_pct, 2)}}%
              </span>
            </td>
            <td>
              <div class="weight-bar-wrapper">
                <div class="weight-progress">
                  <div class="weight-fill" style="width: ${{Math.min(item.weight_pct * 10, 100)}}%;"></div>
                </div>
                <span>${{fmtNum(item.weight_pct, 2)}}%</span>
              </div>
            </td>
          </tr>
          <tr class="holdings-drawer-row" id="holdingsDrawer_${{item.code}}" style="display: none;">
            <td colspan="11">
              <div class="holdings-lot-drawer">
                <table class="holdings-lot-table">
                  <thead>
                    <tr>
                      <th>買進日期</th>
                      <th>持有張數</th>
                      <th>成交價</th>
                      <th>投入成本</th>
                      <th>目前現值</th>
                      <th>該批損益</th>
                      <th>該批報酬率</th>
                      <th>持有天數</th>
                    </tr>
                  </thead>
                  <tbody>
                    ${{lotsRowsHtml}}
                  </tbody>
                </table>
              </div>
            </td>
          </tr>
        `;
      }}).join('');
    }}

    function toggleHoldingsLot(code) {{
      const row = document.getElementById(`holdingsRow_${{code}}`);
      const drawer = document.getElementById(`holdingsDrawer_${{code}}`);
      if (!row || !drawer) return;
      const isHidden = drawer.style.display === 'none';
      drawer.style.display = isHidden ? 'table-row' : 'none';
      row.classList.toggle('expanded', isHidden);
    }}

    function filterHoldingsTable() {{
      renderHoldingsTable();
    }}

    function sortHoldings(col) {{
      if (holdingsSortCol === col) {{
        holdingsSortAsc = !holdingsSortAsc;
      }} else {{
        holdingsSortCol = col;
        holdingsSortAsc = false;
      }}
      renderHoldingsTable();
    }}

    // 自選觀察群組切換與篩選
    function setWatchGroup(group) {{
      currentWatchGroup = group;
      document.getElementById('btnGroupA').classList.toggle('active', group === 'held');
      document.getElementById('btnGroupWatch')?.classList.toggle('active', group === 'watchlist');
      document.getElementById('btnGroupB').classList.toggle('active', group === 'unheld');
      document.getElementById('btnGroupAll').classList.toggle('active', group === 'all');
      renderWatchTable();
    }}

    function setSortMode(mode) {{
      if (currentSortMode === mode) {{
        currentSortMode = 'none';
        document.getElementById('sortGainBtn').classList.remove('active');
        document.getElementById('sortLossBtn').classList.remove('active');
      }} else {{
        currentSortMode = mode;
        document.getElementById('sortGainBtn').classList.toggle('active', mode === 'gain');
        document.getElementById('sortLossBtn').classList.toggle('active', mode === 'loss');
      }}
      renderWatchTable();
    }}

    function setSortCol(col) {{
      currentSortMode = 'col';
      document.getElementById('sortGainBtn').classList.remove('active');
      document.getElementById('sortLossBtn').classList.remove('active');
      if (watchSortCol === col) {{
        watchSortAsc = !watchSortAsc;
      }} else {{
        watchSortCol = col;
        watchSortAsc = false;
      }}
      renderWatchTable();
    }}

    function renderWatchTable() {{
      const query = (document.getElementById('watchSearchInput').value || '').trim().toLowerCase();
      let list = DASHBOARD_DATA.stocks.slice();

      // 分組篩選
      if (currentWatchGroup === 'held') {{
        list = list.filter(s => s.is_held);
      }} else if (currentWatchGroup === 'watchlist') {{
        list = list.filter(s => s.is_watchlist);
      }} else if (currentWatchGroup === 'unheld') {{
        list = list.filter(s => !s.is_held);
      }}

      // 搜尋關鍵字
      if (query) {{
        list = list.filter(s => s.code.includes(query) || s.name.toLowerCase().includes(query));
      }}

      // 排序
      if (currentSortMode === 'gain') {{
        list.sort((a, b) => b.change_pct - a.change_pct);
      }} else if (currentSortMode === 'loss') {{
        list.sort((a, b) => a.change_pct - b.change_pct);
      }} else if (currentSortMode === 'col') {{
        list.sort((a, b) => {{
          let v1 = a[watchSortCol];
          let v2 = b[watchSortCol];
          if (typeof v1 === 'string') return watchSortAsc ? v1.localeCompare(v2) : v2.localeCompare(v1);
          return watchSortAsc ? (v1 - v2) : (v2 - v1);
        }});
      }}

      const tbody = document.getElementById('watchTableBody');
      tbody.innerHTML = list.map(item => {{
        const isUp = item.change >= 0;
        return `
          <tr>
            <td>
              <div class="stock-tag-box">
                <span class="stock-code">${{item.code}}</span>
                <span class="stock-name">${{item.name}}</span>
              </div>
            </td>
            <td><span class="market-badge">${{item.market}}</span></td>
            <td><strong>$${{fmtNum(item.close_price, 2)}}</strong></td>
            <td style="color:var(--text-muted);">$${{fmtNum(item.prev_close, 2)}}</td>
            <td style="color: ${{isUp ? 'var(--color-up)' : 'var(--color-down)'}};">
              ${{isUp ? '+' : ''}}${{fmtNum(item.change, 2)}}
            </td>
            <td>
              <span class="badge-pnl ${{isUp ? 'up' : 'down'}}">
                ${{isUp ? '+' : ''}}${{fmtNum(item.change_pct, 2)}}%
              </span>
            </td>
            <td>${{fmtNum(item.volume_lots, 1)}}</td>
            <td style="text-align:center;">${{item.sparkline}}</td>
            <td>
              ${{item.is_held ? '<span class="badge-pnl badge-held">已買入 ' + item.lots + '張</span>' : '<span style="color:var(--text-dim); font-size:12px;">未持有</span>'}}
            </td>
          </tr>
        `;
      }}).join('');
    }}

    // 繪製資產歷史走勢圖
    function renderAssetChart() {{
      const ctx = document.getElementById('assetHistoryChart').getContext('2d');
      const labels = DASHBOARD_DATA.history.map(h => h.date);
      const navData = DASHBOARD_DATA.history.map(h => h.nav / 1000000); // 轉為百萬
      const cashData = DASHBOARD_DATA.history.map(h => h.cash / 1000000);

      const isDark = document.documentElement.classList.contains('theme-dark');
      const gridColor = isDark ? 'rgba(255, 255, 255, 0.06)' : 'rgba(0, 0, 0, 0.06)';
      const textColor = isDark ? '#94a3b8' : '#64748b';

      window.assetChart = new Chart(ctx, {{
        type: 'line',
        data: {{
          labels: labels,
          datasets: [
            {{
              label: '可交易淨值 NAV (百萬元)',
              data: navData,
              borderColor: '#0284c7',
              backgroundColor: 'rgba(2, 132, 199, 0.12)',
              borderWidth: 2.5,
              tension: 0.35,
              fill: true,
              pointBackgroundColor: '#0284c7',
              pointRadius: 4,
              pointHoverRadius: 6
            }},
            {{
              label: '現金水位 Cash (百萬元)',
              data: cashData,
              borderColor: '#10b981',
              backgroundColor: 'transparent',
              borderWidth: 2,
              borderDash: [4, 4],
              tension: 0.2,
              fill: false,
              pointBackgroundColor: '#10b981',
              pointRadius: 3
            }}
          ]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          interaction: {{
            mode: 'index',
            intersect: false
          }},
          plugins: {{
            legend: {{
              position: 'top',
              labels: {{
                color: textColor,
                font: {{ family: 'Plus Jakarta Sans', size: 12, weight: '600' }}
              }}
            }},
            tooltip: {{
              backgroundColor: isDark ? 'rgba(15, 23, 42, 0.9)' : 'rgba(255, 255, 255, 0.9)',
              titleColor: isDark ? '#f8fafc' : '#0f172a',
              bodyColor: isDark ? '#cbd5e1' : '#334155',
              borderColor: isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)',
              borderWidth: 1,
              padding: 12,
              callbacks: {{
                label: function(context) {{
                  return context.dataset.label + ': ' + Number(context.parsed.y).toLocaleString() + ' 萬元';
                }}
              }}
            }}
          }},
          scales: {{
            x: {{
              grid: {{ color: gridColor }},
              ticks: {{ color: textColor, font: {{ family: 'JetBrains Mono' }} }}
            }},
            y: {{
              grid: {{ color: gridColor }},
              ticks: {{
                color: textColor,
                font: {{ family: 'JetBrains Mono' }},
                callback: function(value) {{
                  return value.toLocaleString() + 'M';
                }}
              }}
            }}
          }}
        }}
      }});

      // 累計總報酬率 (%) 趨勢圖
      const retCtx = document.getElementById('cumReturnChart').getContext('2d');
      const retData = DASHBOARD_DATA.history.map(h => Number(h.cum_return_pct || 0));
      const zeroLine = labels.map(() => 0);
      const latestRet = retData.length ? retData[retData.length - 1] : 0;
      const retColor = latestRet >= 0 ? '#f43f5e' : '#10b981';
      const retFill = latestRet >= 0 ? 'rgba(244, 63, 94, 0.14)' : 'rgba(16, 185, 129, 0.14)';

      window.cumReturnChartInst = new Chart(retCtx, {{
        type: 'line',
        data: {{
          labels: labels,
          datasets: [
            {{
              label: '累計總報酬率 (%)',
              data: retData,
              borderColor: retColor,
              backgroundColor: retFill,
              borderWidth: 2.5,
              tension: 0.35,
              fill: true,
              pointBackgroundColor: retColor,
              pointRadius: 4,
              pointHoverRadius: 6
            }},
            {{
              label: '損益兩平基準 (0%)',
              data: zeroLine,
              borderColor: isDark ? 'rgba(148, 163, 184, 0.45)' : 'rgba(100, 116, 139, 0.45)',
              borderWidth: 1.2,
              borderDash: [5, 5],
              pointRadius: 0,
              fill: false
            }}
          ]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          interaction: {{ mode: 'index', intersect: false }},
          plugins: {{
            legend: {{
              position: 'top',
              labels: {{
                color: textColor,
                font: {{ family: 'Plus Jakarta Sans', size: 12, weight: '600' }}
              }}
            }},
            tooltip: {{
              backgroundColor: isDark ? 'rgba(15, 23, 42, 0.9)' : 'rgba(255, 255, 255, 0.9)',
              titleColor: isDark ? '#f8fafc' : '#0f172a',
              bodyColor: isDark ? '#cbd5e1' : '#334155',
              borderColor: isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)',
              borderWidth: 1,
              padding: 12,
              callbacks: {{
                label: function(context) {{
                  if (context.datasetIndex === 1) return null;
                  const val = Number(context.parsed.y);
                  return `累計總報酬率: ${{val >= 0 ? '+' : ''}}${{val.toFixed(2)}}%`;
                }}
              }}
            }}
          }},
          scales: {{
            x: {{
              grid: {{ color: gridColor }},
              ticks: {{ color: textColor, font: {{ family: 'JetBrains Mono' }} }}
            }},
            y: {{
              grid: {{ color: gridColor }},
              ticks: {{
                color: textColor,
                font: {{ family: 'JetBrains Mono' }},
                callback: function(value) {{
                  return (value >= 0 ? '+' : '') + Number(value).toFixed(2) + '%';
                }}
              }}
            }}
          }}
        }}
      }});

      // 每日競賽排名走勢圖 (Y軸反轉，名次越小越上方)
      const rankCtx = document.getElementById('rankHistoryChart').getContext('2d');
      const totalRankData = DASHBOARD_DATA.history.map(h => h.rank || null);
      const groupRankData = DASHBOARD_DATA.history.map(h => h.group_rank || null);
      window.rankHistoryChartInst = new Chart(rankCtx, {{
        type: 'line',
        data: {{
          labels: labels,
          datasets: [
            {{
              label: '總排名',
              data: totalRankData,
              borderColor: '#f59e0b',
              backgroundColor: 'rgba(245, 158, 11, 0.12)',
              borderWidth: 2.5,
              tension: 0.3,
              fill: false,
              pointBackgroundColor: '#f59e0b',
              pointRadius: 4
            }},
            {{
              label: '社會組排名',
              data: groupRankData,
              borderColor: '#8b5cf6',
              backgroundColor: 'rgba(139, 92, 246, 0.12)',
              borderWidth: 2.5,
              tension: 0.3,
              fill: false,
              pointBackgroundColor: '#8b5cf6',
              pointRadius: 4
            }}
          ]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          interaction: {{ mode: 'index', intersect: false }},
          plugins: {{
            legend: {{
              position: 'top',
              labels: {{ color: textColor, font: {{ family: 'Plus Jakarta Sans', size: 12, weight: '600' }} }}
            }},
            tooltip: {{
              backgroundColor: isDark ? 'rgba(15, 23, 42, 0.9)' : 'rgba(255, 255, 255, 0.9)',
              titleColor: isDark ? '#f8fafc' : '#0f172a',
              bodyColor: isDark ? '#cbd5e1' : '#334155',
              borderColor: isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)',
              borderWidth: 1,
              padding: 12,
              callbacks: {{
                label: function(context) {{
                  const h = DASHBOARD_DATA.history[context.dataIndex] || {{}};
                  if (context.datasetIndex === 0) {{
                    return `總排名: #${{context.parsed.y}} / ${{h.total_teams || '--'}}`;
                  }}
                  return `社會組: #${{context.parsed.y}} / ${{h.group_total || '--'}} (學生組 ${{h.student_total || '--'}} 隊)`;
                }}
              }}
            }}
          }},
          scales: {{
            x: {{
              grid: {{ color: gridColor }},
              ticks: {{ color: textColor, font: {{ family: 'JetBrains Mono' }} }}
            }},
            y: {{
              reverse: true,
              grid: {{ color: gridColor }},
              ticks: {{
                color: textColor,
                precision: 0,
                font: {{ family: 'JetBrains Mono' }},
                callback: function(value) {{ return '#' + value; }}
              }}
            }}
          }}
        }}
      }});

      // 單日報酬率 (%) 柱狀圖
      const dayCtx = document.getElementById('dayReturnChart').getContext('2d');
      const dayRetData = DASHBOARD_DATA.history.map(h => Number(h.day_return_pct || 0));
      const dayRetColors = dayRetData.map(v => v >= 0 ? 'rgba(244, 63, 94, 0.78)' : 'rgba(16, 185, 129, 0.78)');

      window.dayReturnChartInst = new Chart(dayCtx, {{
        type: 'bar',
        data: {{
          labels: labels,
          datasets: [
            {{
              label: '單日報酬率 (%)',
              data: dayRetData,
              backgroundColor: dayRetColors,
              borderRadius: 6
            }}
          ]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          interaction: {{ mode: 'index', intersect: false }},
          plugins: {{
            legend: {{
              position: 'top',
              labels: {{ color: textColor, font: {{ family: 'Plus Jakarta Sans', size: 12, weight: '600' }} }}
            }},
            tooltip: {{
              backgroundColor: isDark ? 'rgba(15, 23, 42, 0.9)' : 'rgba(255, 255, 255, 0.9)',
              titleColor: isDark ? '#f8fafc' : '#0f172a',
              bodyColor: isDark ? '#cbd5e1' : '#334155',
              borderColor: isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)',
              borderWidth: 1,
              padding: 12,
              callbacks: {{
                label: function(context) {{
                  const val = Number(context.parsed.y);
                  return `單日報酬率: ${{val >= 0 ? '+' : ''}}${{val.toFixed(2)}}%`;
                }}
              }}
            }}
          }},
          scales: {{
            x: {{
              grid: {{ color: gridColor }},
              ticks: {{ color: textColor, font: {{ family: 'JetBrains Mono' }} }}
            }},
            y: {{
              grid: {{ color: gridColor }},
              ticks: {{
                color: textColor,
                font: {{ family: 'JetBrains Mono' }},
                callback: function(v) {{ return (v >= 0 ? '+' : '') + Number(v).toFixed(2) + '%'; }}
              }}
            }}
          }}
        }}
      }});
    }}

    let tradesDatePopulated = false;
    function renderTradesTab() {{
      const historyDays = DASHBOARD_DATA.trade_history || [];
      const dateSel = document.getElementById('tradesDateSelect');
      if (!tradesDatePopulated && dateSel) {{
        historyDays.forEach(d => {{
          const opt = document.createElement('option');
          opt.value = d.date;
          opt.textContent = `Day ${{d.day}} · ${{d.date}} (${{d.trades.length}} 筆)`;
          dateSel.appendChild(opt);
        }});
        tradesDatePopulated = true;
      }}

      const selDate = dateSel ? dateSel.value : 'ALL';
      const selSide = document.getElementById('tradesSideSelect').value;
      const query = (document.getElementById('tradesSearchInput').value || '').trim().toLowerCase();

      const rows = [];
      let sumAmount = 0;
      let sumFee = 0;
      let sumTax = 0;

      historyDays.forEach(d => {{
        if (selDate !== 'ALL' && d.date !== selDate) return;
        (d.trades || []).forEach(tr => {{
          if (selSide !== 'ALL' && tr.side !== selSide) return;
          if (query && !tr.code.toLowerCase().includes(query) && !tr.name.toLowerCase().includes(query)) return;
          sumAmount += Number(tr.amount || 0);
          sumFee += Number(tr.fee || 0);
          sumTax += Number(tr.tax || 0);
          rows.push({{ date: d.date, day: d.day, ...tr }});
        }});
      }});

      const summaryEl = document.getElementById('tradesFilterSummary');
      if (summaryEl) {{
        summaryEl.textContent = `篩選結果共 ${{rows.length}} 筆 · 成交金額 $${{fmtNum(sumAmount, 0)}} · 手續費 $${{fmtNum(sumFee, 2)}} · 證交稅 $${{fmtNum(sumTax, 2)}}`;
      }}

      const tbody = document.getElementById('tradesHistoryTableBody');
      if (!tbody) return;
      if (rows.length === 0) {{
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; color:var(--text-dim); padding:24px;">查無符合條件的成交紀錄</td></tr>';
        return;
      }}

      tbody.innerHTML = rows.map(r => {{
        const isBuy = r.side === '買進';
        const lotsVal = Number(r.lots || 0);
        const lotsStr = Number.isInteger(lotsVal) ? fmtNum(lotsVal, 0) : fmtNum(lotsVal, 3);
        return `
          <tr>
            <td style="font-family:'JetBrains Mono', monospace;">${{r.date}} <span style="color:var(--text-dim); font-size:11px;">(D${{r.day}})</span></td>
            <td><span class="badge-pnl ${{isBuy ? 'up' : 'down'}}">${{r.side}}</span></td>
            <td>
              <div class="stock-tag-box">
                <span class="stock-code">${{r.code}}</span>
                <span class="stock-name">${{r.name}}</span>
              </div>
            </td>
            <td><strong>${{lotsStr}}</strong> 張 <span style="color:var(--text-dim); font-size:11px;">(${{fmtNum(r.shares, 0)}}股)</span></td>
            <td style="font-family:'JetBrains Mono', monospace;">$${{fmtNum(r.price, 2)}}</td>
            <td style="font-family:'JetBrains Mono', monospace;">$${{fmtNum(r.amount, 0)}}</td>
            <td style="font-family:'JetBrains Mono', monospace;">$${{fmtNum(r.fee, 2)}}</td>
            <td style="font-family:'JetBrains Mono', monospace;">$${{fmtNum(r.tax, 2)}}</td>
          </tr>
        `;
      }}).join('');
    }}

    function updateChartTheme() {{
      const isDark = document.documentElement.classList.contains('theme-dark');
      const gridColor = isDark ? 'rgba(255, 255, 255, 0.06)' : 'rgba(0, 0, 0, 0.06)';
      const textColor = isDark ? '#94a3b8' : '#64748b';

      [window.assetChart, window.cumReturnChartInst, window.rankHistoryChartInst, window.dayReturnChartInst, window.usageTrendChartInst, window.usageTokenStackChartInst].forEach(ch => {{
        if (!ch || typeof ch.update !== 'function') return;
        if (ch.options.scales) {{
          Object.values(ch.options.scales).forEach(s => {{
            if (s.grid) s.grid.color = gridColor;
            if (s.ticks) s.ticks.color = textColor;
          }});
        }}
        if (ch.options.plugins && ch.options.plugins.legend && ch.options.plugins.legend.labels) {{
          ch.options.plugins.legend.labels.color = textColor;
        }}
        ch.update();
      }});

      if (window.usageStageDonutChartInst && typeof window.usageStageDonutChartInst.update === 'function') {{
        window.usageStageDonutChartInst.options.plugins.legend.labels.color = textColor;
        window.usageStageDonutChartInst.update();
      }}
    }}

    // ================= 頁籤 3: AI 模型用量與成本監控邏輯 =================
    let usageTabRendered = false;

    function fmtCompactTokens(n) {{
      const val = Number(n || 0);
      if (val >= 1000000) return (val / 1000000).toFixed(2) + ' M';
      if (val >= 1000) return (val / 1000).toFixed(1) + ' K';
      return val.toLocaleString('en-US');
    }}

    function fmtDuration(sec) {{
      const s = Math.round(Number(sec || 0));
      const h = Math.floor(s / 3600);
      const m = Math.floor((s % 3600) / 60);
      const rem = s % 60;
      if (h > 0) return `${{h}}h ${{m}}m`;
      if (m > 0) return `${{m}}m ${{rem}}s`;
      return `${{rem}}s`;
    }}

    function fmtDateDash(d8) {{
      const str = String(d8 || '');
      if (str.length === 8) return `${{str.slice(0, 4)}}-${{str.slice(4, 6)}}-${{str.slice(6, 8)}}`;
      return str;
    }}

    function getModelBadgeClass(modelName) {{
      const m = String(modelName || '').toLowerCase();
      if (m.includes('carbon')) return 'carbon';
      if (m.includes('argon')) return 'argon';
      if (m.includes('lite')) return 'fallback';
      return 'flash';
    }}

    function renderUsageTab() {{
      const usage = DASHBOARD_DATA.usage || {{ summary: {{}}, daily_summary: {{}} }};
      renderUsageKpis(usage);
      renderUsageDailyTable(usage);
      requestAnimationFrame(() => {{
        renderUsageCharts(usage);
      }});
    }}

    function renderUsageKpis(usage) {{
      const s = usage.summary || {{}};
      const daily = usage.daily_summary || {{}};
      const numDays = Math.max(1, Object.keys(daily).length);
      const totalCost = Number(s.response_cost || 0);
      const twdCost = Math.round(totalCost * 32);
      const avgDailyCost = totalCost / numDays;
      const totalCalls = Number(s.total_calls || 0);
      const successCalls = Number(s.success_calls || 0);
      const successRate = totalCalls > 0 ? ((successCalls / totalCalls) * 100).toFixed(1) : '100.0';
      const avgDailyMin = (Number(s.duration_seconds || 0) / numDays / 60).toFixed(1);

      const updBadge = document.getElementById('usageUpdatedAtBadge');
      if (updBadge && usage.updated_at) {{
        updBadge.textContent = '更新時間: ' + usage.updated_at.replace('T', ' ').slice(0, 19);
      }}

      const grid = document.getElementById('usageKpiGrid');
      if (!grid) return;
      grid.innerHTML = `
        <div class="glass-card kpi-card">
          <div class="kpi-label">💵 累計調用花費</div>
          <div class="kpi-value">$${{totalCost.toFixed(2)}} <span style="font-size:13px; color:var(--text-dim);">USD</span></div>
          <div class="kpi-subtext">約 NT$ ${{twdCost.toLocaleString('en-US')}} 元 · 日均 $${{avgDailyCost.toFixed(2)}}</div>
        </div>
        <div class="glass-card kpi-card">
          <div class="kpi-label">🪙 總 Token 消耗</div>
          <div class="kpi-value">${{fmtCompactTokens(s.total_tokens)}}</div>
          <div class="kpi-subtext">輸入 ${{fmtCompactTokens(s.prompt_tokens)}} · 輸出 ${{fmtCompactTokens(s.completion_tokens)}} · 沙盒 ${{fmtCompactTokens(s.tool_use_tokens)}}</div>
        </div>
        <div class="glass-card kpi-card">
          <div class="kpi-label">⚡ 模型調用次數</div>
          <div class="kpi-value">${{totalCalls}} 次</div>
          <div class="kpi-subtext"><span class="badge-pnl up" style="padding:2px 8px; font-size:11px;">成功率 ${{successRate}}% (${{successCalls}}/${{totalCalls}})</span></div>
        </div>
        <div class="glass-card kpi-card">
          <div class="kpi-label">🐍 Python 代碼執行</div>
          <div class="kpi-value">${{Number(s.code_execution_call_count || 0).toLocaleString('en-US')}} 次</div>
          <div class="kpi-subtext">Gemini 原生沙盒運算 (無數值幻覺)</div>
        </div>
        <div class="glass-card kpi-card">
          <div class="kpi-label">⏱️ 累計推論耗時</div>
          <div class="kpi-value">${{fmtDuration(s.duration_seconds)}}</div>
          <div class="kpi-subtext">涵蓋 ${{numDays}} 交易日 · 日均 ${{avgDailyMin}} 分鐘</div>
        </div>
      `;
    }}

    function renderUsageCharts(usage) {{
      const dailyMap = usage.daily_summary || {{}};
      const dates = Object.keys(dailyMap).sort();
      const labels = dates.map(d => `${{d.slice(4, 6)}}/${{d.slice(6, 8)}}`);

      const isDark = document.documentElement.classList.contains('theme-dark');
      const gridColor = isDark ? 'rgba(255, 255, 255, 0.06)' : 'rgba(0, 0, 0, 0.06)';
      const textColor = isDark ? '#94a3b8' : '#64748b';
      const tooltipBg = isDark ? 'rgba(15, 23, 42, 0.92)' : 'rgba(255, 255, 255, 0.95)';
      const tooltipTitle = isDark ? '#f8fafc' : '#0f172a';
      const tooltipBody = isDark ? '#cbd5e1' : '#334155';

      // 1. 每日花費與 Token 雙軸趨勢圖
      const costArr = dates.map(d => Number((dailyMap[d].response_cost || 0).toFixed(4)));
      const tokenMArr = dates.map(d => Number(((dailyMap[d].total_tokens || 0) / 1000000).toFixed(3)));

      if (window.usageTrendChartInst && typeof window.usageTrendChartInst.destroy === 'function') {{
        window.usageTrendChartInst.destroy();
      }}
      const ctx1 = document.getElementById('usageTrendChart').getContext('2d');
      window.usageTrendChartInst = new Chart(ctx1, {{
        type: 'bar',
        data: {{
          labels: labels,
          datasets: [
            {{
              label: '每日花費 (USD)',
              data: costArr,
              backgroundColor: 'rgba(56, 189, 248, 0.55)',
              borderColor: '#38bdf8',
              borderWidth: 1.5,
              borderRadius: 6,
              yAxisID: 'y'
            }},
            {{
              label: '總 Tokens (百萬)',
              data: tokenMArr,
              type: 'line',
              borderColor: '#f43f5e',
              backgroundColor: 'rgba(244, 63, 94, 0.15)',
              borderWidth: 2.5,
              tension: 0.35,
              pointRadius: 4,
              yAxisID: 'y1'
            }}
          ]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          interaction: {{ mode: 'index', intersect: false }},
          plugins: {{
            legend: {{ labels: {{ color: textColor, font: {{ family: 'Plus Jakarta Sans', size: 12, weight: '600' }} }} }},
            tooltip: {{ backgroundColor: tooltipBg, titleColor: tooltipTitle, bodyColor: tooltipBody }}
          }},
          scales: {{
            x: {{ grid: {{ color: gridColor }}, ticks: {{ color: textColor, font: {{ family: 'JetBrains Mono' }} }} }},
            y: {{
              type: 'linear',
              position: 'left',
              grid: {{ color: gridColor }},
              ticks: {{ color: textColor, font: {{ family: 'JetBrains Mono' }}, callback: v => '$' + v.toFixed(2) }}
            }},
            y1: {{
              type: 'linear',
              position: 'right',
              grid: {{ drawOnChartArea: false }},
              ticks: {{ color: textColor, font: {{ family: 'JetBrains Mono' }}, callback: v => v.toFixed(2) + 'M' }}
            }}
          }}
        }}
      }});

      // 2. 各任務階段費用佔比圓環圖
      const stageOrder = ['l0', 'l1', 'l2m', 'l2', 'l3', 'l4'];
      const stageNames = {{ l0: 'L0 股票池篩選', l1: 'L1 事實擷取', l2m: 'L2M 市場走向', l2: 'L2 個股推論', l3: 'L3 投組決策', l4: 'L4 委託計算' }};
      const stageTotals = {{ l0: 0, l1: 0, l2m: 0, l2: 0, l3: 0, l4: 0 }};
      dates.forEach(d => {{
        const stg = dailyMap[d].stages || {{}};
        stageOrder.forEach(k => {{
          if (stg[k]) stageTotals[k] += Number(stg[k].response_cost || 0);
        }});
      }});

      if (window.usageStageDonutChartInst && typeof window.usageStageDonutChartInst.destroy === 'function') {{
        window.usageStageDonutChartInst.destroy();
      }}
      const ctx2 = document.getElementById('usageStageDonutChart').getContext('2d');
      window.usageStageDonutChartInst = new Chart(ctx2, {{
        type: 'doughnut',
        data: {{
          labels: stageOrder.map(k => stageNames[k]),
          datasets: [{{
            data: stageOrder.map(k => Number(stageTotals[k].toFixed(4))),
            backgroundColor: ['#0ea5e9', '#10b981', '#06b6d4', '#3b82f6', '#8b5cf6', '#f59e0b'],
            borderWidth: 0,
            hoverOffset: 8
          }}]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          cutout: '64%',
          plugins: {{
            legend: {{
              position: 'bottom',
              labels: {{ color: textColor, padding: 14, font: {{ family: 'Plus Jakarta Sans', size: 12, weight: '600' }} }}
            }},
            tooltip: {{
              backgroundColor: tooltipBg, titleColor: tooltipTitle, bodyColor: tooltipBody,
              callbacks: {{
                label: (ctx) => `${{ctx.label}}: $${{Number(ctx.parsed).toFixed(4)}} USD`
              }}
            }}
          }}
        }}
      }});

      // 3. 每日 Token 細部構成堆疊長條圖
      if (window.usageTokenStackChartInst && typeof window.usageTokenStackChartInst.destroy === 'function') {{
        window.usageTokenStackChartInst.destroy();
      }}
      const ctx3 = document.getElementById('usageTokenStackChart').getContext('2d');
      window.usageTokenStackChartInst = new Chart(ctx3, {{
        type: 'bar',
        data: {{
          labels: labels,
          datasets: [
            {{ label: 'Prompt (輸入)', data: dates.map(d => dailyMap[d].prompt_tokens || 0), backgroundColor: '#38bdf8' }},
            {{ label: 'Completion (輸出)', data: dates.map(d => dailyMap[d].completion_tokens || 0), backgroundColor: '#10b981' }},
            {{ label: 'Tool Use (代碼沙盒)', data: dates.map(d => dailyMap[d].tool_use_tokens || 0), backgroundColor: '#8b5cf6' }},
            {{ label: 'Reasoning (深度思考)', data: dates.map(d => dailyMap[d].reasoning_tokens || 0), backgroundColor: '#f59e0b' }}
          ]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          interaction: {{ mode: 'index', intersect: false }},
          plugins: {{
            legend: {{ labels: {{ color: textColor, font: {{ family: 'Plus Jakarta Sans', size: 12, weight: '600' }} }} }},
            tooltip: {{ backgroundColor: tooltipBg, titleColor: tooltipTitle, bodyColor: tooltipBody }}
          }},
          scales: {{
            x: {{ stacked: true, grid: {{ color: gridColor }}, ticks: {{ color: textColor, font: {{ family: 'JetBrains Mono' }} }} }},
            y: {{
              stacked: true,
              grid: {{ color: gridColor }},
              ticks: {{ color: textColor, font: {{ family: 'JetBrains Mono' }}, callback: v => fmtCompactTokens(v) }}
            }}
          }}
        }}
      }});
    }}

    function renderUsageDailyTable(usage) {{
      const tbody = document.getElementById('usageDailyTableBody');
      if (!tbody) return;
      const dailyMap = usage.daily_summary || {{}};
      const datesDesc = Object.keys(dailyMap).sort((a, b) => b.localeCompare(a));

      const stageOrder = ['l0', 'l1', 'l2m', 'l2', 'l3', 'l4'];
      const stageLabels = {{
        l0: 'L0 股票池篩選',
        l1: 'L1 事實擷取',
        l2m: 'L2M 市場走向',
        l2: 'L2 個股推論',
        l3: 'L3 投組決策',
        l4: 'L4 委託計算'
      }};

      if (datesDesc.length === 0) {{
        tbody.innerHTML = '<tr><td colspan="10" style="text-align:center; padding:32px; color:var(--text-dim);">尚無模型用量紀錄</td></tr>';
        return;
      }}

      tbody.innerHTML = datesDesc.map(d => {{
        const day = dailyMap[d];
        const stages = day.stages || {{}};
        const execCount = Number(day.code_execution_call_count || 0);

        const stageCardsHtml = stageOrder.filter(k => stages[k]).map(k => {{
          const st = stages[k];
          const badgeCls = getModelBadgeClass(st.model);
          const stExec = Number(st.code_execution_call_count || 0);
          return `
            <div class="stage-mini-card">
              <div class="stage-mini-header">
                <span>${{stageLabels[k]}}</span>
                <span class="model-badge ${{badgeCls}}">${{st.model}}</span>
              </div>
              <div class="stage-mini-metrics">
                <span>Tokens: ${{fmtCompactTokens(st.total_tokens)}}</span>
                <span>耗時: ${{fmtDuration(st.duration_seconds)}}</span>
              </div>
              <div class="stage-mini-metrics">
                <span>輸入 ${{fmtCompactTokens(st.prompt_tokens)}} / 輸出 ${{fmtCompactTokens(st.completion_tokens)}}</span>
                <span style="color:var(--text-main); font-weight:700;">$${{Number(st.response_cost || 0).toFixed(4)}}</span>
              </div>
              ${{stExec > 0 ? `<div style="margin-top:2px;"><span class="code-exec-badge">🐍 Code Exec: ${{stExec}} 次</span></div>` : ''}}
            </div>
          `;
        }}).join('');

        return `
          <tr class="usage-day-row" id="usageRow_${{d}}" onclick="toggleUsageDay('${{d}}')">
            <td style="font-weight:700; font-family:var(--font-mono);">
              <span class="usage-chevron">▶</span>${{fmtDateDash(d)}}
            </td>
            <td>${{day.calls}} 次</td>
            <td>${{fmtCompactTokens(day.prompt_tokens)}}</td>
            <td>${{fmtCompactTokens(day.completion_tokens)}}</td>
            <td>${{fmtCompactTokens(day.tool_use_tokens)}}</td>
            <td>${{fmtCompactTokens(day.reasoning_tokens)}}</td>
            <td style="font-weight:700;">${{fmtCompactTokens(day.total_tokens)}}</td>
            <td>${{execCount > 0 ? `<span class="code-exec-badge">🐍 ${{execCount}} 次</span>` : '<span style="color:var(--text-dim);">--</span>'}}</td>
            <td>${{fmtDuration(day.duration_seconds)}}</td>
            <td style="font-weight:800; color:#38bdf8;">$${{Number(day.response_cost || 0).toFixed(4)}}</td>
          </tr>
          <tr class="usage-stages-row" id="usageDrawer_${{d}}" style="display: none;">
            <td colspan="10">
              <div class="usage-stages-drawer">
                ${{stageCardsHtml}}
              </div>
            </td>
          </tr>
        `;
      }}).join('');
    }}

    function toggleUsageDay(d) {{
      const row = document.getElementById(`usageRow_${{d}}`);
      const drawer = document.getElementById(`usageDrawer_${{d}}`);
      if (!row || !drawer) return;
      const isHidden = drawer.style.display === 'none';
      drawer.style.display = isHidden ? 'table-row' : 'none';
      row.classList.toggle('expanded', isHidden);
    }}

    // ================= 每日決策報告瀏覽器 (Tab 4) =================
    let currentReportIndex = 0;
    let reportsTabInitialized = false;

    function renderReportsTab() {{
      const reports = DASHBOARD_DATA.reports || [];
      const select = document.getElementById('reportDateSelect');
      const bodyEl = document.getElementById('reportMarkdownBody');
      const tocEl = document.getElementById('reportTocList');

      if (!reports.length) {{
        select.innerHTML = '<option value="0">尚無決策報告</option>';
        select.disabled = true;
        document.getElementById('reportPrevBtn').disabled = true;
        document.getElementById('reportNextBtn').disabled = true;
        document.getElementById('reportCopyBtn').disabled = true;
        document.getElementById('reportMetaPill').textContent = '0 份報告';
        tocEl.innerHTML = '<div style="font-size:12px; color:var(--text-dim);">無目錄</div>';
        bodyEl.innerHTML = '<p style="color:var(--text-dim);">目前在 <code>data/D-Paln_Output/reports/</code> 找不到任何每日決策報告。</p>';
        return;
      }}

      if (!reportsTabInitialized) {{
        select.innerHTML = reports.map((r, idx) => {{
          const tag = idx === 0 ? ' (最新)' : '';
          return `<option value="${{idx}}">${{r.date}}${{tag}} · ${{r.filename}}</option>`;
        }}).join('');
        reportsTabInitialized = true;
      }}
      selectReportByIndex(currentReportIndex);
    }}

    function selectReportByIndex(idx) {{
      const reports = DASHBOARD_DATA.reports || [];
      if (!reports.length) return;
      currentReportIndex = Math.max(0, Math.min(idx, reports.length - 1));

      const report = reports[currentReportIndex];
      const select = document.getElementById('reportDateSelect');
      if (select) select.value = String(currentReportIndex);

      document.getElementById('reportPrevBtn').disabled = (currentReportIndex >= reports.length - 1);
      document.getElementById('reportNextBtn').disabled = (currentReportIndex <= 0);

      const kb = (report.size_bytes / 1024).toFixed(1);
      document.getElementById('reportMetaPill').textContent = `${{report.date}} · ${{kb}} KB · 更新於 ${{report.updated_at}}`;

      const bodyEl = document.getElementById('reportMarkdownBody');
      const mdText = report.markdown || '';

      if (window.marked && typeof window.marked.parse === 'function') {{
        window.marked.setOptions({{ gfm: true, breaks: true }});
        const rawHtml = window.marked.parse(mdText);
        bodyEl.innerHTML = window.DOMPurify ? window.DOMPurify.sanitize(rawHtml) : rawHtml;
      }} else {{
        // 離線或 CDN 無法載入時的純文字安全回退
        const pre = document.createElement('pre');
        pre.style.whiteSpace = 'pre-wrap';
        pre.textContent = mdText;
        bodyEl.innerHTML = '';
        bodyEl.appendChild(pre);
      }}

      // 為所有表格包覆水平捲動容器，防止寬表格破版
      bodyEl.querySelectorAll('table').forEach((tbl) => {{
        const wrap = document.createElement('div');
        wrap.className = 'report-table-wrap';
        tbl.parentNode.insertBefore(wrap, tbl);
        wrap.appendChild(tbl);
      }});

      // 動態從渲染後標題生成目錄 + Scrollspy 高亮連動
      const tocEl = document.getElementById('reportTocList');
      const headings = Array.from(bodyEl.querySelectorAll('h2, h3'));
      document.getElementById('reportTocCount').textContent = headings.length ? `${{headings.length}} 節` : '';

      window._reportTocPairs = [];
      window._lastActiveReportTocIdx = -1;
      if (!headings.length) {{
        tocEl.innerHTML = '<div style="font-size:12px; color:var(--text-dim);">此報告無子章節</div>';
      }} else {{
        tocEl.innerHTML = '';
        headings.forEach((h, i) => {{
          const targetId = `report-sec-${{i}}`;
          h.id = targetId;
          const btn = document.createElement('button');
          btn.type = 'button';
          btn.className = 'report-toc-item ' + (h.tagName === 'H3' ? 'toc-h3' : 'toc-h2');
          btn.textContent = h.textContent.trim();
          btn.title = h.textContent.trim();
          btn.onclick = () => {{
            const el = document.getElementById(targetId);
            if (el) el.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
            setActiveReportTocIndex(i);
          }};
          tocEl.appendChild(btn);
          window._reportTocPairs.push({{ heading: h, btn }});
        }});
        updateReportTocScrollspy();
      }}
    }}

    function setActiveReportTocIndex(activeIdx) {{
      if (window._lastActiveReportTocIdx === activeIdx) return;
      window._lastActiveReportTocIdx = activeIdx;
      const pairs = window._reportTocPairs || [];
      let activeBtn = null;
      pairs.forEach((p, idx) => {{
        const isActive = (idx === activeIdx);
        p.btn.classList.toggle('active', isActive);
        if (isActive) activeBtn = p.btn;
      }});
      if (activeBtn) {{
        const tocCard = document.querySelector('.report-toc-card');
        if (tocCard && getComputedStyle(tocCard).position === 'sticky') {{
          const btnTop = activeBtn.offsetTop;
          const btnBottom = btnTop + activeBtn.offsetHeight;
          const viewTop = tocCard.scrollTop;
          const viewBottom = viewTop + tocCard.clientHeight;
          if (btnTop < viewTop + 12) {{
            tocCard.scrollTop = Math.max(0, btnTop - 12);
          }} else if (btnBottom > viewBottom - 12) {{
            tocCard.scrollTop = btnBottom - tocCard.clientHeight + 12;
          }}
        }}
      }}
    }}

    function updateReportTocScrollspy() {{
      if (currentTab !== 'tab4') return;
      const pairs = window._reportTocPairs || [];
      if (!pairs.length) return;
      const triggerY = 140;
      let activeIdx = 0;
      for (let i = 0; i < pairs.length; i++) {{
        const rect = pairs[i].heading.getBoundingClientRect();
        if (rect.top <= triggerY) {{
          activeIdx = i;
        }} else {{
          break;
        }}
      }}
      setActiveReportTocIndex(activeIdx);
    }}

    (function initReportTocScrollspy() {{
      let spyTicking = false;
      window.addEventListener('scroll', () => {{
        if (currentTab !== 'tab4') return;
        if (!spyTicking) {{
          spyTicking = true;
          requestAnimationFrame(() => {{
            spyTicking = false;
            updateReportTocScrollspy();
          }});
        }}
      }}, {{ passive: true }});
    }})();

    function stepReport(delta) {{
      selectReportByIndex(currentReportIndex + delta);
    }}

    function copyCurrentReportMarkdown() {{
      const reports = DASHBOARD_DATA.reports || [];
      const report = reports[currentReportIndex];
      if (!report) return;
      const btn = document.getElementById('reportCopyBtn');
      const done = () => {{
        const orig = btn.textContent;
        btn.textContent = '✅ 已複製原文';
        setTimeout(() => {{ btn.textContent = orig; }}, 1800);
      }};
      if (navigator.clipboard && navigator.clipboard.writeText) {{
        navigator.clipboard.writeText(report.markdown).then(done).catch(() => {{}});
      }}
    }}

    // 零版面位移 + 大遲滯區間 (Hysteresis) 偵測：鎖定佔位高度後切換為 fixed 單行懸浮，徹底消除跳動
    function initStickyDockObserver() {{
      const slot = document.getElementById('stickyTopDockSlot');
      const dock = document.getElementById('stickyTopDock');
      if (!slot || !dock) return;
      let isCompact = false;
      let ticking = false;

      const updateDock = () => {{
        ticking = false;
        const y = window.scrollY || window.pageYOffset || 0;
        if (!isCompact && y > 180) {{
          slot.style.minHeight = dock.offsetHeight + 'px';
          isCompact = true;
          dock.classList.add('is-scrolled');
        }} else if (isCompact && y < 40) {{
          isCompact = false;
          dock.classList.remove('is-scrolled');
          slot.style.minHeight = '';
        }}
      }};

      window.addEventListener('scroll', () => {{
        if (!ticking) {{
          ticking = true;
          requestAnimationFrame(updateDock);
        }}
      }}, {{ passive: true }});
    }}

    // =========================================================================
    // Tab 1 內嵌子視圖：競賽全體排行榜
    // =========================================================================
    let rankingGroupFilter = 'all';
    let rankingSortCol = 'rank';
    let rankingSortAsc = true;
    const MY_TEAM_ID = 'TEAM_11402';

    function formatAumYi(aum) {{
      if (aum === null || aum === undefined || isNaN(aum)) return '--';
      const yi = Number(aum) / 100000000;
      return `${{yi.toFixed(3)}} 億`;
    }}

    function formatRankDiffBadge(prevRank, currRank) {{
      if (!prevRank || !currRank) return '<span style="color:var(--text-dim);">--</span>';
      const diff = Number(prevRank) - Number(currRank);
      if (diff > 0) return `<span class="badge-pnl up">▲ ${{diff}}</span>`;
      if (diff < 0) return `<span class="badge-pnl down">▼ ${{Math.abs(diff)}}</span>`;
      return '<span style="color:var(--text-dim); font-size:12px;">持平</span>';
    }}

    function openRankingView() {{
      const overviewEl = document.getElementById('tab1OverviewView');
      const rankingEl = document.getElementById('tab1RankingView');
      if (!overviewEl || !rankingEl) return;
      overviewEl.style.display = 'none';
      rankingEl.style.display = 'block';
      renderRankingView();
      window.scrollTo({{ top: 0, behavior: 'smooth' }});
    }}

    function closeRankingView(scrollTop = true) {{
      const overviewEl = document.getElementById('tab1OverviewView');
      const rankingEl = document.getElementById('tab1RankingView');
      if (!overviewEl || !rankingEl) return;
      rankingEl.style.display = 'none';
      overviewEl.style.display = 'block';
      if (scrollTop) {{
        window.scrollTo({{ top: 0, behavior: 'smooth' }});
      }}
    }}

    function setRankingGroup(grp) {{
      rankingGroupFilter = grp;
      document.getElementById('rankFilterAll').classList.toggle('active', grp === 'all');
      document.getElementById('rankFilterSociety').classList.toggle('active', grp === 'society');
      document.getElementById('rankFilterStudent').classList.toggle('active', grp === 'student');
      renderRankingTable();
    }}

    function sortRankingTable(col) {{
      if (rankingSortCol === col) {{
        rankingSortAsc = !rankingSortAsc;
      }} else {{
        rankingSortCol = col;
        rankingSortAsc = (col === 'rank' || col === 'group_rank' || col === 'team' || col === 'group');
      }}
      renderRankingTable();
    }}

    function renderRankingView() {{
      const lb = DASHBOARD_DATA.leaderboard || {{}};
      const meta = lb.meta || {{}};
      const rows = lb.results || [];
      const groups = meta.groups || {{}};

      const myRow = rows.find(r => r.team === MY_TEAM_ID);
      const top1All = rows.find(r => r.rank === 1) || rows[0];
      const top1Soc = rows.find(r => r.group === 'society' && r.group_rank === 1) || rows.find(r => r.group === 'society');

      const kpiGrid = document.getElementById('rankingKpiGrid');
      if (kpiGrid) {{
        const societyCnt = groups.society ?? rows.filter(r => r.group === 'society').length;
        const studentCnt = groups.student ?? rows.filter(r => r.group === 'student').length;
        const participants = meta.participants || '--';
        const gapAll = (myRow && top1All) ? (myRow.cum_return - top1All.cum_return) : null;
        const gapSoc = (myRow && top1Soc) ? (myRow.cum_return - top1Soc.cum_return) : null;
        const allTopPct = (myRow && rows.length) ? ((myRow.rank / rows.length) * 100).toFixed(1) : '--';
        const socTopPct = (myRow && societyCnt) ? ((myRow.group_rank / societyCnt) * 100).toFixed(1) : '--';

        const top1Cum = top1All ? Number(top1All.cum_return) : null;
        const top1Up = top1Cum !== null && top1Cum >= 0;
        const top1GroupLabel = top1All ? (top1All.group === 'society' ? '社會組' : '學生組') : '--';
        const gapSocUp = gapSoc !== null && gapSoc >= 0;
        const gapAllStr = gapAll !== null ? `${{gapAll >= 0 ? '+' : ''}}${{fmtNum(gapAll, 2)}}%` : '--';
        const top1SocNote = (top1Soc && top1All && top1Soc.team === top1All.team)
          ? `同為全體與社會組 #1 · 淨值 ${{formatAumYi(top1Soc.aum)}}`
          : (top1Soc ? `社會組 #1：${{top1Soc.team}} (${{top1Soc.cum_return >= 0 ? '+' : ''}}${{fmtNum(top1Soc.cum_return, 2)}}%)` : '--');

        kpiGrid.innerHTML = `
          <div class="glass-card kpi-card">
            <div class="kpi-label">我方總排名 (上榜 ${{rows.length}} 隊)</div>
            <div class="kpi-value">${{myRow ? '#' + myRow.rank : '--'}} <span style="font-size:14px; color:var(--text-muted);">/ ${{rows.length}}</span></div>
            <div class="kpi-subtext">前 ${{allTopPct}}% · 總參賽 ${{participants}} 隊</div>
          </div>
          <div class="glass-card kpi-card">
            <div class="kpi-label">我方社會組排名</div>
            <div class="kpi-value">${{myRow ? '#' + myRow.group_rank : '--'}} <span style="font-size:14px; color:var(--text-muted);">/ ${{societyCnt}} 隊</span></div>
            <div class="kpi-subtext">社會組前 ${{socTopPct}}% · 學生組 ${{studentCnt}} 隊</div>
          </div>
          <div class="glass-card kpi-card">
            <div class="kpi-label">全體榜首 (${{top1All ? top1All.team : '--'}})</div>
            <div class="kpi-value ${{top1Cum !== null ? ('badge-pnl ' + (top1Up ? 'up' : 'down')) : ''}}" style="display:inline-block; font-size:21px;">
              ${{top1Cum !== null ? ((top1Up ? '+' : '') + fmtNum(top1Cum, 2) + '%') : '--'}}
            </div>
            <div class="kpi-subtext">${{top1GroupLabel}} #1 · 淨值 ${{top1All ? formatAumYi(top1All.aum) : '--'}}</div>
          </div>
          <div class="glass-card kpi-card">
            <div class="kpi-label">距社會組榜首差距</div>
            <div class="kpi-value ${{gapSoc !== null ? ('badge-pnl ' + (gapSocUp ? 'up' : 'down')) : ''}}" style="display:inline-block; font-size:21px;">
              ${{gapSoc !== null ? ((gapSocUp ? '+' : '') + fmtNum(gapSoc, 2) + '%') : '--'}}
            </div>
            <div class="kpi-subtext">${{top1SocNote}} · 距全體 #1：${{gapAllStr}}</div>
          </div>
        `;
      }}

      const banner = document.getElementById('rankingMyTeamBanner');
      if (banner) {{
        if (myRow) {{
          const cumUp = myRow.cum_return >= 0;
          const dayUp = myRow.day_return >= 0;
          const groupDiffHtml = (myRow.prev_group_rank && myRow.group_rank)
            ? formatRankDiffBadge(myRow.prev_group_rank, myRow.group_rank)
            : '';
          banner.style.display = 'flex';
          banner.innerHTML = `
            <div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap;">
              <span class="kpi-action-pill">我方隊伍</span>
              <strong style="font-family:var(--font-mono); font-size:15px;">${{myRow.team}}</strong>
              <span class="group-badge society">社會組 #${{myRow.group_rank}}</span>
              ${{groupDiffHtml}}
              <span style="font-family:var(--font-mono); font-size:13px; color:var(--text-muted);">總排名 <strong>#${{myRow.rank}}</strong></span>
              ${{formatRankDiffBadge(myRow.prev_rank, myRow.rank)}}
            </div>
            <div style="display:flex; align-items:center; gap:14px; flex-wrap:wrap; font-family:var(--font-mono); font-size:13px;">
              <span>累計：<span class="badge-pnl ${{cumUp ? 'up' : 'down'}}">${{cumUp ? '+' : ''}}${{fmtNum(myRow.cum_return, 2)}}%</span></span>
              <span>當日：<span class="badge-pnl ${{dayUp ? 'up' : 'down'}}">${{dayUp ? '+' : ''}}${{fmtNum(myRow.day_return, 2)}}%</span></span>
              <span title="NT$ ${{fmtNum(myRow.aum, 0)}}">淨值：<strong>${{formatAumYi(myRow.aum)}}</strong></span>
            </div>
          `;
        }} else {{
          banner.style.display = 'none';
        }}
      }}

      renderRankingTable();
    }}

    function renderRankingTable() {{
      const tbody = document.getElementById('rankingTableBody');
      if (!tbody) return;
      const diffHeader = document.getElementById('rankDiffHeader');
      const useGroupDiff = (rankingGroupFilter !== 'all');
      if (diffHeader) {{
        diffHeader.innerHTML = `${{useGroupDiff ? '組名次變動' : '總名次變動'}} <span class="sort-icon">⇅</span>`;
      }}

      const rows = (DASHBOARD_DATA.leaderboard && DASHBOARD_DATA.leaderboard.results) || [];
      if (!rows.length) {{
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; padding:28px; color:var(--text-dim);">尚未同步排行榜資料，請執行後台同步後重試。</td></tr>';
        return;
      }}

      const query = (document.getElementById('rankingSearchInput').value || '').trim().toLowerCase();
      const limitVal = Number(document.getElementById('rankingLimitSelect').value || 0);

      let filtered = rows.filter(r => {{
        if (rankingGroupFilter !== 'all' && r.group !== rankingGroupFilter) return false;
        if (query && !String(r.team || '').toLowerCase().includes(query)) return false;
        return true;
      }});

      filtered.sort((a, b) => {{
        const getDiff = (item) => {{
          const prev = useGroupDiff ? item.prev_group_rank : item.prev_rank;
          const curr = useGroupDiff ? item.group_rank : item.rank;
          return (prev && curr) ? (Number(prev) - Number(curr)) : null;
        }};
        if (rankingSortCol === 'rank_diff') {{
          const d1 = getDiff(a);
          const d2 = getDiff(b);
          if (d1 === null && d2 === null) return 0;
          if (d1 === null) return 1;
          if (d2 === null) return -1;
          return rankingSortAsc ? (d1 - d2) : (d2 - d1);
        }}
        const v1 = a[rankingSortCol];
        const v2 = b[rankingSortCol];
        if (v1 === null || v1 === undefined) return 1;
        if (v2 === null || v2 === undefined) return -1;
        if (typeof v1 === 'string' && typeof v2 === 'string') {{
          return rankingSortAsc ? v1.localeCompare(v2) : v2.localeCompare(v1);
        }}
        return rankingSortAsc ? (Number(v1) - Number(v2)) : (Number(v2) - Number(v1));
      }});

      const displayRows = (!query && limitVal > 0) ? filtered.slice(0, limitVal) : filtered;
      if (!displayRows.length) {{
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; padding:24px; color:var(--text-dim);">找不到符合條件的隊伍。</td></tr>';
        return;
      }}

      tbody.innerHTML = displayRows.map(r => {{
        const isMe = r.team === MY_TEAM_ID;
        const isSoc = r.group === 'society';
        const hasCum = r.cum_return !== null && r.cum_return !== undefined && !isNaN(r.cum_return);
        const hasDay = r.day_return !== null && r.day_return !== undefined && !isNaN(r.day_return);
        const cumUp = hasCum && Number(r.cum_return) >= 0;
        const dayUp = hasDay && Number(r.day_return) >= 0;
        const aumExact = fmtNum(r.aum, 0);
        const diffPrev = useGroupDiff ? r.prev_group_rank : r.prev_rank;
        const diffCurr = useGroupDiff ? r.group_rank : r.rank;
        return `
          <tr class="${{isMe ? 'ranking-my-team-row' : ''}}">
            <td style="font-family:var(--font-mono); font-weight:700;">#${{r.rank}}</td>
            <td style="font-family:var(--font-mono);">${{r.team}}${{isMe ? ' <span class="kpi-action-pill" style="margin-left:6px;">我方</span>' : ''}}</td>
            <td style="text-align:left;"><span class="group-badge ${{isSoc ? 'society' : 'student'}}">${{isSoc ? '社會組' : '學生組'}}</span></td>
            <td style="font-family:var(--font-mono);">#${{r.group_rank}}</td>
            <td>${{formatRankDiffBadge(diffPrev, diffCurr)}}</td>
            <td>${{hasCum ? `<span class="badge-pnl ${{cumUp ? 'up' : 'down'}}">${{cumUp ? '+' : ''}}${{fmtNum(r.cum_return, 2)}}%</span>` : '<span style="color:var(--text-dim);">--</span>'}}</td>
            <td>${{hasDay ? `<span class="badge-pnl ${{dayUp ? 'up' : 'down'}}">${{dayUp ? '+' : ''}}${{fmtNum(r.day_return, 2)}}%</span>` : '<span style="color:var(--text-dim);">--</span>'}}</td>
            <td style="font-family:var(--font-mono);" title="NT$ ${{aumExact}}">${{formatAumYi(r.aum)}}</td>
          </tr>
        `;
      }}).join('');
    }}

    // 初始化渲染
    window.addEventListener('DOMContentLoaded', () => {{
      renderHoldingsTable();
      renderAssetChart();
      initStickyDockObserver();
    }});
  </script>
</body>
</html>
"""
    with open(DIST_HTML, "w", encoding="utf-8") as f:
        f.write(html_template)

    print(f"[builder] 成功生成富果/Apple風格看板: {DIST_HTML}")
    return DIST_HTML


if __name__ == "__main__":
    from tracker import get_latest_portfolio_summary
    from market_api import fetch_all_150_quotes, load_cached_market_data

    summary = get_latest_portfolio_summary()
    if "--offline" in sys.argv:
        quotes = load_cached_market_data().get("stocks", {})
    else:
        quotes = fetch_all_150_quotes(summary["stocks_150"], fetch_candles=False)
    out_file = build_dashboard_html(summary, quotes)
    print(f"完成！網頁已產出至: {out_file}")
