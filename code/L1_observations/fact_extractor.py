"""提取客觀事實陳述，產出 values 數值字典 (只放客觀數據)。

流程：
  1. 依 INPUTS 設定，從 data/ 下各資料夾讀入最新的 parquet / md 檔
  2. 載入 data/D-Paln_Output/l0_sources 的來源清單 (S1, S2 ...)，讓 Gemini 能正確填 source_ref
  3. 組成 prompt 交給 Gemini，並以串流 (Streaming) 方式即時生成與印出字元
  4. 轉成 D-Plan v4.3 的 observations，輸出至
     data/D-Paln_Output/l1_observations/l1_observations_YYYYMMDD.json

用法::

    python fact_extractor.py                 # 呼叫 Gemini 並以 STREAM 即時印出字元
    python fact_extractor.py --dry-run       # 只組 prompt 並存成 txt，不呼叫 API (檢查內容/長度用)
    python fact_extractor.py --no-stream     # 關閉串流印出，改用傳統一次性批次等待
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

# 讓 `configs`、`schemas` 可從 code/ 目錄匯入 (直接以腳本執行時需要)
CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from configs.date_utils import clean_date_str, format_iso_trade_date, prompt_trade_date  # noqa: E402
from configs.json_utils import format_metric_value, to_compact_json  # noqa: E402
from schemas.dplan_models import (  # noqa: E402
    ObservationDraft,
    ObservationsResponse,
    ValueItem,
    drafts_to_observations,
)

ROOT = CODE_DIR.parent
DATA_ROOT = ROOT / "data"
SOURCES_DIR = DATA_ROOT / "D-Paln_Output" / "l0_sources"
OUTPUT_DIR = DATA_ROOT / "D-Paln_Output" / "l1_observations"
OUTPUT_PREFIX = "l1_observations"
TW_TZ = timezone(timedelta(hours=8))


# --------------------------------------------------------------------------- #
# 輸入資料設定 —— 要增減輸入資料，只需修改這個 INPUTS 清單
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class InputSpec:
    folder: str                          # data/ 底下的資料夾 (相對路徑)
    label: str                           # 在 prompt 中顯示的區塊標題
    source_id: Optional[str] = None      # 對應 L0 的 source_id (S1=FinLab, S2=CMoney)；無來源者填 None
    patterns: tuple = ("*.json", "*.parquet", "*.md")  # 要讀的副檔名 (優先 json，向下相容 parquet)


INPUTS: List[InputSpec] = [
    InputSpec("大盤", "市場大盤", source_id="S1"),
    InputSpec("技術面", "技術面", source_id="S1"),
    InputSpec("基本面", "基本面", source_id="S1"),
    InputSpec("籌碼面", "籌碼面", source_id="S1"),
    InputSpec("CMoney_Sentiment", "CMoney 個股情緒", source_id="S2"),
]

# --------------------------------------------------------------------------- #
# Prompt
# --------------------------------------------------------------------------- #
PROMPT_TEMPLATE = """\
你是台股投資研究助理。以下提供今日蒐集的資料，請從中擷取「客觀、可核對的事實」，
作為 D-Plan 的 L1 資訊擷取層 (observations)。

## 目前時間
{now}

## 規則
1. 只寫事實，禁止推論、預測、建議 (「SOX 跌 1.8%」可以；「所以半導體會弱」不行)。
2. 『市場大盤資料』(若有提供) 為 JSON 格式 (格式說明為 `[數值, 日期/交易日]`)，請產生「恰好一筆」大盤 observation：
   - topic 固定使用 tw_market。
   - statement：一到兩句話，客觀摘要加權指數收盤、均線、報酬、最大回撤、法人買賣超、多空排列家數差與生命線等關鍵數字事實 (引用指標名稱與數值)。
   - values：只需填 statement 中提到的數字 (至少 1 筆)；系統會自動以資料原值補齊所有大盤指標。
   - source_ref：填 S1。
3. 『個股指標資料』為以個股代碼為 Key 的 JSON 格式 (格式說明為 `[數值, 日期/季度]`)，包含各檔股票的基本面、技術面 (KD/MACD/布林通道等)、籌碼面指標以及 CMoney 個股情緒數據 (`cmoney_sentiment_*`)。資料中出現的每一個個股代碼，
   必須產生「恰好一筆」observation：
   - topic 使用 stock_<個股代碼> (例如 stock_2330，一律小寫英文與數字)。
   - statement：一到兩句話，客觀摘要該股最重要的數字事實 (如均線/乖離、KD、MACD、布林通道動態、法人籌碼、超額報酬或 CMoney 情緒等，引用指標名稱與數值)，數字須與資料一致。
   - values：只需填 statement 中提到的數字 (至少 1 筆)；系統會自動以資料原值補齊該股所有指標。
   - source_ref：填 S1 或 S2 (若同時引用則皆填)。
