"""【D-Plan 總組裝與全量合規檢驗程式】(build_dplan.py)。

依據 D-Plan Schema v4.3 與 D-Plan 撰寫指南 v4.3 規範：
1. 從 data/D-Paln_Output/ 各子目錄讀入對應日期的產出檔：
   - L0 sources:          data/D-Paln_Output/l0_sources/
   - L1 observations:     data/D-Paln_Output/l1_observations/
   - L2M market_view:     data/D-Paln_Output/l2m_market_view/
   - L2 inferences:       data/D-Paln_Output/l2_inferences/
   - L3 decisions:        data/D-Paln_Output/l3_decisions/
   - L4 orders:           data/D-Paln_Output/l4_orders/
2. 自動注入頂層欄位與架構 (Root Properties)：
   - schema_version: "4.3"
   - doc_type: "D-Plan"
   - team_id: "TEAM_11402" (可自訂)
   - trade_date: YYYY-MM-DD (可自動或手動指定)
3. 自動收集並注入底層 Agent 元資料 (agent_metadata)：
   - model_provider: "google"
   - model_version: 透過 GeminiClient 取得確切模型版本
   - run_started_at: 讀取 l0_sources 檔案建立時間 (+08:00)
   - run_completed_at: 當前完成時間戳記 (+08:00)
   - code_version: 自動抓取 git commit hash (如 git:fbb03c6)
4. 透過 Pydantic DPlanDocument 進行全量 Schema 與上下層因果引用鏈嚴格驗證 (extra='forbid')。
5. 產出正式競賽格式檔案至 data/D-Paln_Output/final_dplan/D-Plan_<team_id>_<trade_date>.json。

用法::

    python build_dplan.py                                    # 自動組裝最新日期
    python build_dplan.py --date 20261027                   # 指定輸入日期
    python build_dplan.py --trade-date 2026-10-27           # 指定 D-Plan 交易日
    python build_dplan.py --team-id TEAM_11402              # 指定隊伍代號
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# 設定 code/ 為匯入路徑
CODE_DIR = Path(__file__).resolve().parent
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from configs.date_utils import prompt_trade_date  # noqa: E402
from configs.gemini_client import GeminiClient  # noqa: E402
from schemas.dplan_models import (  # noqa: E402
    AgentMetadata,
    DPlanDocument,
    Decision,
    Inference,
    MarketView,
    NoTradeDecision,
    Observation,
    Order,
    Source,
)

ROOT = CODE_DIR.parent
DATA_ROOT = ROOT / "data"
OUTPUT_BASE = DATA_ROOT / "D-Paln_Output"

L0_DIR = OUTPUT_BASE / "l0_sources"
L1_DIR = OUTPUT_BASE / "l1_observations"
L2M_DIR = OUTPUT_BASE / "l2m_market_view"
L2_DIR = OUTPUT_BASE / "l2_inferences"
L3_DIR = OUTPUT_BASE / "l3_decisions"
L4_DIR = OUTPUT_BASE / "l4_orders"
FINAL_DPLAN_DIR = OUTPUT_BASE / "final_dplan"

TW_TZ = timezone(timedelta(hours=8))
DEFAULT_TEAM_ID = "TEAM_11402"


# =============================================================================
# 檔案輔助工具
# =============================================================================
def _clean_date_str(date_str: str) -> str:
    """標準化日期字串為 YYYYMMDD。"""
    return re.sub(r"\D", "", date_str)


def _format_trade_date(date_str: str) -> str:
    """將 YYYYMMDD 格式化為 YYYY-MM-DD。"""
    c = _clean_date_str(date_str)
    if len(c) == 8:
        return f"{c[:4]}-{c[4:6]}-{c[6:]}"
    return date_str


def find_latest_file(directory: Path, pattern: str) -> Optional[Path]:
    """在指定目錄尋找符合條件且日期最新的一個檔案。"""
    if not directory.exists():
        return None
    matched = list(directory.glob(pattern))
    if not matched:
        return None

    def _extract_date(p: Path) -> str:
        m = re.findall(r"\d{8}", p.name)
        if m:
            return m[-1]
        m2 = re.findall(r"\d{4}-\d{2}-\d{2}", p.name)
        if m2:
            return m2[-1].replace("-", "")
        return ""

    matched_sorted = sorted(matched, key=lambda p: (_extract_date(p), p.stat().st_mtime))
    return matched_sorted[-1]


def get_git_code_version() -> str:
    """自動取得當前 git 短 commit hash 作為 code_version。"""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(CODE_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            timeout=5,
        )
        commit = res.stdout.strip()
        if commit:
            return f"git:{commit}"
    except Exception:
        pass
    return "git:main"


def get_model_version() -> str:
    """動態取得 Gemini 模型確切名稱。"""
    try:
        client = GeminiClient()
        return client.default_model
    except Exception:
        return "gemini-2.5-flash"


# =============================================================================
# 各層資料讀取器
# =============================================================================
def load_l0_sources(target_date: str) -> Tuple[List[Dict[str, Any]], datetime]:
    """讀入 L0 sources 並傳回最早檔案時間作為 run_started_at。"""
    c_date = _clean_date_str(target_date)
    earliest_time = datetime.now(TW_TZ)

    # 1. 優先嘗試 l0_sources_YYYYMMDD.json
    single_file = L0_DIR / f"l0_sources_{c_date}.json"
    if single_file.exists():
        earliest_time = datetime.fromtimestamp(single_file.stat().st_ctime, tz=TW_TZ)
        with open(single_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else data.get("sources", []), earliest_time

    # 2. 搜尋子檔案 (例如 s1_*.json, s2_*.json)
    matched = list(L0_DIR.glob(f"*{c_date}*.json")) if L0_DIR.exists() else []
    if not matched and L0_DIR.exists():
        matched = list(L0_DIR.glob("*.json"))

    if not matched:
        raise FileNotFoundError(f"找不到 L0 sources 來源檔案，搜尋目錄：{L0_DIR}")

    all_sources: List[Dict[str, Any]] = []
    seen_ids = set()
    timestamps = []

    for p in sorted(matched):
        timestamps.append(p.stat().st_mtime)
        try:
            with open(p, "r", encoding="utf-8") as f:
                content = json.load(f)
                items = content if isinstance(content, list) else [content]
                for item in items:
                    sid = item.get("source_id")
                    if sid and sid not in seen_ids:
                        all_sources.append(item)
                        seen_ids.add(sid)
        except Exception as e:
            print(f"[Warn] 讀取 L0 檔案 {p} 失敗: {e}")

    if timestamps:
        earliest_time = datetime.fromtimestamp(min(timestamps), tz=TW_TZ)

    # 依 S1, S2 排序
    def _sort_key(s: Dict[str, Any]) -> int:
        sid = s.get("source_id", "S999")
        m = re.findall(r"\d+", sid)
        return int(m[0]) if m else 999

    all_sources.sort(key=_sort_key)
    return all_sources, earliest_time


def load_l1_observations(target_date: str) -> List[Dict[str, Any]]:
    """讀入 L1 observations。"""
    c_date = _clean_date_str(target_date)
    exact = L1_DIR / f"l1_observations_{c_date}.json"
    target = exact if exact.exists() else find_latest_file(L1_DIR, "l1_observations_*.json")
    if not target or not target.exists():
        raise FileNotFoundError(f"找不到 L1 observations 檔案：{L1_DIR}")

    with open(target, "r", encoding="utf-8") as f:
        data = json.load(f)
        return data if isinstance(data, list) else data.get("observations", [])


def load_l2m_market_view(target_date: str) -> Dict[str, Any]:
    """讀入 L2M market_view。"""
    c_date = _clean_date_str(target_date)
    exact = L2M_DIR / f"l2m_market_view_{c_date}.json"
    target = exact if exact.exists() else find_latest_file(L2M_DIR, "l2m_market_view_*.json")
    if not target or not target.exists():
        raise FileNotFoundError(f"找不到 L2M market_view 檔案：{L2M_DIR}")

    with open(target, "r", encoding="utf-8") as f:
        data = json.load(f)
        return data.get("market_view", data)


def load_l2_inferences(target_date: str) -> List[Dict[str, Any]]:
    """讀入 L2 inferences。"""
    c_date = _clean_date_str(target_date)
    exact = L2_DIR / f"l2_inferences_{c_date}.json"
    target = exact if exact.exists() else find_latest_file(L2_DIR, "l2_inferences_*.json")
    if not target or not target.exists():
        raise FileNotFoundError(f"找不到 L2 inferences 檔案：{L2_DIR}")

    with open(target, "r", encoding="utf-8") as f:
        data = json.load(f)
        return data if isinstance(data, list) else data.get("inferences", [])


def load_l3_decisions(target_date: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """讀入 L3 decisions 與 no_trade_decisions。"""
    c_date = _clean_date_str(target_date)
    exact = L3_DIR / f"l3_decisions_{c_date}.json"
    target = exact if exact.exists() else find_latest_file(L3_DIR, "l3_decisions_*.json")
    if not target or not target.exists():
        raise FileNotFoundError(f"找不到 L3 decisions 檔案：{L3_DIR}")

    with open(target, "r", encoding="utf-8") as f:
        data = json.load(f)
        return data.get("decisions", []), data.get("no_trade_decisions", [])


def load_l4_orders(target_date: str) -> List[Dict[str, Any]]:
    """讀入 L4 orders。"""
    c_date = _clean_date_str(target_date)
    exact = L4_DIR / f"l4_orders_{c_date}.json"
    target = exact if exact.exists() else find_latest_file(L4_DIR, "l4_orders_*.json")
    if not target or not target.exists():
        raise FileNotFoundError(f"找不到 L4 orders 檔案：{L4_DIR}")

    with open(target, "r", encoding="utf-8") as f:
        data = json.load(f)
        orders = data.get("orders", data if isinstance(data, list) else [])
        # 移除任何非官方規格自訂欄位 (若有殘留)
        clean_orders = []
        for o in orders:
            item = {
                "ticker": str(o["ticker"]).strip(),
                "side": o["side"],
                "shares": int(o["shares"]),
                "decision_ref": str(o["decision_ref"]).strip(),
            }
            if "derivation_detail" in o and o["derivation_detail"]:
                item["derivation_detail"] = o["derivation_detail"]
            clean_orders.append(item)
        return clean_orders


# =============================================================================
# 主組裝流程
# =============================================================================
def assemble_dplan(
    target_date: Optional[str] = None,
    trade_date_override: Optional[str] = None,
    team_id_override: Optional[str] = None,
    output_dir: Optional[Path] = None,
) -> Path:
    """執行全階層 D-Plan 合併組裝、驗證與產出。"""
    now_dt = datetime.now(TW_TZ)
    now_str = now_dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")

    t_date = target_date or now_dt.strftime("%Y%m%d")
    c_date = _clean_date_str(t_date)
    trade_date = trade_date_override or _format_trade_date(c_date)
    team_id = team_id_override or DEFAULT_TEAM_ID

    out_dir = output_dir or FINAL_DPLAN_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*70}")
    print(f" [D-Plan Assembler] 啟動 D-Plan 全量組裝與合規驗證程序")
    print(f" 交易日 (trade_date): {trade_date} | 隊伍 ID (team_id): {team_id}")
    print(f"{'='*70}\n")

    # 1. 載入各層資料
    sources_data, started_dt = load_l0_sources(c_date)
    observations_data = load_l1_observations(c_date)
    market_view_data = load_l2m_market_view(c_date)
    inferences_data = load_l2_inferences(c_date)
    decisions_data, no_trades_data = load_l3_decisions(c_date)
    orders_data = load_l4_orders(c_date)

    run_started_at_str = started_dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    code_ver = get_git_code_version()
    model_ver = get_model_version()

    print(f"[Assembler] L0 來源筆數:        {len(sources_data):>2} 筆")
    print(f"[Assembler] L1 事實筆數:        {len(observations_data):>2} 筆")
    print(f"[Assembler] L2M 市場判斷鏈:      已載入 (regime: {market_view_data.get('regime')}, stance: {market_view_data.get('stance')})")
    print(f"[Assembler] L2 個股推論筆數:    {len(inferences_data):>2} 筆")
    print(f"[Assembler] L3 異動決策筆數:    {len(decisions_data):>2} 筆 | 續抱決策: {len(no_trades_data):>2} 筆")
    print(f"[Assembler] L4 委託單筆數:      {len(orders_data):>2} 筆")
    print(f"[Assembler] 程式碼版本識別:      {code_ver}")
    print(f"[Assembler] 模型版本名稱:        {model_ver}")
    print(f"[Assembler] 開始時刻 (L0):       {run_started_at_str}")
    print(f"[Assembler] 完成時刻:            {now_str}\n")

    # 2. 組裝 agent_metadata (嚴格不放未定義欄位)
    agent_metadata_payload = {
        "model_provider": "google",
        "model_version": model_ver,
        "run_started_at": run_started_at_str,
        "run_completed_at": now_str,
        "code_version": code_ver,
    }

    # 3. 組裝完整 D-Plan Payload
    full_payload = {
        "schema_version": "4.3",
        "doc_type": "D-Plan",
        "team_id": team_id,
        "trade_date": trade_date,
        "sources": sources_data,
        "observations": observations_data,
        "market_view": market_view_data,
        "inferences": inferences_data,
        "decisions": decisions_data,
        "no_trade_decisions": no_trades_data,
        "orders": orders_data,
        "agent_metadata": agent_metadata_payload,
    }

    # 4. 透過 Pydantic DPlanDocument 執行嚴格合規校驗 (全層引用鏈與格式驗證)
    print(f"{'-'*70}")
    print(f"[Assembler] 正在透過 Pydantic 進行 D-Plan v4.3 全量 Schema 與因果引用鏈檢核...")
    try:
        validated_doc = DPlanDocument(**full_payload)
        print(f"[Assembler] [PASS] 全量校驗完全通過！無斷鏈、無孤兒引用、無違反格式、無自訂額外欄位。")
    except Exception as e:
        print(f"\n[Assembler ERROR] [FAIL] 合規校驗未通過！詳細錯誤如下：\n{e}\n")
        raise

    # 5. 輸出正式 D-Plan JSON 檔案
    out_filename = f"D-Plan_{team_id}_{trade_date}.json"
    primary_out_path = out_dir / out_filename
    with open(primary_out_path, "w", encoding="utf-8") as f:
        f.write(validated_doc.model_dump_json(indent=2, exclude_none=True))

    print(f"{'-'*70}")
    print(f"[Assembler] 成功產出正式 D-Plan 檔案至：")
    print(f" -> {primary_out_path}")
    print(f"{'='*70}\n")

    return primary_out_path


# =============================================================================
# CLI 命令列入口
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description="【D-Plan 總組裝與全量合規檢驗程式】")
    parser.add_argument("--date", type=str, default=None, help="輸入資料日期 (例如 20261027 或 2026-10-27)")
    parser.add_argument("--trade-date", type=str, default=None, help="手動指定 D-Plan 交易日 (格式 YYYY-MM-DD)")
    parser.add_argument("--team-id", type=str, default=None, help="指定隊伍代號 (預設 TEAM_11402)")
    parser.add_argument("--output-dir", type=str, default=None, help="指定輸出目錄 (預設 data/D-Paln_Output/final_dplan)")
    args = parser.parse_args()

    # 取得交易日期 (若無命令列參數則在終端機提示輸入)
    target_date = prompt_trade_date(args.date, prompt_text="D-Plan 總組裝 - 輸入資料日期")

    assemble_dplan(
        target_date=target_date,
        trade_date_override=args.trade_date,
        team_id_override=args.team_id,
        output_dir=Path(args.output_dir) if args.output_dir else None,
    )


if __name__ == "__main__":
    main()
