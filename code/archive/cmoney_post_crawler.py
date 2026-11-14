import re
import time
import uuid
import base64
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
import requests
import urllib3
import pandas as pd

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
TW_TZ = timezone(timedelta(hours=8))

session = requests.Session()
session.verify = False
DEVICE_ID = str(uuid.uuid4())

session.headers.update({
    "accept": "application/json, text/plain, */*",
    "accept-language": "zh-TW,zh;q=0.9,en;q=0.8",
    "cmoneyapi-trace-context": json.dumps({
        "device": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0 Safari/537.36",
        "deviceId": DEVICE_ID
    }),
    "content-type": "application/json",
    "origin": "https://www.cmoney.tw",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0 Safari/537.36",
    "x-version": "3.0",
})

def is_token_valid(token: str) -> bool:
    if not token:
        return False
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return payload.get("exp", 0) > (time.time() + 60)
    except Exception:
        return False

def ensure_guest_token(force_refresh: bool = False) -> None:
    current_auth = session.headers.get("authorization", "").replace("Bearer ", "").strip()
    if not force_refresh and is_token_valid(current_auth):
        return

    resp = session.get(
        "https://www.cmoney.tw/forum/stock/2330?tab=discuss",
        headers={"accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
        timeout=15
    )
    resp.raise_for_status()
    tokens = re.findall(r"eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+", resp.text)
    if not tokens:
        raise RuntimeError("無法從 CMoney 網頁原始碼取得訪客 Token")
    session.headers["authorization"] = f"Bearer {tokens[0]}"
    print("🔑 已自動取得最新 CMoney 訪客 Token！")

def parse_article_time(article: Dict[str, Any]) -> Optional[datetime]:
    """強化版時間解析：支援毫秒時間戳與各種長度的 ISO 字串"""
    raw_time = (
        article.get("createTime")
        or article.get("createdAt")
        or article.get("publishTime")
        or article.get("time")
    )
    if not raw_time:
        return None
    try:
        if isinstance(raw_time, (int, float)):
            ts = raw_time / 1000.0 if raw_time > 1e11 else raw_time
            return datetime.fromtimestamp(ts, tz=TW_TZ)
        if isinstance(raw_time, str):
            dt = pd.to_datetime(raw_time)
            if dt.tzinfo is None:
                dt = dt.tz_localize(TW_TZ)
            else:
                dt = dt.tz_convert(TW_TZ)
            return dt.to_pydatetime()
    except Exception:
        return None
    return None

def fetch_articles_until(
    stock_id: str,
    end_date_str: str,
    batch_size: int = 20,
    max_pages: int = 100
) -> List[Dict[str, Any]]:
    """從最新貼文往回抓取，包含 end_date_str 當天（2026-11-13 00:00:00 起）的所有貼文"""
    ensure_guest_token()
    end_dt = datetime.strptime(end_date_str, "%Y-%m-%d").replace(tzinfo=TW_TZ)
    session.headers["referer"] = f"https://www.cmoney.tw/forum/stock/{stock_id}?tab=discuss"

    collected = []
    seen_ids = set()
    start_score = None

    for page in range(1, max_pages + 1):
        params = {"count": batch_size}
        if start_score is not None:
            params["startScore"] = start_score

        url = "https://www.cmoney.tw/api/mach/api/Article/GetChannelsArticleByWeight"
        resp = session.post(url, params=params, json={"items": [f"Stock.{stock_id}"]}, timeout=15)
        if resp.status_code == 401:
            ensure_guest_token(force_refresh=True)
            resp = session.post(url, params=params, json={"items": [f"Stock.{stock_id}"]}, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        articles = data if isinstance(data, list) else (data.get("articles") or data.get("items") or [])
        if not articles:
            print(f"[{stock_id}] 第 {page} 頁已無更多文章，結束抓取。")
            break

        reached_end_date = False
        page_times = []

        for art in articles:
            art_id = art.get("articleId") or art.get("id")
            if art_id in seen_ids:
                continue
            seen_ids.add(art_id)

            art_dt = parse_article_time(art)
            if art_dt:
                page_times.append(art_dt)
                if art_dt < end_dt:
                    reached_end_date = True
                    continue  # 早於 2026-11-13 00:00:00 的貼文不收錄

            collected.append(art)

        oldest_in_page = min(page_times).strftime("%Y-%m-%d %H:%M") if page_times else "未知"
        print(f"[{stock_id}] 第 {page} 頁抓完，累計 {len(collected)} 篇（本頁最舊時間：{oldest_in_page}）")

        if reached_end_date:
            print(f"[{stock_id}] 已抓到早於 {end_date_str} 00:00 的貼文，停止翻頁！")
            break

        last_art = articles[-1]
        next_score = (
            (data.get("nextScore") if isinstance(data, dict) else None)
            or last_art.get("score")
            or last_art.get("weight")
        )
        if not next_score or next_score == start_score:
            print(f"[{stock_id}] 找不到下一頁的 startScore 游標，停止翻頁。")
            break

        start_score = next_score
        time.sleep(0.3)

    return collected

if __name__ == "__main__":
    STOCK_ID = "2330"
    END_DATE = "2026-11-13"

    posts = fetch_articles_until(stock_id=STOCK_ID, end_date_str=END_DATE, batch_size=20, max_pages=10)

    # 將完整貼文資訊存成 JSON 檔（存在執行目錄下）
    out_file = Path(f"cmoney_{STOCK_ID}_posts_{END_DATE.replace('-', '')}.json")
    out_file.write_text(json.dumps(posts, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✅ 測試完成！共收錄 {len(posts)} 篇貼文，完整原始資料已儲存至：{out_file.resolve()}")