4. 『市場/其他資料』區塊 (若有其他非單一個股資料) 請各自產生若干筆 observation：
   - topic 用小寫英文 snake_case，例如 etf_holdings、sentiment。
   - values 的數字必須與資料完全一致，單位寫在 key 名稱內。
5. source_ref 只能填「可用資料來源」中存在的 source_id；標註「無來源」的區塊僅供背景參考，不可單獨作為事實。
6. 資料缺值 (NaN/空白) 就略過，不要編造。

## 可用資料來源
{sources}

## 技術指標定義與數值含意指引 (供精準解讀與引用)
### 1. 市場大盤指標
- `taiex_close_latest`：加權指數最新收盤價 (點)。
- `taiex_return_5d`：加權指數近 5 日報酬率 (%)。
- `taiex_vs_ma10_pct` / `taiex_vs_ma20_pct`：加權指數相對 10 日線 / 20 日均線 (月線) 之乖離率 (%)。正值代表指數站在均線之上，負值代表跌破。
- `taiex_range_pos_10d`：加權指數 10 日價格區間相對位置 (%，0% 位於區間最低點，100% 位於最高點)。
- `taiex_max_drawdown_5d`：加權指數近 5 日最大回撤 (%)，負值表示近期波段最大跌幅。
- `otc_vs_taiex_return_5d`：櫃買指數近 5 日報酬 － 加權近 5 日報酬 (pp)。>0 代表內資主力拉抬中小型題材股強於大盤權值股，動能勝率高；<0 代表中小型股轉弱殺盤。
- `market_foreign_net_buy_5d` / `market_foreign_net_buy_1d`：外資近 5 日累計 / 最新單日全市場(上市)淨買賣超金額 (元)。
- `market_trust_net_buy_5d` / `market_trust_net_buy_1d`：投信近 5 日累計 / 最新單日全市場(上市)淨買賣超金額 (元)。
- `market_advance_decline_ratio`：全市場股票漲跌家數比 (倍)。>1 代表上漲家數多，<1 代表下跌家數多。
- `listed_margin_balance_change_5d`：上市融資餘額近 5 日變化率 (%)，負值代表融資減肥/去槓桿。
- `market_alignment_diff`：全市場均線多空排列家數差 (家) ＝ (5MA≥10MA≥30MA多頭家數) － (5MA<10MA<30MA空頭家數)。正值代表多頭排列佔優，負值代表空頭排列佔優 (如 -1304 代表全市場空頭比多頭多 1304 家)。
- `index_vs_ma5_pct` / `index_vs_ma20_pct`：加權報酬指數相對週線 (5MA) / 生命線 (20MA) 之乖離率 (%)。
- `ma5_change_3d_pct` / `ma20_change_5d_pct`：5MA 週線近 3 日斜率變化率 (%) / 20MA 生命線近 5 日斜率變化率 (%)。

### 2. 個股技術面指標
- **KD (5, 3, 3)**：
  - `k_5` / `d_5`：最新 K 值與 D 值 (0~100)。>80 為高檔超買、<20 為低檔超賣。
  - `k_change_3d`：K 值近 3 日增減點數 (正代表快速走高、負代表轉折下彎)。
  - `kd_above_d_days` / `kd_below_d_days`：K 連續高於 / 低於 D 的天數 (>0 代表兩線多/空領先優勢持續天數)。
  - `kd_cross_days_ago_20d`：近 20 日內最近一次交叉距今天數 (0＝今日、1＝前一交易日、-1＝近 20 日未交叉；若為 0 可配合連續天數確認是黃金交叉或死亡交叉)。
- **MACD (6, 13, 5)**：
  - `macd_dif`：快慢線差 (6EMA － 13EMA)。正值代表短期均線強於中天期均線，負值代表偏弱。
  - `macd_hist`：最新柱狀體 (DIF － Signal)。正值代表 DIF 高於訊號線、負值代表低於訊號線。
  - `macd_hist_change_3d`：柱狀體近 3 日增減。負值變得較不負 (正增加) 代表負差距縮小、動能改善；正值縮小則代表多頭動能減退。
  - `macd_hist_increasing_days` / `macd_hist_decreasing_days`：柱狀體連續遞增 / 連續遞減天數。
  - `macd_cross_days_ago_20d`：近 20 日內 DIF 與 Signal 最近一次交叉距今天數 (0＝今日、-1＝近 20 日未交叉)。
