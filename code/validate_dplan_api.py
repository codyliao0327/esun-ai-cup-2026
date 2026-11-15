"""玉山 AI 挑戰賽 D-Plan 官方線上預檢核工具 (獨立測試版，尚未接入自動化產線)。

透過 EsunChallengeClient 的 OAuth2 SSO 與 CSRF Token，將
`data/D-Paln_Output/final_dplan/` 內的 D-Plan JSON 上傳至官方預檢核端點：
  POST https://fundaiagent.esun-ai-challenge.tw/api/submissions/dplan/validate/

用法：
    python validate_dplan_api.py                       # 自動挑選最新一份 D-Plan JSON 檢核
    python validate_dplan_api.py --date 20261113       # 指定日期檢核
    python validate_dplan_api.py --file path/to.json   # 指定檔案檢核
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

CODE_DIR = Path(__file__).resolve().parent
ROOT = CODE_DIR.parent
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from configs.date_utils import format_iso_trade_date  # noqa: E402
from L0_sources.backend_history_loader import EsunChallengeClient, _load_env_file  # noqa: E402

FINAL_DPLAN_DIR = ROOT / "data" / "D-Paln_Output" / "final_dplan"
VALIDATE_URL = f"{EsunChallengeClient.BASE_SUB}/api/submissions/dplan/validate/"


def resolve_dplan_file(file_path: Optional[str] = None, target_date: Optional[str] = None) -> Path:
    """決定要進行官方預檢核的 D-Plan JSON 檔案路徑。"""
    if file_path:
        p = Path(file_path)
        if not p.is_file():
            raise FileNotFoundError(f"找不到指定的 D-Plan 檔案：{p}")
        return p

    if not FINAL_DPLAN_DIR.exists():
        raise FileNotFoundError(f"找不到 final_dplan 目錄：{FINAL_DPLAN_DIR}")

    if target_date:
        iso_date = format_iso_trade_date(target_date)
        matches = sorted(FINAL_DPLAN_DIR.glob(f"D-Plan_*_{iso_date}.json"))
        if not matches:
            raise FileNotFoundError(f"在 {FINAL_DPLAN_DIR} 找不到日期為 {iso_date} 的 D-Plan 檔案")
        return matches[-1]

    all_files = sorted(FINAL_DPLAN_DIR.glob("D-Plan_*.json"))
    if not all_files:
        raise FileNotFoundError(f"在 {FINAL_DPLAN_DIR} 找不到任何 D-Plan_*.json 檔案")
    return all_files[-1]


def format_validation_report(status_code: int, result: Dict[str, Any]) -> None:
    """以精簡可讀格式印出官方預檢核結果（依 level / state 彙整未通過項目）。"""
    ok = result.get("ok")
    expected_dt = result.get("expected_trade_date") or "--"
    audit = result.get("audit") or {}
    counts = audit.get("counts") or {}

    print("\n" + "=" * 68)
    print(f"📋 官方預檢核結果 (HTTP {status_code} | ok={ok} | 預期交易日={expected_dt})")
    if counts:
        print(
            f"   統計：❌ bad={counts.get('bad', 0)} | "
            f"⚠️ warn={counts.get('warn', 0)} | "
            f"✅ pass={counts.get('pass', 0)} | "
            f"⏭️ skipped={counts.get('skipped', 0)}"
        )
    print("=" * 68)

    # 1. 格式 / Schema 基本檢查 (top-level checks / missing)
    top_checks = result.get("checks") or []
    if top_checks:
        print(f"\n❌ [格式/基礎檢查] {len(top_checks)} 項異常：")
        for idx, chk in enumerate(top_checks, start=1):
            if isinstance(chk, dict):
                code = chk.get("code") or chk.get("field") or ""
                msg = chk.get("msg") or chk.get("message") or json.dumps(chk, ensure_ascii=False)
                print(f"  {idx}. [{code}] {msg}" if code else f"  {idx}. {msg}")
            else:
                print(f"  {idx}. {chk}")

    missing = result.get("missing") or []
    if missing:
        print(f"\n⚠️ [缺少資料] {', '.join(str(m) for m in missing)}")

    # 2. 規則與稽核分組 (audit.groups，涵蓋 level 如「交易規則」、「警告」等，state 如 bad / warn)
    groups = audit.get("groups") or []
    has_issues = bool(top_checks or missing)

    for grp in groups:
        grp_name = grp.get("group") or "未分類"
        level = grp.get("level") or "未標示"
        checks = grp.get("checks") or []
        flagged = [c for c in checks if str(c.get("state", "")).lower() in ("bad", "warn")]
        if not flagged:
            continue

        has_issues = True
        bad_cnt = sum(1 for c in flagged if str(c.get("state", "")).lower() == "bad")
        warn_cnt = sum(1 for c in flagged if str(c.get("state", "")).lower() == "warn")
        icon = "❌" if bad_cnt > 0 else "⚠️"
        summary_parts = []
        if bad_cnt:
            summary_parts.append(f"bad {bad_cnt} 項")
        if warn_cnt:
            summary_parts.append(f"warn {warn_cnt} 項")

        print(f"\n{icon} 【{level} / {grp_name}】共 {len(flagged)} 項未通過（{', '.join(summary_parts)}）：")
        for idx, c in enumerate(flagged, start=1):
            state = str(c.get("state", "")).upper()
            label = c.get("label") or c.get("code") or "未命名檢查"
            code = c.get("code") or ""
            blocking = " [阻擋繳交]" if c.get("blocking") else ""
            msg = c.get("msg") or ""
            print(f"  {idx}. [{state}]{blocking} {label} ({code})")
            if msg:
                print(f"     ↳ {msg}")

    if not has_issues:
        if audit.get("audit_skipped_reason"):
            print(f"\nℹ️ 稽核略過原因：{audit['audit_skipped_reason']}")
        elif ok:
            print("\n✅ 全部檢核項目通過，無任何 bad / warn！")
        else:
            print(f"\n⚠️ 回應異常：{json.dumps(result, ensure_ascii=False, indent=2)}")

    print()


def is_validation_passed(
    status_code: int,
    result: Dict[str, Any],
    allow_warn: bool = False,
) -> bool:
    """判定官方預檢核是否完全通過（預設嚴格要求無 bad、無 warn、無格式錯誤）。"""
    if not (200 <= status_code < 300):
        return False
    if result.get("ok") is not True:
        return False
    if result.get("checks") or result.get("missing"):
        return False

    audit = result.get("audit") or {}
    counts = audit.get("counts") or {}
    if int(counts.get("bad", 0)) > 0:
        return False
    if not allow_warn and int(counts.get("warn", 0)) > 0:
        return False

    for grp in audit.get("groups") or []:
        for chk in grp.get("checks") or []:
            state = str(chk.get("state", "")).lower()
            if state == "bad" or (not allow_warn and state == "warn"):
                return False
    return True


def validate_dplan(
    dplan_json_path: Path,
    raw_output: bool = False,
    allow_warn: bool = False,
) -> Dict[str, Any]:
    """登入後台並上傳 D-Plan JSON 至官方預檢核端點，回傳狀態碼、檢核結果與是否通過。"""
    _load_env_file(CODE_DIR / ".env")
    email = os.getenv("ESUN_EMAIL", "").strip()
    password = os.getenv("ESUN_PASSWORD", "").strip()
    if not email or not password:
        raise RuntimeError("找不到 ESUN_EMAIL 或 ESUN_PASSWORD 環境變數！請於 code/.env 中設定。")

    dplan_payload = json.loads(dplan_json_path.read_text(encoding="utf-8"))

    client = EsunChallengeClient(email=email, password=password)
    client.login()

    print(f"📤 正在上傳 D-Plan 進行官方預檢核：{dplan_json_path.name}（交易日：{dplan_payload.get('trade_date')}）...")
    resp = client._post_json_with_csrf(VALIDATE_URL, payload=dplan_payload, timeout=30)

    try:
        result = resp.json()
    except ValueError:
        result = {"raw_text": resp.text}

    if raw_output:
        print(f"📋 檢核回應（HTTP {resp.status_code}）：\n{json.dumps(result, ensure_ascii=False, indent=2)}")
    else:
        format_validation_report(resp.status_code, result)

    passed = is_validation_passed(resp.status_code, result, allow_warn=allow_warn)
    return {
        "status_code": resp.status_code,
        "result": result,
        "file": str(dplan_json_path),
        "passed": passed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="玉山 AI 挑戰賽 D-Plan 官方預檢核工具")
    parser.add_argument("--file", type=str, default=None, help="指定 D-Plan JSON 檔案路徑")
    parser.add_argument("--date", type=str, default=None, help="指定交易日期 (格式 YYYYMMDD 或 YYYY-MM-DD)")
    parser.add_argument("--raw", action="store_true", help="印出完整原始 JSON 回應")
    parser.add_argument("--allow-warn", action="store_true", help="僅在出現 bad 時視為不通過（允許 warn 通過）")
    args = parser.parse_args()

    target_file = resolve_dplan_file(file_path=args.file, target_date=args.date)
    res = validate_dplan(target_file, raw_output=args.raw, allow_warn=args.allow_warn)
    if not res["passed"]:
        print("❌ 官方預檢核未通過，已中止流程（不進行後續繳交）。")
        sys.exit(1)
    print("✅ 官方預檢核完全通過！")


if __name__ == "__main__":
    main()
