import sys
import re
import time
import uuid
import base64
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
from typing import Dict, Any, Optional
import requests
import urllib3
import pandas as pd

# 關閉 SSL 不安全連線警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 1. 設定台灣時區 (UTC+8)，將毫秒時間戳轉為台灣時間
TW_TZ = timezone(timedelta(hours=8))

def ms_to_tw_str(ms: Optional[int]) -> str:
    """將毫秒 Timestamp 轉換為 YYYY-MM-DD HH:MM"""
    if not ms:
        return ""
    return datetime.fromtimestamp(ms / 1000.0, tz=TW_TZ).strftime("%Y-%m-%d %H:%M")

# 2. 建立 Session 並設定基礎瀏覽器標頭（不再需要寫死 Cookie 與 Authorization）
session = requests.Session()
session.verify = False
DEVICE_ID = str(uuid.uuid4())

session.headers.update({
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'zh-TW,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
    'cache-control': 'private max-age=5',
    'cmoneyapi-trace-context': json.dumps({
        "device": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "deviceId": DEVICE_ID
    }),
    'referer': 'https://www.cmoney.tw/forum/stock/2330?tab=AISummary',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
})

def is_token_valid(token: str) -> bool:
    """解碼 JWT 檢查 Token 是否仍在有效期限內（預留 60 秒緩衝）"""
    if not token:
        return False
    try:
        payload_b64 = token.split('.')[1]
        payload_b64 += '=' * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return payload.get('exp', 0) > (time.time() + 60)
    except Exception:
        return False