- **布林通道 (10日, 1.9個標準差)**：
  - `bollinger_position_pct`：價格在軌道內之相對位置 (%)。0＝下軌、50＝中軌(10MA)、100＝上軌；>100 代表突破上軌、<0 代表跌破下軌。
  - `bollinger_bandwidth_pct`：標準化帶寬 (%)，數值代表目前相對波動幅度。
  - `bollinger_bandwidth_change_3d_pp`：帶寬近 3 日變化 (百分點 pp，正值代表通道擴張、負值代表通道收斂)。
  - `bollinger_contraction_days` / `bollinger_expansion_days`：帶寬連續收斂 (縮小) / 連續擴張 (放大) 天數。
  - `bollinger_bandwidth_percentile_60d`：目前帶寬在近 60 日的歷史百分位 (0~100%，數值越低代表相較近 60 日波動越極致壓縮、醞釀大變盤)。
- **ADX 趨向指標 (7日)**：
  - `plus_di` / `minus_di`：正趨向 (+DI) / 負趨向 (-DI) 指標，分別衡量上漲推升與下跌壓制力道。
  - `di_diff`：正負方向力道差 (plus_di － minus_di)，正值多方佔優、負值空方佔優。
  - `adx`：平均趨向指數 (0~100)，>25 代表存在明確單邊趨勢，<20 代表盤整無趨勢。
  - `adx_change_3d`：今日 ADX 相對 3 日前變化量，>0 代表趨勢力道正在增強。
- **均線、趨勢與價格動能指標**：
  - `close_latest`：最新收盤市價 (元)。
  - `return_1d` / `return_5d` / `return_20d`：當日 / 近 5 日 / 近 20 日還原報酬率 (%)。
  - `excess_return_5d`：近 5 日相對大盤超額報酬差 (pp，正值代表強於大盤/跑贏指數，負值代表弱於大盤)。
  - `price_vs_ma5` / `price_vs_ma20`：最新價相對 5MA (週線) / 20MA (月線) 之乖離率 (%)。
  - `ma10_change_3d`：10MA (雙週線) 近 3 日斜率變化率 (%)，反映短中期均線動能走向。
  - `price_range_pos_10d`：10 日價格區間相對位置 (%，0% 位於區間最低點、100% 位於最高點)。
  - `price_dist_to_high_10d` / `price_dist_to_low_10d`：距離 10 日最高點 / 最低點幅度 (%)。
  - `price_vs_min_close_10d`：距前 10 日最低收盤價幅度 (%，負值代表跌破前 10 日支撐低點)。
  - `rsi_7`：7 日相對強弱指標 (0~100)，短線超買超賣參考。
  - `volatility_10d`：10 日報酬波動率 (%)，反映近期價格震盪劇烈程度。
- **成交量與量比指標**：
  - `volume_ratio_1d`：當日量比 (倍) ＝ 今日成交量 / 近 10 日均量 (不含今日)，>1 代表今日放量。
  - `volume_ratio_3d`：近 3 日量比 (倍) ＝ 近 3 日均量 / 近 3 日之前 10 日均量，反映近日活躍度。
  - `volume_ma5_to_ma20`：5 日均量 / 20 日均量比值 (倍，>1 代表短線出量轉熱、<1 代表短線量縮整理)。
  - `amount_ma5`：5 日日均成交金額 (元)，評估個股流動性。

### 3. 個股籌碼面指標
- `foreign_net_buy_intensity_5d` / `trust_net_buy_intensity_5d`：外資 / 投信近 5 日買賣超強度 (%) ＝ 5日法人淨買賣超 / 5日總成交量。正值代表法人積極加碼吸籌、負值代表法人持續減碼調節。
- `foreign_net_buy_1d` / `trust_net_buy_1d`：最新交易日外資 / 投信單日買賣超佔成交量比重 (%) ＝ 單日法人淨買賣超 / 當日總成交量。正值代表當日積極買超佔比高。

