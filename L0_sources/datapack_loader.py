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

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "Datapack" / "Raw"
PROCESSED_DIR = ROOT / "data" / "Datapack" / "Processed"
DEFAULT_RAW = RAW_DIR / "DataPack_275_2026-10-27.json"

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


def convert_datapack(dp: dict) -> str:
    """將 DataPack dict 轉為給 Gemini 的精簡文字（欄位名與值保持原樣）。"""
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

    lines += ["", "### holdings"]
    if hold is None:
        lines.append("null")
    elif not hold:
        lines.append("[]")
    else:
        cols = ("code", "shares", "receivable_shares", "close_price", "tradable_weight")
        lines.append(",".join(cols))
        for h in hold:
            # code 以字串輸出（不加引號），其餘為數值或 null
            lines.append(",".join(
                str(h.get(c)) if c == "code" else _v(h.get(c)) for c in cols))

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


def load_datapack(raw_path: Path = DEFAULT_RAW) -> dict:
    """讀取原始 DataPack JSON。"""
    with open(raw_path, encoding="utf-8") as f:
        return json.load(f)


def process_datapack(raw_path: Path = DEFAULT_RAW, out_dir: Path = PROCESSED_DIR) -> Path:
    """讀入 Raw JSON，輸出 DataPack_Processed_YYYYMMDD.md（日期取自原始檔名）。"""
    raw_path = Path(raw_path)
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", raw_path.name)
    if not m:
        raise ValueError(f"檔名中找不到日期 (YYYY-MM-DD): {raw_path.name}")
    date_str = "".join(m.groups())

    text = convert_datapack(load_datapack(raw_path))
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"DataPack_Processed_{date_str}.md"
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return out_path


if __name__ == "__main__":
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_RAW
    print(f"已輸出: {process_datapack(src)}")