def ensure_guest_token(force_refresh: bool = False) -> None:
    """從 CMoney SSR 網頁自動萃取最新的訪客 JWT Token"""
    current_auth = session.headers.get('authorization', '').replace('Bearer ', '').strip()
    if not force_refresh and is_token_valid(current_auth):
        return

    resp = session.get(
        "https://www.cmoney.tw/forum/stock/2330?tab=AISummary",
        headers={"accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
        timeout=15
    )
    resp.raise_for_status()

    tokens = re.findall(r'eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+', resp.text)
    if not tokens:
        raise RuntimeError("無法從 CMoney 網頁原始碼中取得訪客 Token！")

    session.headers['authorization'] = f"Bearer {tokens[0]}"
    print("🔑 已自動取得最新 CMoney 訪客 Token！")

def get_stock_sentiment(stock_id: str = "2330") -> Dict[str, Any]:
    ensure_guest_token()
    url = f"https://www.cmoney.tw/api/mach/api/AiSentiment/Stock/{stock_id}"
    session.headers["referer"] = f"https://www.cmoney.tw/forum/stock/{stock_id}?tab=AISummary"

    resp = session.get(url, timeout=15)
    # 若執行中途遇到 401，強制重抓一次新 Token 並重試
    if resp.status_code == 401:
        ensure_guest_token(force_refresh=True)
        resp = session.get(url, timeout=15)

    resp.raise_for_status()
    return resp.json()

def main(target_date: Optional[str] = None):
    # 先取得一次 Guest Token，後續 68 檔直接共用同一個 Token
    ensure_guest_token()

    # 3. 批次抓取多檔股票 (依 20261117_68檔股票池.csv)
    stock_list = [
        "1101", "1216", "1301", "1303", "1326", "1402", "1590", "1785", "1802", "1815",
        "2002", "2207", "2313", "2317", "2330", "2379", "2404", "2409", "2412", "2454",
        "2603", "2609", "2610", "2618", "2801", "2812", "2834", "2880", "2881", "2882",
        "2883", "2884", "2885", "2886", "2887", "2890", "2891", "2892", "2912", "3045",
        "3105", "3227", "3293", "3374", "3443", "3491", "3529", "3533", "3661", "4123",
        "4749", "4904", "5347", "5536", "5871", "5876", "5880", "5903", "6023", "6223",
        "6446", "6505", "6510", "6548", "6919", "7828", "8069", "8415",
    ]

    rows = []
    failed_stocks = []

    for sid in stock_list:
        try:
            data = get_stock_sentiment(sid)
            dist = data.get("distribution") or {}
            
            rows.append({
                "股票代號": sid,
                "情緒分數": data.get("sentimentScore"),
                "樣本數": data.get("sampleCount"),
                "極度樂觀": dist.get("strongBull", 0),
                "樂觀": dist.get("bull", 0),
                "中立": dist.get("neutral", 0),
                "謹慎": dist.get("bear", 0),
                "極度謹慎": dist.get("strongBear", 0),
                "統計開始時間": ms_to_tw_str(data.get("startTime")),
                "統計結束時間": ms_to_tw_str(data.get("endTime")),
            })
            print(f"✅ 成功抓取 {sid}")
        except Exception as e:
            print(f"❌ 抓取 {sid} 失敗: {e}")
            failed_stocks.append((sid, str(e)))

    if failed_stocks:
        raise RuntimeError(
            f"CMoney 個股情緒抓取失敗！共有 {len(failed_stocks)} 檔股票抓取失敗 (必須全數成功，不得漏抓): "
            f"{[f'{s}: {err}' for s, err in failed_stocks]}"
        )

    # 4. 轉換成 Pandas DataFrame
    df_sentiment = pd.DataFrame(rows)
    
    if df_sentiment.empty or len(df_sentiment) != len(stock_list):
        raise RuntimeError(
            f"CMoney 個股情緒資料不完整！預期 {len(stock_list)} 檔，實際取得 {len(df_sentiment)} 檔。"
        )

    print("\n📊 抓取結果預覽：")
    print(df_sentiment)

    # 5. 設定上上層資料夾與動態檔名
    base_dir = Path(__file__).resolve().parent.parent.parent
    target_dir = base_dir / "data" / "CMoney_Sentiment"
    target_dir.mkdir(parents=True, exist_ok=True)

    target_date_str = target_date or datetime.now(TW_TZ).strftime("%Y%m%d")
    file_name = f"cmoney_sentiment_{target_date_str}.parquet"
    output_path = target_dir / file_name

    # 6. 輸出為 parquet 檔
    df_sentiment.to_parquet(output_path, engine="pyarrow", compression="zstd", index=False)
    print(f"\n💾 檔案已成功儲存至: {output_path}")

    # 7. 輸出 D-Plan L0 sources JSON
    write_sources_json(base_dir, target_date_str)


def write_sources_json(base_dir: Path, target_date_str: str) -> Path:
    """輸出 D-Plan L0 sources JSON(陣列);content_as_of 為程式執行當下時間(+08:00)。"""
    source = {
        "source_id": "S2",
        "authority": "vendor",
        "url": "https://www.cmoney.tw/forum/stock",
        "content_as_of": datetime.now(TW_TZ).isoformat(timespec="seconds"),
        "name": "CMoney",
    }
    out_dir = base_dir / "data" / "D-Paln_Output" / "l0_sources"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"s2_cmoney_sentiment_sources_{target_date_str}.json"
    path.write_text(json.dumps([source], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"📄 sources JSON 已儲存至: {path}")
    return path


if __name__ == "__main__":
    import argparse
    # 設定 code/ 為匯入路徑
    CODE_DIR = Path(__file__).resolve().parents[1]
    if str(CODE_DIR) not in sys.path:
        sys.path.insert(0, str(CODE_DIR))
    from configs.date_utils import clean_date_str, prompt_trade_date

    parser = argparse.ArgumentParser(description="CMoney 討論區個股情緒爬蟲")
    parser.add_argument("--date", type=str, default=None, help="目標日期 (格式 YYYYMMDD 或 YYYY-MM-DD)")
    args = parser.parse_args()

    t_date = prompt_trade_date(args.date, prompt_text="CMoney 情緒爬蟲 - 目標日期")
    c_date = clean_date_str(t_date)
    main(target_date=c_date)