### 4. CMoney 個股情緒指標
- `cmoney_sentiment_情緒分數`：CMoney 討論區情緒分數 (0~100)。0~25 代表極度謹慎、25~50 代表謹慎、50 代表中立、50~75 代表樂觀、75~100 代表極度樂觀；當樣本數為 0 時亦為 50 (中立)。
- `cmoney_sentiment_樣本數`：該統計區間內的討論樣本數 (則)。需達一定樣本數才會產出情緒風向；若該指標的資料日期 (`date`) 停留在過去日期，代表該日後皆因樣本數不足而未產出新風向，可能反映近期沒什麼人在討論。
- `cmoney_sentiment_極度樂觀` / `cmoney_sentiment_樂觀` / `cmoney_sentiment_中立` / `cmoney_sentiment_謹慎` / `cmoney_sentiment_極度謹慎`：各情緒分類之討論則數。
- `cmoney_sentiment_樂觀占比` / `cmoney_sentiment_中立占比` / `cmoney_sentiment_謹慎占比`：各情緒分類佔總樣本數之比例 (0~1，分別為 `(極度樂觀+樂觀)/樣本數`、`中立/樣本數`、`(極度謹慎+謹慎)/樣本數`；當 `樣本數` 為 0 時略過不輸出)。

## 資料內容
{data}
"""


# --------------------------------------------------------------------------- #
# 讀檔工具 (嚴格僅抓取當層目錄中，檔名結尾為 _YYYYMMDD 且完全等於 target_date 的檔案)
# --------------------------------------------------------------------------- #
def _files_for_target_date(
    folder: Path,
    patterns: tuple,
    target_date: str,
) -> List[Path]:
    """資料夾當層目錄內，抓取結尾為 _YYYYMMDD 且完全等於 target_date 的檔案。

    若同指標同時存在 .json 與 .parquet，優先使用 .json。
    若指定日期找不到任何檔案，嚴格拋出 FileNotFoundError，絕不降級抓取其他日期。
    """
    c_target = clean_date_str(target_date)
    if not c_target or len(c_target) != 8:
        raise ValueError(f"target_date 必須為 8 碼 YYYYMMDD 格式: '{target_date}'")

    matched_by_stem: Dict[str, Path] = {}
    for pat in patterns:
        for p in sorted(folder.glob(pat)):
            m = re.match(r"^(.*)_(\d{8})$", p.stem)
            if m and m.group(2) == c_target:
                stem = p.stem
                if stem not in matched_by_stem or p.suffix == ".json":
                    matched_by_stem[stem] = p

    return sorted(matched_by_stem.values())


STOCK_CODE_RE = re.compile(r"^\d{4}$")
STOCK_TOPIC_RE = re.compile(r"^stock_(\d{4})$")
MARKET_TOPIC_RE = re.compile(r"^(tw_market|market_overview|market)$")


@dataclass
class LoadedInputs:
    """load_inputs 的結果：給 Gemini 看的文字 + 程式保留的原始數值。"""

    text: str = ""
    # 個股指標數值
    stock_values: Dict[str, Dict[str, float]] = field(default_factory=dict)   # {"2330": {"指標名": 值}}
    stock_asof: Dict[str, Dict[str, str]] = field(default_factory=dict)       # {"2330": {"指標名": "YYYY-MM-DD"}}
    stock_sources: Dict[str, set] = field(default_factory=dict)               # {"2330": {"S1", "S2"}}
    tables: List[str] = field(default_factory=list)                           # 其它個股指標表格文字 (向下相容)
    # 大盤指標數值
    market_values: Dict[str, float] = field(default_factory=dict)             # {"taiex_close_latest": 46041.43}
    market_asof: Dict[str, str] = field(default_factory=dict)                 # {"taiex_close_latest": "YYYY-MM-DD"}
    market_sources: set = field(default_factory=set)                          # {"S1"}
    market_tables: List[str] = field(default_factory=list)                    # 大盤指標表格文字 (向下相容)


def _classify(df: pd.DataFrame) -> str:
    """stock_rows=每列一檔股票 (CMoney)；stock_wide=date x 股票代碼欄；other=其他。"""
    if "股票代號" in df.columns:
        return "stock_rows"
    cols = [c for c in df.columns if c != "date"]
    if "date" in df.columns and cols and sum(bool(STOCK_CODE_RE.match(str(c))) for c in cols) >= len(cols) / 2:
        return "stock_wide"
    return "other"


def _dataset_name(path: Path) -> str:
    m = re.match(r"^(.*)_\d{8}$", path.stem)
    return m.group(1) if m else path.stem


def _read_md(path: Path) -> str:
    return f"[{path.name}]\n" + path.read_text(encoding="utf-8")


def _add_stock_value(res: LoadedInputs, code: str, key: str, value, asof: str, source_id: Optional[str]) -> None:
    if value is None or pd.isna(value):
        return
    res.stock_values.setdefault(code, {})[key] = float(value)
    res.stock_asof.setdefault(code, {})[key] = asof
    if source_id:
        res.stock_sources.setdefault(code, set()).add(source_id)


def _add_market_value(res: LoadedInputs, key: str, value, asof: str, source_id: Optional[str]) -> None:
    if value is None or pd.isna(value):
        return
    res.market_values[key] = float(value)
    res.market_asof[key] = asof
    if source_id:
        res.market_sources.add(source_id)


def _ingest_json(path: Path, spec: InputSpec, res: LoadedInputs, other_parts: List[str]) -> None:
    """讀取 Compact Array JSON 檔案，解析至 market_values 或 stock_values。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    name = _dataset_name(path)

    # 1. 大盤指標
    if spec.folder == "大盤" or "tw_market" in data:
        market_dict = data.get("tw_market", {})
        for metric, item in market_dict.items():
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                val, dt = item[0], str(item[1])
                _add_market_value(res, metric, val, dt, spec.source_id)
            else:
                _add_market_value(res, metric, item, "", spec.source_id)
        return

    # 2. 個股指標 (以個股代碼為 Key)
    has_stocks = False
    for key, metrics in data.items():
        if key.startswith("_"):
            continue
        if STOCK_CODE_RE.match(str(key)) and isinstance(metrics, dict):
            has_stocks = True
            for metric, item in metrics.items():
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    val, dt = item[0], str(item[1])
                    _add_stock_value(res, str(key), metric, val, dt, spec.source_id)
                else:
                    _add_stock_value(res, str(key), metric, item, "", spec.source_id)

    if not has_stocks:
        other_parts.append(f"{name}:\n" + json.dumps(data, ensure_ascii=False, indent=2))


