import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import finlab
import pandas as pd
from finlab import data

# 設定 code/ 為匯入路徑
CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from configs.date_utils import clean_date_str, prompt_trade_date


def main(target_date: Optional[str] = None):
    # 憑證登入
    finlab.login()

    df = data.get('tw_active_etf_holdings_daily')

    # 1. 把索引重置，確保 date 與 stock_id 都是一般欄位
    df = df.reset_index()

    # 2. 將 date 欄位轉換為日期格式
    df['date'] = pd.to_datetime(df['date'])

    # 3. 找出每個 stock_id 最新的一天，並進行篩選
    df = df[df['date'] == df.groupby('stock_id')['date'].transform('max')].copy()

    # 4. 確保 weight 欄位為數值型態
    df['weight'] = pd.to_numeric(df['weight'], errors='coerce')

    # 5. 依照 stock_id 分組，將 weight 由大到小排序，取前 15 名
    top_15_constituents = (
        df.sort_values(by=['stock_id', 'weight'], ascending=[True, False])
          .groupby('stock_id')
          .head(15)
    )

    # 6. 保留需要的欄位
    result = top_15_constituents[['stock_id', 'constituent_id', 'constituent_name', 'weight']]

    # 7. 儲存路徑（相對於本檔案：上上層的 data/Active_ETF_Holdings）並自動建立資料夾
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.normpath(os.path.join(script_dir, '..', '..', 'data', 'Active_ETF_Holdings'))
    os.makedirs(output_dir, exist_ok=True)

    # 8. 輸出 parquet
    today = clean_date_str(target_date) if target_date else datetime.now().strftime('%Y%m%d')
    output_path = os.path.join(output_dir, f'top_15_constituents_{today}.parquet')
    result.to_parquet(output_path, engine='pyarrow', compression='zstd', index=False)

    print(f"處理完成！檔案已成功儲存至：{output_path}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="下載同業主動式 ETF 前 15 大成分股快照")
    parser.add_argument("--date", type=str, default=None, help="目標日期 (格式 YYYYMMDD 或 YYYY-MM-DD)")
    args = parser.parse_args()

    t_date = prompt_trade_date(args.date, prompt_text="主動式 ETF 成分股 - 目標日期")
    main(target_date=t_date)
