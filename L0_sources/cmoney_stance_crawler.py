from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
from typing import Dict, Any, List, Optional  # 👈 這裡補上了 Optional
import requests
import pandas as pd

# 1. 設定台灣時區 (UTC+8)，將毫秒時間戳轉為台灣時間
TW_TZ = timezone(timedelta(hours=8))

def ms_to_tw_str(ms: Optional[int]) -> str:
    """將毫秒 Timestamp 轉換為 YYYY-MM-DD HH:MM"""
    if not ms:
        return ""
    return datetime.fromtimestamp(ms / 1000.0, tz=TW_TZ).strftime("%Y-%m-%d %H:%M")

# 2. 建立 Session 並帶入驗證成功的 Cookies 與 Headers
session = requests.Session()

session.cookies.update({
    '_ga': 'GA1.1.616575418.1792862649',
    '__lt__cid': '2ee2beba-f583-41a0-92f9-63e2ffa12682',
    '_qg_fts': '1792862650',
    'QGUserId': '1385138909155198',
    '_qg_cm': '2',
    'AspSession': '5ptxwsg2wg2ebx2ez4dqbubu',
    '_clck': '1j19rpv%5E2%5Egal%5E0%5E2488',
    '__lt__sid': '31313697-d2a02382',
    '_clsk': 'g5c1z%5E1792963559284%5E8%5E1%5Ei.clarity.ms%2Fcollect',
    'FCNEC': '%5B%5B%22AKsRol9hhw-tMRvZwX2PB5V63Jn9KJCD7InracJyfc35zB77svzuvCAVk4P57RwUlmgLG9x9Oq6Zc24ZahzZr9qpnbrI3fL-RpZi1el5MCdg3DPbLHOoUOehFabgEEOTcNqKv0XBGIYQ2GBihijHs1eVUDeb_oqbVw%3D%3D%22%5D%5D',
    'g_state': '{"i_l":0,"i_ll":1792963559561,"i_b":"JQ2qb1bUSBcBaEOvkkoI56kk7c62V3m1Ly6cyTQM2oc","i_e":{"enable_itp_optimization":24},"i_et":1792963559561}',
    '_ga_4JFZQM569R': 'GS2.1.s1792963470$o5$g1$t1792964791$j60$l0$h0',
    '_ga_SG15L0JFQ7': 'GS2.1.s1792963470$o5$g1$t1792964791$j60$l0$h1168816177',
    '_ga_7VD5TT91L3': 'GS2.1.s1792963470$o5$g1$t1792964791$j60$l0$h0',
    '_ga_H3D2MQFGQP': 'GS2.1.s1792963470$o5$g1$t1792964791$j60$l0$h0',
    '_ga_32V50L7K4M': 'GS2.1.s1792961596$o4$g1$t1792964792$j58$l0$h0',
    'FCCDCF': '%5Bnull%2Cnull%2Cnull%2Cnull%2Cnull%2Cnull%2C%5B%5B32%2C%22%5B%5C%2268a41f29-ee81-42d7-b5d7-eb528d8c8028%5C%22%2C%5B1792862649%2C367000000%5D%5D%22%5D%5D%5D',
    '_gcl_au': '1.1.1605001415.1792862649.1083725803.1792963470.1792963477.1494184096.1792950873.1792964792',
})