def _ingest_parquet(path: Path, spec: InputSpec, res: LoadedInputs, other_parts: List[str]) -> None:
    """依檔案型態處理：大盤存入 market_values；個股寬表與列式表 (如 CMoney 個股情緒) 皆存入 stock_values。"""
    df = pd.read_parquet(path)
    name = _dataset_name(path)

    # 1. 大盤指標資料夾：收集為大盤數值
    if spec.folder == "大盤":
        val_cols = [c for c in df.columns if c != "date"]
        if val_cols:
            s = df.set_index("date")[val_cols[0]].dropna()
            if not s.empty:
                dt = str(s.index[-1]).strip()
                if len(dt) > 10 and " " in dt:
                    dt = dt.split()[0]
                _add_market_value(res, name, s.iloc[-1], dt, spec.source_id)
        return

    kind = _classify(df)

    if kind == "stock_wide":
        # 一個檔案 = 一個指標；values 取每檔股票最新一筆非空值
        for col in df.columns:
            if col == "date" or not STOCK_CODE_RE.match(str(col)):
                continue
            s = df.set_index("date")[col].dropna()
            if s.empty:
                continue
            dt = str(s.index[-1]).strip()
            if len(dt) > 10 and " " in dt:
                dt = dt.split()[0]
            _add_stock_value(res, str(col), name, s.iloc[-1], dt, spec.source_id)
    elif kind == "stock_rows":
        # 每列一檔股票 (例如 CMoney 個股情緒)，併入 stock_values 以 Compact Array JSON 呈現
        m = re.match(r"^(.*)_(\d{8})$", path.stem)
        default_asof = format_iso_trade_date(m.group(2)) if m else ""
        date_col = next((c for c in ("統計結束時間", "date") if c in df.columns), None)
        num_cols = [c for c in df.columns if c not in ("股票代號", "date", "統計開始時間", "統計結束時間")
                    and pd.api.types.is_numeric_dtype(df[c])
                    and not pd.api.types.is_bool_dtype(df[c])]
        has_sentiment_ratio_cols = {
            "樣本數", "極度樂觀", "樂觀", "中立", "謹慎", "極度謹慎",
        }.issubset(df.columns)
        for _, row in df.iterrows():
            code = str(row["股票代號"])
            row_asof = default_asof
            if date_col and pd.notna(row[date_col]):
                dt = str(row[date_col]).strip()
                if dt:
                    if len(dt) > 10 and " " in dt:
                        dt = dt.split()[0]
                    row_asof = dt
            for c in num_cols:
                _add_stock_value(res, code, f"{name}_{c}", row[c], row_asof, spec.source_id)
            if has_sentiment_ratio_cols:
                sample_cnt = row["樣本數"]
                if pd.notna(sample_cnt) and float(sample_cnt) > 0:
                    denom = float(sample_cnt)
                    bull = float(row["極度樂觀"] or 0) + float(row["樂觀"] or 0)
                    neutral = float(row["中立"] or 0)
                    bear = float(row["極度謹慎"] or 0) + float(row["謹慎"] or 0)
                    _add_stock_value(res, code, f"{name}_樂觀占比", round(bull / denom, 4), row_asof, spec.source_id)
                    _add_stock_value(res, code, f"{name}_中立占比", round(neutral / denom, 4), row_asof, spec.source_id)
                    _add_stock_value(res, code, f"{name}_謹慎占比", round(bear / denom, 4), row_asof, spec.source_id)
    else:
        other_parts.append(f"{name}:\n" + df.to_csv(sep="\t", index=False))


