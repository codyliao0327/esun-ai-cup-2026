"""隊伍 ID、API 金鑰、全域路徑設定。"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

# 專案路徑設定 (code/ 目錄)
CONFIGS_DIR = Path(__file__).resolve().parent
BASE_DIR = CONFIGS_DIR.parent
CREDENTIALS_FILE = BASE_DIR / "credentials.json"

# 預設模型名稱
# DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
DEFAULT_GEMINI_MODEL = "gemini-4-argon"


def load_credentials(file_path: Optional[Path] = None) -> Dict[str, Any]:
    """載入本地 credentials.json 憑證檔案。

    若檔案存在且格式正確，回傳字典內容；若不存在則回傳空字典。
    """
    path = file_path or CREDENTIALS_FILE
    if path.is_file():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[警告] 讀取憑證檔 {path} 失敗: {e}")
    return {}


def get_gemini_api_key() -> str:
    """取得 Gemini API 金鑰。

    優先順序：
    1. 本地 credentials.json 檔案中的 "gemini_api_key" 或 "GOOGLE_API_KEY"
    2. 作業系統環境變數 GEMINI_API_KEY / GOOGLE_API_KEY (備用 fallback)

    若皆找不到，拋出 ValueError 並提供指引。
    """
    # 1. 優先讀取本地 credentials.json (不依賴環境變數)
    creds = load_credentials()
    api_key = creds.get("gemini_api_key") or creds.get("GOOGLE_API_KEY")
    if api_key and api_key != "YOUR_GEMINI_API_KEY_HERE":
        return str(api_key).strip()

    # 2. 備援：若有設定環境變數也可使用
    env_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if env_key:
        return env_key.strip()

    raise ValueError(
        f"找不到 Gemini API Key！\n"
        f"請在專案根目錄 ({BASE_DIR}) 建立 `credentials.json`，格式如下：\n"
        f"{{\n"
        f'  "gemini_api_key": "你的Gemini_API金鑰"\n'
        f"}}\n"
        f"或參考 `credentials.json.example` 進行配置。"
    )


def get_team_id() -> str:
    """取得隊伍 ID (如 TEAM_11402)。"""
    creds = load_credentials()
    return creds.get("team_id", "TEAM_11402")
