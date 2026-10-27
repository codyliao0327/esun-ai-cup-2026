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

session.cookies.update({
    '_ga': 'GA1.1.616575418.1792862649',
    '__lt__cid': '2ee2beba-f583-41a0-92f9-63e2ffa12682',
    '_qg_fts': '1792862650',
    'QGUserId': '1385138909155198',
    '_qg_cm': '2',
    '_clck': '1j19rpv%5E2%5Egan%5E0%5E2488',
    'AspSession': 'mde4bmqy343z4tee5gwm2ogz',
    'FCNEC': '%5B%5B%22AKsRol-T6_fqTr2aak7prAqNMrdhzoA8O0-fLV5TCYspfRLLENSP6Ykso_GWCBs3IGT5nqYKoMgwId-Pyv2lX6zBdylqn_XV95xpsOLz7T_wPDd4d3-EMMehMSRXo9QMXvLRcF3FEZo91DJYtAQMDNpEkOKchVT_Wg%3D%3D%22%5D%5D',
    'g_state': '{"i_l":0,"i_ll":1793112710436,"i_b":"EiGJogq1VnqsphjFRq9CM6O5Uo6KJE+B0Rumkw8uAW8","i_e":{"enable_itp_optimization":24},"i_et":1793112710436}',
    '__lt__sid': '31313697-b5542917',
    '_clsk': '125fwk2%5E1793112712188%5E1%5E1%5Eq.clarity.ms%2Fcollect',
    '_ga_H3D2MQFGQP': 'GS2.1.s1793112710$o11$g0$t1793112716$j60$l0$h0',
    '_ga_4JFZQM569R': 'GS2.1.s1793112710$o11$g0$t1793112716$j60$l0$h0',
    '_ga_SG15L0JFQ7': 'GS2.1.s1793112710$o10$g1$t1793112716$j60$l0$h472118498',
    '_ga_7VD5TT91L3': 'GS2.1.s1793112710$o11$g0$t1793112716$j54$l0$h0',
    '_ga_32V50L7K4M': 'GS2.1.s1793112710$o10$g1$t1793112717$j58$l0$h0',
    '_gcl_au': '1.1.1605001415.1792862649.-.-.1793009691.1333421889.1793055057.1793112717',
    'FCCDCF': '%5Bnull%2Cnull%2Cnull%2Cnull%2Cnull%2Cnull%2C%5B%5B32%2C%22%5B%5C%2268a41f29-ee81-42d7-b5d7-eb528d8c8028%5C%22%2C%5B1792862649%2C367000000%5D%5D%22%5D%5D%5D',
})

