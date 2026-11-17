"""台股個股指標定義庫（基本面、技術面、籌碼面）。

此模組專門維護所有指標的計算演算法與公式：
1. 設定全域 START_DATE = "2026-09-01"。
2. 每個指標為一個向量化函式，在 FinLab universe 範圍內一次計算所有股票。
3. 回傳格式為 pd.DataFrame（單列最新一筆）或 Compact Array JSON dict（各股最新一筆，如 KD/MACD/布林/基本面）。
4. 登記於 ALL_INDICATORS 清單供 finlab_market_loader.py 批次排程與存檔。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional, Union
import pandas as pd

# 計算資料起始日期 (確保有足夠 60 交易日計算季線與 60 日百分位)
START_DATE: str = "2026-07-01"

# 目標 68 檔個股 (依 20261117_68檔股票池.csv)
STOCK_IDS: list[str] = [
    "1101", "1216", "1301", "1303", "1326", "1402", "1590", "1785", "1802", "1815",
    "2002", "2207", "2313", "2317", "2330", "2379", "2404", "2409", "2412", "2454",
    "2603", "2609", "2610", "2618", "2801", "2812", "2834", "2880", "2881", "2882",
    "2883", "2884", "2885", "2886", "2887", "2890", "2891", "2892", "2912", "3045",
    "3105", "3227", "3293", "3374", "3443", "3491", "3529", "3533", "3661", "4123",
    "4749", "4904", "5347", "5536", "5871", "5876", "5880", "5903", "6023", "6223",
    "6446", "6505", "6510", "6548", "6919", "7828", "8069", "8415",
]


@dataclass(frozen=True)
class Indicator:
    name: str                           # 檔案名稱與指標 key (如 'excess_return_5d')
    folder: str                         # 存檔目錄: '基本面' | '技術面' | '籌碼面'
    func: Callable[[], Union[pd.DataFrame, dict]] # 計算函式，回傳 (1 x N) DataFrame 或 Compact Array JSON dict
    description: str = ""               # 指標中文說明與單位


# --------------------------------------------------------------------------- #
# 1. 基本面指標 (存至 data/基本面/)
# --------------------------------------------------------------------------- #
def roe_latest() -> dict:
    """最新季 ROE 稅後 (基本面，單位：%)。

    依每檔股票取最新一筆非空值之季度與數值 (若有 Q3 則取 Q3，無 Q3 則向前遞補取 Q2)。
    回傳 Compact Array JSON 字典。
    """
    from finlab import data

    roe = data.get("fundamental_features:ROE稅後")
    out = {"_format": "[value, date]"}

    for sid in STOCK_IDS:
        if sid not in roe.columns:
            continue
        s = roe[sid].dropna()
        if s.empty:
            continue
        dt = str(s.index[-1]).strip()
        if len(dt) > 10 and " " in dt:
            dt = dt.split()[0]
        out[sid] = {"roe_latest": [round(float(s.iloc[-1]), 2), dt]}
    return out


def revenue_yoy_latest() -> dict:
    """最新月營收年增率 (基本面，單位：%)。

    依每檔股票取最新一筆非空值之營收發布日與數值 (若有 11 月則取 11 月，無 11 月則向前遞補取 10 月)。
    回傳 Compact Array JSON 字典。
    """
    from finlab import data

    revenue = data.get("monthly_revenue:去年同月增減(%)", start=START_DATE)
    out = {"_format": "[value, date]"}

    for sid in STOCK_IDS:
        if sid not in revenue.columns:
            continue
        s = revenue[sid].dropna()
        if s.empty:
            continue
        dt = str(s.index[-1]).strip()
        if len(dt) > 10 and " " in dt:
            dt = dt.split()[0]
        out[sid] = {"revenue_yoy_latest": [round(float(s.iloc[-1]), 2), dt]}
    return out


def revenue_mom_latest() -> dict:
    """最新月營收月增率 (基本面，單位：%)。

    依每檔股票取最新一筆非空值之營收發布日與數值 (若有 11 月則取 11 月，無 11 月則向前遞補取 10 月)。
    回傳 Compact Array JSON 字典。
    """
    from finlab import data

    revenue = data.get("monthly_revenue:上月比較增減(%)", start=START_DATE)
    out = {"_format": "[value, date]"}

    for sid in STOCK_IDS:
        if sid not in revenue.columns:
            continue
        s = revenue[sid].dropna()
        if s.empty:
            continue
        dt = str(s.index[-1]).strip()
        if len(dt) > 10 and " " in dt:
            dt = dt.split()[0]
        out[sid] = {"revenue_mom_latest": [round(float(s.iloc[-1]), 2), dt]}
    return out


# --------------------------------------------------------------------------- #
# 2. 技術面指標 (存至 data/技術面/)
# --------------------------------------------------------------------------- #
def close_latest() -> pd.DataFrame:
    """最新收盤價 (技術面，單位：元/股)。"""
    from finlab import data

    close = data.get("price:收盤價", start=START_DATE)
    return close.iloc[[-1]].round(2)


def return_1d() -> pd.DataFrame:
    """當日還原漲跌幅 (技術面，單位：%)。"""
    from finlab import data

    p = data.get("etl:adj_close", start=START_DATE)
    return ((p.iloc[[-1]] / p.iloc[[-2]] - 1) * 100).round(2)


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


def excess_return_5d() -> pd.DataFrame:
    """近 5 日相對大盤報酬差 (技術面，單位：百分點 pp)。"""
    from finlab import data

    p = data.get("etl:adj_close", start=START_DATE)
    b = data.get("benchmark_return:發行量加權股價報酬指數", start=START_DATE)

    # 以收盤價 p 的 index 為基準對齊大盤，收盤價沒有的日期直接忽略
    b = b.squeeze("columns").reindex(p.index).ffill()

    # 計算最後一筆相較於前 5 個交易日的報酬率 (%)
    stock_return_5d = (p.iloc[[-1]] / p.iloc[-6].values - 1) * 100
    bench_return_5d = (b.iloc[-1] / b.iloc[-6] - 1) * 100

    return (stock_return_5d - bench_return_5d).round(2)


def volume_ratio_1d() -> pd.DataFrame:
    """當日量比（今日成交量 / 近10日平均成交量不含今日）(技術面，單位：倍)。"""
    from finlab import data

    volume = data.get("price:成交股數", start=START_DATE)
    ma10_prev = volume.shift(1).rolling(10).mean().iloc[[-1]]
    return (volume.iloc[[-1]] / ma10_prev).round(2)


def volume_ratio_3d() -> pd.DataFrame:
    """近 3 日量比（近3日均量 / 近3日之前10日均量）(技術面，單位：倍)。"""
    from finlab import data

    volume = data.get("price:成交股數", start=START_DATE)
    ma3 = volume.rolling(3).mean().iloc[[-1]]
    ma10_prev = volume.shift(3).rolling(10).mean().iloc[[-1]]
    return (ma3 / ma10_prev).round(2)


def volume_ma5_to_ma20() -> pd.DataFrame:
    """5 日均量 / 20 日均量比值 (技術面，單位：倍)。"""
    from finlab import data

    volume = data.get("price:成交股數", start=START_DATE)
    volume_ma5 = volume.rolling(5).mean().iloc[[-1]]
    volume_ma20 = volume.rolling(20).mean().iloc[[-1]]
    return (volume_ma5 / volume_ma20).round(2)


def amount_ma5() -> pd.DataFrame:
    """5 日平均成交金額 (技術面，單位：元)。"""
    from finlab import data

    amount = data.get("price:成交金額", start=START_DATE)
    return (amount.rolling(5).mean().iloc[[-1]]).round(2)


def volatility_10d() -> pd.DataFrame:
    """10 日報酬波動率，未年化 (技術面，單位：%)。"""
    from finlab import data

    p = data.get("etl:adj_close", start=START_DATE)
    daily_return = p / p.shift(1) - 1
    return (daily_return.rolling(10).std(ddof=1).iloc[[-1]] * 100).round(2)


def ma10_change_3d() -> pd.DataFrame:
    """10 日均線近 3 日變化率 (技術面，單位：%)。"""
    from finlab import data

    p = data.get("etl:adj_close", start=START_DATE)
    ma10 = p.rolling(10).mean()
    return ((ma10.iloc[[-1]] / ma10.iloc[[-4]] - 1) * 100).round(2)


def price_vs_ma5() -> pd.DataFrame:
    """5 日均線乖離率 (技術面，單位：%)。"""
    from finlab import data

    p = data.get("etl:adj_close", start=START_DATE)
    ma5 = p.rolling(5).mean().iloc[[-1]]
    return ((p.iloc[-1] / ma5 - 1) * 100).round(2)


def price_vs_ma20() -> pd.DataFrame:
    """20 日均線乖離率 (技術面，單位：%)。"""
    from finlab import data

    p = data.get("etl:adj_close", start=START_DATE)
    ma20 = p.rolling(20).mean().iloc[[-1]]
    return ((p.iloc[-1] / ma20 - 1) * 100).round(2)


def price_range_pos_10d() -> pd.DataFrame:
    """10 日價格區間相對位置 (技術面，單位：%)。0%位於最低點；100%位於最高點。"""
    from finlab import data

    p = data.get("etl:adj_close", start=START_DATE)
    high_10 = p.rolling(10).max().iloc[[-1]]
    low_10 = p.rolling(10).min().iloc[[-1]]
    diff = high_10 - low_10
    pos = (p.iloc[[-1]] - low_10) / diff.where(diff != 0) * 100
    return pos.round(2)


def price_dist_to_high_10d() -> pd.DataFrame:
    """距離 10 日高點的幅度 (技術面，單位：%)。例如 -2% 代表現價比高點低 2%。"""
    from finlab import data

    p = data.get("etl:adj_close", start=START_DATE)
    high_10 = p.rolling(10).max().iloc[[-1]]
    return ((p.iloc[[-1]] / high_10 - 1) * 100).round(2)


def price_dist_to_low_10d() -> pd.DataFrame:
    """距離 10 日低點的幅度 (技術面，單位：%)。例如 +8% 代表現價比低點高 8%。"""
    from finlab import data

    p = data.get("etl:adj_close", start=START_DATE)
    low_10 = p.rolling(10).min().iloc[[-1]]
    return ((p.iloc[[-1]] / low_10 - 1) * 100).round(2)


def price_vs_min_close_10d() -> pd.DataFrame:
    """距前 10 日最低收盤價幅度（負值代表跌破）(技術面，單位：%)。"""
    from finlab import data

    p = data.get("price:收盤價", start=START_DATE)
    min_10 = p.shift(1).rolling(10).min().iloc[[-1]]
    return ((p.iloc[[-1]] / min_10 - 1) * 100).round(2)


def rsi_7() -> pd.DataFrame:
    """7 日 RSI 相對強弱指標 (技術面，範圍：0~100)。"""
    from finlab import data

    rsi = data.indicator("RSI", adjust_price=True, timeperiod=7)
    return (rsi.iloc[[-1]]).round(2)


def kd_latest() -> dict:
    """18. KD指標 (5, 3, 3) 與交叉動態 (技術面)。"""
    from finlab import data

    k, d = data.indicator(
        "STOCH", adjust_price=True,
        fastk_period=5,
        slowk_period=3, slowk_matype=0,
        slowd_period=3, slowd_matype=0
    )
    last_date = str(k.index[-1])[:10]
    out = {"_format": "[value, date]"}

    for sid in STOCK_IDS:
        if sid not in k.columns:
            continue
        ks = k[sid].dropna()
        ds = d[sid].reindex(ks.index).dropna()
        common_idx = ks.index.intersection(ds.index)
        if len(common_idx) < 21:
            continue
        ks = ks.loc[common_idx]
        ds = ds.loc[common_idx]

        k_val = round(float(ks.iloc[-1]), 2)
        d_val = round(float(ds.iloc[-1]), 2)
        k_change_3d = round(float(ks.iloc[-1] - ks.iloc[-4]), 2)

        gap = ks - ds
        above_d_days = 0
        below_d_days = 0
        for val in gap.iloc[::-1]:
            if pd.isna(val) or val <= 0:
                break
            above_d_days += 1
        for val in gap.iloc[::-1]:
            if pd.isna(val) or val >= 0:
                break
            below_d_days += 1

        cross_up = (ks.shift(1) <= ds.shift(1)) & (ks > ds)
        cross_down = (ks.shift(1) >= ds.shift(1)) & (ks < ds)
        crossed = cross_up | cross_down
        cross_days_ago = -1
        for days_ago in range(min(20, len(crossed))):
            if crossed.iloc[-1 - days_ago]:
                cross_days_ago = days_ago
                break

        out[sid] = {
            "k_5": [k_val, last_date],
            "d_5": [d_val, last_date],
            "k_change_3d": [k_change_3d, last_date],
            "kd_above_d_days": [above_d_days, last_date],
            "kd_below_d_days": [below_d_days, last_date],
            "kd_cross_days_ago_20d": [cross_days_ago, last_date]
        }
    return out


def macd_latest() -> dict:
    """19. MACD指標 (6, 13, 5) 與柱狀動態 (技術面)。"""
    from finlab import data

    dif, signal, hist = data.indicator(
        "MACD", adjust_price=True,
        fastperiod=6, slowperiod=13, signalperiod=5
    )
    last_date = str(dif.index[-1])[:10]
    out = {"_format": "[value, date]"}

    for sid in STOCK_IDS:
        if sid not in dif.columns:
            continue
        dfs = dif[sid].dropna()
        sigs = signal[sid].reindex(dfs.index).dropna()
        hists = hist[sid].reindex(dfs.index).dropna()
        common_idx = dfs.index.intersection(sigs.index).intersection(hists.index)
        if len(common_idx) < 21:
            continue
        dfs = dfs.loc[common_idx]
        sigs = sigs.loc[common_idx]
        hists = hists.loc[common_idx]

        dif_val = round(float(dfs.iloc[-1]), 2)
        hist_val = round(float(hists.iloc[-1]), 2)
        hist_change_3d = round(float(hists.iloc[-1] - hists.iloc[-4]), 2)

        hist_change = hists.diff()
        hist_increasing_days = 0
        hist_decreasing_days = 0
        for change in hist_change.iloc[::-1]:
            if pd.isna(change) or change <= 0:
                break
            hist_increasing_days += 1
        for change in hist_change.iloc[::-1]:
            if pd.isna(change) or change >= 0:
                break
            hist_decreasing_days += 1

        cross_up = (dfs.shift(1) <= sigs.shift(1)) & (dfs > sigs)
        cross_down = (dfs.shift(1) >= sigs.shift(1)) & (dfs < sigs)
        crossed = cross_up | cross_down
        cross_days_ago = -1
        for days_ago in range(min(20, len(crossed))):
            if crossed.iloc[-1 - days_ago]:
                cross_days_ago = days_ago
                break

        out[sid] = {
            "macd_dif": [dif_val, last_date],
            "macd_hist": [hist_val, last_date],
            "macd_hist_change_3d": [hist_change_3d, last_date],
            "macd_hist_increasing_days": [hist_increasing_days, last_date],
            "macd_hist_decreasing_days": [hist_decreasing_days, last_date],
            "macd_cross_days_ago_20d": [cross_days_ago, last_date]
        }
    return out


def bollinger_latest() -> dict:
    """20. 布林通道 (10日, 1.9個標準差) 與頻寬動態 (技術面)。"""
    from finlab import data

    upper, middle, lower = data.indicator(
        "BBANDS", adjust_price=True,
        timeperiod=10, nbdevup=1.9, nbdevdn=1.9, matype=0
    )
    price = data.get("etl:adj_close")
    last_date = str(price.index[-1])[:10]
    out = {"_format": "[value, date]"}

    for sid in STOCK_IDS:
        if sid not in price.columns:
            continue
        p = price[sid].dropna()
        u = upper[sid].reindex(p.index).dropna()
        m = middle[sid].reindex(p.index).dropna()
        l = lower[sid].reindex(p.index).dropna()
        common_idx = p.index.intersection(u.index).intersection(m.index).intersection(l.index)
        if len(common_idx) < 60:
            continue
        p = p.loc[common_idx]
        u = u.loc[common_idx]
        m = m.loc[common_idx]
        l = l.loc[common_idx]

        bw = (u - l) / m.where(m != 0) * 100
        if len(bw) < 60 or bw.iloc[-60:].isna().any():
            continue

        width = u.iloc[-1] - l.iloc[-1]
        if width <= 0:
            continue
        pos_pct = round(float((p.iloc[-1] - l.iloc[-1]) / width * 100), 2)
        bw_val = round(float(bw.iloc[-1]), 2)
        bw_change_3d = round(float(bw.iloc[-1] - bw.iloc[-4]), 2)

        bw_change = bw.diff()
        contraction_days = 0
        expansion_days = 0
        for change in bw_change.iloc[::-1]:
            if pd.isna(change) or change >= 0:
                break
            contraction_days += 1
        for change in bw_change.iloc[::-1]:
            if pd.isna(change) or change <= 0:
                break
            expansion_days += 1

        bw_pctl_60d = round(float((bw.iloc[-60:] < bw.iloc[-1]).mean() * 100), 2)

        out[sid] = {
            "bollinger_position_pct": [pos_pct, last_date],
            "bollinger_bandwidth_pct": [bw_val, last_date],
            "bollinger_bandwidth_change_3d_pp": [bw_change_3d, last_date],
            "bollinger_contraction_days": [contraction_days, last_date],
            "bollinger_expansion_days": [expansion_days, last_date],
            "bollinger_bandwidth_percentile_60d": [bw_pctl_60d, last_date]
        }
    return out


def adx_latest() -> dict:
    """21. ADX 趨向指標 (7日) 與動態 (技術面)。"""
    from finlab import data

    plus_di = data.indicator("PLUS_DI", adjust_price=True, timeperiod=7)
    minus_di = data.indicator("MINUS_DI", adjust_price=True, timeperiod=7)
    adx = data.indicator("ADX", adjust_price=True, timeperiod=7)
    di_diff = plus_di - minus_di
    adx_change_3d = adx - adx.shift(3)

    last_date = str(adx.index[-1])[:10]
    out = {"_format": "[value, date]"}

    for sid in STOCK_IDS:
        if sid not in adx.columns:
            continue
        adx_s = adx[sid].dropna()
        if len(adx_s) < 4:
            continue
        p_di = plus_di[sid].reindex(adx_s.index).dropna()
        m_di = minus_di[sid].reindex(adx_s.index).dropna()
        common_idx = adx_s.index.intersection(p_di.index).intersection(m_di.index)
        if len(common_idx) < 4:
            continue

        adx_val = round(float(adx_s.loc[common_idx].iloc[-1]), 2)
        p_di_val = round(float(p_di.loc[common_idx].iloc[-1]), 2)
        m_di_val = round(float(m_di.loc[common_idx].iloc[-1]), 2)
        diff_val = round(float(p_di_val - m_di_val), 2)
        chg_3d = round(float(adx_s.loc[common_idx].iloc[-1] - adx_s.loc[common_idx].iloc[-4]), 2)

        out[sid] = {
            "plus_di": [p_di_val, last_date],
            "minus_di": [m_di_val, last_date],
            "di_diff": [diff_val, last_date],
            "adx": [adx_val, last_date],
            "adx_change_3d": [chg_3d, last_date],
        }
    return out


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
    """外資最新交易日買賣超佔成交量比重 (籌碼面，單位：%)。"""
    from finlab import data

    volume = data.get("price:成交股數", start=START_DATE)
    foreign = data.get("institutional_investors_trading_summary:外陸資買賣超股數(不含外資自營商)", start=START_DATE)
    foreign = foreign.reindex(volume.index)
    return (foreign.iloc[[-1]] / volume.iloc[[-1]] * 100).round(2)


def trust_net_buy_intensity_5d() -> pd.DataFrame:
    """投信近 5 日買賣超強度（投信買賣超/成交量）(籌碼面，單位：%)。"""
    from finlab import data

    volume = data.get("price:成交股數", start=START_DATE)
    trust = data.get("institutional_investors_trading_summary:投信買賣超股數", start=START_DATE)
    trust = trust.reindex(volume.index)
    return (trust.rolling(5).sum().iloc[[-1]] / volume.rolling(5).sum().iloc[[-1]] * 100).round(2)


def trust_net_buy_1d() -> pd.DataFrame:
    """投信最新交易日買賣超佔成交量比重 (籌碼面，單位：%)。"""
    from finlab import data

    volume = data.get("price:成交股數", start=START_DATE)
    trust = data.get("institutional_investors_trading_summary:投信買賣超股數", start=START_DATE)
    trust = trust.reindex(volume.index)
    return (trust.iloc[[-1]] / volume.iloc[[-1]] * 100).round(2)


# --------------------------------------------------------------------------- #
# 指標總清單登記
# --------------------------------------------------------------------------- #
ALL_INDICATORS: list[Indicator] = [
    # 基本面 (3)
    Indicator("roe_latest", "基本面", roe_latest, "最新季 ROE 稅後 (%)"),
    Indicator("revenue_yoy_latest", "基本面", revenue_yoy_latest, "最新月營收年增率 (%)"),
    Indicator("revenue_mom_latest", "基本面", revenue_mom_latest, "最新月營收月增率 (%)"),
    # 技術面 (22)
    Indicator("close_latest", "技術面", close_latest, "最新收盤價 (元)"),
    Indicator("return_1d", "技術面", return_1d, "當日還原漲跌幅 (%)"),
    Indicator("return_5d", "技術面", return_5d, "近5日報酬率 (%)"),
    Indicator("return_20d", "技術面", return_20d, "近20日報酬率 (%)"),
    Indicator("excess_return_5d", "技術面", excess_return_5d, "近5日相對大盤報酬差 (pp)"),
    Indicator("volume_ratio_1d", "技術面", volume_ratio_1d, "當日量比 (倍)"),
    Indicator("volume_ratio_3d", "技術面", volume_ratio_3d, "近3日量比 (倍)"),
    Indicator("volume_ma5_to_ma20", "技術面", volume_ma5_to_ma20, "5日均量/20日均量比值 (倍)"),
    Indicator("amount_ma5", "技術面", amount_ma5, "5日平均成交金額 (元)"),
    Indicator("volatility_10d", "技術面", volatility_10d, "10日報酬波動率 (%)"),
    Indicator("ma10_change_3d", "技術面", ma10_change_3d, "10日均線近3日變化率 (%)"),
    Indicator("price_vs_ma5", "技術面", price_vs_ma5, "5日均線乖離率 (%)"),
    Indicator("price_vs_ma20", "技術面", price_vs_ma20, "20日均線乖離率 (%)"),
    Indicator("price_range_pos_10d", "技術面", price_range_pos_10d, "10日價格區間位置 (%)"),
    Indicator("price_dist_to_high_10d", "技術面", price_dist_to_high_10d, "距離10日高點幅度 (%)"),
    Indicator("price_dist_to_low_10d", "技術面", price_dist_to_low_10d, "距離10日低點幅度 (%)"),
    Indicator("price_vs_min_close_10d", "技術面", price_vs_min_close_10d, "距前10日最低收盤價幅度 (%)"),
    Indicator("rsi_7", "技術面", rsi_7, "7日 RSI (0~100)"),
    Indicator("kd_latest", "技術面", kd_latest, "KD指標 (5,3,3) 與交叉動態"),
    Indicator("macd_latest", "技術面", macd_latest, "MACD指標 (6,13,5) 與柱狀動態"),
    Indicator("bollinger_latest", "技術面", bollinger_latest, "布林通道 (10,1.9) 與頻寬動態"),
    Indicator("adx_latest", "技術面", adx_latest, "ADX趨向指標 (7日) 與動態"),
    # 籌碼面 (4)
    Indicator("foreign_net_buy_intensity_5d", "籌碼面", foreign_net_buy_intensity_5d, "外資近5日買賣超強度 (%)"),
    Indicator("foreign_net_buy_1d", "籌碼面", foreign_net_buy_1d, "外資最新交易日買賣超佔成交量比重 (%)"),
    Indicator("trust_net_buy_intensity_5d", "籌碼面", trust_net_buy_intensity_5d, "投信近5日買賣超強度 (%)"),
    Indicator("trust_net_buy_1d", "籌碼面", trust_net_buy_1d, "投信最新交易日買賣超佔成交量比重 (%)"),
]
