"""提取客觀事實陳述，產出 values 數值字典 (只放客觀數據)。

流程：
  1. 依 INPUTS 設定，從 data/ 下各資料夾讀入最新的 parquet / md 檔
  2. 載入 data/D-Paln_Output/l0_sources 的來源清單 (S1, S2 ...)，讓 Gemini 能正確填 source_ref
  3. 組成 prompt 交給 Gemini，並以 Pydantic schema 強制 JSON 結構 (structured output)
  4. 轉成 D-Plan v4.3 的 observations，輸出至
     data/D-Paln_Output/l1_observations/l1_observations_YYYYMMDD.json

用法::

    python fact_extractor.py                 # 呼叫 Gemini 並輸出檔案
    python fact_extractor.py --dry-run       # 只組 prompt 並存成 txt，不呼叫 API (檢查內容/長度用)
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
    patterns: tuple = ("*.parquet", "*.md")  # 要讀的副檔名


# INPUTS: List[InputSpec] = [
#     InputSpec("Active_ETF_Holdings", "主動式 ETF 前十五大成分股", source_id="S1"),
#     InputSpec("CMoney_Sentiment", "CMoney 個股情緒", source_id="S2"),
#     # DataPack 是官方帳戶快照，不屬於 L0 外部資料來源 (故 source_id=None)
#     InputSpec("Datapack/Processed", "官方 DataPack (帳戶/持股/合規)", source_id=None),
#     InputSpec("M1_市場趨勢", "M1 市場趨勢", source_id="S1"),
#     InputSpec("M2_市場風險", "M2 市場風險", source_id="S1"),
#     InputSpec("M3_市場資金與交易情緒", "M3 市場資金與交易情緒", source_id="S1"),
#     InputSpec("F1_企業財務品質", "F1 企業財務品質", source_id="S1"),
#     InputSpec("F2_企業營運成長", "F2 企業營運成長", source_id="S1"),
#     InputSpec("F1F2_估值與產業脈絡", "F1F2 估值與產業脈絡", source_id="S1"),
#     InputSpec("F4_股價與籌碼動能", "F4 股價與籌碼動能", source_id="S1"),
#     # InputSpec("F3_企業改善動能", "F3 企業改善動能", source_id="S1"),   # 需要時取消註解
# ]

INPUTS: List[InputSpec] = [
    InputSpec("F1_企業財務品質", "F1 企業財務品質", source_id="S1"),
    InputSpec("F4_股價與籌碼動能", "F4 股價與籌碼動能", source_id="S1"),
    InputSpec("CMoney_Sentiment", "CMoney 個股情緒", source_id="S2")
]

# --------------------------------------------------------------------------- #
# Prompt (大致版本，請自行修改)
# --------------------------------------------------------------------------- #
PROMPT_TEMPLATE = """\
你是台股投資研究助理。以下提供今日蒐集的資料，請從中擷取「客觀、可核對的事實」，
作為 D-Plan 的 L1 資訊擷取層 (observations)。

## 目前時間
{now}

## 規則
1. 只寫事實，禁止推論、預測、建議 (「SOX 跌 1.8%」可以；「所以半導體會弱」不行)。
2. 『個股資料』區塊中，每一檔股票 (標題為 stock_XXXX) 必須產生「恰好一筆」observation：
   - topic 直接使用該標題 (例如 stock_2330)。
   - statement：一到兩句話，客觀摘要該股最重要的數字事實 (價格、財務、籌碼、情緒等)，數字須與資料一致。
   - values：只需填 statement 中提到的數字 (至少 1 筆)；系統會自動以資料原值補齊該股所有指標。
   - source_ref：填該股資料所屬的 source_id (系統會再校正)。
3. 『市場/其他資料』區塊 (大盤、市場風險、資金、ETF 持股等非單一個股的資料) 請各自產生若干筆 observation：
   - topic 用小寫英文 snake_case，例如 tw_market、market_risk、etf_holdings、sentiment。
   - values 的數字必須與資料完全一致，單位寫在 key 名稱內 (例如 TAIEX_chg_pct)。
4. source_ref 只能填「可用資料來源」中存在的 source_id；資料區塊標題後有標註 (來源: Sx)。
   標註「無來源」的區塊僅供背景參考，不可單獨作為事實。