def load_inputs(
    inputs: List[InputSpec] = INPUTS,
    target_date: Optional[str] = None,
    max_stocks: Optional[int] = None,
) -> LoadedInputs:
    """依 INPUTS 讀入所有指定日期結尾的資料。

    - 嚴格比對檔名結尾為 _YYYYMMDD，完全等於 target_date。
    - 若特定資料夾找不到該日期檔案，直接拋出 FileNotFoundError。
    - 若指定 max_stocks，僅保留前 max_stocks 檔個股資料（供快速測試使用）。
    """
    if not target_date:
        raise ValueError("load_inputs 必須指定 target_date (格式 YYYYMMDD)")
    c_target = clean_date_str(target_date)

    res = LoadedInputs()
    other_blocks: List[str] = []
    for spec in inputs:
        folder = DATA_ROOT / spec.folder
        src = f"來源: {spec.source_id}" if spec.source_id else "無來源"
        if not folder.is_dir():
            raise FileNotFoundError(f"找不到輸入資料夾: {folder}")
        files = _files_for_target_date(folder, spec.patterns, target_date=c_target)
        if not files:
            raise FileNotFoundError(f"資料夾 {folder} 找不到日期結尾為 _{c_target} 的資料檔案！")
        parts: List[str] = []
        for p in files:
            try:
                if p.suffix == ".json":
                    _ingest_json(p, spec, res, parts)
                elif p.suffix == ".parquet":
                    _ingest_parquet(p, spec, res, parts)
                else:
                    parts.append(_read_md(p))
            except Exception as e:  # noqa: BLE001
                print(f"[警告] 讀取 {p} 失敗: {e}")
                raise
        if parts:
            other_blocks.append(f"#### {spec.label} ({src})\n" + "\n".join(parts))
        print(f"[讀入] {spec.folder}: {len(files)} 個檔案 (日期: {c_target})")

    if max_stocks and max_stocks > 0:
        keep_codes = set(sorted(res.stock_values.keys())[:max_stocks])
        res.stock_values = {k: v for k, v in res.stock_values.items() if k in keep_codes}
        res.stock_asof = {k: v for k, v in res.stock_asof.items() if k in keep_codes}
        res.stock_sources = {k: v for k, v in res.stock_sources.items() if k in keep_codes}
        print(f"[抽樣測試] 已限制僅保留前 {len(keep_codes)} 檔個股: {sorted(keep_codes)}")

    # 組裝大盤 Compact Array JSON
    market_json = {"_format": "[value, date]"}
    if res.market_values:
        market_json["tw_market"] = {
            metric: [format_metric_value(val), res.market_asof.get(metric, "")]
            for metric, val in res.market_values.items()
        }

    # 組裝個股 Compact Array JSON (包含基本面、技術面、籌碼面及 CMoney 個股情緒等具備交易日/季度的指標)
    stock_json = {"_format": "[value, date]"}
    for code in sorted(res.stock_values.keys()):
        metrics_dict = {}
        for metric, val in res.stock_values[code].items():
            asof_date = res.stock_asof[code].get(metric, "")
            if asof_date:
                metrics_dict[metric] = [format_metric_value(val), asof_date]
        if metrics_dict:
            stock_json[code] = metrics_dict

    sections = []
    if res.market_values:
        sections.append(
            "### 市場大盤資料 (JSON 格式，格式說明: [value, date])\n"
            + to_compact_json(market_json)
        )
    if stock_json and len(stock_json) > 1:
        sections.append(
            "### 個股指標資料 (以個股代碼為 Key 的 JSON 格式，格式說明: [value, date])\n"
            + to_compact_json(stock_json)
        )
    if other_blocks:
        sections.append("### 市場/其他資料\n" + "\n\n".join(other_blocks))
    res.text = "\n\n".join(sections)
    return res


