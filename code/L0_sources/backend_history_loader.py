"""玉山 AI 挑戰賽後台歷史數據自動抓取器 (L0 Source)。

透過官方 OAuth2 SSO 登入流程取得子網域 Session Cookie，並呼叫後台 API 抓取：
  - 每日競賽排名 (總排名 / 社會組排名 / 總隊數 / 社會組總隊數)
  - 每日投組績效摘要 (AUM / 單日與累計報酬率 / 持股與現金比例 / 集中度)
  - 每日交易摘要與完整分頁成交明細 (含 4 位小數成交價、單筆手續費與證交稅)

預設採用「增量更新 + 重抓最新 1 日」模式（兼顧速度與盤後結算/排名修正），
可加上 `--full` 強制從 Day 1 全量重建；輸出以原子寫入儲存至
`data/backend_reports/backend_all_history.json`。

用法：
    python backend_history_loader.py          # 增量更新 + 重抓最新 1 日
    python backend_history_loader.py --full   # 從 Day 1 全量重抓覆蓋
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, quote, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

CODE_DIR = Path(__file__).resolve().parents[1]
ROOT = CODE_DIR.parent
DEFAULT_OUTPUT_PATH = ROOT / "data" / "backend_reports" / "backend_all_history.json"


def _load_env_file(env_path: Path) -> None:
    """載入 code/.env（優先使用 python-dotenv，無則以內建簡易解析器載入）。"""
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path, override=False)
        return
    except ImportError:
        pass

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


class EsunChallengeClient:
    """玉山 AI 挑戰賽後台 API 客戶端。"""

    BASE_MAIN = "https://esun-ai-challenge.tw"
    BASE_SUB = "https://fundaiagent.esun-ai-challenge.tw"

    def __init__(self, email: str, password: str, timeout: int = 15) -> None:
        self.email = email
        self.password = password
        self.timeout = timeout
        self.session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET", "POST"),
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update({
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-TW,zh;q=0.9,en;q=0.8",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
        })

    def login(self) -> None:
        """執行 OAuth2 SSO 登入：主站帳密 -> 子網域 state -> 授權碼換發 -> Callback。"""
        login_resp = self.session.post(
            f"{self.BASE_MAIN}/api/token/",
            headers={
                "content-type": "application/json",
                "origin": self.BASE_MAIN,
                "referer": f"{self.BASE_MAIN}/login",
            },
            json={"email": self.email, "password": self.password},
            timeout=self.timeout,
        )
        login_resp.raise_for_status()
        main_access = login_resp.json().get("access")
        if not main_access:
            raise RuntimeError(f"主站登入失敗，未取得 access token：{login_resp.text}")
        print("✅ [1/3] 主站帳密驗證成功")

        init_resp = self.session.get(
            f"{self.BASE_SUB}/api/auth/login",
            allow_redirects=True,
            timeout=self.timeout,
        )
        qs = parse_qs(urlparse(init_resp.url).query)
        if "state" not in qs:
            init_resp = self.session.get(
                f"{self.BASE_SUB}/",
                allow_redirects=True,
                timeout=self.timeout,
            )
            qs = parse_qs(urlparse(init_resp.url).query)

        state = qs["state"][0] if "state" in qs else secrets.token_urlsafe(32)
        redirect_uri = (
            qs["redirect_uri"][0]
            if "redirect_uri" in qs
            else f"{self.BASE_SUB}/api/auth/callback"
        )

        auth_resp = self.session.post(
            f"{self.BASE_MAIN}/api/sso/authorize/",
            headers={
                "authorization": f"Bearer {main_access}",
                "content-type": "application/json",
                "origin": self.BASE_MAIN,
                "referer": (
                    f"{self.BASE_MAIN}/sso?event=fundaiagent"
                    f"&redirect_uri={quote(redirect_uri, safe='')}&state={state}"
                ),
            },
            json={
                "event": "fundaiagent",
                "redirect_uri": redirect_uri,
                "state": state,
            },
            timeout=self.timeout,
        )
        auth_resp.raise_for_status()
        auth_data = auth_resp.json()

        callback_url = auth_data.get("redirect_url") or auth_data.get("url")
        if not callback_url and auth_data.get("code"):
            base_cb = auth_data.get("redirect_uri", redirect_uri)
            callback_url = f"{base_cb}?code={auth_data['code']}&state={auth_data.get('state', state)}"
        if not callback_url:
            raise RuntimeError(f"SSO 授權回應缺少 callback URL：{auth_data}")

        cb_resp = self.session.get(
            callback_url,
            headers={
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "referer": f"{self.BASE_MAIN}/",
            },
            allow_redirects=True,
            timeout=self.timeout,
        )

        cookies = self.session.cookies.get_dict()
        if "esarena_event_token" not in cookies and "sessionid" not in cookies:
            raise RuntimeError(
                f"Callback 失敗（狀態碼：{cb_resp.status_code}，網址：{cb_resp.url}，"
                f"Cookies：{list(cookies.keys())}），回應：{cb_resp.text[:300]}"
            )
        print(f"✅ [2/3] 子網域 SSO 憑證換發成功（Cookies：{list(cookies.keys())}）")

    def _get_json(self, url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """發送子網域 API 請求，若遇 401/403 自動重新登入並重試一次。"""
        headers = {
            "accept": "application/json, text/plain, */*",
            "referer": f"{self.BASE_SUB}/",
        }
        resp = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
        if resp.status_code in (401, 403):
            print("⚠️ 憑證過期或未授權，正在自動重新執行 SSO 登入...")
            self.login()
            resp = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def _post_json_with_csrf(
        self,
        url: str,
        payload: Dict[str, Any],
        timeout: int = 30,
    ) -> requests.Response:
        """發送帶 X-CSRFToken 的 JSON POST 請求，遇 401/403 自動重新登入並重試一次。"""
        csrf_token = self.session.cookies.get("csrftoken", "")
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "origin": self.BASE_SUB,
            "referer": f"{self.BASE_SUB}/docs",
            "x-csrftoken": csrf_token,
        }
        resp = self.session.post(url, headers=headers, json=payload, timeout=timeout)
        if resp.status_code in (401, 403):
            print("⚠️ 憑證或 CSRF Token 失效，正在重新執行 SSO 登入...")
            self.login()
            headers["x-csrftoken"] = self.session.cookies.get("csrftoken", "")
            resp = self.session.post(url, headers=headers, json=payload, timeout=timeout)
        return resp

    def fetch_all_trades_for_date(self, date_str: str) -> Dict[str, Any]:
        """抓完指定日期的所有分頁交易明細（處理 next 分頁並去除重複 trade_date 欄位）。"""
        all_results: List[Dict[str, Any]] = []
        trade_summary = None
        next_url: Optional[str] = f"{self.BASE_SUB}/api/portfolio/trades/?date={date_str}&page=1"

        while next_url:
            data = self._get_json(next_url)
            if trade_summary is None:
                trade_summary = data.get("summary")
            for item in data.get("results", []):
                all_results.append({k: v for k, v in item.items() if k != "trade_date"})
            next_url = data.get("next")

        return {"trade_summary": trade_summary, "trades": all_results}

    def fetch_day_record(self, day: int, date_str: str) -> Dict[str, Any]:
        """抓取單一交易日的排名、投組摘要與成交明細。"""
        dash = self._get_json(f"{self.BASE_SUB}/api/dashboard/", params={"day": day})
        port = self._get_json(f"{self.BASE_SUB}/api/portfolio/", params={"date": date_str})
        trades_info = self.fetch_all_trades_for_date(date_str)
        kpi = dash.get("kpi") or {}

        return {
            "day": day,
            "date": date_str,
            "ranking": {
                "rank": kpi.get("rank"),
                "total_teams": kpi.get("total_teams"),
                "group_rank": kpi.get("group_rank"),
                "group_total": kpi.get("group_total"),
            },
            "portfolio": {
                "aum": port.get("aum"),
                "day_return": port.get("day_return"),
                "cum_return": port.get("cum_return"),
                "stock_ratio": port.get("stock_ratio"),
                "cash_ratio": port.get("cash_ratio"),
                "holdings_count": port.get("holdings_count"),
                "top10_weight": port.get("top10_weight"),
                "aum_breakdown": port.get("aum_breakdown"),
                "corporate_actions": port.get("corporate_actions"),
                "carry": port.get("carry"),
            },
            "trade_summary": port.get("trade_summary") or trades_info["trade_summary"],
            "trades": trades_info["trades"],
        }

    def fetch_history(
        self,
        existing_records: Optional[List[Dict[str, Any]]] = None,
        full_refresh: bool = False,
    ) -> List[Dict[str, Any]]:
        """抓取後台歷史數據；預設只補抓缺漏日與重抓最後 1 日，full_refresh=True 時全量重抓。"""
        latest_dash = self._get_json(f"{self.BASE_SUB}/api/dashboard/")
        trading_days = latest_dash.get("aum_series") or []
        if not trading_days:
            raise RuntimeError("無法從 Dashboard 取得歷史交易日清單 (aum_series 為空)")

        by_date: Dict[str, Dict[str, Any]] = {}
        latest_existing_date: Optional[str] = None
        if not full_refresh and existing_records:
            for rec in existing_records:
                dt = str(rec.get("date") or "").strip()
                if dt:
                    by_date[dt] = rec
            if by_date:
                latest_existing_date = max(by_date.keys())

        targets = [
            item for item in trading_days
            if full_refresh
            or item["date"] not in by_date
            or item["date"] == latest_existing_date
        ]

        total = len(targets)
        mode_label = "全量覆蓋" if full_refresh or not by_date else "增量 + 最新日覆核"
        print(f"📡 [3/3] 模式：{mode_label}，本次需抓取 {total} / {len(trading_days)} 個交易日...")

        for idx, item in enumerate(targets, start=1):
            day = item["day"]
            date_str = item["date"]
            print(f"⏳ 正在抓取 ({idx}/{total}) Day {day} ({date_str})...")
            by_date[date_str] = self.fetch_day_record(day, date_str)

        merged = sorted(by_date.values(), key=lambda x: (int(x.get("day", 0)), str(x.get("date", ""))))
        return merged


def sync_backend_history(
    output_path: Path = DEFAULT_OUTPUT_PATH,
    full_refresh: bool = False,
) -> Path:
    """登入後台並同步歷史數據至指定 JSON 路徑（原子寫入）。"""
    _load_env_file(CODE_DIR / ".env")
    email = os.getenv("ESUN_EMAIL", "").strip()
    password = os.getenv("ESUN_PASSWORD", "").strip()
    if not email or not password:
        raise RuntimeError(
            "找不到 ESUN_EMAIL 或 ESUN_PASSWORD 環境變數！請於 code/.env 中設定。"
        )

    existing_records: Optional[List[Dict[str, Any]]] = None
    if not full_refresh and output_path.is_file():
        try:
            existing_records = json.loads(output_path.read_text(encoding="utf-8"))
        except Exception:
            existing_records = None

    client = EsunChallengeClient(email=email, password=password)
    client.login()
    history_data = client.fetch_history(
        existing_records=existing_records,
        full_refresh=full_refresh,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(history_data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(output_path)

    print(f"🎉 後台歷史數據同步完成！共 {len(history_data)} 個交易日，已儲存至：{output_path}")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="抓取玉山 AI 挑戰賽後台歷史數據至 backend_all_history.json")
    parser.add_argument("--full", action="store_true", help="強制從 Day 1 全量重抓並覆蓋")
    parser.add_argument("--date", type=str, default=None, help="相容產線參數（會同步至最新可取得交易日）")
    parser.add_argument("--output", type=str, default=None, help="自訂輸出 JSON 路徑")
    args = parser.parse_args()

    out_path = Path(args.output) if args.output else DEFAULT_OUTPUT_PATH
    sync_backend_history(output_path=out_path, full_refresh=args.full)


if __name__ == "__main__":
    main()
