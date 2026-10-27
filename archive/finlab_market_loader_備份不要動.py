"""透過 FinLab API 抓取台股市場資料。

依據 data/Data Directory Structure.md 的清單,逐一下載資料並存到對應資料夾,
檔名格式:``<檔案名稱>_<YYYYMMDD>.parquet``(YYYYMMDD 為執行當日日期)。

儲存格式選擇 Parquet(zstd 壓縮):
- 欄式儲存 + 壓縮,對「日期 x 股票」的寬表通常比 CSV 小 5~10 倍。
- 保留 dtype(float / datetime),讀回時不需重新 parse,速度快。
- pandas / polars / DuckDB / Spark 皆可直接讀取。

用法::

    python finlab_market_loader.py                 # 下載全部
    python finlab_market_loader.py --only price_收盤價 M1   # 只下載名稱或資料夾含關鍵字者
    python finlab_market_loader.py --overwrite     # 當日檔案已存在時仍重新下載

在其他程式中讀取::

    from finlab_market_loader import load_dataset
    close = load_dataset("price_收盤價")           # 自動讀取最新日期的檔案
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

# 專案根目錄 / data(本檔位於 code/L0_sources/)
DATA_ROOT = Path(__file__).resolve().parents[2] / "data"
START_DATE = "2025-04-24"
FILE_FORMAT = "parquet"
PARQUET_COMPRESSION = "zstd"

# 只下載這 40 檔個股(以 data.universe(whitelist=...) 篩選)
STOCK_IDS: list[str] = [
    "1303", "4958", "6505", "8046", "3189", "4938", "1301", "3533", "1802", "6415",
    "1326", "2603", "2368", "2891", "3034", "3037", "2409", "3044", "3653", "2379",
    "2383", "2881", "3231", "2609", "2313", "6446", "2882", "2357", "3443", "3711",
    "2317", "3008", "2345", "2404", "2330", "2887", "3661", "2376", "2382", "2883",
]

# D-Plan L0 資料來源層 sources 輸出位置
SOURCES_DIR = DATA_ROOT / "D-Paln_Output" / "l0_sources"
SOURCES_PREFIX = "s1_finlab_market_sources"


@dataclass(frozen=True)
class Dataset:
    folder: str          # 資料夾目錄
    name: str            # 檔案名稱(不含日期與副檔名)
    key: str             # data.get 的資料集 key
    column: Optional[str] = None  # 若需取表中某欄位(如 company_basic_info)
    use_range: bool = True        # 是否帶 start/end 參數


# DATASETS: list[Dataset] = [
#     Dataset("M1_市場趨勢", "taiex_total_index_收盤指數", "taiex_total_index:收盤指數"),
#     Dataset("M2_市場風險", "margin_transactions_融資使用率", "margin_transactions:融資使用率"),
#     Dataset("M2_市場風險", "margin_transactions_融資今日餘額", "margin_transactions:融資今日餘額"),
#     Dataset("M2_市場風險", "tw_credit_trading_daily_擔保維持率", "tw_credit_trading_daily:擔保維持率"),
#     Dataset("M3_市場資金與交易情緒", "market_transaction_info_成交金額", "market_transaction_info:成交金額"),
#     Dataset("F1_企業財務品質", "fundamental_features_ROE稅後", "fundamental_features:ROE稅後"),
#     Dataset("F1_企業財務品質", "fundamental_features_ROA稅後息前", "fundamental_features:ROA稅後息前"),
#     Dataset("F1_企業財務品質", "fundamental_features_營業毛利率", "fundamental_features:營業毛利率"),
#     Dataset("F1_企業財務品質", "fundamental_features_營業利益率", "fundamental_features:營業利益率"),
#     Dataset("F1_企業財務品質", "fundamental_features_稅後淨利率", "fundamental_features:稅後淨利率"),
#     Dataset("F1_企業財務品質", "fundamental_features_負債比率", "fundamental_features:負債比率"),
#     Dataset("F1_企業財務品質", "fundamental_features_流動比率", "fundamental_features:流動比率"),
#     Dataset("F1_企業財務品質", "financial_statement_營業活動之淨現金流入_流出", "financial_statement:營業活動之淨現金流入_流出"),
#     Dataset("F1_企業財務品質", "fundamental_features_自由現金流量", "fundamental_features:自由現金流量"),
#     Dataset("F1_企業財務品質", "fundamental_features_業外收支營收率", "fundamental_features:業外收支營收率"),
#     Dataset("F2_企業營運成長", "financial_statement_每股盈餘", "financial_statement:每股盈餘"),
#     Dataset("F2_企業營運成長", "monthly_revenue_當月營收", "monthly_revenue:當月營收"),
#     Dataset("F2_企業營運成長", "monthly_revenue_去年同月增減(%)", "monthly_revenue:去年同月增減(%)"),
#     Dataset("F1F2_估值與產業脈絡", "price_earning_ratio_本益比", "price_earning_ratio:本益比"),
#     Dataset("F1F2_估值與產業脈絡", "price_earning_ratio_股價淨值比", "price_earning_ratio:股價淨值比"),
#     Dataset("F1F2_估值與產業脈絡", "etl_market_value", "etl:market_value"),
#     # 公司基本資料無日期維度,不帶 start/end,只取「產業類別」欄位
#     Dataset("F1F2_估值與產業脈絡", "company_basic_info", "company_basic_info", column="產業類別", use_range=False),
#     Dataset("F4_股價與籌碼動能", "price_開盤價", "price:開盤價"),
#     Dataset("F4_股價與籌碼動能", "price_最高價", "price:最高價"),
#     Dataset("F4_股價與籌碼動能", "price_最低價", "price:最低價"),
#     Dataset("F4_股價與籌碼動能", "price_收盤價", "price:收盤價"),
#     Dataset("F4_股價與籌碼動能", "price_成交股數", "price:成交股數"),
#     Dataset("F4_股價與籌碼動能", "price_成交金額", "price:成交金額"),
#     Dataset("F4_股價與籌碼動能", "institutional_investors_trading_summary_投信買賣超股數",
#             "institutional_investors_trading_summary:投信買賣超股數"),
#     Dataset("F4_股價與籌碼動能", "institutional_investors_trading_summary_外陸資買賣超股數(不含外資自營商)",
#             "institutional_investors_trading_summary:外陸資買賣超股數(不含外資自營商)"),
#     Dataset("F4_股價與籌碼動能", "foreign_investors_shareholding_全體外資及陸資持股比率",
#             "foreign_investors_shareholding:全體外資及陸資持股比率"),
# ]

DATASETS: list[Dataset] = [
    Dataset("F1_企業財務品質", "fundamental_features_ROE稅後", "fundamental_features:ROE稅後"),
    Dataset("F4_股價與籌碼動能", "price_收盤價", "price:收盤價"),
]

# --------------------------------------------------------------------------- #
# 工具函式
# --------------------------------------------------------------------------- #
def _safe_filename(name: str) -> str:
    """移除 Windows 不允許的檔名字元(<>:"/\\|?*)。"""
    return re.sub(r'[<>:"/\\|?*]', "_", name)


def build_path(ds: Dataset, day: Optional[date] = None) -> Path:
    day = day or date.today()
    fname = f"{_safe_filename(ds.name)}_{day:%Y%m%d}.{FILE_FORMAT}"
    return DATA_ROOT / ds.folder / fname


def _to_frame(obj) -> pd.DataFrame:
    """統一轉成 DataFrame,並確保 parquet 可寫入(欄名為字串、日期索引變成欄位)。"""
    df = obj.to_frame() if isinstance(obj, pd.Series) else pd.DataFrame(obj)
    # finlab 回傳的是 FinLabDataFrame(pandas 子類別),轉回純 DataFrame
    df = pd.DataFrame(df)
    df.columns = df.columns.astype(str)
    if df.index.name is None:
        df.index.name = "date" if isinstance(df.index, pd.DatetimeIndex) else "symbol"
    return df.reset_index()


def fetch_dataset(ds: Dataset) -> pd.DataFrame:
    from finlab import data  # 延遲匯入,讓 load_dataset 不需安裝 finlab

    today = date.today().isoformat()
    # 全市場指標(如加權指數、大盤成交金額)無個股欄位,下方欄位過濾無命中時會保留原表
    with data.universe(whitelist=STOCK_IDS):
        if ds.use_range:
            raw = data.get(ds.key, start=START_DATE, end=today)
        else:
            raw = data.get(ds.key)
    if ds.column is not None:
        raw = raw[ds.column]
    # 保險再過濾:寬表以欄位(股票代號)、公司基本資料以索引(股票代號)
    if isinstance(raw, pd.Series):
        raw = raw[raw.index.astype(str).isin(STOCK_IDS)]
    else:
        cols = [c for c in raw.columns if str(c) in STOCK_IDS]
        if cols:
            raw = raw[cols]
    return _to_frame(raw)


def save_dataset(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, engine="pyarrow", compression=PARQUET_COMPRESSION, index=False)


def write_sources_json(day: Optional[date] = None) -> Path:
    """輸出 D-Plan L0 sources JSON;content_as_of 為程式執行當下時間(含時區)。"""
    day = day or date.today()
    # schema 規定時間戳一律為台北時區 +08:00
    now_tpe = datetime.now(timezone(timedelta(hours=8)))
    source = {
        "source_id": "S1",
        "authority": "vendor",  # schema enum 為 vendor
        "url": "https://finlab.finance",
        "content_as_of": now_tpe.isoformat(timespec="seconds"),
        "name": "FinLab",
    }
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    path = SOURCES_DIR / f"{SOURCES_PREFIX}_{day:%Y%m%d}.json"
    # D-Plan 的 sources 為陣列(1~50 筆)
    path.write_text(json.dumps([source], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"sources JSON -> {path}")
    return path


# --------------------------------------------------------------------------- #
# 對外 API
# --------------------------------------------------------------------------- #
def download_all(only: Optional[list[str]] = None, overwrite: bool = False) -> dict[str, str]:
    """下載所有(或符合關鍵字的)資料集,回傳 {檔案名稱: 狀態}。"""
    import finlab

    finlab.login()  # 憑證已快取時不會再開瀏覽器

    targets = [
        ds for ds in DATASETS
        if not only or any(k in ds.name or k in ds.folder for k in only)
    ]
    results: dict[str, str] = {}
    for i, ds in enumerate(targets, 1):
        path = build_path(ds)
        tag = f"[{i}/{len(targets)}] {ds.folder}/{ds.name}"
        if path.exists() and not overwrite:
            print(f"{tag} 已存在,略過")
            results[ds.name] = "skipped"
            continue
        try:
            df = fetch_dataset(ds)
            save_dataset(df, path)
            print(f"{tag} -> {path.name} shape={df.shape} size={path.stat().st_size / 1024:.1f}KB")
            results[ds.name] = "ok"
        except Exception as e:  # noqa: BLE001
            # 額度用完時後續下載必定失敗,直接中止
            if type(e).__name__ == "QuotaExceededError":
                print(f"{tag} 每日額度已用完,中止:{e}")
                results[ds.name] = "quota_exceeded"
                break
            print(f"{tag} 失敗:{type(e).__name__}: {e}")
            results[ds.name] = f"error: {e}"

    failed = [k for k, v in results.items() if v not in ("ok", "skipped")]
    print(f"\n完成:成功/略過 {len(results) - len(failed)},失敗 {len(failed)}")
    for k in failed:
        print(f"  - {k}: {results[k]}")
    return results


def load_dataset(name: str, day: Optional[str] = None, set_index: bool = True) -> pd.DataFrame:
    """讀取已下載資料。

    name: 檔案名稱(如 'price_收盤價')。
    day:  'YYYYMMDD';None 時讀取該資料集最新日期的檔案。
    set_index: True 時把 date(或 symbol)欄位還原為索引,得到「日期 x 股票」寬表。
    """
    matches = [ds for ds in DATASETS if ds.name == name]
    if not matches:
        raise KeyError(f"未知資料集:{name}")
    ds = matches[0]
    folder = DATA_ROOT / ds.folder
    prefix = _safe_filename(ds.name)
    if day:
        path = folder / f"{prefix}_{day}.{FILE_FORMAT}"
    else:
        # 檔名固定以 _YYYYMMDD 結尾,用 regex 避免 price_成交股數 誤配 price_成交股數_xxx
        pat = re.compile(rf"^{re.escape(prefix)}_(\d{{8}})\.{FILE_FORMAT}$")
        files = sorted(p for p in folder.glob(f"{prefix}_*.{FILE_FORMAT}") if pat.match(p.name))
        if not files:
            raise FileNotFoundError(f"{folder} 找不到 {prefix}_*.{FILE_FORMAT}")
        path = files[-1]
    df = pd.read_parquet(path)
    if set_index:
        idx = "date" if "date" in df.columns else df.columns[0]
        df = df.set_index(idx)
    return df


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="下載 FinLab 市場資料並存成 parquet")
    parser.add_argument("--only", nargs="*", help="只下載名稱或資料夾包含這些關鍵字的資料集")
    parser.add_argument("--overwrite", action="store_true", help="當日檔案已存在時仍重新下載")
    args, _ = parser.parse_known_args(argv)
    results = download_all(only=args.only, overwrite=args.overwrite)
    write_sources_json()
    return 0 if all(v in ("ok", "skipped") for v in results.values()) else 1


if __name__ == "__main__":
    main()
