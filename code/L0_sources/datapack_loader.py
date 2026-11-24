"""讀取官方每日 DataPack JSON (取現金、庫存、NAV)。

將官方 DataPack JSON 轉成「適合放入 Gemini prompt」的精簡文字：
  - 固定的欄位說明（忠實濃縮自 DataPack 規格書 v4.3）
  - 動態的狀態判讀（第一天 / 結算未產生 / 正常）
  - holdings 用 CSV 表格（欄位名只寫一次）節省 token

保真原則：欄位名稱、數值（不四捨五入、不換算單位）、null / [] 皆與原始 JSON 一致，
只改變排版。

用法：
    python datapack_loader.py                       # 處理預設 Raw 檔
    python datapack_loader.py path/to/DataPack_275_2026-10-27.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional, Tuple

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 設定 code/ 為匯入路徑
CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from configs.date_utils import (  # noqa: E402
    clean_date_str,
    format_iso_trade_date,
    prompt_trade_date,
)

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "Datapack" / "Raw"
PROCESSED_DIR = ROOT / "data" / "Datapack" / "Processed"
BACKEND_REPORTS_DIR = ROOT / "data" / "backend_reports"

COMPETITION_START_DATE = "2026-10-27"
COMPETITION_END_DATE = "2026-11-27"
INITIAL_NAV = 1_000_000_000.0
LOT_SIZE = 1000


def get_datapack_incomplete_reasons(dp: dict) -> List[str]:
    """檢查 DataPack 是否尚未完成後台結算／收盤資料更新。

    回傳空串列代表資料完整可用（包含首日全現金、holdings=[]、missing=[] 的合法狀態）；
    回傳非空串列則列出所有未就緒的原因。
    """
    reasons: List[str] = []
    missing = dp.get("missing") or []
    if missing:
        reasons.append(f"missing={missing}")
    if dp.get("account") is None:
        reasons.append("account=null")
    if dp.get("holdings") is None:
        reasons.append("holdings=null")
    po = dp.get("prev_day_orders")
    if isinstance(po, dict) and po.get("outcome") == "unknown":
        reasons.append("prev_day_orders.outcome=unknown")
    return reasons


def is_datapack_ready(dp: dict) -> bool:
    """回傳 DataPack 是否已完成後台更新並具備有效帳戶與持股資訊。"""
    return len(get_datapack_incomplete_reasons(dp)) == 0


def sync_latest_datapack_raw(
    raw_dir: Path = RAW_DIR,
    allow_incomplete: bool = False,
) -> Optional[Path]:
    """透過 OAuth2 SSO 從玉山後台 /api/data-pack/ 自動下載最新 DataPack Raw JSON。

    若後台尚未更新完成（例如 missing 非空、account/holdings 為 null、
    prev_day_orders.outcome 為 unknown），預設不寫入檔案並回傳 None。
    """
    from L0_sources.backend_history_loader import EsunChallengeClient, _load_env_file

    _load_env_file(CODE_DIR / ".env")
    email = os.getenv("ESUN_EMAIL", "").strip()
    password = os.getenv("ESUN_PASSWORD", "").strip()
    if not email or not password:
        raise RuntimeError(
            "找不到 ESUN_EMAIL 或 ESUN_PASSWORD 環境變數！請於 code/.env 中設定。"
        )

    client = EsunChallengeClient(email=email, password=password)
    client.login()
    dp = client._get_json(f"{EsunChallengeClient.BASE_SUB}/api/data-pack/")

    dp_trade_date = str(dp.get("trade_date") or "").strip()
    if not dp_trade_date:
        raise RuntimeError(f"後台 /api/data-pack/ 回傳缺少 trade_date：{list(dp.keys())}")

    incomplete_reasons = get_datapack_incomplete_reasons(dp)
    if incomplete_reasons and not allow_incomplete:
        print(
            f"[datapack_loader] 後台 DataPack ({dp_trade_date}) 尚未更新完成"
            f"（{', '.join(incomplete_reasons)}），略過不存檔。"
        )
        return None

    raw_dir.mkdir(parents=True, exist_ok=True)
    # 若目錄下已有同交易日檔案 (例如 DataPack_275_2026-11-16.json)，直接覆寫該檔以保持檔名一致
    existing = [
        p for p in raw_dir.glob("*.json")
        if p.stem.endswith(f"_{dp_trade_date}") or p.stem.endswith(f"_{dp_trade_date.replace('-', '')}")
    ]
    if existing:
        out_path = existing[0]
    else:
        # 沿用既有 Raw 檔的數字隊伍編號前綴（例如 DataPack_275_YYYY-MM-DD.json）
        team_tag = None
        for p in sorted(raw_dir.glob("DataPack_*.json"), reverse=True):
            m = re.match(r"^DataPack_(\d+)_\d{4}-\d{2}-\d{2}$", p.stem)
            if m:
                team_tag = m.group(1)
                break
        if not team_tag:
            team_tag = str(dp.get("team_id") or os.getenv("TEAM_ID") or "275").strip()
        out_path = raw_dir / f"DataPack_{team_tag}_{dp_trade_date}.json"

    tmp_path = out_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(dp, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(out_path)
    print(f"[datapack_loader] 已從後台 API 同步最新 DataPack ({dp_trade_date}) -> {out_path.name}")
    return out_path


def find_datapack_raw(target_date: Optional[str] = None) -> Path:
    """在 Raw 資料夾當層目錄中尋找日期結尾完全等於 target_date 的 DataPack JSON 檔案。

    若找不到符合日期的檔案，嚴格拋出 FileNotFoundError。
    """
    if not RAW_DIR.exists():
        raise FileNotFoundError(f"找不到 DataPack Raw 目錄: {RAW_DIR}")

    if not target_date:
        raise ValueError("必須指定 target_date (格式 YYYYMMDD)")

    c_date = clean_date_str(target_date)
    iso_date = format_iso_trade_date(target_date)

    raw_files = list(RAW_DIR.glob("*.json"))
    for p in raw_files:
        # 比對檔名結尾為 _YYYYMMDD 或 _YYYY-MM-DD
        if p.stem.endswith(f"_{c_date}") or p.stem.endswith(f"_{iso_date}"):
            return p

    raise FileNotFoundError(
        f"在 {RAW_DIR} 找不到日期結尾為 {c_date} (或 {iso_date}) 的 DataPack Raw JSON 檔案！"
    )

# 固定說明：忠實濃縮自 DataPack_規格書_v4.3，欄位名與原始 JSON 完全一致
GLOSSARY = """\
## 欄位說明（依官方 DataPack 規格書 v4.3）
單位：金額=元；比率=小數(0.1125 表示 11.25%)；股數=整數股；日期=YYYY-MM-DD；時間=台北時間(+08:00)。
- trade_date：本檔對應的交易日，即接下來要繳交的那一個交易日。
- as_of_date：account 與 holdings 實際反映的交易日（有日期時為 trade_date 的前一交易日收盤結算後結果）。null=尚無結算資料：第一個交易日（account 為全現金、0 檔的真值），或前一交易日結算尚未產生（missing 含 prev_settlement，此時 account 整段為 null）。
- missing：系統缺少的資料源，齊備時為 []。prev_settlement=前一交易日結算尚未產生，account、as_of_date、holdings 皆為 null；prev_close=收盤價尚未匯入，account.cash_ratio_tradable 為 null。
- prev_day_orders.outcome：none=前一交易日未繳交，沒有委託；unknown=委託結果尚未判定；voided=已繳交但整批作廢、未成交；executed=有成交。
- prev_day_orders.void_reasons：整批作廢的全部原因（outcome 為 voided 時至少一筆，其餘為 []）。值：insufficient_funds資金不足 / oversell賣出股數超過持股 / no_price委託標的缺當日成交均價且不在標的池內 / compliance_fail合規檢查未通過（持股檔數、標的池限制、現金部位、當日加碼個股權重之一，不細分） / dplan_reference_chain文件引用鏈不完整 / dplan_decision_coverage決策覆蓋不完整 / dplan_round_lot委託非整股。
- prev_day_orders.excluded_codes：被排除、未成交，但其餘委託照常成交的證券代號（outcome 為 executed 時仍可能非空：該檔缺當日成交均價）。
- account.cash：可動用現金（不含應收配息）。不等於當日買進上限，交割以淨額計，同日賣出款也計入結算。
- account.cash_ratio_tradable：cash ÷ nav_tradable。missing 非空時為 null。
- account.nav_tradable：可交易淨值 = cash + Σ(holdings.shares × holdings.close_price)，是計算現金比與個股權重的分母。
- account.aum：總資產，另含應收配息與應收配股市值。不是 nav_tradable，不可用於計算比率。
- account.receivable_cash：已生效的應收配息。計入 aum，賽期內不會到帳，不可用於下單。
- account.holdings_count：持股檔數，只計 shares>0 的檔；與 holdings 的列數不一定相同。
- holdings（逐檔一列，shares 與 receivable_shares 之一不為 0 即列出）：code=證券代號；shares=庫存持股，賣出不得超過此數；receivable_shares=應收配股，賽期內不可賣、不計入 holdings_count 與權重；close_price=as_of_date 收盤價，null=該檔查無行情，計算 nav_tradable 時以 0 計入；tradable_weight=個股權重(分母為 nav_tradable)，null=不適用（只有應收配股或無收盤價，不是 0）。
  holdings 為 [] 只在成功建倉前，代表真的空手；為 null（結算未產生）則不是空手，兩者不同。
