"""每日排程執行的 D-Plan 自動化端到端主程式入口。

執行順序：
  Step 1: L2M 市場整體判斷 (market_view_agent)
  Step 2: L2 個股推論 (stock_inference_agent)
  Step 3: L3 投資組合配置決策 (portfolio_decision_agent)
  Step 4: L4 官方演算法委託單計算與智能覆核 (order_calculator)
  Step 5: 總組裝與全量合規校驗 (build_dplan) -> 產出 D-Plan_<team_id>_<trade_date>.json
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

TW_TZ = timezone(timedelta(hours=8))
PYTHON_EXE = sys.executable


def _run_substage(script_relpath: str, args_list: list[str]) -> bool:
    """透過獨立子進程執行單一 Agent 階段。"""
    script_path = CODE_DIR / script_relpath
    cmd = [PYTHON_EXE, str(script_path)] + args_list
    print(f" -> 執行指令: {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=str(CODE_DIR))
    if res.returncode != 0:
        raise RuntimeError(f"階段 {script_relpath} 執行失敗 (returncode={res.returncode})")
    return True


def run_pipeline(
    target_date: str = None,
    trade_date: str = None,
    team_id: str = "TEAM_11402",
    skip_l2m: bool = False,
    skip_l2: bool = False,
    skip_l3: bool = False,
    skip_l4: bool = False,
):
    """一鍵執行每日 D-Plan 端到端完整生成流程。"""
    t_date = target_date or datetime.now(TW_TZ).strftime("%Y%m%d")

    print("\n" + "=" * 75)
    print(f" [D-Plan Pipeline] 啟動每日端到端自動化產線 (日期: {t_date}, 隊伍: {team_id})")
    print("=" * 75)

    # 1. L2M Market View
    if not skip_l2m:
        print("\n>>> [Step 1/5] 執行 L2M 市場整體判斷 Agent...")
        _run_substage("L2M_market_view/market_view_agent.py", ["--date", t_date])
    else:
        print("\n>>> [Step 1/5] 跳過 L2M (使用既有快照)")

    # 2. L2 Inferences
    if not skip_l2:
        print("\n>>> [Step 2/5] 執行 L2 個股推論 Agent...")
        _run_substage("L2_inferences/stock_inference_agent.py", ["--date", t_date])
    else:
        print("\n>>> [Step 2/5] 跳過 L2 (使用既有快照)")

    # 3. L3 Decisions
    if not skip_l3:
        print("\n>>> [Step 3/5] 執行 L3 投資組合決策 Agent...")
        _run_substage("L3_decisions/portfolio_decision_agent.py", ["--date", t_date])
    else:
        print("\n>>> [Step 3/5] 跳過 L3 (使用既有快照)")

    # 4. L4 Orders
    if not skip_l4:
        print("\n>>> [Step 4/5] 執行 L4 委託單計算與智能覆核 Agent...")
        _run_substage("L4_orders/order_calculator.py", ["--date", t_date])
    else:
        print("\n>>> [Step 4/5] 跳過 L4 (使用既有快照)")

    # 5. D-Plan Assembler & Validator
    print("\n>>> [Step 5/5] 執行 D-Plan 總組裝與全量合規驗證...")
    final_file = assemble_dplan(
        target_date=t_date,
        trade_date_override=trade_date,
        team_id_override=team_id,
    )

    print("\n" + "=" * 75)
    print(f" [Pipeline 成功完成] 最終繳交檔已產出：\n -> {final_file}")
    print("=" * 75 + "\n")
    return final_file


def main():
    parser = argparse.ArgumentParser(description="每日排程執行的 D-Plan 端到端主程式")
    parser.add_argument("--date", type=str, default=None, help="指定資料日期 (格式 YYYYMMDD)")
    parser.add_argument("--trade-date", type=str, default=None, help="指定 D-Plan 交易日 (格式 YYYY-MM-DD)")
    parser.add_argument("--team-id", type=str, default="TEAM_11402", help="指定隊伍代號 (預設 TEAM_11402)")
    parser.add_argument("--skip-l2m", action="store_true", help="跳過 L2M 步驟")
    parser.add_argument("--skip-l2", action="store_true", help="跳過 L2 步驟")
    parser.add_argument("--skip-l3", action="store_true", help="跳過 L3 步驟")
    parser.add_argument("--skip-l4", action="store_true", help="跳過 L4 步驟")
    args = parser.parse_args()

    run_pipeline(
        target_date=args.date,
        trade_date=args.trade_date,
        team_id=args.team_id,
        skip_l2m=args.skip_l2m,
        skip_l2=args.skip_l2,
        skip_l3=args.skip_l3,
        skip_l4=args.skip_l4,
    )


if __name__ == "__main__":
    main()
