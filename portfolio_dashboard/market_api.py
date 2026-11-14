"""
Market API Fetcher for 2026 玉山人工智慧挑戰賽
100% 統一透過玉山證券行情 SDK (REST API) 抓取 150 檔官方標的收盤行情與歷史日線：
  - 使用開發者權限之 intraday.quote 抓取 150 檔即時/收盤報價（600 次/分，無須分批冷卻，內建 429 重試）
  - 以 2330 官方歷史日 K 作為台股開市日曆，並一律以 API 回傳之交易日 (api_date) 作為存檔 Key
  - 自動比對快取與官方開市日曆：缺漏交易日或出現非交易日髒資料時自動觸發歷史重建
  - 盤中防呆提醒：僅於 api_date == 本機今日 且 09:00 <= 現在時間 < 13:35 時發出盤中提示
"""
import os
import json
import time
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 指定 keyrings.cryptfile 後端，使 CLI 終端機自動讀取先前已存好的憑證密碼
os.environ["PYTHON_KEYRING_BACKEND"] = "keyrings.cryptfile.cryptfile.CryptFileKeyring"

from configparser import ConfigParser
from esun_marketdata import EsunMarketdata

DASHBOARD_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = DASHBOARD_DIR.parent.parent
API_DOCS_DIR = PROJECT_ROOT / "docs" / "API說明" / "esun api說明"
CONFIG_PATH = API_DOCS_DIR / "config.ini"
CACHE_FILE = DASHBOARD_DIR / "market_cache.json"
COMPETITION_START_DATE = "2026-10-27"


def init_esun_client():
    """初始化並登入玉山證券行情 SDK 客戶端"""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"找不到玉山 API 設定檔: {CONFIG_PATH}")

    config = ConfigParser()
    config.read(str(CONFIG_PATH), encoding="utf-8")
    cert_file = (CONFIG_PATH.parent / config.get("Cert", "Path")).resolve()
    config.set("Cert", "Path", str(cert_file))

    sdk = EsunMarketdata(config)
    sdk.login()
    return sdk.rest_client.stock


def load_cached_market_data() -> Dict[str, Any]:
    """載入本地行情快取"""
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_cached_market_data(data: Dict[str, Any]):
    """儲存行情快取"""
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_official_trading_dates(client, start_date: str = COMPETITION_START_DATE) -> List[str]:
    """透過 2330 官方歷史日 K 取得自起始日以來的台股真實開市日曆（僅耗 1 次配額）"""
    res = client.historical.candles(symbol="2330", timeframe="D")
    data = res.get("data", []) if isinstance(res, dict) else []
    dates = sorted({c["date"] for c in data if c.get("date", "") >= start_date})
    return dates


def _warn_if_intraday(api_date: str):
    """僅於盤中時段 (09:00 ~ 13:35) 且 API 日期為今日時發出提醒，開盤前或盤後不誤報"""
    now = datetime.now()
    local_today = now.strftime("%Y-%m-%d")
    hhmm = now.strftime("%H:%M")
    if api_date == local_today and "09:00" <= hhmm < "13:35":
        print(f"⚠️ [盤中提醒] 目前為台股盤中時段 ({hhmm})，API 回傳之 {api_date} 價格為盤中即時價，非最終收盤價！")


def _fetch_single_intraday_quote(client, code: str, max_retries: int = 3) -> Optional[Dict[str, Any]]:
    """呼叫 intraday.quote 抓取單檔報價，內建 429 自動冷卻重試"""
    for _ in range(max_retries):
        try:
            q = client.intraday.quote(symbol=code)
            if isinstance(q, dict) and q.get("statusCode") == 429:
                print(f"   ⚠️ 觸發 429 限速，冷卻 62 秒後重試 {code}...")
                time.sleep(62)
                continue
            return q
        except Exception as e:
            print(f"   ⚠️ 連線異常 ({code}): {e}，等待 3 秒重試...")
            time.sleep(3)
    return None


def _parse_intraday_quote(q: Dict[str, Any], meta: Dict[str, str], fallback_date: str) -> Dict[str, Any]:
    code = q.get("symbol") or meta.get("code", "")
    name = meta.get("name", code)
    market = meta.get("market", "上市")
    close_price = float(q.get("closePrice") or 0.0)
    prev_close = float(q.get("previousClose") or close_price)
    change = float(q.get("change") or (close_price - prev_close))
    change_pct = float(q.get("changePercent") or ((change / prev_close * 100) if prev_close else 0.0))
    total = q.get("total") or {}
    volume_lots = round(float(total.get("tradeVolume") or 0.0), 1)
    quote_date = q.get("date") or fallback_date

    return {
        "code": code,
        "name": name,
        "market": market,
        "close_price": round(close_price, 2),
        "prev_close": round(prev_close, 2),
        "change": round(change, 2),
        "change_pct": round(change_pct, 2),
        "volume_lots": volume_lots,
        "trade_value": total.get("tradeValue") or 0,
        "last_updated": quote_date,
    }


