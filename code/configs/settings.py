"""隊伍 ID、API 金鑰、LiteLLM 路由設定檔與全域路徑設定。"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv

# 專案路徑設定
CONFIGS_DIR = Path(__file__).resolve().parent
BASE_DIR = CONFIGS_DIR.parent                # code/ 目錄
PROJECT_ROOT = BASE_DIR.parent               # 專案根目錄

ENV_FILE = BASE_DIR / ".env"
ROOT_ENV_FILE = PROJECT_ROOT / ".env"
CREDENTIALS_FILE = BASE_DIR / "credentials.json"

# 預設模型與階段路由別名設定
DEFAULT_GEMINI_MODEL = "gemini/gemini-4-argon"
DEFAULT_STAGE_ALIAS = "stage-l2"

STAGE_MODEL_ALIASES: Dict[str, str] = {
    "l0": "stage-l0",
    "l1": "stage-l1",
    "l2m": "stage-l2m",
    "l2": "stage-l2",
    "l3": "stage-l3",
    "l4": "stage-l4",
}


def load_credentials(file_path: Optional[Path] = None) -> Dict[str, Any]:
    """載入本地 credentials.json 憑證檔案 (向下相容備援)。"""
    path = file_path or CREDENTIALS_FILE
    if path.is_file():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[警告] 讀取憑證檔 {path} 失敗: {e}")
    return {}


def migrate_credentials_to_env() -> None:
    """若 .env 尚未建立且存在 credentials.json，自動將金鑰與隊伍 ID 遷移至 .env。"""
    if ENV_FILE.is_file() and ROOT_ENV_FILE.is_file():
        return

    creds = load_credentials()
    if not creds:
        return

    api_key = str(creds.get("gemini_api_key") or creds.get("GOOGLE_API_KEY") or "").strip()
    team_id = str(creds.get("team_id") or "TEAM_11402").strip()
    if not api_key or api_key == "YOUR_GEMINI_API_KEY_HERE":
        return

    lines = [
        "# 自動由 credentials.json 遷移之環境變數設定",
        f"GEMINI_API_KEY={api_key}",
        f"TEAM_ID={team_id}",
        "",
    ]
    content = "\n".join(lines)

    for target_env in (ENV_FILE, ROOT_ENV_FILE):
        if not target_env.is_file():
            try:
                target_env.write_text(content, encoding="utf-8")
            except Exception as e:
                print(f"[警告] 寫入 {target_env} 失敗: {e}")


# 模組載入時自動執行遷移並載入 .env
migrate_credentials_to_env()
if ENV_FILE.is_file():
    load_dotenv(dotenv_path=ENV_FILE, override=False)
if ROOT_ENV_FILE.is_file():
    load_dotenv(dotenv_path=ROOT_ENV_FILE, override=False)


def get_gemini_api_key() -> str:
    """取得 Gemini API 金鑰並同步注入 os.environ["GEMINI_API_KEY"]。

    優先順序：
    1. 環境變數 / .env 檔案中的 GEMINI_API_KEY 或 GOOGLE_API_KEY
    2. 本地 credentials.json 檔案中的 "gemini_api_key" 或 "GOOGLE_API_KEY" (向下相容)
    """
    # 重新確保 .env 已載入
    if ENV_FILE.is_file():
        load_dotenv(dotenv_path=ENV_FILE, override=False)
    if ROOT_ENV_FILE.is_file():
        load_dotenv(dotenv_path=ROOT_ENV_FILE, override=False)

    env_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if env_key and env_key.strip() not in ("", "your_gemini_api_key_here", "YOUR_GEMINI_API_KEY_HERE"):
        clean_key = env_key.strip()
        os.environ["GEMINI_API_KEY"] = clean_key
        return clean_key

    # 備援：讀取舊版 credentials.json
    creds = load_credentials()
    api_key = creds.get("gemini_api_key") or creds.get("GOOGLE_API_KEY")
    if api_key and str(api_key).strip() not in ("", "your_gemini_api_key_here", "YOUR_GEMINI_API_KEY_HERE"):
        clean_key = str(api_key).strip()
        os.environ["GEMINI_API_KEY"] = clean_key
        return clean_key

    raise ValueError(
        f"找不到 Gemini API Key！\n"
        f"請在 `{ENV_FILE}` 或 `{ROOT_ENV_FILE}` 設定：\n"
        f"GEMINI_API_KEY=你的Gemini_API金鑰\n"
        f"（可參考 `.env.example` 進行配置）"
    )


def get_team_id() -> str:
    """取得隊伍 ID (優先讀取 .env 中的 TEAM_ID，次選 credentials.json，預設 TEAM_11402)。"""
    env_team = os.getenv("TEAM_ID")
    if env_team and env_team.strip():
        return env_team.strip()
    creds = load_credentials()
    return str(creds.get("team_id", "TEAM_11402")).strip()


def get_models_config_path() -> Path:
    """取得 models_config.yaml 路徑（優先專案根目錄，若兩處皆有且內容不同則取最新修改者）。"""
    root_cfg = PROJECT_ROOT / "models_config.yaml"
    code_cfg = BASE_DIR / "models_config.yaml"

    if root_cfg.is_file() and code_cfg.is_file():
        try:
            if root_cfg.read_bytes() == code_cfg.read_bytes():
                return root_cfg
        except Exception:
            pass
        return root_cfg if root_cfg.stat().st_mtime >= code_cfg.stat().st_mtime else code_cfg
    if root_cfg.is_file():
        return root_cfg
    if code_cfg.is_file():
        return code_cfg
    raise FileNotFoundError(
        f"找不到 models_config.yaml！請確認 `{root_cfg}` 或 `{code_cfg}` 是否存在。"
    )