session.headers.update({
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'zh-TW,zh;q=0.9,en;q=0.8',
    'authorization': 'Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6IkEydWczbUIxRFQiLCJ0eXAiOiJKV1QifQ.eyJzdWIiOiI0MzYyMjYzIiwidXNlcl9ndWlkIjoiNjU3MzQ4NjUtMzQ5Yy00ZGE2LTllNmQtZmE5MzVmYWIwZjNkIiwidG9rZW5faWQiOiIwIiwiYXBwX2lkIjoiMjEiLCJpc19ndWVzdCI6dHJ1ZSwibmJmIjoxNzkyOTYxMTAwLCJleHAiOjE3OTMwNTExMDAsImlhdCI6MTc5Mjk2NDcwMCwiaXNzIjoiaHR0cHM6Ly93d3cuY21vbmV5LnR3IiwiYXVkIjoiY21vbmV5YXBpIn0.gOkWJR3H2fNlbNQ4i0Ri0dYVqzc_439aQ-hkDz6wed1yZFghTVhrD8qczNHOtF_3RK50VizWRW95fhhaFaNjTxlamGzokt29eFVkG9xg8VLPwjjfL064nJahBKlD0NcaMtMAh6ICZtjcYlqGCzWQBaWFMAVvVK0YwIbxB3p6JMY3YKRuWIYevFr5cz8h7a3RttZtM4mI8Y8tCuO9iUDqiOgf-pyIa_Tj36s7sY9o6bxmWrdDngJsAgB3iOna9OH4X67ei2FubpoT_PEVEHK3UJ3ZB68hBD1b59T3aZE4o92HPBbwMoXM_ZTNiWS23h_Ffg1YZ6Ewh0uNt4a3UMp-jQ',
    'cache-control': 'private max-age=5',
    'cmoneyapi-trace-context': '{"device":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36 Edg/156.0.0.0","deviceId":"daf31bb2-abd9-4d25-afd0-b71830b25c5f"}',
    'priority': 'u=1, i',
    'sec-ch-ua': '"Not:A-Brand";v="8", "Chromium";v="156", "Microsoft Edge";v="156"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36 Edg/156.0.0.0',
})

def get_stock_sentiment(stock_id: str = "2330") -> Dict[str, Any]:
    url = f"https://www.cmoney.tw/api/mach/api/AiSentiment/Stock/{stock_id}"
    session.headers["Referer"] = f"https://www.cmoney.tw/forum/stock/{stock_id}?tab=AISummary"

    resp = session.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json()

def main():
    # 3. 批次抓取多檔股票
    stock_list = [
    "2330", "2454", "2308", "2317", "3711", "2881", "2383", "2303", "2882", "3037",
    "2891", "1303", "2345", "2382", "2408", "7769", "2412", "2327", "6669", "3017",
    "2885", "2887", "2360", "2886", "2059", "6505", "2884", "2880", "2357", "2890",
    "8046", "2344", "3231", "2892", "3008", "2356", "2404", "6515", "3533", "2313",
    "2337", "5871", "3044", "3702", "1101", "2409", "6239", "2609", "2834", "6139",
    "2883", "3443", "3653", "2395", "2301", "6446", "4958", "2603", "5880", "1216",
    "3045", "2368", "3665", "4904", "3481", "2379", "1301", "1326", "3189", "3034",
    "2207", "2002", "2801", "2449", "1590", "3661", "6770", "3036", "2615", "2618",
    "2912", "4938", "2376", "5876", "1519", "6415", "6919", "2324", "2347", "1504",
    "7750", "1402", "1605", "2610", "6789", "1802", "8210", "2451", "2812", "2377"
]
    rows = []

    for sid in stock_list:
        try:
            data = get_stock_sentiment(sid)
            dist = data.get("distribution") or {}
            
            rows.append({
                "股票代號": sid,
                "情緒分數": data.get("sentimentScore"),
                "樣本數": data.get("sampleCount"),
                "狀態": data.get("state"),
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

    # 4. 轉換成 Pandas DataFrame
    df_sentiment = pd.DataFrame(rows)
    
    if not df_sentiment.empty:
        print("\n📊 抓取結果預覽：")
        print(df_sentiment)

        # 5. 設定上上層資料夾與動態檔名 (帶有今天日期)
        # 假設 py 檔在子資料夾中，Path(__file__).resolve().parent.parent.parent 代表上上層
        base_dir = Path(__file__).resolve().parent.parent.parent
        target_dir = base_dir / "data" / "CMoney_Sentiment"
        
        # 自動建立目標資料夾（若不存在）
        target_dir.mkdir(parents=True, exist_ok=True)

        # 取得今天日期並組合成檔名 (例如: cmoney_sentiment_20261026.parquet)
        today_str = datetime.now(TW_TZ).strftime("%Y%m%d")
        file_name = f"cmoney_sentiment_{today_str}.parquet"
        output_path = target_dir / file_name

        # 6. 輸出為 parquet 檔
        df_sentiment.to_parquet(output_path, engine="pyarrow", compression="zstd", index=False)
        print(f"\n💾 檔案已成功儲存至: {output_path}")
    else:
        print("⚠️ 沒有成功抓取到任何資料。")

if __name__ == "__main__":
    main()