5. 資料缺值 (NaN/空白) 就略過，不要編造。

## 可用資料來源
{sources}

## 資料內容
{data}
"""


# --------------------------------------------------------------------------- #
# 讀檔工具
# --------------------------------------------------------------------------- #
def _latest_per_dataset(folder: Path, patterns: tuple) -> List[Path]:
    """資料夾內，同一資料集 (去掉結尾 _YYYYMMDD) 只取日期最新的一個檔案。"""
    latest: dict = {}
    for pat in patterns:
        for p in folder.glob(pat):
            m = re.match(r"^(.*)_(\d{8})$", p.stem)
            key = (m.group(1) if m else p.stem, p.suffix)
            stamp = m.group(2) if m else ""
            if key not in latest or stamp > latest[key][0]:
                latest[key] = (stamp, p)
    return sorted(p for _, p in latest.values())


STOCK_CODE_RE = re.compile(r"^\d{4}$")
STOCK_TOPIC_RE = re.compile(r"^stock_(\d{4})$")


@dataclass
class LoadedInputs:
    """load_inputs 的結果：給 Gemini 看的文字 + 程式保留的個股原始數值。"""

    text: str = ""
    stock_values: Dict[str, Dict[str, float]] = field(default_factory=dict)   # {"2330": {"指標名": 值}}
    stock_asof: Dict[str, Dict[str, str]] = field(default_factory=dict)       # {"2330": {"指標名": "YYYY-MM-DD"}}
    stock_sources: Dict[str, set] = field(default_factory=dict)               # {"2330": {"S1", "S2"}}


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


def _ingest_parquet(path: Path, spec: InputSpec, res: LoadedInputs, other_parts: List[str]) -> None:
    """依檔案型態處理：個股資料轉成每檔股票的指標；其它直接整份轉 CSV。"""
    df = pd.read_parquet(path)
    name = _dataset_name(path)
    kind = _classify(df)

    if kind == "stock_wide":
        # 一個檔案 = 一個指標；每檔股票取最新一筆非空值
        df = df.sort_values("date")
        for col in df.columns:
            if col == "date" or not STOCK_CODE_RE.match(str(col)):
                continue
            s = df.set_index("date")[col].dropna()
            if s.empty:
                continue
            _add_stock_value(res, str(col), name, s.iloc[-1], str(s.index[-1])[:10], spec.source_id)
    elif kind == "stock_rows":
        # 每列一檔股票，數值欄位各形成一個指標 (文字/時間欄位不進 values)
        num_cols = [c for c in df.columns if c != "股票代號" and pd.api.types.is_numeric_dtype(df[c])
                    and not pd.api.types.is_bool_dtype(df[c])]
        for _, row in df.iterrows():
            code = str(row["股票代號"])
            for c in num_cols:
                _add_stock_value(res, code, f"{name}_{c}", row[c], "", spec.source_id)
    else:
        other_parts.append(f"[{path.name}] shape={df.shape}\n" + df.to_csv(index=False))


def _stock_section(res: LoadedInputs) -> str:
    lines = ["### 個股資料 (每檔股票一個區塊，指標值為最新一筆，括號內為資料日期)"]
    for code in sorted(res.stock_values):
        srcs = ",".join(sorted(res.stock_sources.get(code, []))) or "無來源"
        lines.append(f"#### stock_{code} (來源: {srcs})")
        for key, val in res.stock_values[code].items():
            asof = res.stock_asof[code].get(key)
            lines.append(f"- {key}{f' ({asof})' if asof else ''}: {val:g}")
    return "\n".join(lines)


def load_inputs(inputs: List[InputSpec] = INPUTS) -> LoadedInputs:
    """依 INPUTS 讀入所有資料。個股資料按股票重組，其它資料原樣放入 prompt。"""
    res = LoadedInputs()
    other_blocks: List[str] = []
    for spec in inputs:
        folder = DATA_ROOT / spec.folder
        src = f"來源: {spec.source_id}" if spec.source_id else "無來源"
        if not folder.is_dir():
            print(f"[略過] 找不到資料夾 {folder}")
            continue
        files = _latest_per_dataset(folder, spec.patterns)
        if not files:
            print(f"[略過] {folder} 內沒有符合 {spec.patterns} 的檔案")
            continue
        parts: List[str] = []
        for p in files:
            try:
                if p.suffix == ".parquet":
                    _ingest_parquet(p, spec, res, parts)
                else:
                    parts.append(_read_md(p))
            except Exception as e:  # noqa: BLE001
                print(f"[警告] 讀取 {p} 失敗: {e}")
        if parts:
            other_blocks.append(f"#### {spec.label} ({src})\n" + "\n".join(parts))
        print(f"[讀入] {spec.folder}: {len(files)} 個檔案")

    sections = []
    if res.stock_values:
        sections.append(_stock_section(res))
    if other_blocks:
        sections.append("### 市場/其他資料\n" + "\n\n".join(other_blocks))
    res.text = "\n\n".join(sections)
    return res


def load_sources() -> List[dict]:
    """讀取 L0 輸出的最新來源清單 (每個 s*_*.json 取最新一份)，合併為清單。"""
    sources: List[dict] = []
    if not SOURCES_DIR.is_dir():
        return sources
    for p in _latest_per_dataset(SOURCES_DIR, ("*.json",)):
        try:
            sources.extend(json.loads(p.read_text(encoding="utf-8")))
        except Exception as e:  # noqa: BLE001
            print(f"[警告] 讀取來源檔 {p.name} 失敗: {e}")
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
    """個股 observation：用資料原值覆寫 values (確保數字不被 LLM 改動、指標完整)，
    並以實際來源覆寫 source_ref。順序：個股(依代號) → 其它 (保持 Gemini 順序)，再由 drafts_to_observations 編 O1..On。"""
    stock_drafts: Dict[str, ObservationDraft] = {}
    others: List[ObservationDraft] = []
    for d in resp.observations:
        m = STOCK_TOPIC_RE.match(d.topic or "")
        if m and m.group(1) in loaded.stock_values:
            if m.group(1) in stock_drafts:
                raise ValueError(f"Gemini 對 {d.topic} 產生了多筆 observation")
            code = m.group(1)
            d.values = [ValueItem(key=k, value=v) for k, v in loaded.stock_values[code].items()]
            d.source_ref = sorted(loaded.stock_sources.get(code, d.source_ref))
            stock_drafts[code] = d
        else:
            others.append(d)

    missing = sorted(set(loaded.stock_values) - set(stock_drafts))
    if missing:
        raise ValueError(f"Gemini 漏掉了這些股票的 observation: {missing}")
    resp.observations = [stock_drafts[c] for c in sorted(stock_drafts)] + others
    return resp


def extract_observations(prompt: str, loaded: LoadedInputs, valid_source_ids: Optional[set]) -> list:
    from configs.gemini_client import GeminiClient

    client = GeminiClient()
    resp = client.generate_structured(prompt, ObservationsResponse)
    resp = finalize_stock_observations(resp, loaded)
    return drafts_to_observations(resp, valid_source_ids)


def save_observations(observations: list, day: Optional[datetime] = None) -> Path:
    day = day or datetime.now(TW_TZ)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"{OUTPUT_PREFIX}_{day:%Y%m%d}.json"
    payload = [o.model_dump(exclude_none=True) for o in observations]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="以 Gemini 擷取 D-Plan L1 observations")
    parser.add_argument("--dry-run", action="store_true", help="只輸出 prompt 文字檔，不呼叫 Gemini")
    args = parser.parse_args(argv)

    sources = load_sources()
    loaded = load_inputs()
    prompt = build_prompt(loaded.text, sources)
    print(f"個股數: {len(loaded.stock_values)} | Prompt 字元數: {len(prompt):,}")

    if args.dry_run:
        out = OUTPUT_DIR / f"{OUTPUT_PREFIX}_prompt_{datetime.now(TW_TZ):%Y%m%d}.txt"
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out.write_text(prompt, encoding="utf-8")
        print(f"dry-run：prompt 已存至 {out}")
        return 0

    valid_ids = {s["source_id"] for s in sources} or None
    observations = extract_observations(prompt, loaded, valid_ids)
    path = save_observations(observations)
    print(f"完成：{len(observations)} 筆 observations -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