def load_sources(target_date: Optional[str] = None) -> List[dict]:
    """讀取 L0 輸出的來源清單 (嚴格比對檔名結尾為 _YYYYMMDD.json)。"""
    if not target_date:
        raise ValueError("load_sources 必須指定 target_date (格式 YYYYMMDD)")
    c_target = clean_date_str(target_date)

    if not SOURCES_DIR.is_dir():
        raise FileNotFoundError(f"找不到 L0 sources 目錄: {SOURCES_DIR}")
    files = _files_for_target_date(SOURCES_DIR, ("*.json",), target_date=c_target)
    if not files:
        raise FileNotFoundError(f"目錄 {SOURCES_DIR} 找不到日期結尾為 _{c_target}.json 的來源檔案！")

    sources: List[dict] = []
    for p in files:
        try:
            sources.extend(json.loads(p.read_text(encoding="utf-8")))
        except Exception as e:  # noqa: BLE001
            print(f"[警告] 讀取來源檔 {p.name} 失敗: {e}")
            raise
    return sorted(sources, key=lambda s: s.get("source_id", ""))


def build_prompt(data_text: str, sources: List[dict]) -> str:
    src_text = "\n".join(
        f"- {s['source_id']}: {s.get('name', '')} ({s['authority']}) {s['url']}" for s in sources
    ) or "(尚無來源檔，請先執行 L0_sources 內的程式)"
    return PROMPT_TEMPLATE.format(
        now=datetime.now(TW_TZ).isoformat(timespec="seconds"),
        sources=src_text,
        data=data_text,
    )


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def finalize_stock_observations(resp: ObservationsResponse, loaded: LoadedInputs) -> ObservationsResponse:
    """處理 observations：
    1. 大盤 observation：獨立一筆 (topic=tw_market)，覆寫 values 完整包含所有大盤數值，source_ref 標註 S1。
    2. 個股 observations：用資料原值覆寫 values (確保數字不被 LLM 改動、指標完整)，並以實際來源覆寫 source_ref。
    順序：大盤 (若有) → 個股 (依代號排序) → 其它 (保持順序)，再由 drafts_to_observations 編 O1..On。
    """
    stock_drafts: Dict[str, ObservationDraft] = {}
    market_draft: Optional[ObservationDraft] = None
    others: List[ObservationDraft] = []

    for d in resp.observations:
        topic = (d.topic or "").strip()

        # 1. 大盤 observation 識別
        if MARKET_TOPIC_RE.match(topic):
            if loaded.market_values:
                d.topic = "tw_market"
                d.values = [ValueItem(key=k, value=v) for k, v in loaded.market_values.items()]
                d.source_ref = sorted(loaded.market_sources or (set(d.source_ref) if d.source_ref else {"S1"}))
                market_draft = d
            else:
                others.append(d)
            continue

        # 2. 個股 observation 識別
        m = STOCK_TOPIC_RE.match(topic)
        if m and m.group(1) in loaded.stock_values:
            code = m.group(1)
            if code in stock_drafts:
                raise ValueError(f"Gemini 對 {d.topic} 產生了多筆 observation")
            d.values = [ValueItem(key=k, value=v) for k, v in loaded.stock_values[code].items()]
            d.source_ref = sorted(loaded.stock_sources.get(code, d.source_ref))
            stock_drafts[code] = d
        else:
            others.append(d)

    # 若有大盤資料但 Gemini 漏掉產生 tw_market，自動建立獨立 observation
    if loaded.market_values and market_draft is None:
        market_draft = ObservationDraft(
            topic="tw_market",
            statement="市場大盤加權指數收盤、均線、報酬、最大回撤、法人買賣超與市場融資等關鍵指標總覽。",
            values=[ValueItem(key=k, value=v) for k, v in loaded.market_values.items()],
            source_ref=sorted(loaded.market_sources) or ["S1"],
        )

    missing = sorted(set(loaded.stock_values) - set(stock_drafts))
    if missing:
        raise ValueError(f"Gemini 漏掉了這些股票的 observation: {missing}")

    # 組合順序：大盤獨立 1 筆 -> 40 檔個股 -> 其它 (例如 sentiment)
    final_list: List[ObservationDraft] = []
    if market_draft:
        final_list.append(market_draft)
    final_list.extend([stock_drafts[c] for c in sorted(stock_drafts)])
    final_list.extend(others)

    resp.observations = final_list
    return resp