def _fetch_quotes_via_intraday(
    client, stocks_150: Dict[str, Dict[str, str]]
) -> Tuple[str, Dict[str, Dict[str, Any]]]:
    """透過 intraday.quote 抓取 150 檔報價（開發者方案 600 次/分，無須分批冷卻）"""
    symbols = list(stocks_150.keys())
    parsed: Dict[str, Dict[str, Any]] = {}
    api_date: Optional[str] = None

    for idx, code in enumerate(symbols, start=1):
        meta = stocks_150.get(code, {})
        name = meta.get("name", code)

        q = _fetch_single_intraday_quote(client, code)
        if isinstance(q, dict) and q.get("closePrice"):
            if not api_date and q.get("date"):
                api_date = q["date"]
            item = _parse_intraday_quote(q, meta, fallback_date=api_date or "")
            parsed[code] = item
            sign = "+" if item["change"] >= 0 else ""
            print(f"[{idx:3d}/{len(symbols)}] {code} {name:<4s}: 現價 {item['close_price']:7.2f} ({sign}{item['change_pct']:5.2f}%)")
        else:
            print(f"[{idx:3d}/{len(symbols)}] ⚠️ {code} {name:<4s}: API 無法取得資料")

    return api_date or "", parsed


def _check_needs_history_rebuild(
    cached_stocks: Dict[str, Any],
    symbols: List[str],
    official_dates: List[str],
    api_date: str,
) -> Tuple[bool, str]:
    """比對快取與 2330 官方開市日曆，自動判斷是否需要重抓 150 檔歷史日線"""
    if not cached_stocks:
        return True, "本地快取為空"

    if not official_dates:
        return False, ""

    official_set = set(official_dates)
    expected_before_api = {d for d in official_dates if d < api_date}

    for code in symbols:
        item = cached_stocks.get(code)
        if not item:
            return True, f"缺少標的 {code} 的快取紀錄"

        dates = item.get("dates") or []
        trend = item.get("trend") or []
        if not dates or not trend or len(dates) != len(trend):
            return True, f"標的 {code} 歷史序列缺漏或長度不一致"

        dates_set = set(dates)
        missing_days = expected_before_api - dates_set
        if missing_days:
            return True, f"標的 {code} 缺少交易日: {sorted(missing_days)}"

        invalid_days = [d for d in dates if d > api_date or (d < api_date and d not in official_set)]
        if invalid_days:
            return True, f"標的 {code} 含有非官方交易日資料: {invalid_days}"

    return False, ""


def rebuild_full_candles(
    stocks_150: Dict[str, Dict[str, str]],
    client=None,
) -> Dict[str, Dict[str, Any]]:
    """調用官方 historical.candles 完整拉取自 2026-10-27 以來的所有官方真實日 K 線 (防呆覆蓋保證)"""
    if client is None:
        client = init_esun_client()
    symbols = list(stocks_150.keys())
    print(f"\n[market_api] 正在透過玉山 API historical.candles 完整重建 150 檔官方歷史日線...")
    print(f"[market_api] 標的數量: {len(symbols)} 檔，分 3 批執行（歷史行情配額保護 60 次/分）...")

    results = {}
    history_candles = {}
    BATCH_SIZE = 50
    call_count = 0

    for idx, code in enumerate(symbols, 1):
        meta = stocks_150.get(code, {})
        name = meta.get("name", code)
        market = meta.get("market", "上市")

        if call_count > 0 and call_count % BATCH_SIZE == 0:
            print(f"\n⏳ [配額保護] 已呼叫 {call_count} 次，冷卻等待 62 秒重置每分鐘配額...")
            time.sleep(62)
            print("   ✅ 配額計數器已重置，繼續執行下一批...\n")

        call_count += 1
        try:
            res = client.historical.candles(symbol=code, timeframe="D")
            data = res.get("data", [])
            comp_candles = [c for c in data if c.get("date", "") >= COMPETITION_START_DATE]
            comp_candles.sort(key=lambda x: x["date"])

            trend = [float(c["close"]) for c in comp_candles]
            history_candles[code] = trend

            latest_c = comp_candles[-1] if comp_candles else {}
            prev_c = comp_candles[-2] if len(comp_candles) >= 2 else latest_c

            close_price = float(latest_c.get("close", 0.0))
            prev_close = float(prev_c.get("close", close_price))
            change = round(close_price - prev_close, 2)
            change_pct = round((change / prev_close * 100), 2) if prev_close else 0.0

            results[code] = {
                "code": code,
                "name": name,
                "market": market,
                "close_price": close_price,
                "prev_close": prev_close,
                "change": change,
                "change_pct": change_pct,
                "volume_lots": round(latest_c.get("volume", 0) / 1000.0, 1),
                "trade_value": 0,
                "last_updated": latest_c.get("date", ""),
                "trend": trend,
                "dates": [c["date"] for c in comp_candles],
            }
            print(f"[{idx:3d}/150] {code} {name:<4s}: {len(trend)} 根日線, 現價 {close_price:7.2f} ({change:+.2f})")
        except Exception as e:
            print(f"[{idx:3d}/150] ⚠️ 抓取 {code} {name} 失敗: {e}")

        time.sleep(0.2)

    save_cached_market_data({
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stocks": results,
        "history_candles": history_candles,
    })
    print(f"\n[market_api] ✅ 150 檔官方歷史日線已 100% 完整覆蓋重建完畢！")
    return results


