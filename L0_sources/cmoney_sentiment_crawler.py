import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
from typing import Dict, Any, List, Optional
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

# 2. 建立 Session 並帶入驗證成功的 Cookies 與 Headers
session = requests.Session()
# 忽略 CMoney 伺服器缺少 Subject Key Identifier 之 SSL 憑證驗證問題
session.verify = False

session.headers.update({
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'zh-TW,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
    'authorization': 'Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6IkEydWczbUIxRFQiLCJ0eXAiOiJKV1QifQ.eyJzdWIiOiI0MzYyMjYzIiwidXNlcl9ndWlkIjoiNjU3MzQ4NjUtMzQ5Yy00ZGE2LTllNmQtZmE5MzVmYWIwZjNkIiwidG9rZW5faWQiOiIwIiwiYXBwX2lkIjoiMjEiLCJpc19ndWVzdCI6dHJ1ZSwibmJmIjoxNzk0MTQwNzAwLCJleHAiOjE3OTQyMzA3MDAsImlhdCI6MTc5NDE0NDMwMCwiaXNzIjoiaHR0cHM6Ly93d3cuY21vbmV5LnR3IiwiYXVkIjoiY21vbmV5YXBpIn0.Ob9eC8ZZA74pJzq0tZazxqaJLe5tRR1Qddi4ut0SIh9tFtqUF2cwYmZwtB0GPkd0SGqXrZCzq7FG7v62atY2TXaAQeKOwmHFGjVzVX_aSsSETsn6p3pRzZRQGSqUzvu1_IrQknsffQE4jGfpyfvaGXqj4HI7ZjLfciFD2Lcm_UZw86epIpfYnjUcRGCii9ozFh1_ZoCIZIhkNqJiAhlxb3R9Z0HG6fX1e9ecHBrjJA0AVL5A98fckPY7Pm-De5ZX82eIipK43Kv4ax2Voz4dmBI0NaF7VXeOj-dxpfQ05cqHkeKfstB8GTCiyIGWxl-xeFPDF56qtSrci_Q4QH_0VA',
    'cache-control': 'private max-age=5',
    'cmoneyapi-trace-context': '{"device":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36 Edg/157.0.0.0","deviceId":"daf31bb2-abd9-4d25-afd0-b71830b25c5f"}',
    'priority': 'u=1, i',
    'referer': 'https://www.cmoney.tw/forum/stock/2330?utm_source=chatgpt.com&tab=AISummary',
    'sec-ch-ua': '"Not-A.Brand";v="99", "Microsoft Edge";v="157", "Chromium";v="157"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36 Edg/157.0.0.0',
    # 'cookie': '_ga=GA1.1.616575418.1792862649; __lt__cid=2ee2beba-f583-41a0-92f9-63e2ffa12682; _qg_fts=1792862650; QGUserId=1385138909155198; AspSession=qdw1vkqigvntgtfdvui1fdvl; _ga_5XLZWTV92B=GS2.1.s1793465416$o2$g0$t1793465416$j60$l0$h0; _clck=1j19rpv%5E2%5Egaz%5E0%5E2488; _qg_cm=2; FCNEC=%5B%5B%22AKsRol9a8yOx1wtgUdb9-aTCyLUcT_sftPD73v8XzoG4KQ5D-82l1kPHhlygLWz7RiZFJSzsXW6dTylJJlDG81KFGZSmivBasQ%3D%3D%22%5D%5D; g_state={"i_l":0,"i_ll":1794144366560,"i_b":"P8agA8QXu09erByc4zpnxCjGE8rBPjs0w31wmfWu3Qo","i_e":{"enable_itp_optimization":24},"i_et":1794144366560}; __lt__sid=31313697-cb0b5cde; _clsk=vh34b8%5E1794144367540%5E1%5E1%5Ef.clarity.ms%2Fcollect; _ga_7VD5TT91L3=GS2.1.s1794144366$o23$g0$t1794144375$j60$l0$h0; _ga_H3D2MQFGQP=GS2.1.s1794144366$o22$g0$t1794144375$j60$l0$h0; _ga_4JFZQM569R=GS2.1.s1794144366$o23$g0$t1794144375$j60$l0$h0; _ga_SG15L0JFQ7=GS2.1.s1794144366$o21$g1$t1794144375$j60$l0$h1116897774; _ga_32V50L7K4M=GS2.1.s1794144366$o23$g1$t1794144375$j52$l0$h0; _gcl_au=1.1.1605001415.1792862649.585204758.1794129260.1794144376.1342686813.1794129260.1794144376; FCCDCF=%5Bnull%2Cnull%2Cnull%2Cnull%2Cnull%2Cnull%2C%5B%5B32%2C%22%5B%5C%2268a41f29-ee81-42d7-b5d7-eb528d8c8028%5C%22%2C%5B1792862649%2C367000000%5D%5D%22%5D%5D%5D',
})

def get_stock_sentiment(stock_id: str = "2330") -> Dict[str, Any]:
    url = f"https://www.cmoney.tw/api/mach/api/AiSentiment/Stock/{stock_id}"
    session.headers["Referer"] = f"https://www.cmoney.tw/forum/stock/{stock_id}?tab=AISummary"

    resp = session.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json()

def main(target_date: Optional[str] = None):
    # 3. 批次抓取多檔股票
    stock_list = [
        # "0050", "00631L", "00685L",
        "1101", "1216", "1402", "1504", "1802", "1815", "2002", "2059", "2207", "2317",
        "2330", "2379", "2382", "2412", "2449", "2451", "2603", "2609", "2610", "2615",
        "2618", "2801", "2812", "2834", "2880", "2881", "2882", "2884", "2885", "2886",
        "2887", "2890", "2891", "2892", "2912", "3045", "3105", "3227", "3260", "3293",
        "3324", "3374", "3491", "4123", "4904", "4938", "5274", "5289", "5871", "5876",
        "5880", "5903", "6023", "6121", "6415", "6446", "8069", "8415", "8932",
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
                # "狀態": data.get("state"),
                "極度樂觀": dist.get("strongBull", 0),
                "樂觀": dist.get("bull", 0),
                "中立": dist.get("neutral", 0),
                "謹慎": dist.get("bear", 0),
                "極度謹慎": dist.get("strongBear", 0),
                # "統計開始時間": ms_to_tw_str(data.get("startTime")),
                # "統計結束時間": ms_to_tw_str(data.get("endTime")),
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