- compliance.violations：違規天數（累計），為取消資格的依據（對應後台右上角「警告次數」）。compliance.notices：異常提示列數（累計），不計入取消資格。
- compliance.incidents：違規與異常提示紀錄。status=fail 計入 violations；status=warn 計入 notices。message 為判定說明。
- 賽期進度與帳戶淨值演變（由歷史 DataPack 計算）：
  - elapsed_trading_days / remaining_trading_days / progress_pct / phase：賽期已過交易日、剩餘交易日、進度 (%) 與階段（剩餘 <=5 日為 sprint 衝刺期）。
  - cum_return_pct：相對初始 10 億之累計帳面報酬率 (%)；peak_nav / drawdown_from_peak_pct / max_drawdown_pct：賽期最高淨值、距高點回撤 (%) 與歷史最大回撤 MDD (%)。
  - nav_return_1d_pct / nav_return_3d_pct / nav_return_5d_pct：近 1 / 3 / 5 個交易日淨值變化率 (%)；consecutive_loss_days：連續虧損天數；recent_5d_trajectory：近 5 日淨值走勢。
- holdings 衍生追蹤欄位（由歷史 DataPack 與 backend_reports 實際成交紀錄計算，百分比欄位單位為 %）：
  - entry_date / holding_days：最近一次建倉日期與已持有交易日數；avg_cost：實際成交移動加權平均成本；pnl_pct：目前未實現損益 (%)。
  - peak_price / peak_pnl_pct / dd_from_peak_pct：持有期間最高收盤價、最高浮盈 (%) 與自高點回落幅度 (%)（移動停利依據）。
