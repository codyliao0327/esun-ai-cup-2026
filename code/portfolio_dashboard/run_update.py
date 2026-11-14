"""
Daily One-Click Update Runner for 2026 玉山人工智慧挑戰賽 看板系統
用法：
  python run_update.py
  python run_update.py --push   (更新完自動 git commit & push)
"""
import argparse
import json
import subprocess
import time
from pathlib import Path
import sys

# 確保 Windows 終端機正常輸出 UTF-8 (避免 cp950 編碼問題)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
CURRENT_DIR = Path(__file__).resolve().parent
CODE_DIR = CURRENT_DIR.parent
PROJECT_ROOT = CODE_DIR.parent

import sys
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from tracker import get_latest_portfolio_summary
from builder import build_dashboard_html


def refresh_dashboard_with_cached_quotes() -> Path:
    """使用本地快取行情 (market_cache.json) 與最新報告/持股快照，快速重建 dist/index.html（不呼叫玉山行情 SDK）。"""
    summary = get_latest_portfolio_summary()
    cache_file = CURRENT_DIR / "market_cache.json"
    quotes = {}
    if cache_file.is_file():
        try:
            quotes = json.loads(cache_file.read_text(encoding="utf-8")).get("stocks", {})
        except Exception:
            quotes = {}
    return build_dashboard_html(summary, quotes)


def run_update(auto_push: bool = False, fetch_candles: bool = True, rebuild_candles: bool = False):
    from market_api import fetch_all_150_quotes, rebuild_full_candles
    print("=" * 65)
    print("🚀 啟動 2026 玉山 AI 經理人投資看板 - 每日收盤數據自動更新產線")
    print("=" * 65)

    # 1. 解析後台成交資料與 DataPack
    print("\n[Step 1/3] 正在解析後台真實成交明細與每日 DataPack 快照...")
    summary = get_latest_portfolio_summary()
    acc = summary["account"]
    print(f"  基準日期: {summary['as_of_date']} (繳交對應交易日: {summary['trade_date']})")
    print(f"  可交易淨值 (NAV): NT$ {acc['nav']:,} 元")
    print(f"  現有現金 (Cash): NT$ {acc['cash']:,} 元 ({acc['cash_ratio_pct']}%)")
    print(f"  累計報酬率: {acc['cum_return_pct']}% (總損益: NT$ {acc['cum_pnl']:,} 元)")
    print(f"  目前持股檔數: {acc['holdings_count']} 檔")

    # 2. 串接玉山證券行情 SDK (100% 透過玉山 API 取得所有行情)
    if rebuild_candles:
        print("\n[Step 2/3] [強制完整重建模式] 正在調用玉山 historical.candles 完整拉取官方 150 檔日 K 線...")
        quotes = rebuild_full_candles(summary["stocks_150"])
    else:
        print("\n[Step 2/3] 正在登入玉山證券 SDK 並抓取 150 檔標的最新收盤行情...")
        quotes = fetch_all_150_quotes(summary["stocks_150"], fetch_candles=fetch_candles)

    # 2.5 先結算並合併所有 LiteLLM Usage 紀錄至本地歷史 usage_history.json，確保網頁讀取最新數據
    usage_history_file = CURRENT_DIR / "usage_history.json"
    try:
        if str(CODE_DIR) not in sys.path:
            sys.path.insert(0, str(CODE_DIR))
        from configs.gemini_client import settle_usage_history

        settle_usage_history()
        print(f"  ✅ LiteLLM Usage 歷史紀錄已結算更新: {usage_history_file}")
    except Exception as e:
        print(f"  ⚠️ 結算 Usage 歷史紀錄時發生提示: {e}")

    # 3. 渲染富果/Apple風格液態毛玻璃網頁
    print("\n[Step 3/3] 正在生成富果 Fugle 專業版面 + Apple 毛玻璃前端網頁...")
    out_file = build_dashboard_html(summary, quotes)
    print(f"  ✅ 網頁生成完畢: {out_file}")

    # 4. 可選 Git Push (支援 Cloudflare Pages 自動部署)
    if auto_push:
        print("\n[Git 部署] 正在執行 Git 提交與推送至遠端倉庫...")
        try:
            git_files = [str(out_file), str(CURRENT_DIR / "market_cache.json")]
            if usage_history_file.is_file():
                git_files.append(str(usage_history_file))
            subprocess.run(["git", "add", *git_files], cwd=str(CODE_DIR), check=True)
            commit_msg = f"chore(dashboard): update portfolio dashboard as of {summary['as_of_date']}"
            subprocess.run(["git", "commit", "-m", commit_msg], cwd=str(CODE_DIR), check=True)
            subprocess.run(["git", "push"], cwd=str(CODE_DIR), check=True)
            print("  ✅ 成功推送至 GitHub！Cloudflare Pages 將於數秒內自動完成部署。")
        except Exception as e:
            print(f"  ⚠️ Git 推送過程中發生提示或無變動: {e}")
    else:
        print("\n💡 提示：若您已在 Cloudflare Pages 綁定此 Repo，可在終端機執行：")
        print(f"   cd code")
        print(f"   git add portfolio_dashboard/dist/index.html")
        print(f"   git commit -m \"update dashboard {summary['as_of_date']}\"")
        print(f"   git push")
        print("   即可完成線上網頁即時部署！")
        print(f"   您也可以在電腦端直接雙擊打開該檔案在本地預覽：\n   file:///{str(out_file).replace(chr(92), '/')}")

    print("\n" + "=" * 65)
    print("🎉 儀表板更新全部順利完成！")
    print("=" * 65)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="玉山 AI 挑戰賽投資看板每日一鍵更新工具")
    parser.add_argument("--push", action="store_true", help="完成後自動執行 git commit & push")
    parser.add_argument("--no-candles", action="store_true", help="跳過歷史 K 線，僅抓取今日最新現價")
    parser.add_argument("--rebuild-candles", action="store_true", help="強制重新自玉山 API historical.candles 完整拉取自 10/27 起官方歷史 K 線")
    parser.add_argument("--reports-only", action="store_true", help="僅使用本地快取行情快速重新生成網頁（同步最新每日決策報告）")
    args = parser.parse_args()

    if args.reports_only:
        out_file = refresh_dashboard_with_cached_quotes()
        print(f"✅ 已使用快取行情同步最新報告至網頁: {out_file}")
    else:
        run_update(auto_push=args.push, fetch_candles=not args.no_candles, rebuild_candles=args.rebuild_candles)
