"""台股大盤與全市場指標定義庫。

此模組專門維護全市場與加權指數（大盤）的計算演算法與公式：
1. 設定全域 START_DATE = "2026-07-01"（確保 60 日均線有充足交易日）。
2. 大盤指標不綁定特定 40 檔個股 whitelist，於全市場資料中計算。
3. 每個指標回傳 pd.DataFrame，單列（最新交易日），index 為 date，欄位為指標名稱。
4. 登記於 ALL_MARKET_INDICATORS 清單供 finlab_market_loader.py 存至 data/大盤/。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Union
import pandas as pd

# 計算資料起始日期 (需要至少 60 交易日以計算 60MA)
START_DATE: str = "2026-07-01"


@dataclass(frozen=True)
class MarketIndicator:
    name: str                           # 指標唯一名稱 (如 'taiex_close_latest')
    folder: str                         # 存檔目錄: 固定為 '大盤'
    func: Callable[[], Union[pd.DataFrame, dict]] # 計算函式，回傳單列 DataFrame 或 Compact Array JSON dict
    description: str = ""               # 中文說明與單位


def _format_result(series_or_df: pd.Series | pd.DataFrame, col_name: str) -> pd.DataFrame:
    """將計算結果統一格式化為單列 DataFrame，index 名為 date，欄位為指標名稱。"""
    if isinstance(series_or_df, pd.Series):
        df = series_or_df.to_frame(name=col_name)
    else:
        df = series_or_df.copy()
        df.columns = [col_name]
    df.index.name = "date"
    return df.iloc[[-1]]


# --------------------------------------------------------------------------- #
# 大盤與全市場指標定義
# --------------------------------------------------------------------------- #
def taiex_close_latest() -> pd.DataFrame:
    """加權指數最新收盤價 (單位：點)。"""
    from finlab import data

    p = data.get("taiex_total_index:收盤指數", start=START_DATE)
    res = (p.iloc[[-1]]).round(2)
    return _format_result(res, "taiex_close_latest")


def taiex_return_20d() -> pd.DataFrame:
    """加權指數近 20 日報酬率 (單位：%)。"""
    from finlab import data

    p = data.get("taiex_total_index:收盤指數", start=START_DATE)
    res = ((p.iloc[[-1]] / p.iloc[[-21]] - 1) * 100).round(2)
    return _format_result(res, "taiex_return_20d")


def taiex_ma20_latest() -> pd.DataFrame:
    """加權指數 20 日均線 (單位：點)。"""
    from finlab import data

    p = data.get("taiex_total_index:收盤指數", start=START_DATE)
    res = (p.rolling(20).mean().iloc[[-1]]).round(2)
    return _format_result(res, "taiex_ma20_latest")


def taiex_ma60_latest() -> pd.DataFrame:
    """加權指數 60 日均線 (單位：點)。"""
    from finlab import data

    p = data.get("taiex_total_index:收盤指數", start=START_DATE)
    res = (p.rolling(60).mean().iloc[[-1]]).round(2)
    return _format_result(res, "taiex_ma60_latest")


def taiex_max_drawdown_20d() -> pd.DataFrame:
    """加權指數近 20 日最大回撤，負值表示跌幅 (單位：%)。"""
    from finlab import data

    p = data.get("taiex_total_index:收盤指數", start=START_DATE)
    recent = p.iloc[-20:]
    running_high = recent.cummax()
    drawdown = (recent / running_high - 1) * 100
    res = drawdown.min().to_frame().T.round(2)
    res.index = [p.index[-1]]
    return _format_result(res, "taiex_max_drawdown_20d")


def market_foreign_net_buy_20d() -> pd.DataFrame:
    """外資近 20 日全市場(上市)淨買賣超金額 (單位：元)。"""
    from finlab import data

    foreign = data.get("institutional_investors_trading_all_market_summary:買賣超", start=START_DATE)["上市外資及陸資(不含外資自營商)"]
    res = (foreign.rolling(20).sum().iloc[[-1]]).round(2)
    return _format_result(res, "market_foreign_net_buy_20d")


def market_trust_net_buy_20d() -> pd.DataFrame:
    """投信近 20 日全市場(上市)淨買賣超金額 (單位：元)。"""
    from finlab import data

    trust = data.get("institutional_investors_trading_all_market_summary:買賣超", start=START_DATE)["上市投信"]
    res = (trust.rolling(20).sum().iloc[[-1]]).round(2)
    return _format_result(res, "market_trust_net_buy_20d")


def market_advance_decline_ratio() -> pd.DataFrame:
    """全市場股票漲跌家數比 (單位：倍)。注意：不可受限於個股 whitelist。"""
    from finlab import data

    up = data.get("limit_up_down_count:上漲")["股票"]
    down = data.get("limit_up_down_count:下跌")["股票"]
    down = down.reindex(up.index)
    up_count = up.iloc[[-1]]
    down_count = down.iloc[[-1]]
    res = (up_count / down_count).round(2)
    return _format_result(res, "market_advance_decline_ratio")


def listed_margin_balance_change_5d() -> pd.DataFrame:
    """上市市場融資交易金額餘額近 5 日變化率 (單位：%)。"""
    from finlab import data

    margin = data.get("margin_balance:融資券總餘額", start=START_DATE)["上市融資交易金額"]
    res = (((margin.iloc[[-1]] / margin.iloc[-6]) - 1) * 100).round(2)
    return _format_result(res, "listed_margin_balance_change_5d")


def market_alignment() -> dict:
    """10. 全市場多空排列家數差 (單位：家)。"""
    from finlab import data

    with data.universe():
        close = data.get("price:收盤價").sort_index()

    ma5 = close.average(5)
    ma10 = close.average(10)
    ma30 = close.average(30)

    if close.empty or not (
        ma5.notna() & ma10.notna() & ma30.notna()
    ).iloc[-1].any():
        raise ValueError("最新交易日的均線資料不足")

    bullish = (ma5 >= ma10) & (ma10 >= ma30)
    bearish = (ma5 < ma10) & (ma10 < ma30)

    bullish_count = int(bullish.iloc[-1].sum())
    bearish_count = int(bearish.iloc[-1].sum())
    alignment_count_diff = bullish_count - bearish_count
    last_date = str(close.index[-1])[:10]

    return {
        "_format": "[value, date]",
        "tw_market": {
            "market_alignment_diff": [alignment_count_diff, last_date]
        }
    }


def listed_market_lifeline() -> dict:
    """11. 生命線：加權報酬指數與月線關係 (單位：%)。"""
    from finlab import data
    import pandas as pd

    index = data.get("benchmark_return:發行量加權股價報酬指數")
    index = index.squeeze("columns").sort_index()

    if not isinstance(index, pd.Series):
        raise ValueError("預期加權報酬指數只有一個數值欄位")

    ma20 = index.rolling(20).mean()

    if len(index) < 25 or index.iloc[-25:].isna().any() or (index.iloc[-25:] <= 0).any():
        raise ValueError("計算生命線需要最近25個交易日的有效報酬指數")

    index_vs_ma20_pct = round(float((index.iloc[-1] / ma20.iloc[-1] - 1) * 100), 2)
    ma20_change_5d_pct = round(float((ma20.iloc[-1] / ma20.iloc[-6] - 1) * 100), 2)
    last_date = str(index.index[-1])[:10]

    return {
        "_format": "[value, date]",
        "tw_market": {
            "index_vs_ma20_pct": [index_vs_ma20_pct, last_date],
            "ma20_change_5d_pct": [ma20_change_5d_pct, last_date]
        }
    }


# --------------------------------------------------------------------------- #
# 大盤指標總清單登記
# --------------------------------------------------------------------------- #
ALL_MARKET_INDICATORS: list[MarketIndicator] = [
    MarketIndicator("taiex_close_latest", "大盤", taiex_close_latest, "加權指數最新收盤價 (點)"),
    MarketIndicator("taiex_return_20d", "大盤", taiex_return_20d, "加權指數近20日報酬率 (%)"),
    MarketIndicator("taiex_ma20_latest", "大盤", taiex_ma20_latest, "加權指數20日均線 (點)"),
    MarketIndicator("taiex_ma60_latest", "大盤", taiex_ma60_latest, "加權指數60日均線 (點)"),
    MarketIndicator("taiex_max_drawdown_20d", "大盤", taiex_max_drawdown_20d, "加權指數近20日最大回撤 (%)"),
    MarketIndicator("market_foreign_net_buy_20d", "大盤", market_foreign_net_buy_20d, "外資近20日上市買賣超金額 (元)"),
    MarketIndicator("market_trust_net_buy_20d", "大盤", market_trust_net_buy_20d, "投信近20日上市買賣超金額 (元)"),
    MarketIndicator("market_advance_decline_ratio", "大盤", market_advance_decline_ratio, "全市場股票漲跌家數比 (倍)"),
    MarketIndicator("listed_margin_balance_change_5d", "大盤", listed_margin_balance_change_5d, "上市融資餘額近5日變化率 (%)"),
    MarketIndicator("market_alignment", "大盤", market_alignment, "全市場多空排列家數差 (家)"),
    MarketIndicator("market_lifeline", "大盤", listed_market_lifeline, "加權報酬指數生命線與月線關係 (%)"),
]