"""


def _v(x) -> str:
    """與原始 JSON 一致的值字串：null / true / false / [..]；整數值浮點去掉 .0（數值不變）。"""
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return json.dumps(x, ensure_ascii=False)


def _list(x) -> str:
    """字串陣列以 JSON 形式輸出（空陣列即 [] ）。"""
    return json.dumps(x, ensure_ascii=False)


def _status_note(dp: dict) -> str:
    """依資料狀態產生一句判讀（僅複述規格書語意）。"""
    missing = dp.get("missing") or []
    if "prev_settlement" in missing:
        return ("前一交易日結算尚未產生：account 與 holdings 為 null（不是空手），"
                "規格書建議於結算產生後重新下載。")
    if dp.get("as_of_date") is None:
        return "第一個交易日：尚無結算資料；account 為全現金、0 檔的真值，holdings=[] 代表真的空手。"
    note = f"account 與 holdings 為 {dp['as_of_date']} 收盤結算後的狀態。"
    if "prev_close" in missing:
        note += " 收盤價尚未匯入，cash_ratio_tradable 為 null。"
    return note


class _TableHTMLParser(HTMLParser):
    """極簡 HTML 表格解析器，不依賴 lxml。"""

    def __init__(self) -> None:
        super().__init__()
        self.tables: List[List[List[str]]] = []
        self._cur_t: Optional[List[List[str]]] = None
        self._cur_r: Optional[List[str]] = None
        self._cur_c: Optional[List[str]] = None

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "table":
            self._cur_t = []
        elif tag == "tr" and self._cur_t is not None:
            self._cur_r = []
        elif tag in ("td", "th") and self._cur_r is not None:
            self._cur_c = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._cur_c is not None:
            self._cur_r.append("".join(self._cur_c).strip())
            self._cur_c = None
        elif tag == "tr" and self._cur_r is not None:
            self._cur_t.append(self._cur_r)
            self._cur_r = None
        elif tag == "table" and self._cur_t is not None:
            self.tables.append(self._cur_t)
            self._cur_t = None

    def handle_data(self, data: str) -> None:
        if self._cur_c is not None:
            self._cur_c.append(data)


_SIDE_MAP = {
    "buy": "買進",
    "sell": "賣出",
    "買進": "買進",
    "賣出": "賣出",
}


def _load_trades_from_json(
    json_path: Path,
    up_to_iso: Optional[str] = None,
) -> List[dict]:
    """從 backend_all_history.json 讀取已成交交易明細（保留原始 4 位小數成交價）。"""
    records = json.loads(json_path.read_text(encoding="utf-8"))
    trades: List[dict] = []
    for day_entry in records:
        t_date = str(day_entry.get("date") or "").strip()
        if not t_date or (up_to_iso and t_date > up_to_iso):
            continue
        for tr in day_entry.get("trades") or []:
            outcome = str(tr.get("outcome", "")).strip().lower()
            if outcome and outcome != "filled":
                continue
            side = _SIDE_MAP.get(str(tr.get("side", "")).strip().lower())
            code = str(tr.get("code", "")).strip()
            shares = int(tr.get("shares", 0))
            if not side or not code or shares <= 0:
                continue
            trades.append({
                "date": t_date,
                "side": side,
                "code": code,
                "shares": shares,
                "price": float(tr["price"]),
            })
    return trades


def _load_trades_from_htm(
    reports_dir: Path,
    up_to_iso: Optional[str] = None,
) -> List[dict]:
    """備援：從 backend_reports/*.htm 讀取已成交交易明細。"""
    trades: List[dict] = []
    for htm_path in sorted(reports_dir.glob("*.htm")):
        parser = _TableHTMLParser()
        parser.feed(htm_path.read_text(encoding="utf-8"))
        for table in parser.tables:
            if not table:
                continue
            header = table[0]
            if "交易日" not in header or "代號" not in header or "成交價" not in header:
                continue
            idx = {col: i for i, col in enumerate(header)}
            for row in table[1:]:
                if len(row) < len(header):
                    continue
                status = row[idx.get("結果", -1)] if "結果" in idx else "已成交"
                if status != "已成交":
                    continue
                t_date = row[idx["交易日"]].strip()
                if up_to_iso and t_date > up_to_iso:
                    continue
                side = row[idx["買/賣"]].strip()
                code = row[idx["代號"]].strip()
                lots = int(row[idx["張數"]].replace(",", "").strip())
                price = float(row[idx["成交價"]].replace(",", "").strip())
                trades.append({
                    "date": t_date,
                    "side": side,
                    "code": code,
                    "shares": lots * LOT_SIZE,
                    "price": price,
                })
    return trades


def load_backend_trades(
    reports_dir: Path = BACKEND_REPORTS_DIR,
    up_to_date: Optional[str] = None,
) -> List[dict]:
    """讀取已成交交易明細，依交易日排序。優先使用 backend_all_history.json，無則退回 *.htm。"""
    if not reports_dir.exists():
        return []

    up_to_iso = format_iso_trade_date(up_to_date) if up_to_date else None
    history_json = reports_dir / "backend_all_history.json"
    if history_json.exists():
        trades = _load_trades_from_json(history_json, up_to_iso=up_to_iso)
    else:
        trades = _load_trades_from_htm(reports_dir, up_to_iso=up_to_iso)

    trades.sort(key=lambda r: (r["date"], 0 if r["side"] == "買進" else 1, r["code"]))
    return trades


def load_datapack_history(
    raw_dir: Path = RAW_DIR,
    up_to_trade_date: Optional[str] = None,
) -> List[dict]:
    """讀取截至 up_to_trade_date（含）的所有歷史 DataPack Raw JSON，依 trade_date 排序。"""
    if not raw_dir.exists():
        return []
    up_to_iso = format_iso_trade_date(up_to_trade_date) if up_to_trade_date else None
    items: List[dict] = []
    for p in sorted(raw_dir.glob("*.json")):
        try:
            dp = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        t_date = dp.get("trade_date") or ""
        if up_to_iso and t_date > up_to_iso:
            continue
        if not is_datapack_ready(dp):
            continue
        items.append(dp)
    items.sort(key=lambda d: d.get("trade_date") or "")
    return items


def _count_weekdays(start_iso: str, end_iso: str) -> int:
    """計算起訖日（含兩端）之間的工作日（週一至週五）天數。"""
    d0 = date.fromisoformat(start_iso)
    d1 = date.fromisoformat(end_iso)
    if d1 < d0:
        return 0
    cnt = 0
    cur = d0
    while cur <= d1:
        if cur.weekday() < 5:
            cnt += 1
        cur += timedelta(days=1)
    return cnt


def _build_progress_lines(trade_date: str, history: List[dict]) -> List[str]:
    """計算賽期進度資訊。"""
    elapsed = len(history) if history else _count_weekdays(COMPETITION_START_DATE, trade_date)
    remaining = _count_weekdays(trade_date, COMPETITION_END_DATE)
    total = elapsed + max(remaining - 1, 0)
    progress_pct = round(elapsed / total * 100, 1) if total > 0 else 0.0
    if remaining <= 5:
        phase = "sprint (最後衝刺期，避免新建倉低波動防禦股)"
    elif progress_pct >= 50:
        phase = "mid-late (中後期)"
    else:
        phase = "early (初期)"
    return [
        "### 賽期進度",
        f"start_date: {COMPETITION_START_DATE} | end_date: {COMPETITION_END_DATE} | "
        f"elapsed_trading_days: {elapsed} | remaining_trading_days: {remaining} | "
        f"progress_pct: {progress_pct}% | phase: {phase}",
    ]


def _build_nav_trajectory_lines(history: List[dict]) -> List[str]:
    """從歷史 DataPack 計算淨值累計報酬、MDD、1D/3D/5D 報酬率與連虧天數。"""
    series: List[Tuple[str, float]] = []
    seen_dates = set()
    for dp in history:
        as_of = dp.get("as_of_date")
        acc = dp.get("account") or {}
        nav = acc.get("nav_tradable")
        if as_of and nav is not None and as_of not in seen_dates:
            seen_dates.add(as_of)
            series.append((as_of, float(nav)))

    if not series:
        return ["### 帳戶淨值演變", "(尚無歷史結算淨值資料)"]

    # 以初始資金 10 億作為起點計算回撤與連虧
    full_points: List[Tuple[str, float]] = [("initial", INITIAL_NAV)] + series
    peak_nav = INITIAL_NAV
    peak_date = "initial"
    mdd = 0.0
    for dt, nav in series:
        if nav > peak_nav:
            peak_nav = nav
            peak_date = dt
        dd = (nav / peak_nav - 1.0) * 100.0
        if dd < mdd:
            mdd = dd

    latest_dt, latest_nav = series[-1]
    cum_ret = (latest_nav / INITIAL_NAV - 1.0) * 100.0
    dd_from_peak = (latest_nav / peak_nav - 1.0) * 100.0

    def _ret_n(n: int) -> Optional[float]:
        if len(full_points) <= n:
            return None
        base = full_points[-1 - n][1]
        return (latest_nav / base - 1.0) * 100.0 if base else None

    r1d = _ret_n(1)
    r3d = _ret_n(3)
    r5d = _ret_n(5)

    consec_loss = 0
    for i in range(len(full_points) - 1, 0, -1):
        if full_points[i][1] < full_points[i - 1][1]:
            consec_loss += 1
        else:
            break

    def _fmt_pct(v: Optional[float]) -> str:
        return "null" if v is None else f"{v:+.2f}%"

    # 近 5 個結算日淨值走勢摘要
    recent_start = max(1, len(full_points) - 5)
    traj_parts = []
    for i in range(recent_start, len(full_points)):
        dt, nav = full_points[i]
        prev_nav = full_points[i - 1][1]
        d_ret = (nav / prev_nav - 1.0) * 100.0
        traj_parts.append(f"{dt[5:]}: {nav / 1e8:.3f}億 ({d_ret:+.2f}%)")

    return [
        "### 帳戶淨值演變",
        f"initial_nav: {INITIAL_NAV:,.0f} | latest_nav ({latest_dt}): {latest_nav:,.2f} | "
        f"cum_return_pct: {_fmt_pct(cum_ret)} | peak_nav ({peak_date}): {peak_nav:,.2f} | "
        f"drawdown_from_peak_pct: {_fmt_pct(dd_from_peak)} | max_drawdown_pct: {mdd:.2f}%",
        f"nav_return_1d_pct: {_fmt_pct(r1d)} | nav_return_3d_pct: {_fmt_pct(r3d)} | "
        f"nav_return_5d_pct: {_fmt_pct(r5d)} | consecutive_loss_days: {consec_loss}",
        "recent_5d_trajectory: " + " -> ".join(traj_parts),
    ]


def _compute_holdings_tracking(
    dp: dict,
    history: List[dict],
    trades: List[dict],
) -> Dict[str, dict]:
    """結合 backend_reports 實際成交均價與歷史 DataPack 收盤價，計算每檔持股成本與高點回落。"""
    holdings = dp.get("holdings") or []
    if not holdings:
        return {}

    # 1. 由 backend_reports 計算目前持股的移動加權平均成本與建倉日
    pos: Dict[str, dict] = {}
    for tr in trades:
        code = tr["code"]
        st = pos.setdefault(code, {"shares": 0, "cost_total": 0.0, "entry_date": None})
        qty = tr["shares"]
        if tr["side"] == "買進":
            if st["shares"] == 0:
                st["entry_date"] = tr["date"]
            st["shares"] += qty
            st["cost_total"] += qty * tr["price"]
        elif tr["side"] == "賣出":
            if st["shares"] > 0:
                avg_c = st["cost_total"] / st["shares"]
                st["shares"] = max(0, st["shares"] - qty)
                st["cost_total"] = st["shares"] * avg_c
                if st["shares"] == 0:
                    st["entry_date"] = None

    # 2. 收集各個歷史結算日的收盤價與持有天數
    price_history: Dict[str, List[Tuple[str, float]]] = {}
    seen_asof = set()
    ordered_asof: List[str] = []
    for h_dp in history:
        as_of = h_dp.get("as_of_date")
        if not as_of or as_of in seen_asof:
            continue
        seen_asof.add(as_of)
        ordered_asof.append(as_of)
        for item in h_dp.get("holdings") or []:
            c = str(item.get("code", "")).strip()
            cp = item.get("close_price")
            if c and cp is not None and int(item.get("shares", 0)) > 0:
                price_history.setdefault(c, []).append((as_of, float(cp)))

    latest_asof = dp.get("as_of_date") or (ordered_asof[-1] if ordered_asof else "")
    result: Dict[str, dict] = {}

    for h in holdings:
        if int(h.get("shares", 0)) <= 0:
            continue
        code = str(h.get("code", "")).strip()
        close_p = h.get("close_price")
        close_val = float(close_p) if close_p is not None else None

        st = pos.get(code)
        if st and st["shares"] > 0 and st["entry_date"]:
            entry_date = st["entry_date"]
            avg_cost = st["cost_total"] / st["shares"]
        else:
            # 若 backend_reports 缺漏該檔，退回以歷史 DataPack 首次出現日與收盤價估算
            hist_pts = price_history.get(code, [])
            entry_date = hist_pts[0][0] if hist_pts else latest_asof
            avg_cost = hist_pts[0][1] if hist_pts else (close_val or 0.0)

        # 計算持有交易日數 (從 entry_date 至 latest_asof)
        holding_days = sum(1 for d in ordered_asof if entry_date <= d <= latest_asof)
        if holding_days == 0 and entry_date:
            holding_days = _count_weekdays(entry_date, latest_asof) if latest_asof >= entry_date else 1

        # 計算持有期間最高收盤價 (自 entry_date 起)
        held_prices = [p for d, p in price_history.get(code, []) if d >= entry_date]
        if close_val is not None:
            held_prices.append(close_val)
        peak_price = max(held_prices) if held_prices else close_val

        if avg_cost > 0 and close_val is not None and peak_price is not None:
            pnl_pct = round((close_val / avg_cost - 1.0) * 100.0, 2)
            peak_pnl_pct = round((peak_price / avg_cost - 1.0) * 100.0, 2)
            dd_from_peak_pct = round((close_val / peak_price - 1.0) * 100.0, 2)
        else:
            pnl_pct = peak_pnl_pct = dd_from_peak_pct = None

        peak_fmt = int(peak_price) if (peak_price is not None and float(peak_price).is_integer()) else peak_price
        result[code] = {
            "entry_date": entry_date,
            "holding_days": holding_days,
            "avg_cost": round(avg_cost, 2) if avg_cost > 0 else None,
            "pnl_pct": pnl_pct,
            "peak_price": peak_fmt,
            "peak_pnl_pct": peak_pnl_pct,
            "dd_from_peak_pct": dd_from_peak_pct,
        }

    return result


def convert_datapack(
    dp: dict,
    history: Optional[List[dict]] = None,
    trades: Optional[List[dict]] = None,
) -> str:
    """將 DataPack dict 轉為給 Gemini 的精簡文字（欄位名與值保持原樣，並附加路徑演變特徵）。"""
    po = dp.get("prev_day_orders")
    acc = dp.get("account")
    hold = dp.get("holdings")
    comp = dp.get("compliance") or {}

    lines = [
        "# DataPack（官方每日帳戶/部位/合規快照）",
        GLOSSARY,
        "## 資料",
        f"schema_version: {_v(dp.get('schema_version'))} | doc_type: {_v(dp.get('doc_type'))} | "
        f"team_id: {_v(dp.get('team_id'))}",
        f"trade_date: {_v(dp.get('trade_date'))} | as_of_date: {_v(dp.get('as_of_date'))} | "
        f"generated_at: {_v(dp.get('generated_at'))}",
        f"missing: {_list(dp.get('missing'))}",
        f"狀態判讀: {_status_note(dp)}",
        "",
        "### prev_day_orders",
    ]
    if po is None:
        lines.append("null")
    else:
        lines.append(
            f"outcome: {_v(po.get('outcome'))} | void_reasons: {_list(po.get('void_reasons'))} | "
            f"excluded_codes: {_list(po.get('excluded_codes'))}"
        )

    lines += ["", "### account"]
    if acc is None:
        lines.append("null")
    else:
        lines.append(" | ".join(f"{k}: {_v(acc.get(k))}" for k in (
            "cash", "cash_ratio_tradable", "nav_tradable", "aum", "receivable_cash", "holdings_count")))

    trade_date = dp.get("trade_date") or ""
    if history is not None and trade_date:
        lines += [""] + _build_progress_lines(trade_date, history)
        lines += [""] + _build_nav_trajectory_lines(history)

    tracking_map = _compute_holdings_tracking(dp, history, trades or []) if (history is not None and trade_date) else {}

    lines += ["", "### holdings"]
    if hold is None:
        lines.append("null")
    elif not hold:
        lines.append("[]")
    else:
        cols = ("shares", "receivable_shares", "close_price", "tradable_weight")
        lines.append("{")
        if tracking_map:
            note_val = "原生欄位: shares, receivable_shares, close_price, tradable_weight；追蹤欄位(百分比單位 %): entry_date, holding_days, avg_cost, pnl_pct, peak_price, peak_pnl_pct, dd_from_peak_pct"
            lines.append(f'  "_note": {json.dumps(note_val, ensure_ascii=False)},')
        for idx, h in enumerate(hold):
            code_str = str(h.get("code"))
            entry = {
                c: (int(h.get(c)) if isinstance(h.get(c), float) and h.get(c).is_integer() else h.get(c))
                for c in cols
            }
            if code_str in tracking_map:
                entry.update(tracking_map[code_str])
            comma = "," if idx < len(hold) - 1 else ""
            lines.append(f'  {json.dumps(code_str, ensure_ascii=False)}: {json.dumps(entry, ensure_ascii=False)}{comma}')
        lines.append("}")

    lines += ["", "### compliance",
              f"violations: {_v(comp.get('violations'))} | notices: {_v(comp.get('notices'))}"]
    incidents = comp.get("incidents")
    if not incidents:
        lines.append(f"incidents: {_list(incidents if incidents is not None else None)}")
    else:
        lines.append("incidents (date,check_code,status,message):")
        for i in incidents:
            lines.append(f"{i.get('date')},{i.get('check_code')},{i.get('status')},{i.get('message')}")

    return "\n".join(lines) + "\n"


def load_datapack(raw_path: Optional[Path] = None, target_date: Optional[str] = None) -> dict:
    """讀取原始 DataPack JSON。"""
    actual_path = raw_path or find_datapack_raw(target_date)
    if not actual_path or not actual_path.exists():
        raise FileNotFoundError(f"找不到 DataPack Raw JSON 檔案 (搜尋目錄: {RAW_DIR}, 目標日期: {target_date})")
    with open(actual_path, encoding="utf-8") as f:
        return json.load(f)


def process_datapack(
    raw_path: Optional[Path] = None,
    target_date: Optional[str] = None,
    out_dir: Path = PROCESSED_DIR,
    fetch_api: bool = True,
) -> Path:
    """讀入 Raw JSON（預設先從後台 API 同步最新 DataPack），輸出 DataPack_Processed_YYYYMMDD.md。"""
    actual_path = raw_path
    if not actual_path:
        if fetch_api:
            fetched_path = sync_latest_datapack_raw(RAW_DIR)
            if not target_date:
                if fetched_path is None:
                    raise RuntimeError(
                        "後台最新 DataPack 尚未更新完成（未儲存至 Raw），"
                        "請待結算產生後再執行，或使用 --date 指定歷史交易日。"
                    )
                actual_path = fetched_path
            else:
                iso_target = format_iso_trade_date(target_date)
                if fetched_path is not None:
                    fetched_data = load_datapack(fetched_path)
                    if fetched_data.get("trade_date") == iso_target:
                        actual_path = fetched_path
                    else:
                        print(
                            f"[datapack_loader] API 最新 DataPack 為 {fetched_data.get('trade_date')}，"
                            f"改讀取本地歷史檔 ({iso_target})..."
                        )
                        actual_path = find_datapack_raw(target_date)
                else:
                    print(
                        f"[datapack_loader] API 最新 DataPack 尚未更新完成（已略過儲存），"
                        f"改嘗試讀取本地歷史檔 ({iso_target})..."
                    )
                    actual_path = find_datapack_raw(target_date)
        else:
            actual_path = find_datapack_raw(target_date)

    if not actual_path or not actual_path.exists():
        raise FileNotFoundError(f"找不到 DataPack Raw JSON 檔案 (搜尋目錄: {RAW_DIR}, 目標日期: {target_date})")

    # 決定輸出日期標籤
    if target_date:
        date_str = clean_date_str(target_date)
    else:
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", actual_path.name)
        if m:
            date_str = "".join(m.groups())
        else:
            m2 = re.findall(r"\d{8}", actual_path.name)
            date_str = m2[-1] if m2 else ""

    if not date_str or len(date_str) != 8:
        raise ValueError(f"無法從檔名或參數取得合規日期 (YYYYMMDD): {actual_path.name}")

    raw_data = load_datapack(actual_path)
    dp_trade_date = raw_data.get("trade_date") or date_str
    dp_as_of_date = raw_data.get("as_of_date") or dp_trade_date
    history = load_datapack_history(RAW_DIR, up_to_trade_date=dp_trade_date)
    trades = load_backend_trades(BACKEND_REPORTS_DIR, up_to_date=dp_as_of_date)
    text = convert_datapack(raw_data, history=history, trades=trades)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"DataPack_Processed_{date_str}.md"
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

    print(f"[datapack_loader] 成功轉換 DataPack: {actual_path.name} -> {out_path.name}")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="讀取官方每日 DataPack JSON 並轉換為 Processed Markdown")
    parser.add_argument("--date", type=str, default=None, help="目標交易日期 (格式如 20261028 或 2026-10-28)")
    parser.add_argument("--raw-path", type=str, default=None, help="直接指定 DataPack Raw JSON 檔案路徑")
    parser.add_argument("--no-fetch", action="store_true", help="跳過後台 /api/data-pack/ 自動下載，僅使用本地 Raw 檔案")
    args = parser.parse_args()

    custom_raw = Path(args.raw_path) if args.raw_path else None
    target_date = args.date

    # 僅在跳過 API 下載且未指定檔案/日期時，才詢問交易日期
    if args.no_fetch and not custom_raw and not target_date:
        target_date = prompt_trade_date(prompt_text="DataPack 轉換 - 交易日期")

    out_file = process_datapack(
        raw_path=custom_raw,
        target_date=target_date,
        fetch_api=not args.no_fetch,
    )
    print(f"已產出 Processed 檔案: {out_file}")


if __name__ == "__main__":
    main()