def extract_observations(
    prompt: str,
    loaded: LoadedInputs,
    valid_source_ids: Optional[set],
    target_date: str,
    stream: bool = True,
    model: Optional[str] = None,
) -> list:
    from configs.gemini_client import GeminiClient

    client = GeminiClient(model=model, stage="l1", target_date=target_date)
    if stream:
        print("\n" + "=" * 60)
        print(" [LiteLLM Router / stage-l1 串流模式啟動] 正在即時生成 Observations...")
        print(" (提示：若發現輸出內容方向不符，可隨時按 Ctrl + C 中斷以節省費用)")
        print("=" * 60 + "\n")

    resp = client.generate_structured(
        prompt,
        ObservationsResponse,
        stream=stream,
        stage="l1",
        target_date=target_date,
    )

    # 輸出 LiteLLM Usage 統計
    client.save_usage_metadata(
        output_dir=OUTPUT_DIR,
        stage_prefix="l1",
        target_date=target_date,
    )

    if stream:
        print("\n" + "=" * 60)
        print(" [Gemini 串流完成] 已接收全部資料，進行結構驗證與覆寫...")
        print("=" * 60 + "\n")

    resp = finalize_stock_observations(resp, loaded)
    return drafts_to_observations(resp, valid_source_ids)


def save_observations(observations: list, target_date_str: Optional[str] = None) -> Path:
    clean_date = clean_date_str(target_date_str) if target_date_str else datetime.now(TW_TZ).strftime("%Y%m%d")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"{OUTPUT_PREFIX}_{clean_date}.json"
    payload = [o.model_dump(exclude_none=True) for o in observations]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="以 LiteLLM Router (stage-l1) 擷取 D-Plan L1 observations")
    parser.add_argument("--date", type=str, default=None, help="指定輸出交易日期 (格式 YYYYMMDD 或 YYYY-MM-DD)")
    parser.add_argument("--input-date", type=str, default=None, help="指定讀取 L0 輸入資料之日期 (預設同 --date)")
    parser.add_argument("--max-stocks", type=int, default=None, help="限制僅抽樣前 N 檔個股進行測試")
    parser.add_argument("--model", type=str, default=None, help="指定模型或路由別名 (預設使用 stage-l1)")
    parser.add_argument("--dry-run", action="store_true", help="只輸出 prompt 文字檔，不呼叫 LLM")
    parser.add_argument("--no-stream", action="store_true", help="關閉串流顯示，改用傳統非串流批次等待")
    args = parser.parse_args(argv)

    # 取得交易日期 (若無命令列參數則在終端機提示輸入)
    target_date = prompt_trade_date(args.date, prompt_text="L1 事實擷取 - 交易日期")
    clean_date = clean_date_str(target_date)
    input_clean_date = clean_date_str(args.input_date) if args.input_date else clean_date

    sources = load_sources(target_date=input_clean_date)
    loaded = load_inputs(target_date=input_clean_date, max_stocks=args.max_stocks)
    prompt = build_prompt(loaded.text, sources)
    print(f"輸出日期: {clean_date} (輸入日期: {input_clean_date}) | 大盤指標數: {len(loaded.market_values)} | 個股數: {len(loaded.stock_values)} | Prompt 字元數: {len(prompt):,}")

    # 無論 dry-run 或正式執行，皆儲存 Prompt 供排查與回溯
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / f"{OUTPUT_PREFIX}_prompt_{clean_date}.txt"
    out.write_text(prompt, encoding="utf-8")
    print(f"[FactExtractor] Prompt 已保存至: {out}")

    if args.dry_run:
        print(f"dry-run 模式：Prompt 已存至 {out}，不呼叫 Gemini API。")
        return 0

    valid_ids = {s["source_id"] for s in sources} or None
    observations = extract_observations(
        prompt,
        loaded,
        valid_ids,
        target_date=clean_date,
        stream=not args.no_stream,
        model=args.model,
    )
    path = save_observations(observations, target_date_str=clean_date)
    print(f"完成：{len(observations)} 筆 observations -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
