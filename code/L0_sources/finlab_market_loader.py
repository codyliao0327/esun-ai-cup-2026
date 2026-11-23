"""透過 FinLab API 計算台股個股指標（基本面、技術面、籌碼面）及大盤指標並存檔。

每個指標由 stock_indicators.py（個股 29 個）與 market_indicators.py（大盤 16 個）定義，
並於 ALL_INDICATORS 登記。本程式負責排程執行、Compact Array JSON 儲存與 D-Plan L0 sources 產出。

存檔位置：
- 大盤指標 -> data/大盤/<指標名稱>_<YYYYMMDD>.json
- 基本面指標 -> data/基本面/<指標名稱>_<YYYYMMDD>.json
- 技術面指標 -> data/技術面/<指標名稱>_<YYYYMMDD>.json
- 籌碼面指標 -> data/籌碼面/<指標名稱>_<YYYYMMDD>.json

輸出格式 (Compact Array JSON)：
- 個股指標：以個股為 Key 的精簡字典，如 {"_format": "[value, date]", "1303": {"volume_ma5_to_ma20": [0.83, "2026-11-03"]}}
- 大盤指標：以 tw_market 為 Key 的精簡字典，如 {"_format": "[value, date]", "tw_market": {"taiex_close_latest": [0.83, "2026-11-03"]}}

用法::

    python finlab_market_loader.py                       # 計算全部指標 (個股 29 + 大盤 16 共 45 個)
    python finlab_market_loader.py --only 大盤            # 只算大盤指標
    python finlab_market_loader.py --only 技術面          # 只算個股技術面
    python finlab_market_loader.py --only taiex          # 只算加權指數相關
    python finlab_market_loader.py --overwrite           # 當日檔案已存在時仍重新計算

在其他程式中讀取::

    from finlab_market_loader import load_dataset
    df = load_dataset("taiex_close_latest", day="20261104")     # 自動讀取大盤收盤價 DataFrame
    df = load_dataset("volume_ma5_to_ma20", day="20261104")     # 自動讀取個股技術指標 DataFrame
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Union

import pandas as pd

# 設定 L0_sources/ 與 code/ 為匯入路徑
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

CODE_DIR = CURRENT_DIR.parent
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

# 匯入指標定義
from stock_indicators import ALL_INDICATORS as ALL_STOCK_INDICATORS, Indicator as StockIndicator
from market_indicators import ALL_MARKET_INDICATORS, MarketIndicator

# 合併所有指標清單
ALL_INDICATORS: list[Union[StockIndicator, MarketIndicator]] = (
    list(ALL_STOCK_INDICATORS) + list(ALL_MARKET_INDICATORS)
)

# 專案根目錄 / data (本檔位於 code/L0_sources/)
DATA_ROOT = Path(__file__).resolve().parents[2] / "data"
FILE_FORMAT = "json"
PARQUET_COMPRESSION = "zstd"

# 預設 52 檔備援清單 (當 data/Stock_Pool/ 尚無 stock_list_*.json 時使用)
DEFAULT_STOCK_IDS: list[str] = [
    "1101", "1216", "1402", "1519", "1590", "2002", "2207", "2317", "2330", "2379",
    "2395", "2412", "2454", "2603", "2609", "2610", "2618", "2801", "2834", "2880",
    "2881", "2882", "2886", "2891", "2892", "2912", "3045", "3227", "3231", "3293",
    "3491", "3529", "3661", "3665", "4123", "4749", "4904", "4966", "5347", "5536",
    "5871", "5876", "5880", "5903", "6023", "6505", "6548", "6919", "7828", "8069",
    "8299", "8415",
]

from stock_pool_screener import load_stock_pool_ids  # noqa: E402
import stock_indicators as _stock_indicators_mod  # noqa: E402

# 動態股票池清單（執行 download_all 時會依 target_date 重新載入並同步至 stock_indicators）
STOCK_IDS: list[str] = load_stock_pool_ids(fallback=DEFAULT_STOCK_IDS)

# D-Plan L0 資料來源層 sources 輸出位置
SOURCES_DIR = DATA_ROOT / "D-Paln_Output" / "l0_sources"
SOURCES_PREFIX = "s1_finlab_market_sources"

# 向下相容
TechIndicator = StockIndicator
TECH_INDICATORS = ALL_INDICATORS

from configs.date_utils import clean_date_str, prompt_trade_date  # noqa: E402
from configs.json_utils import format_metric_value, to_compact_json  # noqa: E402

# --------------------------------------------------------------------------- #
# 工具函式
# --------------------------------------------------------------------------- #
def _safe_filename(name: str) -> str:
    """移除 Windows 不允許的檔名字元 (<>:"/\\|?*)。"""
    return re.sub(r'[<>:"/\\|?*]', "_", name)


def build_path(ind: Union[StockIndicator, MarketIndicator], day: Optional[Union[date, str]] = None) -> Path:
    """根據指標所屬資料夾 (大盤 / 基本面 / 技術面 / 籌碼面) 產生存檔路徑。"""
    if isinstance(day, str):
        c_date = clean_date_str(day)
    elif isinstance(day, date):
        c_date = f"{day:%Y%m%d}"
    else:
        c_date = date.today().strftime("%Y%m%d")
    fname = f"{_safe_filename(ind.name)}_{c_date}.{FILE_FORMAT}"
    return DATA_ROOT / ind.folder / fname


def compute_indicator(ind: Union[StockIndicator, MarketIndicator]) -> Union[pd.DataFrame, dict]:
    """執行指標計算，回傳單列 DataFrame 或 Compact Array JSON dict。

    - 大盤指標：不受 whitelist 限制，回傳 date x 指標名稱 (或 Compact Array JSON dict)。
    - 個股指標：在 52 檔 whitelist 範圍內運算，回傳 date x 52 檔股票代碼 (或 Compact Array JSON dict)。
    """
    from finlab import data

    if ind.folder == "大盤":
        # 大盤與全市場指標（如漲跌家數比）不能受限於 52 檔 whitelist
        with data.universe(None):
            raw = ind.func()

        if isinstance(raw, dict):
            return raw

        df = raw.copy()
        if df.index.name != "date":
            df.index.name = "date"
        df = df.reset_index()
        df["date"] = df["date"].astype(str)
        # 確保第一欄為 date，第二欄為指標名稱
        if len(df.columns) > 1 and df.columns[1] != ind.name:
            df = df.rename(columns={df.columns[1]: ind.name})
        return df

    # 個股指標計算
    with data.universe(whitelist=STOCK_IDS):
        raw = ind.func()

    if isinstance(raw, dict):
        return raw

    df = raw.copy()

    # 確保 index 命名為 date
    if df.index.name != "date":
        df.index.name = "date"
    df = df.reset_index()
    # 日期或季度統一轉字串 (例如 "2026-10-24" 或 "2026-Q2")
    df["date"] = df["date"].astype(str)

    # 確保 59 檔股票代碼欄位齊全 (若有某檔無數據則填 NaN)
    for sid in STOCK_IDS:
        if sid not in df.columns:
            df[sid] = float("nan")

    # 整理欄位順序：date 欄在最前，其餘 59 檔依序排列
    ordered_cols = ["date"] + [sid for sid in STOCK_IDS if sid in df.columns]
    df = df[ordered_cols]
    return df


def df_to_compact_json(df: pd.DataFrame, ind_name: str, is_market: bool = False) -> dict:
    """將指標單列 DataFrame 轉換為以個股/大盤為 Key 的 Compact Array JSON 格式字典。

    格式說明：
    - 個股: {"_format": "[value, date]", "1303": {"volume_ma5_to_ma20": [0.83, "2026-11-03"]}, ...}
    - 大盤: {"_format": "[value, date]", "tw_market": {"taiex_close_latest": [0.83, "2026-11-03"]}}
    """
    row = df.iloc[-1]
    dt = str(row["date"]).strip()
    if len(dt) > 10 and " " in dt:
        dt = dt.split()[0]

    data_dict = {"_format": "[value, date]"}
    if is_market:
        val_col = ind_name if ind_name in df.columns else [c for c in df.columns if c != "date"][0]
        val = format_metric_value(row[val_col])
        if val is not None:
            data_dict["tw_market"] = {ind_name: [val, dt]}
    else:
        for col in df.columns:
            if col == "date":
                continue
            val = format_metric_value(row[col])
            if val is not None:
                data_dict[str(col)] = {ind_name: [val, dt]}
    return data_dict


def save_dataset(data: Union[dict, pd.DataFrame], path: Path) -> None:
    """儲存指標檔案 (支援 Compact Array JSON 或 Parquet 格式)。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".json" or isinstance(data, dict):
        if isinstance(data, pd.DataFrame):
            raise TypeError("儲存為 JSON 時必須傳入 Compact Array JSON dict")
        path.write_text(to_compact_json(data), encoding="utf-8")
    else:
        data.to_parquet(path, engine="pyarrow", compression=PARQUET_COMPRESSION, index=False)


def write_sources_json(day: Optional[Union[date, str]] = None) -> Path:
    """輸出 D-Plan L0 sources JSON；content_as_of 為台北時區執行當下時間。"""
    if isinstance(day, str):
        c_date = clean_date_str(day)
    elif isinstance(day, date):
        c_date = f"{day:%Y%m%d}"
    else:
        c_date = date.today().strftime("%Y%m%d")

    now_tpe = datetime.now(timezone(timedelta(hours=8)))
    source = {
        "source_id": "S1",
        "authority": "vendor",
        "url": "https://finlab.finance",
        "content_as_of": now_tpe.isoformat(timespec="seconds"),
        "name": "FinLab",
    }
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    path = SOURCES_DIR / f"{SOURCES_PREFIX}_{c_date}.json"
    path.write_text(json.dumps([source], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"sources JSON -> {path}")
    return path


# --------------------------------------------------------------------------- #
# 對外 API
# --------------------------------------------------------------------------- #
def download_all(
    only: Optional[list[str]] = None,
    overwrite: bool = False,
    target_date: Optional[Union[date, str]] = None,
) -> dict[str, str]:
    """計算所有 (或符合關鍵字的) 指標，回傳 {指標名稱: 狀態}。"""
    import finlab

    # 依 target_date 動態載入當日股票池，並同步至 stock_indicators.STOCK_IDS
    t_str = (
        clean_date_str(target_date)
        if isinstance(target_date, str)
        else (f"{target_date:%Y%m%d}" if isinstance(target_date, date) else None)
    )
    active_ids = load_stock_pool_ids(target_date=t_str, fallback=DEFAULT_STOCK_IDS)
    STOCK_IDS[:] = active_ids
    _stock_indicators_mod.set_stock_ids(active_ids)

    finlab.login()  # 憑證已快取時不會再開瀏覽器

    targets = [
        ind for ind in ALL_INDICATORS
        if not only or any(k in ind.name or k in ind.folder for k in only)
    ]
    results: dict[str, str] = {}
    for i, ind in enumerate(targets, 1):
        path = build_path(ind, day=target_date)
        tag = f"[{i}/{len(targets)}] {ind.folder}/{ind.name}"
        if path.exists() and not overwrite:
            print(f"{tag} 已存在，略過")
            results[ind.name] = "skipped"
            continue
        try:
            res = compute_indicator(ind)
            if isinstance(res, dict):
                data_dict = res
            else:
                data_dict = df_to_compact_json(res, ind.name, is_market=(ind.folder == "大盤"))
            save_dataset(data_dict, path)
            print(f"{tag} -> {path.name} size={path.stat().st_size / 1024:.1f}KB")
            results[ind.name] = "ok"
        except Exception as e:  # noqa: BLE001
            # 額度用完時後續計算必定失敗，直接中止
            if type(e).__name__ == "QuotaExceededError":
                print(f"{tag} 每日額度已用完，中止: {e}")
                results[ind.name] = "quota_exceeded"
                break
            print(f"{tag} 失敗: {type(e).__name__}: {e}")
            results[ind.name] = f"error: {e}"

    failed = [k for k, v in results.items() if v not in ("ok", "skipped")]
    print(f"\n完成: 成功/略過 {len(results) - len(failed)}，失敗 {len(failed)}")
    for k in failed:
        print(f"  - {k}: {results[k]}")
    return results


def load_dataset(name: str, day: str, set_index: bool = True) -> pd.DataFrame:
    """讀取已計算的指標檔 (優先搜尋當層目錄下 {name}_{day}.json，次選 .parquet)。

    name: 指標名稱 (如 'taiex_close_latest', 'roe_latest', 'foreign_net_buy_5d' 等)。
    day:  'YYYYMMDD' (必填)。
    set_index: True 時把 date 欄位還原為索引。
    """
    if not day:
        raise ValueError("load_dataset 必須指定 day (格式 YYYYMMDD)")

    c_day = clean_date_str(day)
    matches = [ind for ind in ALL_INDICATORS if ind.name == name]
    prefix = _safe_filename(name)

    folders_to_search = []
    if matches:
        folders_to_search.append(DATA_ROOT / matches[0].folder)
    else:
        folders_to_search.extend([
            DATA_ROOT / "大盤",
            DATA_ROOT / "基本面",
            DATA_ROOT / "技術面",
            DATA_ROOT / "籌碼面",
        ])

    target_path: Optional[Path] = None
    for folder in folders_to_search:
        if not folder.exists():
            continue
        p_json = folder / f"{prefix}_{c_day}.json"
        if p_json.exists():
            target_path = p_json
            break
        p_parquet = folder / f"{prefix}_{c_day}.parquet"
        if p_parquet.exists():
            target_path = p_parquet
            break

    if target_path is None:
        raise FileNotFoundError(f"找不到指標 {name} 日期為 {c_day} 的資料檔案 (已搜尋當層: {[str(f) for f in folders_to_search]})")

    if target_path.suffix == ".json":
        data = json.loads(target_path.read_text(encoding="utf-8"))
        if "tw_market" in data:
            row_dict = {}
            dt = None
            for metric_col, item in data["tw_market"].items():
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    val, dt = item[0], item[1]
                else:
                    val = item
                row_dict[metric_col] = val
            df = pd.DataFrame([{"date": dt, **row_dict}])
        else:
            rows = []
            for sid, metrics in data.items():
                if sid.startswith("_"):
                    continue
                row = {"stock_id": sid}
                for metric_col, item in metrics.items():
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        val, date_str = item[0], item[1]
                    else:
                        val, date_str = item, ""
                    row[metric_col] = val
                    row["date"] = date_str
                rows.append(row)
            df = pd.DataFrame(rows)
            val_cols = [c for c in df.columns if c not in ("stock_id", "date")]
            if len(val_cols) == 1:
                metric_name = val_cols[0]
                dt = df["date"].iloc[0] if not df.empty and "date" in df.columns else ""
                wide_row = {"date": dt}
                for _, r in df.iterrows():
                    wide_row[r["stock_id"]] = r[metric_name]
                df = pd.DataFrame([wide_row])
    else:
        df = pd.read_parquet(target_path)

    if set_index:
        idx = "date" if "date" in df.columns else df.columns[0]
        df = df.set_index(idx)
    return df


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="以 FinLab 資料計算指標 (大盤、基本面、技術面、籌碼面) 並存成 Compact Array JSON")
    parser.add_argument("--date", type=str, default=None, help="目標日期 (格式 YYYYMMDD 或 YYYY-MM-DD)")
    parser.add_argument("--only", nargs="*", help="只計算名稱或資料夾包含這些關鍵字的指標 (例如: 大盤、基本面、taiex)")
    parser.add_argument("--overwrite", action="store_true", help="當日檔案已存在時仍重新計算")
    args, _ = parser.parse_known_args(argv)

    target_date = prompt_trade_date(args.date, prompt_text="FinLab 市場寬表計算 - 目標日期")
    c_date = clean_date_str(target_date)

    results = download_all(only=args.only, overwrite=args.overwrite, target_date=c_date)
    failed = [k for k, v in results.items() if v not in ("ok", "skipped")]
    if failed:
        raise RuntimeError(f"FinLab 指標計算有 {len(failed)} 個失敗 (不得漏抓): {failed}")

    write_sources_json(day=c_date)
    return 0


if __name__ == "__main__":
    sys.exit(main())
