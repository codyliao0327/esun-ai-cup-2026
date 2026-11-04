"""JSON 輔助工具函式庫。

提供 Compact Array JSON 格式化與數值精簡化工具，
確保個股與大盤技術指標在存檔與進入 LLM Prompt 時節省 Token 並保持最佳結構。
"""

from __future__ import annotations

import json
import re
from typing import Any
import pandas as pd


def format_metric_value(val: Any) -> Any:
    """將指標數值標準化 (整數轉 int，浮點數保留 float，NaN/None 轉 None)。"""
    if val is None or pd.isna(val):
        return None
    try:
        v = float(val)
        return int(v) if v.is_integer() else v
    except (ValueError, TypeError):
        return val


def to_compact_json(obj: Any, indent: int = 2) -> str:
    """產出以指定縮排、但二元陣列 [value, date] 保持單行的精簡 JSON 字串 (Compact Array JSON)。

    格式範例：
    [0.83, "2026-11-03"] 或 [1250, "2026-11-04"] 或 [-4.1, "2026-09"]
    """
    raw = json.dumps(obj, ensure_ascii=False, indent=indent)
    # 將跨行的 [ \n val, \n "date" \n ] 壓縮為單行 [val, "date"]
    return re.sub(
        r'\[\s*(-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?|null)\s*,\s*("[^"]*")\s*\]',
        r'[\1, \2]',
        raw,
    )
