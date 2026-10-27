"""交易日期處理與終端機互動輸入工具。

支援：
1. 終端機 input() 互動式手動輸入交易日期 (Enter 預設帶入今日)。
2. 日期字串清理 (YYYYMMDD)。
3. YYYYMMDD 與 YYYY-MM-DD 格式互相轉換。
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

TW_TZ = timezone(timedelta(hours=8))


def clean_date_str(date_str: str) -> str:
    """將日期字串中的非數字字元清除，標準化為 YYYYMMDD。"""
    if not date_str:
        return ""
    return re.sub(r"\D", "", str(date_str).strip())


def format_iso_trade_date(date_str: str) -> str:
    """將 YYYYMMDD 格式化為 YYYY-MM-DD。若原本已有橫線且長度合法則直接回傳。"""
    cleaned = clean_date_str(date_str)
    if len(cleaned) == 8:
        return f"{cleaned[:4]}-{cleaned[4:6]}-{cleaned[6:]}"
    return str(date_str).strip()


def prompt_trade_date(
    cli_date: Optional[str] = None,
    prompt_text: str = "請輸入交易日期",
) -> str:
    """取得交易日期 (回傳 YYYYMMDD 格式)。

    邏輯：
    1. 若命令列參數 cli_date 已提供，優先使用該值 (不打擾使用者)。
    2. 若未提供 cli_date，在終端機透過 input() 提示使用者輸入。
       預設值為今日日期 (按 Enter 直接套用)。
    """
    if cli_date and str(cli_date).strip():
        cleaned = clean_date_str(cli_date)
        if len(cleaned) == 8:
            return cleaned
        return str(cli_date).strip()

    today_str = datetime.now(TW_TZ).strftime("%Y%m%d")
    prompt_msg = (
        f"\n>>> [{prompt_text}] (格式 YYYYMMDD，直接按 Enter 預設為今日 {today_str}): "
    )
    try:
        user_input = input(prompt_msg).strip()
        if not user_input:
            print(f" -> 使用預設交易日期: {today_str}")
            return today_str
        cleaned = clean_date_str(user_input)
        if len(cleaned) == 8:
            print(f" -> 已設定交易日期: {cleaned}")
            return cleaned
        print(f" -> 輸入日期: {user_input}")
        return user_input
    except (EOFError, KeyboardInterrupt):
        print(f"\n -> 採用預設交易日期: {today_str}")
        return today_str
