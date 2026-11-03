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
import sys
from pathlib import Path
from typing import Dict, Any, List

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

DASHBOARD_DIR = Path(__file__).resolve().parent
DIST_DIR = DASHBOARD_DIR / "dist"
DIST_HTML = DIST_DIR / "index.html"


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

    # 轉為 JSON 注入前端以利動態排序與篩選
    json_data_payload = {
        "as_of_date": summary_data["as_of_date"],
        "trade_date": summary_data["trade_date"],
        "account": account,
        "history": history,
        "stocks": all_stocks_list
    }

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

  <style>
    :root {{
      --font-sans: 'Plus Jakarta Sans', 'Noto Sans TC', -apple-system, BlinkMacSystemFont, sans-serif;
      --font-mono: 'JetBrains Mono', monospace;
      
      /* 台股習慣色彩：紅漲綠跌 */
      --color-up: #ef4444;
      --color-up-bg: rgba(239, 68, 68, 0.12);
      --color-up-border: rgba(239, 68, 68, 0.25);
      --color-down: #10b981;
      --color-down-bg: rgba(16, 185, 129, 0.12);
      --color-down-border: rgba(16, 185, 129, 0.25);
      --color-flat: #94a3b8;

      --primary-accent: #0284c7;
      --primary-glow: rgba(2, 132, 199, 0.25);
    }}

    /* 深色主題 (Apple Liquid Dark Glass) */
    .theme-dark {{
      --bg-gradient: radial-gradient(circle at 10% 20%, #0d121d 0%, #090c13 50%, #05070a 100%);
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
      --text-dim: #64748b;
      
      --glass-bg: rgba(18, 24, 38, 0.65);
      --glass-bg-hover: rgba(28, 38, 58, 0.75);
      --glass-border: rgba(255, 255, 255, 0.08);
      --glass-border-specular: rgba(255, 255, 255, 0.18);
      --glass-shadow: 0 12px 36px -4px rgba(0, 0, 0, 0.5), inset 0 1px 1px 0 rgba(255, 255, 255, 0.1);
      
      --card-highlight: linear-gradient(135deg, rgba(255, 255, 255, 0.05) 0%, rgba(255, 255, 255, 0) 100%);
      --table-stripe: rgba(255, 255, 255, 0.015);
      --table-hover: rgba(255, 255, 255, 0.04);
      --pill-bg: rgba(255, 255, 255, 0.06);
    }}

    /* 淺色主題 (Apple Liquid White Glass) */
    .theme-light {{
      --bg-gradient: radial-gradient(circle at 10% 10%, #f8fafc 0%, #e2e8f0 60%, #cbd5e1 100%);
      --text-main: #0f172a;
      --text-muted: #475569;
      --text-dim: #94a3b8;
      
      --glass-bg: rgba(255, 255, 255, 0.7);
      --glass-bg-hover: rgba(255, 255, 255, 0.88);
      --glass-border: rgba(255, 255, 255, 0.6);
      --glass-border-specular: rgba(255, 255, 255, 0.9);
      --glass-shadow: 0 12px 32px -4px rgba(0, 0, 0, 0.08), inset 0 1px 2px 0 rgba(255, 255, 255, 0.9);
      
      --card-highlight: linear-gradient(135deg, rgba(255, 255, 255, 0.6) 0%, rgba(255, 255, 255, 0.1) 100%);
      --table-stripe: rgba(0, 0, 0, 0.015);
      --table-hover: rgba(0, 0, 0, 0.035);
      --pill-bg: rgba(0, 0, 0, 0.05);
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
      color: var(--text-main);
      min-height: 100vh;
      overflow-x: hidden;
      padding-bottom: 48px;
      transition: background 0.3s ease, color 0.3s ease;
    }}

    /* 頂部光暈氛圍特效 */
    .ambient-glow {{
      position: fixed;
      top: -160px;
      left: 50%;
      transform: translateX(-50%);
      width: 700px;
      height: 380px;
      background: radial-gradient(ellipse at center, rgba(14, 165, 233, 0.15) 0%, rgba(99, 102, 241, 0.08) 50%, transparent 80%);
      filter: blur(60px);
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

    .logo-badge {{
      width: 44px;
      height: 44px;
      border-radius: 14px;
      background: linear-gradient(135deg, #0284c7 0%, #38bdf8 100%);
      display: flex;
      align-items: center;
      justify-content: center;
      color: white;
      font-weight: 800;
      font-size: 20px;
      box-shadow: 0 4px 16px rgba(2, 132, 199, 0.4);
    }}

    .header-title-box h1 {{
      font-size: 20px;
      font-weight: 800;
      letter-spacing: -0.02em;
      display: flex;
      align-items: center;
      gap: 8px;
    }}

    .header-title-box .team-pill {{
      font-size: 12px;
      padding: 3px 8px;
      border-radius: 6px;
      background: var(--pill-bg);
      color: var(--primary-accent);
      font-weight: 700;
      font-family: var(--font-mono);
      border: 1px solid var(--glass-border-specular);
    }}

    .header-subtitle {{
      font-size: 13px;
      color: var(--text-muted);
      margin-top: 2px;
    }}

    .header-actions {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}

    .date-pill {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 7px 14px;
      border-radius: 20px;
      background: var(--glass-bg);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1px solid var(--glass-border-specular);
      font-size: 13px;
      font-weight: 600;
      font-family: var(--font-mono);
      color: var(--text-main);
      box-shadow: var(--glass-shadow);
    }}

    .date-pill::before {{
      content: '';
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #10b981;
      display: inline-block;
      box-shadow: 0 0 8px #10b981;
    }}

    /* 主題切換按鈕 */
    .theme-toggle-btn {{
      background: var(--glass-bg);
      border: 1px solid var(--glass-border-specular);
      color: var(--text-main);
      border-radius: 20px;
      padding: 7px 14px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 13px;
      font-weight: 600;
      backdrop-filter: blur(16px);
      box-shadow: var(--glass-shadow);
      transition: all 0.2s ease;
    }}
    .theme-toggle-btn:hover {{
      background: var(--glass-bg-hover);
      transform: translateY(-1px);
    }}

    /* 主選單分頁切換 (Tabs) - Apple 膠囊控制器 */
    .tab-nav-container {{
      display: flex;
      justify-content: center;
      margin-bottom: 28px;
    }}

    .segmented-control {{
      display: inline-flex;
      background: var(--glass-bg);
      backdrop-filter: blur(24px);
      -webkit-backdrop-filter: blur(24px);
      padding: 5px;
      border-radius: 16px;
      border: 1px solid var(--glass-border-specular);
      box-shadow: var(--glass-shadow);
      gap: 6px;
    }}

    .tab-btn {{
      border: none;
      background: transparent;
      color: var(--text-muted);
      padding: 10px 22px;
      font-size: 14px;
      font-weight: 700;
      border-radius: 12px;
      cursor: pointer;
      transition: all 0.2s ease;
      display: flex;
      align-items: center;
      gap: 8px;
    }}

    .tab-btn.active {{
      background: var(--card-highlight), var(--glass-bg-hover);
      color: var(--text-main);
      border: 1px solid var(--glass-border-specular);
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    }}

    /* 毛玻璃卡片通用樣式 (Glass Card) */
    .glass-card {{
      background: var(--glass-bg);
      backdrop-filter: blur(24px);
      -webkit-backdrop-filter: blur(24px);
      border: 1px solid var(--glass-border);
      border-radius: 20px;
      padding: 20px;
      box-shadow: var(--glass-shadow);
      position: relative;
      overflow: hidden;
      transition: transform 0.2s ease, box-shadow 0.2s ease;
    }}

    .glass-card::before {{
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 1px;
      background: var(--card-highlight);
      pointer-events: none;
    }}

    /* 頂部 KPI 卡片網格 */
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 16px;
      margin-bottom: 28px;
    }}

    .kpi-card {{
      padding: 18px 20px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
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
      margin-bottom: 16px;
    }}

    .filter-pills {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }}

    .filter-btn {{
      background: var(--pill-bg);
      border: 1px solid var(--glass-border);
      color: var(--text-muted);
      padding: 8px 16px;
      border-radius: 12px;
      font-size: 13px;
      font-weight: 700;
      cursor: pointer;
      transition: all 0.15s ease;
    }}

    .filter-btn:hover {{
      background: var(--glass-bg-hover);
      color: var(--text-main);
    }}

    .filter-btn.active {{
      background: var(--primary-accent);
      color: #fff;
      border-color: var(--primary-accent);
      box-shadow: 0 2px 10px var(--primary-glow);
    }}

    .search-box {{
      position: relative;
      min-width: 240px;
    }}

    .search-input {{
      width: 100%;
      background: var(--pill-bg);
      border: 1px solid var(--glass-border-specular);
      padding: 9px 14px 9px 36px;
      border-radius: 12px;
      color: var(--text-main);
      font-size: 13px;
      font-family: var(--font-sans);
      outline: none;
      transition: all 0.2s ease;
    }}

    .search-input:focus {{
      border-color: var(--primary-accent);
      box-shadow: 0 0 0 3px var(--primary-glow);
    }}

    .search-icon {{
      position: absolute;
      left: 12px;
      top: 50%;
      transform: translateY(-50%);
      font-size: 14px;
      color: var(--text-dim);
      pointer-events: none;
    }}

    /* 專業表格樣式 (Table) - 富果風格高密度 */
    .table-container {{
      overflow-x: auto;
      border-radius: 16px;
    }}

    table.fugle-table {{
      width: 100%;
      border-collapse: separate;
      border-spacing: 0;
      font-size: 13px;
    }}

    table.fugle-table th {{
      background: var(--pill-bg);
      color: var(--text-muted);
      font-weight: 700;
      text-align: right;
      padding: 12px 14px;
      border-bottom: 1px solid var(--glass-border);
      white-space: nowrap;
      cursor: pointer;
      user-select: none;
      transition: color 0.15s ease;
    }}

    table.fugle-table th:first-child {{
      text-align: left;
      border-top-left-radius: 12px;
    }}
    table.fugle-table th:nth-child(2) {{
      text-align: left;
    }}
    table.fugle-table th:last-child {{
      border-top-right-radius: 12px;
    }}

    table.fugle-table th:hover {{
      color: var(--text-main);
    }}

    table.fugle-table th .sort-icon {{
      margin-left: 4px;
      font-size: 11px;
      opacity: 0.5;
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

    .market-badge {{
      font-size: 11px;
      padding: 2px 6px;
      border-radius: 4px;
      background: var(--pill-bg);
      color: var(--text-dim);
      font-family: var(--font-sans);
    }}

    /* 漲跌徽章 (Up/Down Badges) */
    .badge-pnl {{
      display: inline-flex;
      align-items: center;
      padding: 3px 8px;
      border-radius: 6px;
      font-weight: 700;
      font-size: 12px;
      font-family: var(--font-mono);
    }}

    .badge-pnl.up {{
      background: var(--color-up-bg);
      color: var(--color-up);
      border: 1px solid var(--color-up-border);
    }}

    .badge-pnl.down {{
      background: var(--color-down-bg);
      color: var(--color-down);
      border: 1px solid var(--color-down-border);
    }}

    .badge-pnl.flat {{
      color: var(--color-flat);
    }}

    /* 權重進度條 */
    .weight-bar-wrapper {{
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 8px;
    }}

    .weight-progress {{
      width: 50px;
      height: 6px;
      border-radius: 3px;
      background: var(--pill-bg);
      overflow: hidden;
    }}

    .weight-fill {{
      height: 100%;
      background: linear-gradient(90deg, #38bdf8, #0284c7);
      border-radius: 3px;
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

    /* RWD 適應 */
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
      .search-box {{
        width: 100%;
      }}
    }}
  </style>
</head>
<body>
  <div class="ambient-glow"></div>

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

    <!-- 頁尾 -->
    <footer class="app-footer">
      <div>AI CUP 2026 玉山人工智慧公開挑戰賽 · 隊伍 TEAM_11402 專用看板</div>
      <div>數據更新自官方 DataPack 與玉山證券行情 SDK · 僅供研究與競賽內部覆核使用</div>
    </footer>
  </div>

  <!-- 資料 Payload 注入 -->
  <script>
    const DASHBOARD_DATA = {json.dumps(json_data_payload, ensure_ascii=False)};
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

    // 初始化主題
    (function initTheme() {{
      const saved = localStorage.getItem('esun_dashboard_theme');
      if (saved === 'light') {{
        document.documentElement.classList.remove('theme-dark');
        document.documentElement.classList.add('theme-light');
        document.getElementById('themeIcon').textContent = '🌙';
        document.getElementById('themeLabel').textContent = '深色模式';
      }}
    }})();

    // 分頁切換
    function switchTab(tabId) {{
      currentTab = tabId;
      document.getElementById('tabBtn1').classList.toggle('active', tabId === 'tab1');
      document.getElementById('tabBtn2').classList.toggle('active', tabId === 'tab2');
      document.getElementById('tab1Content').style.display = tabId === 'tab1' ? 'block' : 'none';
      document.getElementById('tab2Content').style.display = tabId === 'tab2' ? 'block' : 'none';
      if (tabId === 'tab2') {{
        renderWatchTable();
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
              ${{item.is_held ? '<span class="badge-pnl" style="background:rgba(2,132,199,0.15); color:#0284c7; border:1px solid rgba(2,132,199,0.3);">已買入 ' + item.lots + '張</span>' : '<span style="color:var(--text-dim); font-size:12px;">未持有</span>'}}
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
      if (!window.assetChart) return;
      const isDark = document.documentElement.classList.contains('theme-dark');
      const gridColor = isDark ? 'rgba(255, 255, 255, 0.06)' : 'rgba(0, 0, 0, 0.06)';
      const textColor = isDark ? '#94a3b8' : '#64748b';

      window.assetChart.options.scales.x.grid.color = gridColor;
      window.assetChart.options.scales.x.ticks.color = textColor;
      window.assetChart.options.scales.y.grid.color = gridColor;
      window.assetChart.options.scales.y.ticks.color = textColor;
      window.assetChart.options.plugins.legend.labels.color = textColor;
      window.assetChart.update();
    }}

    // 初始化渲染
    window.addEventListener('DOMContentLoaded', () => {{
      renderHoldingsTable();
      renderAssetChart();
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
    from market_api import fetch_all_150_quotes

    summary = get_latest_portfolio_summary()
    quotes = fetch_all_150_quotes(summary["stocks_150"], fetch_candles=False)
    out_file = build_dashboard_html(summary, quotes)
    print(f"完成！網頁已產出至: {out_file}")
