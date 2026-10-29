"""每日排程執行的 D-Plan 自動化端到端主程式入口。

執行順序：
  Step 0: L0 外部多源資料收集與預處理 (任一失敗即直接中斷報錯，嚴防漏抓)
    - 0a: DataPack Loader (datapack_loader.py)
    - 0b: CMoney 討論區情緒爬蟲 (cmoney_sentiment_crawler.py)
    - 0c: FinLab 市場與個股量化寬表 (finlab_market_loader.py)
    - 0d: 同業主動式 ETF 前15大持股快照 (finlab_active_etf_loader.py)
  Step 1: L1 事實提取 (fact_extractor.py)
  Step 2: L2M 市場整體判斷 (market_view_agent.py)
  Step 3: L2 個股推論 (stock_inference_agent.py)
  Step 4: L3 投資組合配置決策 (portfolio_decision_agent.py)
  Step 5: L4 官方演算法委託單計算與智能覆核 (order_calculator.py)
  Step 6: D-Plan 總組裝與全量合規校驗 (build_dplan.py) -> 產出 D-Plan_<team_id>_<trade_date>.json
  Step 7: 每日投資決策與投資組合回顧報告生成 (generate_daily_report.py) -> 產出 Markdown 報告供真人回顧
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 設定 code/ 為匯入路徑
CODE_DIR = Path(__file__).resolve().parent
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from build_dplan import assemble_dplan  # noqa: E402
from configs.date_utils import format_iso_trade_date, prompt_trade_date  # noqa: E402
from generate_daily_report import build_daily_report  # noqa: E402

TW_TZ = timezone(timedelta(hours=8))
PYTHON_EXE = sys.executable


def _run_substage(script_relpath: str, args_list: list[str]) -> bool:
    """透過獨立子進程執行單一 Agent 階段；失敗時拋出 RuntimeError 中斷整體產線。"""
    script_path = CODE_DIR / script_relpath
    cmd = [PYTHON_EXE, str(script_path)] + args_list
    print(f" -> 執行指令: {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=str(CODE_DIR))
    if res.returncode != 0:
        raise RuntimeError(
            f"❌ 階段 {script_relpath} 執行失敗！(returncode={res.returncode})\n"
            f"產線已中斷，請確認該模組執行紀錄與錯誤訊息後再重新執行。"
        )
    return True


def run_pipeline(
    target_date: str = None,
    trade_date: str = None,
    team_id: str = "TEAM_11402",
    skip_l0: bool = False,
    skip_l1: bool = False,
    skip_l2m: bool = False,
    skip_l2: bool = False,
    skip_l3: bool = False,
    skip_l4: bool = False,
    skip_report: bool = False,
):
    """一鍵執行每日 D-Plan 端到端完整生成流程。"""
    t_date = prompt_trade_date(target_date, prompt_text="D-Plan 自動產線 - 交易日期")
    final_trade_date = trade_date or format_iso_trade_date(t_date)

    print("\n" + "=" * 80)
    print(f" [D-Plan Pipeline] 啟動每日端到端自動化產線")
    print(f" 資料基準日期: {t_date} ｜ 繳交交易日: {final_trade_date} ｜ 隊伍: {team_id}")
    print("=" * 80)

    # -------------------------------------------------------------------------
    # Step 0: L0 外部多源資料收集 (嚴格報錯中斷，不得漏抓)
    # -------------------------------------------------------------------------
    if not skip_l0:
        print("\n>>> [Step 0/7] 執行 L0 資料收集階段 (DataPack / CMoney / FinLab Market / Active ETF)...")
        
        # 0a: DataPack Loader
        print(" [0a] 檢查並轉換官方 DataPack 原始資料...")
        _run_substage("L0_sources/datapack_loader.py", ["--date", t_date])

        # 0b: CMoney Sentiment Crawler
        print(" [0b] 抓取 CMoney 討論區個股情緒資料...")
        _run_substage("L0_sources/cmoney_sentiment_crawler.py", ["--date", t_date])

        # 0c: FinLab Market Loader
        print(" [0c] 計算 FinLab 市場寬表與個股多面向指標...")
        _run_substage("L0_sources/finlab_market_loader.py", ["--date", t_date])

        # 0d: FinLab Active ETF Loader
        print(" [0d] 下載同業主動式 ETF 前15大成分股持股快照...")
        _run_substage("L0_sources/finlab_active_etf_loader.py", ["--date", t_date])
    else:
        print("\n>>> [Step 0/7] 跳過 L0 資料收集 (使用既有快照)")

    # -------------------------------------------------------------------------
    # Step 1: L1 事實提取
    # -------------------------------------------------------------------------
    if not skip_l1:
        print("\n>>> [Step 1/7] 執行 L1 客觀事實擷取 Agent (fact_extractor)...")
        _run_substage("L1_observations/fact_extractor.py", ["--date", t_date])
    else:
        print("\n>>> [Step 1/7] 跳過 L1 (使用既有快照)")

    # -------------------------------------------------------------------------
    # Step 2: L2M 市場整體判斷
    # -------------------------------------------------------------------------
    if not skip_l2m:
        print("\n>>> [Step 2/7] 執行 L2M 市場整體判斷 Agent (market_view_agent)...")
        _run_substage("L2M_market_view/market_view_agent.py", ["--date", t_date])
    else:
        print("\n>>> [Step 2/7] 跳過 L2M (使用既有快照)")

    # -------------------------------------------------------------------------
    # Step 3: L2 個股推論
    # -------------------------------------------------------------------------
    if not skip_l2:
        print("\n>>> [Step 3/7] 執行 L2 個股推論 Agent (stock_inference_agent)...")
        _run_substage("L2_inferences/stock_inference_agent.py", ["--date", t_date])
    else:
        print("\n>>> [Step 3/7] 跳過 L2 (使用既有快照)")

    # -------------------------------------------------------------------------
    # Step 4: L3 投資組合配置決策
    # -------------------------------------------------------------------------
    if not skip_l3:
        print("\n>>> [Step 4/7] 執行 L3 投資組合決策 Agent (portfolio_decision_agent)...")
        _run_substage("L3_decisions/portfolio_decision_agent.py", ["--date", t_date])
    else:
        print("\n>>> [Step 4/7] 跳過 L3 (使用既有快照)")

    # -------------------------------------------------------------------------
    # Step 5: L4 委託單計算與智能覆核
    # -------------------------------------------------------------------------
    if not skip_l4:
        print("\n>>> [Step 5/7] 執行 L4 委託單計算與智能覆核 Agent (order_calculator)...")
        _run_substage("L4_orders/order_calculator.py", ["--date", t_date])
    else:
        print("\n>>> [Step 5/7] 跳過 L4 (使用既有快照)")

    # -------------------------------------------------------------------------
    # Step 6: D-Plan 總組裝與全量合規驗證
    # -------------------------------------------------------------------------
    print("\n>>> [Step 6/7] 執行 D-Plan 總組裝與全量合規驗證 (build_dplan)...")
    final_file = assemble_dplan(
        target_date=t_date,
        trade_date_override=final_trade_date,
        team_id_override=team_id,
    )

    # -------------------------------------------------------------------------
    # Step 7: 每日投資決策與投資組合回顧報告生成 (真人回顧報告)
    # -------------------------------------------------------------------------
    if not skip_report:
        print("\n>>> [Step 7/7] 產生每日投資決策與投資組合回顧 Markdown 報告...")
        try:
            _, report_file = build_daily_report(target_date=t_date, dplan_path=final_file)
            print(f" -> 決策回顧報告已產出：{report_file}")
        except Exception as exc:
            print(f" ⚠️ 決策回顧報告產出遇到警示: {exc} (主 D-Plan 檔案已順利產出)")
    else:
        print("\n>>> [Step 7/7] 跳過每日決策回顧報告產出")

    print("\n" + "=" * 80)
    print(f" 🎉 [Pipeline 成功完成] 每日自動化產線全部成功！")
    print(f" -> 最終繳交檔: {final_file}")
    if not skip_report:
        print(f" -> 決策回顧報告: {REPORT_DIR / f'Daily_Decision_Report_{t_date}.md'}")
    print("=" * 80 + "\n")
    return final_file


def main():
    parser = argparse.ArgumentParser(description="每日排程執行的 D-Plan 端到端主程式")
    parser.add_argument("--date", type=str, default=None, help="指定資料日期 (格式 YYYYMMDD)")
    parser.add_argument("--trade-date", type=str, default=None, help="指定 D-Plan 交易日 (格式 YYYY-MM-DD)")
    parser.add_argument("--team-id", type=str, default="TEAM_11402", help="指定隊伍代號 (預設 TEAM_11402)")
    parser.add_argument("--skip-l0", action="store_true", help="跳過 L0 資料收集步驟")
    parser.add_argument("--skip-l1", action="store_true", help="跳過 L1 事實提取步驟")
    parser.add_argument("--skip-l2m", action="store_true", help="跳過 L2M 市場判斷步驟")
    parser.add_argument("--skip-l2", action="store_true", help="跳過 L2 個股推論步驟")
    parser.add_argument("--skip-l3", action="store_true", help="跳過 L3 組合決策步驟")
    parser.add_argument("--skip-l4", action="store_true", help="跳過 L4 委託單步驟")
    parser.add_argument("--skip-report", action="store_true", help="跳過產生 Markdown 回顧報告步驟")
    args = parser.parse_args()

    run_pipeline(
        target_date=args.date,
        trade_date=args.trade_date,
        team_id=args.team_id,
        skip_l0=args.skip_l0,
        skip_l1=args.skip_l1,
        skip_l2m=args.skip_l2m,
        skip_l2=args.skip_l2,
        skip_l3=args.skip_l3,
        skip_l4=args.skip_l4,
        skip_report=args.skip_report,
    )


if __name__ == "__main__":
    main()
