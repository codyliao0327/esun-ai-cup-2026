"""玉山 AI 挑戰賽 D-Plan 官方後台正式繳交工具。

透過 EsunChallengeClient 的 OAuth2 SSO 與 CSRF Token，將
`data/D-Paln_Output/final_dplan/` 內的 D-Plan JSON 上傳至官方正式繳交端點：
  POST https://fundaiagent.esun-ai-challenge.tw/api/submissions/dplan/

並嚴格確認 HTTP 狀態碼與回傳 JSON 內容確實代表「繳交成功」，否則以非零狀態碼中止流程。

用法：
    python submit_dplan_api.py                       # 自動挑選最新一份 D-Plan JSON 正式繳交
    python submit_dplan_api.py --date 20261116       # 指定交易日繳交
    python submit_dplan_api.py --file path/to.json   # 指定檔案繳交
    python submit_dplan_api.py --dry-run             # 僅檢查檔案與登入連線，不實際送出繳交 POST
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

CODE_DIR = Path(__file__).resolve().parent
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from L0_sources.backend_history_loader import EsunChallengeClient, _load_env_file  # noqa: E402
from validate_dplan_api import resolve_dplan_file  # noqa: E402

SUBMIT_URL = f"{EsunChallengeClient.BASE_SUB}/api/submissions/dplan/"


def is_submission_succeeded(status_code: int, result: Any) -> Tuple[bool, str]:
    """驗證官方正式繳交端點之回傳狀態與內容是否確實成功。

    Returns:
        (succeeded, reason_message)
    """
    if not (200 <= status_code < 300):
        return False, f"HTTP 狀態碼非 2xx（HTTP {status_code}）"

    if not isinstance(result, dict) or "raw_text" in result:
        return False, "回應非預期之 JSON 物件格式"

    if result.get("ok") is False or ("ok" in result and result.get("ok") is not True):
        return False, f"回傳 ok={result.get('ok')}"

    if "success" in result and result.get("success") is not True:
        return False, f"回傳 success={result.get('success')}"

    if result.get("error") or result.get("errors"):
        return False, f"回傳包含錯誤訊息：{result.get('error') or result.get('errors')}"

    if result.get("checks") or result.get("missing"):
        return False, "回傳包含未通過之 checks 或 missing 欄位"

    status_val = str(result.get("status", "")).strip().lower()
    if status_val in ("error", "failed", "fail", "rejected", "invalid"):
        return False, f"回傳 status={result.get('status')}"

    counts = result.get("counts") or {}
    if isinstance(counts, dict) and int(counts.get("bad", 0)) > 0:
        return False, f"回傳 counts.bad={counts.get('bad')}，繳交檢核未通過"

    has_receipt = (
        result.get("id") is not None
        or status_val in ("received", "accepted", "success", "ok")
        or bool((result.get("stored") or {}).get("gcs_path"))
    )
    if not has_receipt:
        return False, "回應缺少繳交收據欄位（id / status=received / stored.gcs_path）"

    return True, "HTTP 2xx 且已取得官方收據（status=received / id / stored）"


def format_submission_report(status_code: int, result: Any, succeeded: bool, reason: str) -> None:
    """以精簡可讀格式印出官方正式繳交結果（需看原始 JSON 可加 --raw）。"""
    icon = "✅" if succeeded else "❌"
    print("\n" + "=" * 68)
    print(f"{icon} 官方 D-Plan 正式繳交結果 (HTTP {status_code} | 狀態={'成功' if succeeded else '失敗'})")
    if isinstance(result, dict):
        sub_id = result.get("id")
        sub_status = result.get("status")
        attempt_no = result.get("attempt_no")
        remaining = result.get("attempts_remaining")
        submitted_at = result.get("submitted_at")

        meta_parts = []
        if sub_id is not None:
            meta_parts.append(f"繳交編號 #{sub_id}")
        if sub_status:
            meta_parts.append(f"後台狀態={sub_status}")
        if attempt_no is not None:
            meta_parts.append(f"第 {attempt_no} 次繳交")
        if remaining is not None:
            meta_parts.append(f"今日剩餘次數 {remaining}")
        if meta_parts:
            print(f"   摘要：{' | '.join(meta_parts)}")
        if submitted_at:
            print(f"   時間：{submitted_at}")

        counts = result.get("counts")
        if isinstance(counts, dict):
            print(
                f"   統計：❌ bad={counts.get('bad', 0)} | "
                f"⚠️ warn={counts.get('warn', 0)} | "
                f"✅ pass={counts.get('pass', 0)} | "
                f"⏭️ skipped={counts.get('skipped', 0)}"
            )
    if not succeeded:
        print(f"   失敗原因：{reason}")
        if isinstance(result, dict):
            err_msg = result.get("detail") or result.get("error") or result.get("errors") or result.get("message") or result.get("msg")
            if err_msg:
                print(f"   後台訊息：{err_msg}")
    print("=" * 68 + "\n")


def submit_dplan(
    dplan_json_path: Path,
    dry_run: bool = False,
    raw_output: bool = False,
) -> Dict[str, Any]:
    """登入後台並將 D-Plan JSON 上傳至官方正式繳交端點，驗證是否確實繳交成功。"""
    _load_env_file(CODE_DIR / ".env")
    email = os.getenv("ESUN_EMAIL", "").strip()
    password = os.getenv("ESUN_PASSWORD", "").strip()
    if not email or not password:
        raise RuntimeError("找不到 ESUN_EMAIL 或 ESUN_PASSWORD 環境變數！請於 code/.env 中設定。")

    dplan_payload = json.loads(dplan_json_path.read_text(encoding="utf-8"))
    trade_date = dplan_payload.get("trade_date")

    client = EsunChallengeClient(email=email, password=password)
    client.login()

    if dry_run:
        print(f"🧪 [Dry-Run] 已完成登入驗證與檔案讀取：{dplan_json_path.name}（交易日：{trade_date}），未實際送出 POST 繳交請求。")
        return {
            "status_code": 0,
            "result": {"dry_run": True, "trade_date": trade_date},
            "file": str(dplan_json_path),
            "succeeded": True,
            "reason": "Dry-Run 模式跳過實際送出",
        }

    print(f"🚀 正在正式繳交 D-Plan 至官方後台：{dplan_json_path.name}（交易日：{trade_date}）...")
    resp = client._post_json_with_csrf(SUBMIT_URL, payload=dplan_payload, timeout=30)

    try:
        result = resp.json()
    except ValueError:
        result = {"raw_text": resp.text}

    succeeded, reason = is_submission_succeeded(resp.status_code, result)

    if raw_output:
        print(f"📋 繳交回應（HTTP {resp.status_code}）：\n{json.dumps(result, ensure_ascii=False, indent=2)}")
    else:
        format_submission_report(resp.status_code, result, succeeded, reason)

    return {
        "status_code": resp.status_code,
        "result": result,
        "file": str(dplan_json_path),
        "succeeded": succeeded,
        "reason": reason,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="玉山 AI 挑戰賽 D-Plan 官方後台正式繳交工具")
    parser.add_argument("--file", type=str, default=None, help="指定 D-Plan JSON 檔案路徑")
    parser.add_argument("--date", type=str, default=None, help="指定交易日期 (格式 YYYYMMDD 或 YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="僅測試登入與讀取檔案，不實際送出 POST 繳交請求")
    parser.add_argument("--raw", action="store_true", help="印出完整原始 JSON 回應")
    args = parser.parse_args()

    target_file = resolve_dplan_file(file_path=args.file, target_date=args.date)
    res = submit_dplan(target_file, dry_run=args.dry_run, raw_output=args.raw)
    if not res["succeeded"]:
        print(f"❌ 官方 D-Plan 正式繳交失敗：{res['reason']}")
        sys.exit(1)
    if not args.dry_run:
        print("🎉 官方 D-Plan 正式繳交成功！")


if __name__ == "__main__":
    main()
