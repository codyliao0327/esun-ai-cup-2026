"""
Dashboard HTML Builder for 2026 玉山人工智慧挑戰賽
風格：富果 Fugle 專業版面 + Apple iOS 液態毛玻璃 (Liquid Glass)
功能：
  - 帳戶總覽卡片、歷史 NAV 走勢圖、庫存損益明細表 (可排序)
  - 自選觀察群組 (我的持股 25 檔 vs 其餘 125 檔 vs 全部 150 檔)
  - 漲跌幅排序、即時搜尋、10-27 起股價趨勢微圖 (Sparkline)
  - 淺色 / 深色主題切換、完全響應式 (RWD) 手機與電腦極致優化
"""
import json
import re
import sys
from datetime import datetime
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
DIST_DIR = DASHBOARD_DIR / "dist"
DIST_HTML = DIST_DIR / "index.html"


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
    history = summary_data["history"]
    held_positions = summary_data["held_positions"]
    stocks_150 = summary_data["stocks_150"]

    held_codes = set(p["code"] for p in held_positions)

    # 整合 150 檔行情與持股狀態
    all_stocks_list = []
    for code, meta in stocks_150.items():
        q = market_quotes.get(code, {})
        is_held = code in held_codes
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
            "shares": held_info["shares"] if held_info else 0,
            "lots": held_info["lots"] if held_info else 0.0,
            "avg_cost": held_info["avg_cost"] if held_info else 0.0,
            "market_value": held_info["market_value"] if held_info else 0,
            "unrealized_pnl": held_info["unrealized_pnl"] if held_info else 0,
            "unrealized_return_pct": held_info["unrealized_return_pct"] if held_info else 0.0,
            "weight_pct": held_info["weight_pct"] if held_info else 0.0,
            "sparkline": sparkline_svg,
            "trend": trend
        })

    # 讀取 LiteLLM Usage 歷史結算資料
    usage_history_path = DASHBOARD_DIR / "usage_history.json"
    usage_data: Dict[str, Any] = {"summary": {}, "daily_summary": {}, "records": []}
    if usage_history_path.exists():
        try:
            usage_data = json.loads(usage_history_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[builder] 讀取 usage_history.json 失敗: {exc}")

    # 讀取所有每日決策報告 (歷史 + 最新)
    decision_reports = load_decision_reports()

    # 轉為 JSON 注入前端以利動態排序與篩選
    json_data_payload = {
        "as_of_date": summary_data["as_of_date"],
        "trade_date": summary_data["trade_date"],
        "account": account,
        "history": history,
        "stocks": all_stocks_list,
        "usage": usage_data,
        "reports": decision_reports
    }
    safe_json_payload = json.dumps(json_data_payload, ensure_ascii=False).replace("</", "<\\/")

    html_template = f"""<!DOCTYPE html>
<html lang="zh-TW" class="theme-dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>TEAM_11402 · 玉山人工智慧挑戰賽 · 投資決策與持股看板</title>
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
      --primary-glow: rgba(56, 189, 248, 0.34);
      --spring-ease: cubic-bezier(0.22, 1, 0.36, 1);
      --glass-alpha-scale: 1;
      --glass-blur-px: 26px;
    }}

    /* 深色主題 (Apple iOS 27 Second-Gen Refined Liquid Dark Glass) */
    .theme-dark {{
      --bg-gradient:
        radial-gradient(ellipse 62% 46% at 12% 8%, rgba(6, 182, 212, 0.38) 0%, transparent 65%),
        radial-gradient(ellipse 58% 48% at 88% 12%, rgba(139, 92, 246, 0.36) 0%, transparent 65%),
        radial-gradient(ellipse 55% 45% at 20% 50%, rgba(244, 63, 94, 0.24) 0%, transparent 65%),
        radial-gradient(ellipse 60% 50% at 82% 55%, rgba(16, 185, 129, 0.25) 0%, transparent 65%),
        radial-gradient(ellipse 65% 45% at 28% 92%, rgba(245, 158, 11, 0.20) 0%, transparent 65%),
        radial-gradient(ellipse 65% 50% at 82% 92%, rgba(37, 99, 235, 0.32) 0%, transparent 70%),
        linear-gradient(160deg, #040710 0%, #080d1a 48%, #050811 100%);
      --ambient-orb-1:
        radial-gradient(380px circle at 18% 22%, rgba(56, 189, 248, 0.30) 0%, rgba(56, 189, 248, 0.06) 45%, transparent 70%),
        radial-gradient(420px circle at 82% 28%, rgba(168, 85, 247, 0.28) 0%, rgba(168, 85, 247, 0.05) 45%, transparent 70%),
        radial-gradient(360px circle at 32% 68%, rgba(244, 63, 94, 0.22) 0%, transparent 70%),
        radial-gradient(400px circle at 74% 72%, rgba(16, 185, 129, 0.22) 0%, transparent 70%);
      --ambient-orb-2:
        linear-gradient(125deg, transparent 18%, rgba(56, 189, 248, 0.11) 36%, rgba(236, 72, 153, 0.10) 52%, rgba(16, 185, 129, 0.10) 68%, transparent 84%);
      --silk-opacity: 0.68;

      --text-main: #f8fafc;
      --text-muted: #cbd5e1;
      --text-dim: #94a3b8;
      
      /* iOS 27 二代液態玻璃：雙層稜鏡折射邊框 + 高對比光學景深 */
      --glass-backdrop: blur(var(--glass-blur-px, 26px)) saturate(215%) contrast(104%);
      --glass-bg:
        radial-gradient(120% 95% at 50% 0%, rgba(255, 255, 255, calc(0.14 * var(--glass-alpha-scale, 1))) 0%, transparent 60%),
        linear-gradient(135deg, rgba(30, 43, 72, calc(0.50 * var(--glass-alpha-scale, 1))) 0%, rgba(13, 20, 38, calc(0.32 * var(--glass-alpha-scale, 1))) 52%, rgba(24, 37, 64, calc(0.46 * var(--glass-alpha-scale, 1))) 100%);
      --glass-bg-hover:
        radial-gradient(120% 95% at 50% 0%, rgba(255, 255, 255, calc(0.20 * var(--glass-alpha-scale, 1))) 0%, transparent 62%),
        linear-gradient(135deg, rgba(40, 56, 92, calc(0.58 * var(--glass-alpha-scale, 1))) 0%, rgba(18, 28, 52, calc(0.38 * var(--glass-alpha-scale, 1))) 52%, rgba(32, 48, 82, calc(0.52 * var(--glass-alpha-scale, 1))) 100%);
      --glass-border: rgba(255, 255, 255, 0.15);
      --glass-border-specular: rgba(255, 255, 255, 0.42);
      --prismatic-rim: linear-gradient(135deg, rgba(255, 255, 255, 0.58) 0%, rgba(56, 189, 248, 0.28) 28%, rgba(255, 255, 255, 0.05) 50%, rgba(168, 85, 247, 0.30) 76%, rgba(255, 255, 255, 0.45) 100%);
      --glass-shadow:
        0 24px 52px -12px rgba(0, 0, 0, 0.72),
        0 4px 16px -2px rgba(0, 0, 0, 0.45),
        0 0 0 1px rgba(0, 0, 0, 0.48),
        inset 0 1.75px 1.2px 0 rgba(255, 255, 255, 0.46),
        inset 0 -1.75px 2.5px 0 rgba(56, 189, 248, 0.18),
        inset 1.25px 0 1.5px 0 rgba(255, 255, 255, 0.22),
        inset -1.25px 0 2px 0 rgba(168, 85, 247, 0.16);
      
      --meniscus-sheen:
        radial-gradient(92% 75% at 50% -2%, rgba(255, 255, 255, 0.24) 0%, rgba(255, 255, 255, 0.05) 45%, transparent 72%),
        linear-gradient(180deg, rgba(255, 255, 255, 0.11) 0%, transparent 16%);
      --cursor-glint: radial-gradient(360px circle at var(--mx, 50%) var(--my, 0%), rgba(255, 255, 255, 0.16) 0%, rgba(56, 189, 248, 0.05) 42%, transparent 70%);

      /* iOS 27 3D 凸透鏡水滴膠囊按鈕 (Convex Droplet Capsule) */
      --btn-glass-bg:
        radial-gradient(110% 90% at 50% 8%, rgba(255, 255, 255, 0.28) 0%, rgba(255, 255, 255, 0.06) 52%, transparent 80%),
        linear-gradient(180deg, rgba(255, 255, 255, 0.14) 0%, rgba(15, 23, 42, 0.22) 58%, rgba(56, 189, 248, 0.14) 100%);
      --btn-glass-hover:
        radial-gradient(110% 90% at 50% 8%, rgba(255, 255, 255, 0.38) 0%, rgba(255, 255, 255, 0.10) 52%, transparent 80%),
        linear-gradient(180deg, rgba(255, 255, 255, 0.22) 0%, rgba(15, 23, 42, 0.18) 58%, rgba(56, 189, 248, 0.22) 100%);
      --btn-glass-border: rgba(255, 255, 255, 0.24);
      --btn-glass-shadow:
        0 8px 18px -4px rgba(0, 0, 0, 0.55),
        0 0 0 1px rgba(0, 0, 0, 0.35),
        inset 0 1.75px 1.2px 0 rgba(255, 255, 255, 0.52),
        inset 0 -1.5px 2px 0 rgba(56, 189, 248, 0.22);

      /* 激活態 iOS 27 液態寶石膠囊 (Tinted Aqua Gem Droplet) */
      --btn-active-bg:
        radial-gradient(110% 90% at 50% 6%, rgba(255, 255, 255, 0.45) 0%, transparent 58%),
        linear-gradient(180deg, rgba(56, 189, 248, 0.62) 0%, rgba(2, 132, 199, 0.42) 55%, rgba(14, 165, 233, 0.56) 100%);
      --btn-active-border: rgba(186, 230, 253, 0.75);
      --btn-active-shadow:
        0 10px 24px -4px rgba(14, 165, 233, 0.52),
        0 0 0 1px rgba(2, 132, 199, 0.4),
        inset 0 2px 1.5px 0 rgba(255, 255, 255, 0.82),
        inset 0 -2px 2.5px 0 rgba(2, 132, 199, 0.55);
      --btn-active-text: #ffffff;

      --tab-active-shadow:
        0 8px 22px -4px rgba(0, 0, 0, 0.5),
        0 0 20px -4px var(--primary-glow),
        inset 0 2px 1.2px 0 rgba(255, 255, 255, 0.72),
        inset 0 -1.75px 2px 0 rgba(56, 189, 248, 0.30);

      /* 凹槽軌道與輸入框 (Recessed Liquid Well) */
      --well-bg: rgba(5, 9, 20, 0.52);
      --well-border: rgba(255, 255, 255, 0.15);
      --well-shadow:
        inset 0 2.5px 6px rgba(0, 0, 0, 0.65),
        inset 0 -1px 0.8px rgba(255, 255, 255, 0.20),
        0 1px 0 rgba(255, 255, 255, 0.08);

      --table-header-bg: linear-gradient(180deg, rgba(255, 255, 255, 0.11) 0%, rgba(255, 255, 255, 0.03) 100%);
      --table-hover: linear-gradient(90deg, rgba(56, 189, 248, 0.08) 0%, rgba(255, 255, 255, 0.09) 50%, rgba(168, 85, 247, 0.08) 100%);
      --pill-bg: rgba(255, 255, 255, 0.09);
    }}

    /* 淺色主題 (Apple iOS 27 Second-Gen Prismatic Daylight Crystal Glass) */
    .theme-light {{
      --color-up: #dc2626;
      --color-up-bg:
        radial-gradient(100% 80% at 50% 8%, rgba(255, 255, 255, 0.85) 0%, transparent 60%),
        linear-gradient(180deg, rgba(254, 202, 202, 0.72) 0%, rgba(254, 226, 226, 0.38) 100%);
      --color-up-border: rgba(239, 68, 68, 0.42);
      --color-up-shadow: inset 0 1.5px 1px rgba(255, 255, 255, 1), 0 3px 8px -2px rgba(239, 68, 68, 0.22);

      --color-down: #059669;
      --color-down-bg:
        radial-gradient(100% 80% at 50% 8%, rgba(255, 255, 255, 0.85) 0%, transparent 60%),
        linear-gradient(180deg, rgba(167, 243, 208, 0.72) 0%, rgba(209, 250, 229, 0.38) 100%);
      --color-down-border: rgba(16, 185, 129, 0.42);
      --color-down-shadow: inset 0 1.5px 1px rgba(255, 255, 255, 1), 0 3px 8px -2px rgba(16, 185, 129, 0.22);

      --primary-accent: #0284c7;
      --primary-glow: rgba(14, 165, 233, 0.35);

      /* iOS 27 淺色流光絲綢底色 + 高飽和彩帶，讓玻璃折射產生強烈透鏡對比 */
      --bg-gradient:
        radial-gradient(ellipse 60% 45% at 12% 8%, rgba(14, 165, 233, 0.52) 0%, transparent 62%),
        radial-gradient(ellipse 58% 48% at 88% 12%, rgba(139, 92, 246, 0.46) 0%, transparent 62%),
        radial-gradient(ellipse 55% 45% at 18% 52%, rgba(244, 63, 94, 0.38) 0%, transparent 62%),
        radial-gradient(ellipse 60% 50% at 84% 54%, rgba(16, 185, 129, 0.42) 0%, transparent 62%),
        radial-gradient(ellipse 62% 46% at 28% 92%, rgba(245, 158, 11, 0.35) 0%, transparent 65%),
        radial-gradient(ellipse 65% 50% at 82% 94%, rgba(59, 130, 246, 0.45) 0%, transparent 68%),
        linear-gradient(145deg, #dbeafe 0%, #ede9fe 34%, #fce7f3 66%, #d1fae5 100%);
      --ambient-orb-1:
        radial-gradient(350px circle at 20% 20%, rgba(14, 165, 233, 0.48) 0%, rgba(56, 189, 248, 0.12) 48%, transparent 70%),
        radial-gradient(390px circle at 80% 24%, rgba(139, 92, 246, 0.46) 0%, rgba(167, 139, 250, 0.12) 48%, transparent 70%),
        radial-gradient(340px circle at 28% 66%, rgba(244, 63, 94, 0.38) 0%, rgba(251, 113, 133, 0.10) 48%, transparent 70%),
        radial-gradient(370px circle at 75% 70%, rgba(16, 185, 129, 0.40) 0%, rgba(45, 212, 191, 0.10) 48%, transparent 70%);
      --ambient-orb-2:
        linear-gradient(125deg, rgba(255, 255, 255, 0.25) 0%, rgba(14, 165, 233, 0.20) 30%, rgba(236, 72, 153, 0.18) 52%, rgba(16, 185, 129, 0.18) 74%, rgba(255, 255, 255, 0.25) 100%);
      --silk-opacity: 0.92;

      --text-main: #0f172a;
      --text-muted: #1e293b;
      --text-dim: #475569;
      
      /* iOS 27 淺色高通透冰晶玻璃：超清透中層 + 銳利深色微外框 + 135° 鑽石稜鏡切邊 */
      --glass-backdrop: blur(var(--glass-blur-px, 26px)) saturate(235%) contrast(106%);
      --glass-bg:
        radial-gradient(120% 90% at 50% 0%, rgba(255, 255, 255, calc(0.66 * var(--glass-alpha-scale, 1))) 0%, transparent 56%),
        linear-gradient(135deg, rgba(255, 255, 255, calc(0.38 * var(--glass-alpha-scale, 1))) 0%, rgba(255, 255, 255, calc(0.14 * var(--glass-alpha-scale, 1))) 48%, rgba(224, 242, 254, calc(0.28 * var(--glass-alpha-scale, 1))) 100%);
      --glass-bg-hover:
        radial-gradient(120% 90% at 50% 0%, rgba(255, 255, 255, calc(0.76 * var(--glass-alpha-scale, 1))) 0%, transparent 58%),
        linear-gradient(135deg, rgba(255, 255, 255, calc(0.48 * var(--glass-alpha-scale, 1))) 0%, rgba(255, 255, 255, calc(0.22 * var(--glass-alpha-scale, 1))) 48%, rgba(224, 242, 254, calc(0.38 * var(--glass-alpha-scale, 1))) 100%);
      --glass-border: rgba(255, 255, 255, 0.85);
      --glass-border-specular: rgba(255, 255, 255, 1);
      --prismatic-rim: linear-gradient(135deg, rgba(255, 255, 255, 1) 0%, rgba(56, 189, 248, 0.55) 28%, rgba(255, 255, 255, 0.35) 50%, rgba(168, 85, 247, 0.50) 76%, rgba(255, 255, 255, 0.98) 100%);
      --glass-shadow:
        0 22px 48px -12px rgba(15, 23, 42, 0.17),
        0 6px 18px -4px rgba(2, 132, 199, 0.10),
        0 0 0 1px rgba(15, 23, 42, 0.08),
        inset 0 2.5px 2px 0 rgba(255, 255, 255, 1),
        inset 0 -2.5px 4px 0 rgba(14, 165, 233, 0.24),
        inset 1.75px 0 2px 0 rgba(255, 255, 255, 0.96),
        inset -1.75px 0 3px 0 rgba(139, 92, 246, 0.18);
      
      --meniscus-sheen:
        radial-gradient(92% 72% at 50% -2%, rgba(255, 255, 255, 0.82) 0%, rgba(255, 255, 255, 0.14) 45%, transparent 72%),
        linear-gradient(180deg, rgba(255, 255, 255, 0.55) 0%, transparent 15%);
      --cursor-glint: radial-gradient(360px circle at var(--mx, 50%) var(--my, 0%), rgba(255, 255, 255, 0.85) 0%, rgba(56, 189, 248, 0.12) 45%, transparent 70%);

      /* iOS 27 淺色 3D 凸透鏡水滴按鈕：飽滿水滴弧頂 + 底部天藍焦散光 (Caustic Glow) */
      --btn-glass-bg:
        radial-gradient(110% 95% at 50% 8%, rgba(255, 255, 255, 0.95) 0%, rgba(255, 255, 255, 0.25) 55%, transparent 82%),
        linear-gradient(180deg, rgba(255, 255, 255, 0.52) 0%, rgba(255, 255, 255, 0.16) 55%, rgba(186, 230, 253, 0.44) 100%);
      --btn-glass-hover:
        radial-gradient(110% 95% at 50% 8%, rgba(255, 255, 255, 1) 0%, rgba(255, 255, 255, 0.42) 55%, transparent 82%),
        linear-gradient(180deg, rgba(255, 255, 255, 0.72) 0%, rgba(255, 255, 255, 0.30) 55%, rgba(186, 230, 253, 0.62) 100%);
      --btn-glass-border: rgba(255, 255, 255, 0.95);
      --btn-glass-shadow:
        0 8px 18px -4px rgba(15, 23, 42, 0.14),
        0 2px 5px rgba(2, 132, 199, 0.08),
        0 0 0 1px rgba(15, 23, 42, 0.08),
        inset 0 2.2px 1.2px 0 rgba(255, 255, 255, 1),
        inset 0 -2px 2.5px 0 rgba(2, 132, 199, 0.24);

      --btn-active-bg:
        radial-gradient(110% 90% at 50% 6%, rgba(255, 255, 255, 0.62) 0%, transparent 55%),
        linear-gradient(180deg, rgba(56, 189, 248, 0.92) 0%, rgba(2, 132, 199, 0.78) 55%, rgba(3, 105, 161, 0.88) 100%);
      --btn-active-border: rgba(224, 242, 254, 1);
      --btn-active-shadow:
        0 10px 22px -4px rgba(2, 132, 199, 0.42),
        0 0 0 1px rgba(2, 132, 199, 0.32),
        inset 0 2.2px 1.5px 0 rgba(255, 255, 255, 0.95),
        inset 0 -2px 2.5px 0 rgba(3, 105, 161, 0.52);
      --btn-active-text: #ffffff;

      --tab-active-shadow:
        0 10px 24px -4px rgba(15, 23, 42, 0.18),
        0 3px 8px rgba(2, 132, 199, 0.15),
        0 0 0 1px rgba(15, 23, 42, 0.07),
        inset 0 2.5px 1.5px 0 rgba(255, 255, 255, 1),
        inset 0 -2px 2.5px 0 rgba(14, 165, 233, 0.26);

      --well-bg: rgba(15, 23, 42, 0.08);
      --well-border: rgba(255, 255, 255, 0.85);
      --well-shadow:
        inset 0 2.5px 5px rgba(15, 23, 42, 0.13),
        inset 0 -1.5px 1px rgba(255, 255, 255, 0.98),
        0 1px 2px rgba(255, 255, 255, 0.9);

      --table-header-bg: linear-gradient(180deg, rgba(255, 255, 255, 0.58) 0%, rgba(255, 255, 255, 0.20) 100%);
      --table-hover: linear-gradient(90deg, rgba(14, 165, 233, 0.10) 0%, rgba(255, 255, 255, 0.62) 50%, rgba(139, 92, 246, 0.10) 100%);
      --pill-bg: rgba(255, 255, 255, 0.42);
    }}

    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
    }}

    body {{
      font-family: var(--font-sans);
      background: var(--bg-gradient);
      background-attachment: fixed;
      color: var(--text-main);
      min-height: 100vh;
      overflow-x: hidden;
      padding-bottom: 48px;
      transition: color 0.25s ease;
    }}

    /* iOS 27 零耗能 3D 流光絲綢折射光場 (靜態 GPU 圖層，讓液態玻璃產生明顯邊緣透鏡彎曲與色散) */
    .ambient-glow {{
      position: fixed;
      inset: 0;
      background: var(--ambient-orb-1);
      pointer-events: none;
      z-index: 0;
      transform: translateZ(0);
      overflow: hidden;
    }}

    .ambient-glow::before {{
      content: '';
      position: absolute;
      inset: 0;
      background: var(--ambient-orb-2);
      pointer-events: none;
    }}

    .ambient-silk-svg {{
      position: absolute;
      inset: -4%;
      width: 108%;
      height: 108%;
      opacity: var(--silk-opacity, 0.85);
      pointer-events: none;
      transform: translateZ(0);
    }}

    /* 容器架構 */
    .app-container {{
      max-width: 1360px;
      margin: 0 auto;
      padding: 24px 20px;
      position: relative;
      z-index: 1;
    }}

    /* 頂部導航欄 (Header) */
    .app-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 16px;
      padding-bottom: 24px;
      border-bottom: 1px solid var(--glass-border);
      margin-bottom: 24px;
    }}

    .header-branding {{
      display: flex;
      align-items: center;
      gap: 14px;
    }}

    /* Apple 液態玻璃寶石徽章 */
    .logo-badge {{
      width: 46px;
      height: 46px;
      border-radius: 15px;
      background: linear-gradient(145deg, rgba(56, 189, 248, 0.92) 0%, rgba(2, 132, 199, 0.78) 55%, rgba(3, 105, 161, 0.9) 100%);
      border: 1px solid rgba(186, 230, 253, 0.65);
      display: flex;
      align-items: center;
      justify-content: center;
      color: white;
      font-weight: 800;
      font-size: 20px;
      position: relative;
      overflow: hidden;
      box-shadow:
        0 8px 20px -4px rgba(2, 132, 199, 0.5),
        inset 0 2px 1.5px 0 rgba(255, 255, 255, 0.75),
        inset 0 -2px 3px 0 rgba(3, 105, 161, 0.6);
    }}

    .logo-badge::before {{
      content: '';
      position: absolute;
      inset: 0;
      background: radial-gradient(90% 70% at 30% 0%, rgba(255, 255, 255, 0.55) 0%, transparent 65%);
      pointer-events: none;
    }}

    .header-title-box h1 {{
      font-size: 20px;
      font-weight: 800;
      letter-spacing: -0.02em;
      display: flex;
      align-items: center;
      gap: 10px;
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

    .header-subtitle {{
      font-size: 13px;
      color: var(--text-muted);
      margin-top: 3px;
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
      backdrop-filter: blur(18px) saturate(200%);
      -webkit-backdrop-filter: blur(18px) saturate(200%);
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

    /* 頂部膠囊狀態標籤與液態按鈕 */
    .date-pill {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 16px;
      border-radius: 999px;
      background: var(--btn-glass-bg);
      backdrop-filter: blur(18px) saturate(200%);
      -webkit-backdrop-filter: blur(18px) saturate(200%);
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

    /* 主題切換按鈕 (Apple iOS 27 3D Convex Droplet Button) */
    .theme-toggle-btn {{
      background: var(--btn-glass-bg);
      border: 1px solid var(--btn-glass-border);
      color: var(--text-main);
      border-radius: 999px;
      padding: 8px 16px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 7px;
      font-size: 13px;
      font-weight: 700;
      font-family: var(--font-sans);
      backdrop-filter: blur(18px) saturate(200%);
      -webkit-backdrop-filter: blur(18px) saturate(200%);
      box-shadow: var(--btn-glass-shadow);
      position: relative;
      overflow: hidden;
      transition: transform 0.25s var(--spring-ease), background 0.2s ease, box-shadow 0.2s ease;
    }}
    .theme-toggle-btn:hover {{
      background: var(--btn-glass-hover);
      transform: translateY(-1px) scale(1.02);
    }}
    .theme-toggle-btn:active {{
      transform: translateY(0) scale(0.96);
    }}

    /* 主選單分頁切換 (Tabs) - Apple iOS 27 二代液態玻璃膠囊控制器 */
    .tab-nav-container {{
      display: flex;
      justify-content: center;
      margin-bottom: 28px;
    }}

    .segmented-control {{
      display: inline-flex;
      background: var(--well-bg);
      backdrop-filter: blur(22px) saturate(200%);
      -webkit-backdrop-filter: blur(22px) saturate(200%);
      padding: 6px;
      border-radius: 999px;
      border: 1px solid var(--well-border);
      box-shadow: var(--well-shadow), 0 14px 34px -8px rgba(0, 0, 0, 0.22);
      gap: 6px;
      position: relative;
    }}

    .tab-btn {{
      border: 1px solid transparent;
      background: transparent;
      color: var(--text-muted);
      padding: 10px 24px;
      font-size: 14px;
      font-weight: 700;
      font-family: var(--font-sans);
      border-radius: 999px;
      cursor: pointer;
      transition: all 0.28s var(--spring-ease);
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

    /* 液態玻璃卡片通用樣式 (Apple iOS 27 Second-Gen Liquid Glass Card) */
    .glass-card {{
      background: var(--glass-bg);
      backdrop-filter: var(--glass-backdrop);
      -webkit-backdrop-filter: var(--glass-backdrop);
      border: 1px solid var(--glass-border);
      border-radius: 26px;
      padding: 22px;
      box-shadow: var(--glass-shadow);
      position: relative;
      overflow: hidden;
      transition: transform 0.28s var(--spring-ease), box-shadow 0.28s ease, border-color 0.28s ease;
    }}

    /* iOS 27 135° 對角稜鏡折射高光邊框 + 頂部水滴張力光暈 (Prismatic Rim & Meniscus Lens) */
    .glass-card::before {{
      content: '';
      position: absolute;
      inset: 0;
      border-radius: inherit;
      padding: 1.25px;
      background: var(--prismatic-rim);
      -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
      -webkit-mask-composite: xor;
      mask-composite: exclude;
      pointer-events: none;
      z-index: 2;
    }}

    /* 滑鼠懸停動態微光折射 + 頂部水滴張力曲面 (平時靜態零消耗，Hover 觸發焦散微光) */
    .glass-card::after {{
      content: '';
      position: absolute;
      inset: 0;
      border-radius: inherit;
      background: var(--cursor-glint), var(--meniscus-sheen);
      opacity: 0.65;
      transition: opacity 0.3s ease;
      pointer-events: none;
      z-index: 0;
    }}

    .glass-card:hover::after {{
      opacity: 1;
    }}

    .glass-card > * {{
      position: relative;
      z-index: 1;
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

    /* 歷史圖表區域 */
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

    /* 液態玻璃膠囊按鈕 (Filter & Sort Liquid Buttons) */
    .filter-btn {{
      background: var(--btn-glass-bg);
      border: 1px solid var(--btn-glass-border);
      color: var(--text-muted);
      padding: 8px 18px;
      border-radius: 999px;
      font-size: 13px;
      font-weight: 700;
      font-family: var(--font-sans);
      cursor: pointer;
      box-shadow: var(--btn-glass-shadow);
      transition: transform 0.22s var(--spring-ease), background 0.2s ease, color 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
    }}

    .filter-btn:hover {{
      background: var(--btn-glass-hover);
      color: var(--text-main);
      transform: translateY(-1px) scale(1.015);
    }}

    .filter-btn:active {{
      transform: translateY(0) scale(0.96);
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
      font-size: 13px;
      color: var(--text-dim);
      pointer-events: none;
    }}

    /* 專業表格樣式 (Table) - 富果高密度 + 液態玻璃質感 */
    .table-container {{
      overflow-x: auto;
      border-radius: 18px;
      border: 1px solid var(--glass-border);
      background: rgba(255, 255, 255, 0.01);
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
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
      border-bottom: 1px solid var(--glass-border);
      text-align: right;
      font-family: var(--font-mono);
      white-space: nowrap;
      transition: background 0.15s ease;
    }}

    table.fugle-table tbody tr:last-child td {{
      border-bottom: none;
    }}

    table.fugle-table td:first-child,
    table.fugle-table td:nth-child(2) {{
      text-align: left;
    }}

    table.fugle-table tbody tr:hover td {{
      background: var(--table-hover);
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
      .app-header {{
        flex-direction: column;
        align-items: flex-start;
      }}
      .header-actions {{
        width: 100%;
        justify-content: space-between;
      }}
      .segmented-control {{
        width: 100%;
      }}
      .tab-btn {{
        flex: 1;
        justify-content: center;
      }}
      .kpi-grid {{
        grid-template-columns: repeat(2, 1fr);
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
        width: 100%;
      }}
      .usage-charts-grid {{
        grid-template-columns: 1fr !important;
      }}
    }}

    /* ================= AI 模型用量與成本監控 (Tab 3) ================= */
    .usage-charts-grid {{
      display: grid;
      grid-template-columns: 2fr 1fr;
      gap: 20px;
      margin-bottom: 20px;
    }}

    .usage-chart-card {{
      padding: 20px 24px;
    }}

    .usage-chart-title {{
      font-size: 15px;
      font-weight: 700;
      margin-bottom: 14px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      color: var(--text-primary);
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
      border-radius: 14px;
      background: var(--glass-pill-bg);
      border: 1px solid var(--glass-border-subtle);
      font-size: 12px;
      font-weight: 600;
    }}

    .model-badge {{
      display: inline-flex;
      align-items: center;
      padding: 3px 9px;
      border-radius: 999px;
      font-family: var(--font-mono);
      font-size: 11px;
      font-weight: 700;
    }}

    .model-badge.flash {{
      background: rgba(16, 185, 129, 0.16);
      color: #10b981;
      border: 1px solid rgba(16, 185, 129, 0.35);
    }}

    .model-badge.argon {{
      background: rgba(56, 189, 248, 0.16);
      color: #38bdf8;
      border: 1px solid rgba(56, 189, 248, 0.35);
    }}

    .model-badge.fallback {{
      background: rgba(245, 158, 11, 0.16);
      color: #f59e0b;
      border: 1px solid rgba(245, 158, 11, 0.35);
    }}

    .code-exec-badge {{
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 3px 9px;
      border-radius: 999px;
      background: rgba(139, 92, 246, 0.16);
      color: #a78bfa;
      border: 1px solid rgba(139, 92, 246, 0.35);
      font-family: var(--font-mono);
      font-size: 11px;
      font-weight: 700;
    }}

    .usage-day-row {{
      cursor: pointer;
      transition: background 0.2s ease;
    }}

    .usage-day-row:hover {{
      background: rgba(255, 255, 255, 0.05);
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
      color: var(--accent-primary);
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
    }}

    .report-controls-right {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 10px;
    }}

    .report-select {{
      appearance: none;
      background: var(--glass-pill-bg);
      color: var(--text-main);
      border: 1px solid var(--glass-border);
      border-radius: 12px;
      padding: 8px 34px 8px 14px;
      font-family: var(--font-sans);
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      outline: none;
      background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%2394a3b8' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E");
      background-repeat: no-repeat;
      background-position: right 12px center;
      transition: border-color 0.2s, box-shadow 0.2s;
    }}

    .report-select:hover, .report-select:focus {{
      border-color: var(--primary-accent);
      box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.18);
    }}

    .report-select option {{
      background: #0f172a;
      color: #f8fafc;
    }}

    html.theme-light .report-select option {{
      background: #ffffff;
      color: #0f172a;
    }}

    .report-action-btn {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 8px 13px;
      border-radius: 12px;
      border: 1px solid var(--glass-border);
      background: var(--glass-pill-bg);
      color: var(--text-main);
      font-family: var(--font-sans);
      font-size: 12.5px;
      font-weight: 600;
      cursor: pointer;
      transition: transform 0.15s var(--spring-ease), border-color 0.2s, background 0.2s;
    }}

    .report-action-btn:hover:not(:disabled) {{
      border-color: var(--primary-accent);
      transform: translateY(-1px);
    }}

    .report-action-btn:disabled {{
      opacity: 0.4;
      cursor: not-allowed;
    }}

    .report-meta-pill {{
      font-size: 12px;
      color: var(--text-dim);
      font-family: var(--font-mono);
      padding: 6px 12px;
      border-radius: 10px;
      background: var(--glass-pill-bg);
      border: 1px solid var(--glass-border-subtle);
    }}

    .report-layout {{
      display: grid;
      grid-template-columns: 260px minmax(0, 1fr);
      gap: 18px;
      align-items: start;
    }}

    .report-toc-card {{
      position: sticky;
      top: 18px;
      max-height: calc(100vh - 36px);
      overflow-y: auto;
      padding: 18px 16px;
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

    .report-toc-item.toc-h3 {{
      padding-left: 22px;
      font-size: 12px;
      color: var(--text-dim);
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
      scroll-margin-top: 20px;
    }}

    .markdown-body h3 {{
      font-size: 15.5px;
      font-weight: 700;
      margin: 20px 0 10px 0;
      color: var(--primary-accent);
      scroll-margin-top: 20px;
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
  </style>
</head>
<body>
  <!-- iOS 27 3D 稜鏡流光絲綢背景：靜態向量彩帶穿過卡片後方，讓 backdrop-filter 折射出清晰的光學透鏡感且 0 效能負擔 -->
  <div class="ambient-glow">
    <svg class="ambient-silk-svg" viewBox="0 0 1600 1000" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="ios27SilkCyan" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#06b6d4" stop-opacity="0.45"/>
          <stop offset="50%" stop-color="#3b82f6" stop-opacity="0.32"/>
          <stop offset="100%" stop-color="#8b5cf6" stop-opacity="0.42"/>
        </linearGradient>
        <linearGradient id="ios27SilkRose" x1="100%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stop-color="#ec4899" stop-opacity="0.38"/>
          <stop offset="50%" stop-color="#f43f5e" stop-opacity="0.28"/>
          <stop offset="100%" stop-color="#f59e0b" stop-opacity="0.35"/>
        </linearGradient>
        <linearGradient id="ios27SilkEmerald" x1="0%" y1="100%" x2="100%" y2="0%">
          <stop offset="0%" stop-color="#10b981" stop-opacity="0.38"/>
          <stop offset="50%" stop-color="#14b8a6" stop-opacity="0.28"/>
          <stop offset="100%" stop-color="#38bdf8" stop-opacity="0.40"/>
        </linearGradient>
      </defs>
      <path d="M-120,160 C320,-40 620,420 1060,180 C1340,30 1520,240 1720,110 L1720,390 C1420,510 1120,220 740,430 C380,620 140,340 -120,460 Z" fill="url(#ios27SilkCyan)"/>
      <path d="M-100,520 C280,690 680,290 1120,540 C1380,680 1540,490 1720,610 L1720,860 C1400,720 1040,960 620,740 C260,550 80,790 -100,710 Z" fill="url(#ios27SilkRose)"/>
      <path d="M180,-80 C540,180 880,-40 1260,260 C1480,430 1620,290 1740,440 L1740,640 C1460,480 1140,680 780,380 C440,100 160,310 -80,140 Z" fill="url(#ios27SilkEmerald)"/>
    </svg>
  </div>

  <div class="app-container">
    <!-- 頂部標頭 -->
    <header class="app-header">
      <div class="header-branding">
        <div class="logo-badge">玉</div>
        <div class="header-title-box">
          <h1>
            <span>2026 AI 經理人投資決策看板</span>
            <span class="team-pill">TEAM_11402</span>
          </h1>
          <div class="header-subtitle">玉山證券行情 SDK 串接 · Multi-Agent 每日決策追蹤系統</div>
        </div>
      </div>
      <div class="header-actions">
        <div class="date-pill" id="dateBadge">基準日: {summary_data['as_of_date']}</div>
        <div class="ios27-slider-pill" title="iOS 27 液態玻璃通透度調節 (左：極致冰晶 / 右：溫潤凝霜)">
          <span>💧 通透度</span>
          <input type="range" id="glassAlphaSlider" min="35" max="145" value="100" oninput="setGlassTransparency(this.value)">
        </div>
        <button class="theme-toggle-btn" id="themeToggle" onclick="toggleTheme()">
          <span id="themeIcon">☀️</span>
          <span id="themeLabel">淺色模式</span>
        </button>
      </div>
    </header>

    <!-- 分頁導航切換 -->
    <div class="tab-nav-container">
      <div class="segmented-control">
        <button class="tab-btn active" id="tabBtn1" onclick="switchTab('tab1')">
          <span>📊</span> 帳戶總覽與庫存損益
        </button>
        <button class="tab-btn" id="tabBtn2" onclick="switchTab('tab2')">
          <span>📈</span> 自選行情觀察群組
        </button>
        <button class="tab-btn" id="tabBtn3" onclick="switchTab('tab3')">
          <span>🤖</span> AI 模型用量與成本監控
        </button>
        <button class="tab-btn" id="tabBtn4" onclick="switchTab('tab4')">
          <span>📄</span> 每日決策報告
        </button>
      </div>
    </div>

    <!-- ================= 頁籤 1: 帳戶總覽與庫存損益 ================= -->
    <div id="tab1Content">
      <!-- 頂部 KPI 卡片 -->
      <div class="kpi-grid">
        <div class="glass-card kpi-card">
          <div class="kpi-label">可交易淨值 (NAV)</div>
          <div class="kpi-value">${account['nav']:,.0f}</div>
          <div class="kpi-subtext">初始資金 $1,000,000,000</div>
        </div>
        <div class="glass-card kpi-card">
          <div class="kpi-label">累計總報酬率</div>
          <div class="kpi-value {'badge-pnl up' if account['cum_return_pct'] >= 0 else 'badge-pnl down'}" style="display:inline-block; font-size:22px;">
            {'+' if account['cum_return_pct'] >= 0 else ''}{account['cum_return_pct']:.2f}%
          </div>
          <div class="kpi-subtext">累計損益 ${account['cum_pnl']:,.0f}</div>
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
      </div>

      <!-- 資產走勢折線圖 -->
      <div class="glass-card chart-section">
        <div class="chart-header">
          <div class="chart-title">
            <span>📈</span> 每日可交易淨值 (NAV) 與現金水位變化趨勢
          </div>
        </div>
        <div class="chart-wrapper">
          <canvas id="assetHistoryChart"></canvas>
        </div>
      </div>

      <!-- 目前庫存持股明細表 -->
      <div class="glass-card">
        <div class="table-toolbar">
          <div class="chart-title">
            <span>📋</span> 目前庫存部位與未實現損益明細 ({len(held_positions)} 檔)
          </div>
          <div class="search-box">
            <span class="search-icon">🔍</span>
            <input type="text" class="search-input" id="holdingsSearchInput" placeholder="搜尋代號或名稱..." oninput="filterHoldingsTable()">
          </div>
        </div>

        <div class="table-container">
          <table class="fugle-table" id="holdingsTable">
            <thead>
              <tr>
                <th onclick="sortHoldings('code')">代號/名稱 <span class="sort-icon">⇅</span></th>
                <th onclick="sortHoldings('market')">市場 <span class="sort-icon">⇅</span></th>
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
    </div>

    <!-- ================= 頁籤 2: 自選行情觀察群組 ================= -->
    <div id="tab2Content" style="display: none;">
      <div class="glass-card">
        <div class="table-toolbar">
          <div class="filter-pills">
            <button class="filter-btn active" id="btnGroupA" onclick="setWatchGroup('held')">
              我的持股 ({len(held_positions)} 檔)
            </button>
            <button class="filter-btn" id="btnGroupB" onclick="setWatchGroup('unheld')">
              其餘標的 ({150 - len(held_positions)} 檔)
            </button>
            <button class="filter-btn" id="btnGroupAll" onclick="setWatchGroup('all')">
              全部 150 檔
            </button>
          </div>

          <div style="display:flex; gap:10px; flex-wrap:wrap;">
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
            <span class="usage-chart-subtitle">L1 ~ L4 算力分佈</span>
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
            <span>L1 事實擷取</span>
            <span class="model-badge flash">gemini-3.8-flash</span>
            <span style="color:var(--text-dim); font-size:11px;">備援: gemini-3.5-flash-lite</span>
          </div>
          <div class="routing-pill">
            <span>L2M 市場走向</span>
            <span class="model-badge argon">gemini-4-argon</span>
            <span style="color:var(--text-dim); font-size:11px;">備援: gemini-3.6-flash</span>
          </div>
          <div class="routing-pill">
            <span>L2 個股推論</span>
            <span class="model-badge argon">gemini-4-argon</span>
            <span class="code-exec-badge">🐍 Code Exec</span>
          </div>
          <div class="routing-pill">
            <span>L3 投組決策</span>
            <span class="model-badge argon">gemini-4-argon</span>
            <span class="code-exec-badge">🐍 Code Exec</span>
          </div>
          <div class="routing-pill">
            <span>L4 委託計算</span>
            <span class="model-badge argon">gemini-4-argon</span>
            <span class="code-exec-badge">🐍 Code Exec</span>
          </div>
        </div>
      </div>

      <!-- 區塊 D: 每日歷史用量下鑽折疊表 -->
      <div class="glass-card">
        <div class="table-toolbar">
          <div>
            <h3 style="font-size:16px; font-weight:700; margin:0;">📅 每日歷史用量與 5 階段執行明細</h3>
            <div style="font-size:12px; color:var(--text-dim); margin-top:4px;">點擊任一交易日即可展開該日 L1 ～ L4 各階段模型、Token 結構、Code Execution 次數與耗時明細</div>
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

    <!-- 頁尾 -->
    <footer class="app-footer">
      <div>AI CUP 2026 玉山人工智慧公開挑戰賽 · 隊伍 TEAM_11402 專用看板</div>
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

    // 主題切換 (深淺模式)
    function toggleTheme() {{
      const html = document.documentElement;
      const isDark = html.classList.contains('theme-dark');
      if (isDark) {{
        html.classList.remove('theme-dark');
        html.classList.add('theme-light');
        document.getElementById('themeIcon').textContent = '🌙';
        document.getElementById('themeLabel').textContent = '深色模式';
        localStorage.setItem('esun_dashboard_theme', 'light');
      }} else {{
        html.classList.remove('theme-light');
        html.classList.add('theme-dark');
        document.getElementById('themeIcon').textContent = '☀️';
        document.getElementById('themeLabel').textContent = '淺色模式';
        localStorage.setItem('esun_dashboard_theme', 'dark');
      }}
      if (window.assetChart) {{
        updateChartTheme();
      }}
    }}

    // 初始化主題與 iOS 27 通透度滑桿
    function setGlassTransparency(val) {{
      const scale = (Number(val) / 100).toFixed(2);
      const blurPx = Math.round(14 + (Number(val) / 100) * 12);
      document.documentElement.style.setProperty('--glass-alpha-scale', scale);
      document.documentElement.style.setProperty('--glass-blur-px', blurPx + 'px');
      localStorage.setItem('esun_dashboard_glass_alpha', val);
    }}

    (function initTheme() {{
      const saved = localStorage.getItem('esun_dashboard_theme');
      if (saved === 'light') {{
        document.documentElement.classList.remove('theme-dark');
        document.documentElement.classList.add('theme-light');
        document.getElementById('themeIcon').textContent = '🌙';
        document.getElementById('themeLabel').textContent = '深色模式';
      }}
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
      document.getElementById('tab1Content').style.display = tabId === 'tab1' ? 'block' : 'none';
      document.getElementById('tab2Content').style.display = tabId === 'tab2' ? 'block' : 'none';
      document.getElementById('tab3Content').style.display = tabId === 'tab3' ? 'block' : 'none';
      document.getElementById('tab4Content').style.display = tabId === 'tab4' ? 'block' : 'none';
      if (tabId === 'tab2') {{
        renderWatchTable();
      }} else if (tabId === 'tab3') {{
        renderUsageTab();
      }} else if (tabId === 'tab4') {{
        renderReportsTab();
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
        return `
          <tr>
            <td>
              <div class="stock-tag-box">
                <span class="stock-code">${{item.code}}</span>
                <span class="stock-name">${{item.name}}</span>
              </div>
            </td>
            <td><span class="market-badge">${{item.market}}</span></td>
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
        `;
      }}).join('');
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
    }}

    function updateChartTheme() {{
      const isDark = document.documentElement.classList.contains('theme-dark');
      const gridColor = isDark ? 'rgba(255, 255, 255, 0.06)' : 'rgba(0, 0, 0, 0.06)';
      const textColor = isDark ? '#94a3b8' : '#64748b';

      [window.assetChart, window.usageTrendChartInst, window.usageTokenStackChartInst].forEach(ch => {{
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
      if (!usageTabRendered) {{
        usageTabRendered = true;
        initLiquidSpecularGlint();
      }}
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
      const stageOrder = ['l1', 'l2m', 'l2', 'l3', 'l4'];
      const stageNames = {{ l1: 'L1 事實擷取', l2m: 'L2M 市場走向', l2: 'L2 個股推論', l3: 'L3 投組決策', l4: 'L4 委託計算' }};
      const stageTotals = {{ l1: 0, l2m: 0, l2: 0, l3: 0, l4: 0 }};
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
            backgroundColor: ['#10b981', '#06b6d4', '#3b82f6', '#8b5cf6', '#f59e0b'],
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

      const stageOrder = ['l1', 'l2m', 'l2', 'l3', 'l4'];
      const stageLabels = {{
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
                <span style="color:var(--text-primary); font-weight:700;">$${{Number(st.response_cost || 0).toFixed(4)}}</span>
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

      // 動態從渲染後標題生成目錄 (完全相容任何報告格式)
      const tocEl = document.getElementById('reportTocList');
      const headings = Array.from(bodyEl.querySelectorAll('h2, h3'));
      document.getElementById('reportTocCount').textContent = headings.length ? `${{headings.length}} 節` : '';

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
          }};
          tocEl.appendChild(btn);
        }});
      }}
    }}

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

    // 輕量級液態玻璃表面微光追蹤 (Passive 事件且僅更新當前卡片 CSS 變數，無背景常駐運算)
    function initLiquidSpecularGlint() {{
      if (window.matchMedia && window.matchMedia('(pointer: coarse)').matches) return;
      document.querySelectorAll('.glass-card').forEach(card => {{
        card.addEventListener('pointermove', (e) => {{
          const rect = card.getBoundingClientRect();
          card.style.setProperty('--mx', `${{(e.clientX - rect.left).toFixed(0)}}px`);
          card.style.setProperty('--my', `${{(e.clientY - rect.top).toFixed(0)}}px`);
        }}, {{ passive: true }});
      }});
    }}

    // 初始化渲染
    window.addEventListener('DOMContentLoaded', () => {{
      renderHoldingsTable();
      renderAssetChart();
      initLiquidSpecularGlint();
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