def fetch_all_150_quotes(
    stocks_150: Dict[str, Dict[str, str]],
    fetch_candles: bool = True,
    force_refresh: bool = False,
) -> Dict[str, Dict[str, Any]]:
    """透過玉山 API 抓取 150 檔最新行情，並依 2330 官方開市日曆自動判斷是否需補抓歷史日線"""
    client = init_esun_client()
    cache = load_cached_market_data()
    cached_stocks = cache.get("stocks", {})
    history_candles = cache.get("history_candles", {})

    symbols = list(stocks_150.keys())
    if not symbols:
        print("[market_api] ⚠️ 警告：傳入的 150 檔標的清單為空！終止抓取以防止清空本地快取。")
        return cached_stocks

    # 1. 取得 2330 官方開市日曆（僅 1 次歷史 API 請求）
    official_dates: List[str] = []
    try:
        official_dates = fetch_official_trading_dates(client)
        print(f"[market_api] 📅 2330 官方開市日曆已同步（共 {len(official_dates)} 個交易日，最新至 {official_dates[-1] if official_dates else '無'}）")
    except Exception as e:
        print(f"[market_api] ⚠️ 無法取得 2330 官方日曆，將略過自動歷史比對: {e}")

    # 2. 透過 intraday.quote 抓取 150 檔最新行情（開發者方案 600 次/分，無須分批冷卻）
    print("\n[market_api] 正在透過玉山 API intraday.quote 抓取 150 檔最新行情...")
    api_date, fetched_quotes = _fetch_quotes_via_intraday(client, stocks_150)

    if not api_date:
        print("[market_api] ⚠️ 無法取得 API 交易日期，保留本地快取。")
        return cached_stocks

    _warn_if_intraday(api_date)

    # 3. 檢查是否需要自動觸發歷史日線重建（若 fetch_candles=True）
    if fetch_candles and official_dates:
        need_rebuild, reason = _check_needs_history_rebuild(cached_stocks, symbols, official_dates, api_date)
        if need_rebuild:
            print(f"\n[market_api] 🔄 自動偵測到需重建歷史日線（原因：{reason}），自動執行 rebuild_full_candles...")
            cached_stocks = rebuild_full_candles(stocks_150, client=client)
            history_candles = {c: v.get("trend", []) for c, v in cached_stocks.items()}

    # 4. 以 API 回傳的 api_date 為 Key，將最新行情安全寫入/覆蓋對應交易日
    results: Dict[str, Dict[str, Any]] = {}
    for code in symbols:
        meta = stocks_150.get(code, {})
        existing_item = cached_stocks.get(code, {})
        fresh_item = fetched_quotes.get(code)

        if fresh_item and fresh_item.get("close_price", 0) > 0:
            item = fresh_item
        else:
            item = {
                "code": code,
                "name": meta.get("name", code),
                "market": meta.get("market", "上市"),
                "close_price": existing_item.get("close_price", 0.0),
                "prev_close": existing_item.get("prev_close", 0.0),
                "change": existing_item.get("change", 0.0),
                "change_pct": existing_item.get("change_pct", 0.0),
                "volume_lots": existing_item.get("volume_lots", 0.0),
                "trade_value": existing_item.get("trade_value", 0),
                "last_updated": existing_item.get("last_updated", api_date),
            }

        existing_dates = existing_item.get("dates") or []
        existing_trend = history_candles.get(code, []) or existing_item.get("trend", [])

        date_map: Dict[str, float] = {}
        if existing_dates and len(existing_dates) == len(existing_trend):
            for d, p in zip(existing_dates, existing_trend):
                if not official_dates or d in official_dates or d == api_date:
                    date_map[d] = p

        latest_c = item.get("close_price", 0.0)
        if latest_c > 0:
            date_map[item["last_updated"]] = latest_c

        sorted_keys = sorted(date_map.keys())
        trend = [date_map[k] for k in sorted_keys]
        item["dates"] = sorted_keys
        item["trend"] = trend
        history_candles[code] = trend
        results[code] = item

    save_cached_market_data({
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stocks": results,
        "history_candles": history_candles,
    })

    print(f"\n[market_api] ✅ 150 檔行情已 100% 同步完畢（交易日：{api_date}）！")
    return results


if __name__ == "__main__":
    from tracker import load_150_stocks
    stocks_150 = load_150_stocks()
    quotes = fetch_all_150_quotes(stocks_150)
    print(f"4938 和碩: {quotes.get('4938')}")
    print(f"3231 緯創: {quotes.get('3231')}")
