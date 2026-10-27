"""台股個股指標定義庫（基本面、技術面、籌碼面）。

此模組專門維護所有指標的計算演算法與公式：
1. 設定全域 START_DATE = "2026-09-01"。
2. 每個指標為一個向量化函式，在 FinLab universe 範圍內一次計算所有股票。
3. 回傳格式為 pd.DataFrame，單列（最新一筆），index 為日期/季度，columns 為各股票代碼。
4. 登記於 ALL_INDICATORS 清單供 finlab_market_loader.py 批次排程與存檔。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional
import pandas as pd

# 計算資料起始日期
START_DATE: str = "2026-09-01"


@dataclass(frozen=True)
class Indicator:
    name: str                           # 檔案名稱與指標 key (如 'excess_return_20d')
    folder: str                         # 存檔目錄: '基本面' | '技術面' | '籌碼面'
    func: Callable[[], pd.DataFrame]    # 向量化計算函式，回傳 (1 x N) DataFrame
    description: str = ""               # 指標中文說明與單位


# --------------------------------------------------------------------------- #
# 1. 基本面指標 (存至 data/基本面/)
# --------------------------------------------------------------------------- #
def roe_latest() -> pd.DataFrame:
    """最新季 ROE 稅後 (基本面，單位：%)。"""
    from finlab import data

    # 取得全體股票季ROE資料
    roe = data.get("fundamental_features:ROE稅後")
    # 優先取 2026-Q2，若無則取最新一季
    if "2026-Q2" in roe.index:
        return roe.loc[["2026-Q2"]].round(2)
    return roe.iloc[[-1]].round(2)


def revenue_yoy_latest() -> pd.DataFrame:
    """最新月營收年增率 (基本面，單位：%)。"""
    from finlab import data

    revenue = data.get("monthly_revenue:去年同月增減(%)", start=START_DATE)
    return revenue.iloc[[-1]].round(2)


def revenue_mom_latest() -> pd.DataFrame:
    """最新月營收月增率 (基本面，單位：%)。"""
    from finlab import data

    revenue = data.get("monthly_revenue:上月比較增減(%)", start=START_DATE)
    return revenue.iloc[[-1]].round(2)


# --------------------------------------------------------------------------- #
# 2. 技術面指標 (存至 data/技術面/)
# --------------------------------------------------------------------------- #
def close_latest() -> pd.DataFrame:
    """最新收盤價 (技術面，單位：元/股)。"""
    from finlab import data

    close = data.get("price:收盤價", start=START_DATE)
    return close.iloc[[-1]].round(2)


def return_5d() -> pd.DataFrame:
    """近 5 日還原報酬率 (技術面，單位：%)。"""
    from finlab import data

    p = data.get("etl:adj_close", start=START_DATE)
    return ((p.iloc[[-1]] / p.iloc[[-6]] - 1) * 100).round(2)


def return_20d() -> pd.DataFrame:
    """近 20 日還原報酬率 (技術面，單位：%)。"""
    from finlab import data

    p = data.get("etl:adj_close", start=START_DATE)
    return ((p.iloc[[-1]] / p.iloc[[-21]] - 1) * 100).round(2)


def excess_return_20d() -> pd.DataFrame:
    """近 20 日相對大盤報酬差 (技術面，單位：百分點 pp)。"""
    from finlab import data

    p = data.get("etl:adj_close", start=START_DATE)
    b = data.get("benchmark_return:發行量加權股價報酬指數", start=START_DATE)

    # 以收盤價 p 的 index 為基準對齊大盤，收盤價沒有的日期直接忽略
    b = b.squeeze("columns").reindex(p.index).ffill()

    # 計算最後一筆相較於前 20 個交易日的報酬率 (%)
    stock_return_20d = (p.iloc[[-1]] / p.iloc[-21].values - 1) * 100
    bench_return_20d = (b.iloc[-1] / b.iloc[-21] - 1) * 100

    return (stock_return_20d - bench_return_20d).round(2)


def volume_ma5_to_ma20() -> pd.DataFrame:
    """5 日均量 / 20 日均量比值 (技術面，單位：倍)。"""
    from finlab import data

    volume = data.get("price:成交股數", start=START_DATE)
    volume_ma5 = volume.rolling(5).mean().iloc[[-1]]
    volume_ma20 = volume.rolling(20).mean().iloc[[-1]]
    return (volume_ma5 / volume_ma20).round(2)


def amount_ma20() -> pd.DataFrame:
    """20 日平均成交金額 (技術面，單位：元)。"""
    from finlab import data

    amount = data.get("price:成交金額", start=START_DATE)
    return (amount.rolling(20).mean().iloc[[-1]]).round(2)


def volatility_10d() -> pd.DataFrame:
    """10 日報酬波動率，未年化 (技術面，單位：%)。"""
    from finlab import data

    p = data.get("etl:adj_close", start=START_DATE)
    daily_return = p / p.shift(1) - 1
    return (daily_return.rolling(10).std(ddof=1).iloc[[-1]] * 100).round(2)


def ma20_change_5d() -> pd.DataFrame:
    """20 日均線近 5 日變化率 (技術面，單位：%)。"""
    from finlab import data

    p = data.get("etl:adj_close", start=START_DATE)
    ma20 = p.rolling(20).mean()
    return ((ma20.iloc[[-1]] / ma20.iloc[[-6]] - 1) * 100).round(2)


def price_vs_ma20() -> pd.DataFrame:
    """20 日均線乖離率 (技術面，單位：%)。"""
    from finlab import data

    p = data.get("etl:adj_close", start=START_DATE)
    ma20 = p.rolling(20).mean().iloc[[-1]]
    return ((p.iloc[-1] / ma20 - 1) * 100).round(2)


def rsi_14() -> pd.DataFrame:
    """14 日 RSI 相對強弱指標 (技術面，範圍：0~100)。"""
    from finlab import data

    rsi = data.indicator("RSI", adjust_price=True, timeperiod=14)
    return (rsi.iloc[[-1]]).round(2)


# --------------------------------------------------------------------------- #
# 3. 籌碼面指標 (存至 data/籌碼面/)
# --------------------------------------------------------------------------- #
def foreign_net_buy_intensity_5d() -> pd.DataFrame:
    """外資近 5 日買賣超強度（外資買賣超/成交量）(籌碼面，單位：%)。"""
    from finlab import data

    volume = data.get("price:成交股數", start=START_DATE)
    foreign = data.get("institutional_investors_trading_summary:外陸資買賣超股數(不含外資自營商)", start=START_DATE)
    foreign = foreign.reindex(volume.index)
    return (foreign.rolling(5).sum().iloc[[-1]] / volume.rolling(5).sum().iloc[[-1]] * 100).round(2)


def foreign_net_buy_1d() -> pd.DataFrame:
    """外資最新交易日買賣超股數 (籌碼面，單位：股)。"""
    from finlab import data

    foreign = data.get("institutional_investors_trading_summary:外陸資買賣超股數(不含外資自營商)", start=START_DATE)
    return foreign.iloc[[-1]]


def trust_net_buy_intensity_5d() -> pd.DataFrame:
    """投信近 5 日買賣超強度（投信買賣超/成交量）(籌碼面，單位：%)。"""
    from finlab import data

    volume = data.get("price:成交股數", start=START_DATE)
    trust = data.get("institutional_investors_trading_summary:投信買賣超股數", start=START_DATE)
    trust = trust.reindex(volume.index)
    return (trust.rolling(5).sum().iloc[[-1]] / volume.rolling(5).sum().iloc[[-1]] * 100).round(2)


def trust_net_buy_1d() -> pd.DataFrame:
    """投信最新交易日買賣超股數 (籌碼面，單位：股)。"""
    from finlab import data

    trust = data.get("institutional_investors_trading_summary:投信買賣超股數", start=START_DATE)
    return trust.iloc[[-1]]


# --------------------------------------------------------------------------- #
# 指標總清單登記
# --------------------------------------------------------------------------- #
ALL_INDICATORS: list[Indicator] = [
    # 基本面 (3)
    Indicator("roe_latest", "基本面", roe_latest, "最新季 ROE 稅後 (%)"),
    Indicator("revenue_yoy_latest", "基本面", revenue_yoy_latest, "最新月營收年增率 (%)"),
    Indicator("revenue_mom_latest", "基本面", revenue_mom_latest, "最新月營收月增率 (%)"),
    # 技術面 (10)
    Indicator("close_latest", "技術面", close_latest, "最新收盤價 (元)"),
    Indicator("return_5d", "技術面", return_5d, "近5日報酬率 (%)"),
    Indicator("return_20d", "技術面", return_20d, "近20日報酬率 (%)"),
    Indicator("excess_return_20d", "技術面", excess_return_20d, "近20日相對大盤報酬差 (pp)"),
    Indicator("volume_ma5_to_ma20", "技術面", volume_ma5_to_ma20, "5日均量/20日均量比值 (倍)"),
    Indicator("amount_ma20", "技術面", amount_ma20, "20日平均成交金額 (元)"),
    Indicator("volatility_10d", "技術面", volatility_10d, "10日報酬波動率 (%)"),
    Indicator("ma20_change_5d", "技術面", ma20_change_5d, "20日均線近5日變化率 (%)"),
    Indicator("price_vs_ma20", "技術面", price_vs_ma20, "20日均線乖離率 (%)"),
    Indicator("rsi_14", "技術面", rsi_14, "14日 RSI (0~100)"),
    # 籌碼面 (4)
    Indicator("foreign_net_buy_intensity_5d", "籌碼面", foreign_net_buy_intensity_5d, "外資近5日買賣超強度 (%)"),
    Indicator("foreign_net_buy_1d", "籌碼面", foreign_net_buy_1d, "外資最新交易日買賣超 (股)"),
    Indicator("trust_net_buy_intensity_5d", "籌碼面", trust_net_buy_intensity_5d, "投信近5日買賣超強度 (%)"),
    Indicator("trust_net_buy_1d", "籌碼面", trust_net_buy_1d, "投信最新交易日買賣超 (股)"),
]