session.headers.update({
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'zh-TW,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
    'authorization': 'Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6IkEydWczbUIxRFQiLCJ0eXAiOiJKV1QifQ.eyJzdWIiOiI0MzYyMjYzIiwidXNlcl9ndWlkIjoiNjU3MzQ4NjUtMzQ5Yy00ZGE2LTllNmQtZmE5MzVmYWIwZjNkIiwidG9rZW5faWQiOiIwIiwiYXBwX2lkIjoiMjEiLCJpc19ndWVzdCI6dHJ1ZSwibmJmIjoxNzkzMTA5MDAwLCJleHAiOjE3OTMxOTkwMDAsImlhdCI6MTc5MzExMjYwMCwiaXNzIjoiaHR0cHM6Ly93d3cuY21vbmV5LnR3IiwiYXVkIjoiY21vbmV5YXBpIn0.UkyXieVxKuqfmWz2Z0hM2IKpE19kttcOTb4O89M41lAf85eMiEPZaXO4cWqwwMtRNGwMGGnrmr5FQRw7-9xqZdxzvKXK8MqAk0nklBOlkWYg-bkBomCO3PQCm_FdHo_9Yt8CgCeYoUoxZS0ABT2kuCZ-w4ldxE5TqgYVeR4dIFmlWHqB1uuY6p3P0_Sc1-DwBBa5bTOU4XQ71nvs5HnItjC1FxQ2DV391f5Jj2Q2Q4AwtjE4WXsXq8Xh6bMdgE8EuqcBheqS28xQM7xbp9X4Ok88gmng3KdGg6WLxebwxUnh1jcvfVcOOK4tqpa-Jyw5MJhBbKS0EdBTJyILg8Hcig',
    'cache-control': 'private max-age=5',
    'cmoneyapi-trace-context': '{"device":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36 Edg/156.0.0.0","deviceId":"daf31bb2-abd9-4d25-afd0-b71830b25c5f"}',
    'priority': 'u=1, i',
    'referer': 'https://www.cmoney.tw/forum/stock/2330?utm_source=chatgpt.com&tab=AISummary',
    'sec-ch-ua': '"Not:A-Brand";v="8", "Chromium";v="156", "Microsoft Edge";v="156"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36 Edg/156.0.0.0',
    # 'cookie': '_ga=GA1.1.616575418.1792862649; __lt__cid=2ee2beba-f583-41a0-92f9-63e2ffa12682; _qg_fts=1792862650; QGUserId=1385138909155198; _qg_cm=2; _clck=1j19rpv%5E2%5Egan%5E0%5E2488; AspSession=mde4bmqy343z4tee5gwm2ogz; FCNEC=%5B%5B%22AKsRol-T6_fqTr2aak7prAqNMrdhzoA8O0-fLV5TCYspfRLLENSP6Ykso_GWCBs3IGT5nqYKoMgwId-Pyv2lX6zBdylqn_XV95xpsOLz7T_wPDd4d3-EMMehMSRXo9QMXvLRcF3FEZo91DJYtAQMDNpEkOKchVT_Wg%3D%3D%22%5D%5D; g_state={"i_l":0,"i_ll":1793112710436,"i_b":"EiGJogq1VnqsphjFRq9CM6O5Uo6KJE+B0Rumkw8uAW8","i_e":{"enable_itp_optimization":24},"i_et":1793112710436}; __lt__sid=31313697-b5542917; _clsk=125fwk2%5E1793112712188%5E1%5E1%5Eq.clarity.ms%2Fcollect; _ga_H3D2MQFGQP=GS2.1.s1793112710$o11$g0$t1793112716$j60$l0$h0; _ga_4JFZQM569R=GS2.1.s1793112710$o11$g0$t1793112716$j60$l0$h0; _ga_SG15L0JFQ7=GS2.1.s1793112710$o10$g1$t1793112716$j60$l0$h472118498; _ga_7VD5TT91L3=GS2.1.s1793112710$o11$g0$t1793112716$j54$l0$h0; _ga_32V50L7K4M=GS2.1.s1793112710$o10$g1$t1793112717$j58$l0$h0; _gcl_au=1.1.1605001415.1792862649.-.-.1793009691.1333421889.1793055057.1793112717; FCCDCF=%5Bnull%2Cnull%2Cnull%2Cnull%2Cnull%2Cnull%2C%5B%5B32%2C%22%5B%5C%2268a41f29-ee81-42d7-b5d7-eb528d8c8028%5C%22%2C%5B1792862649%2C367000000%5D%5D%22%5D%5D%5D',
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
        "1303", "4958", "6505", "8046", "3189", "4938", "1301", "3533", "1802", "6415",
        "1326", "2603", "2368", "2891", "3034", "3037", "2409", "3044", "3653", "2379",
        "2383", "2881", "3231", "2609", "2313", "6446", "2882", "2357", "3443", "3711",
        "2317", "3008", "2345", "2404", "2330", "2887", "3661", "2376", "2382", "2883"
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

    # 4. 轉換成 Pandas DataFrame
    df_sentiment = pd.DataFrame(rows)
    
    if not df_sentiment.empty:
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
    else:
        print("⚠️ 沒有成功抓取到任何資料。")


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