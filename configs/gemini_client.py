"""Google Gemini API 客戶端封裝 (基於 LiteLLM Router 多模型路由、Fallback 與全域 Usage Callback)。

提供機能：
1. 載入專案根目錄 `models_config.yaml`，透過 `litellm.Router` 依任務階段 (`stage`) 自動路由模型並支援 Rate Limit / 超時 Fallback。
2. 支援 Gemini 原生沙盒執行 (`tools=[{"code_execution": {}}]`)。
3. 註冊全域 `litellm.success_callback` 與 `litellm.failure_callback`：
   - 自動統計 LiteLLM 標準 Token 與美金成本 (`response_cost`)。
   - 從 `completion_response._hidden_params.get("original_response")` 的 `candidates -> content -> parts` 解析 `executable_code`，填入 `code_execution_used`、`code_execution_call_count` 與 `executed_codes`。
4. 單次執行收集所有 Usage 紀錄，輸出各階段 Usage JSON 並合併結算至本地 `usage_history.json`。
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, TypeVar

import litellm
import yaml
from litellm import Router
from pydantic import BaseModel, ValidationError

try:
    import json_repair
except ImportError:
    json_repair = None

if __package__ in (None, ""):
    _CODE_DIR = Path(__file__).resolve().parents[1]
    if str(_CODE_DIR) not in sys.path:
        sys.path.insert(0, str(_CODE_DIR))
    from configs.date_utils import clean_date_str
    from configs.settings import (
        BASE_DIR,
        DEFAULT_GEMINI_MODEL,
        DEFAULT_STAGE_ALIAS,
        PROJECT_ROOT,
        STAGE_MODEL_ALIASES,
        get_gemini_api_key,
        get_models_config_path,
    )
else:
    from .date_utils import clean_date_str
    from .settings import (
        BASE_DIR,
        DEFAULT_GEMINI_MODEL,
        DEFAULT_STAGE_ALIAS,
        PROJECT_ROOT,
        STAGE_MODEL_ALIASES,
        get_gemini_api_key,
        get_models_config_path,
    )

# 定義泛型型別，綁定 Pydantic BaseModel
T = TypeVar("T", bound=BaseModel)

# 台灣時區 (UTC+8)
TW_TZ = timezone(timedelta(hours=8))

# 關閉 LiteLLM 冗餘終端提示訊息
litellm.suppress_debug_info = True
litellm.drop_params = True

# 註冊 Gemini 模型定價表 (確保 LiteLLM 原生計算 response_cost 精準反映美金成本)
_GEMINI_MODEL_PRICING: Dict[str, Dict[str, Any]] = {
    "gemini-4-argon": {
        "max_tokens": 65536,
        "max_input_tokens": 1048576,
        "max_output_tokens": 65536,
        "input_cost_per_token": 2.00 / 1_000_000,
        "output_cost_per_token": 10.00 / 1_000_000,
        "cache_read_input_token_cost": 0.10 / 1_000_000,
        "litellm_provider": "gemini",
        "mode": "chat",
    },
    "gemini/gemini-4-argon": {
        "max_tokens": 65536,
        "max_input_tokens": 1048576,
        "max_output_tokens": 65536,
        "input_cost_per_token": 2.00 / 1_000_000,
        "output_cost_per_token": 10.00 / 1_000_000,
        "cache_read_input_token_cost": 0.10 / 1_000_000,
        "litellm_provider": "gemini",
        "mode": "chat",
    },
    "gemini-3.8-flash": {
        "max_tokens": 65536,
        "max_input_tokens": 1048576,
        "max_output_tokens": 65536,
        "input_cost_per_token": 0.75 / 1_000_000,
        "output_cost_per_token": 3.75 / 1_000_000,
        "cache_read_input_token_cost": 0.075 / 1_000_000,
        "litellm_provider": "gemini",
        "mode": "chat",
    },
    "gemini/gemini-3.8-flash": {
        "max_tokens": 65536,
        "max_input_tokens": 1048576,
        "max_output_tokens": 65536,
        "input_cost_per_token": 0.75 / 1_000_000,
        "output_cost_per_token": 3.75 / 1_000_000,
        "cache_read_input_token_cost": 0.075 / 1_000_000,
        "litellm_provider": "gemini",
        "mode": "chat",
    },
    "gemini-3.6-flash": {
        "max_tokens": 65536,
        "max_input_tokens": 1048576,
        "max_output_tokens": 65536,
        "input_cost_per_token": 0.75 / 1_000_000,
        "output_cost_per_token": 3.75 / 1_000_000,
        "cache_read_input_token_cost": 0.075 / 1_000_000,
        "litellm_provider": "gemini",
        "mode": "chat",
    },
    "gemini/gemini-3.6-flash": {
        "max_tokens": 65536,
        "max_input_tokens": 1048576,
        "max_output_tokens": 65536,
        "input_cost_per_token": 0.75 / 1_000_000,
        "output_cost_per_token": 3.75 / 1_000_000,
        "cache_read_input_token_cost": 0.075 / 1_000_000,
        "litellm_provider": "gemini",
        "mode": "chat",
    },
    "gemini-3.5-flash-lite": {
        "max_tokens": 65536,
        "max_input_tokens": 1048576,
        "max_output_tokens": 65536,
        "input_cost_per_token": 0.30 / 1_000_000,
        "output_cost_per_token": 2.50 / 1_000_000,
        "cache_read_input_token_cost": 0.03 / 1_000_000,
        "litellm_provider": "gemini",
        "mode": "chat",
    },
    "gemini/gemini-3.5-flash-lite": {
        "max_tokens": 65536,
        "max_input_tokens": 1048576,
        "max_output_tokens": 65536,
        "input_cost_per_token": 0.30 / 1_000_000,
        "output_cost_per_token": 2.50 / 1_000_000,
        "cache_read_input_token_cost": 0.03 / 1_000_000,
        "litellm_provider": "gemini",
        "mode": "chat",
    },
}
try:
    litellm.register_model(_GEMINI_MODEL_PRICING)
except Exception:
    pass


# =============================================================================
# 辅助資料結構與 Gemini 原始回應正規化 (支援 dict 與屬性存取)
# =============================================================================
class AttrDict(dict):
    """同時支援字典 `d['key']` 與物件屬性 `d.key` 存取的強化字典。"""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'AttrDict' object has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


def _to_attr_dict(obj: Any) -> Any:
    """遞迴將 dict / list 轉為 AttrDict，並將 camelCase 的 executableCode 同步映射為 executable_code。"""
    if isinstance(obj, dict):
        new_d = AttrDict()
        for k, v in obj.items():
            conv_v = _to_attr_dict(v)
            new_d[k] = conv_v
            if k == "executableCode" and "executable_code" not in obj:
                new_d["executable_code"] = conv_v
            elif k == "codeExecutionResult" and "code_execution_result" not in obj:
                new_d["code_execution_result"] = conv_v
            elif k == "usageMetadata" and "usage_metadata" not in obj:
                new_d["usage_metadata"] = conv_v
        return new_d
    if isinstance(obj, list):
        return [_to_attr_dict(item) for item in obj]
    return obj


def _get_field(obj: Any, key: str, default: Any = None) -> Any:
    """安全取得 dict 或物件的欄位值。"""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


# =============================================================================
# 掛鉤 LiteLLM Gemini 底層轉換器以保留 _hidden_params["original_response"]
# =============================================================================
_STREAM_STATE = threading.local()
_LATEST_ORIGINAL_RESPONSE: Optional[AttrDict] = None
_HOOKS_INSTALLED = False


def _install_litellm_gemini_hooks() -> None:
    """確保非串流與串流模式下，`completion_response._hidden_params['original_response']`
    皆完整保留 Gemini 原始 `candidates -> content -> parts` (含 `executable_code`)，
    且 `usage.completion_tokens_details.tool_use_tokens` 同步映射。
    """
    global _HOOKS_INSTALLED
    if _HOOKS_INSTALLED:
        return

    try:
        from litellm.llms.vertex_ai.gemini.vertex_and_google_ai_studio_gemini import (
            ModelResponseIterator,
            VertexGeminiConfig,
        )
        from litellm.types.utils import CompletionTokensDetailsWrapper

        orig_transform = VertexGeminiConfig._transform_google_generate_content_to_openai_model_response

        def _wrapped_transform(
            self: Any,
            completion_response: Any,
            model_response: Any,
            model: str,
            logging_obj: Any,
            raw_response: Any,
        ) -> Any:
            global _LATEST_ORIGINAL_RESPONSE
            res = orig_transform(
                self,
                completion_response=completion_response,
                model_response=model_response,
                model=model,
                logging_obj=logging_obj,
                raw_response=raw_response,
            )
            try:
                norm_orig = _to_attr_dict(
                    dict(completion_response) if isinstance(completion_response, dict) else completion_response
                )
                _LATEST_ORIGINAL_RESPONSE = norm_orig
                if not hasattr(res, "_hidden_params") or res._hidden_params is None:
                    res._hidden_params = {}
                res._hidden_params["original_response"] = norm_orig

                # 同步將 tool_use_tokens 映射至 usage.completion_tokens_details.tool_use_tokens
                usage = getattr(res, "usage", None)
                if usage is not None:
                    p_details = getattr(usage, "prompt_tokens_details", None)
                    tool_tokens = getattr(p_details, "tool_use_tokens", None) if p_details else None
                    if tool_tokens is None and isinstance(norm_orig, dict):
                        u_meta = norm_orig.get("usageMetadata") or {}
                        tool_tokens = u_meta.get("toolUsePromptTokenCount")
                    c_details = getattr(usage, "completion_tokens_details", None)
                    if c_details is None:
                        c_details = CompletionTokensDetailsWrapper()
                        setattr(usage, "completion_tokens_details", c_details)
                    if getattr(c_details, "tool_use_tokens", None) is None:
                        setattr(c_details, "tool_use_tokens", int(tool_tokens or 0))
            except Exception:
                pass
            return res

        VertexGeminiConfig._transform_google_generate_content_to_openai_model_response = _wrapped_transform

        orig_chunk_parser = ModelResponseIterator.chunk_parser

        def _wrapped_chunk_parser(self: Any, chunk: dict) -> Any:
            global _LATEST_ORIGINAL_RESPONSE
            if not hasattr(self, "_accumulated_gemini_parts"):
                self._accumulated_gemini_parts = []
                self._latest_gemini_usage_meta = {}

            try:
                if isinstance(chunk, dict):
                    u_meta = chunk.get("usageMetadata")
                    if isinstance(u_meta, dict) and u_meta:
                        self._latest_gemini_usage_meta = dict(u_meta)

                    cands = chunk.get("candidates") or []
                    for cand in cands:
                        content = cand.get("content") if isinstance(cand, dict) else None
                        parts = content.get("parts") if isinstance(content, dict) else None
                        if isinstance(parts, list):
                            for p in parts:
                                norm_p = _to_attr_dict(p)
                                self._accumulated_gemini_parts.append(norm_p)
                                # 若啟用串流即時印出 Code Execution
                                if getattr(_STREAM_STATE, "print_code_execution", False):
                                    exec_code = _get_field(norm_p, "executable_code")
                                    if exec_code and _get_field(exec_code, "code"):
                                        lang = _get_field(exec_code, "language", "PYTHON")
                                        code_str = _get_field(exec_code, "code", "")
                                        print(
                                            f"\n\n[模型執行 Python 程式碼 ({lang})]\n```python\n{code_str}\n```\n",
                                            flush=True,
                                        )
                                    exec_res = _get_field(norm_p, "code_execution_result")
                                    if exec_res and _get_field(exec_res, "output") is not None:
                                        outcome = _get_field(exec_res, "outcome", "")
                                        out_str = _get_field(exec_res, "output", "")
                                        print(
                                            f"\n[程式碼執行結果 ({outcome})]\n```text\n{out_str}\n```\n",
                                            flush=True,
                                        )
            except Exception:
                pass

            model_resp = orig_chunk_parser(self, chunk)
            try:
                synth_orig = _to_attr_dict(
                    {
                        "candidates": [{"content": {"parts": list(self._accumulated_gemini_parts)}}],
                        "usageMetadata": dict(self._latest_gemini_usage_meta),
                    }
                )
                _LATEST_ORIGINAL_RESPONSE = synth_orig
                if model_resp is not None:
                    if not hasattr(model_resp, "_hidden_params") or model_resp._hidden_params is None:
                        model_resp._hidden_params = {}
                    model_resp._hidden_params["original_response"] = synth_orig
            except Exception:
                pass
            return model_resp

        ModelResponseIterator.chunk_parser = _wrapped_chunk_parser
        _HOOKS_INSTALLED = True
    except Exception as e:
        print(f"[警告] 安裝 LiteLLM Gemini 原始回應攔截器失敗: {e}")


_install_litellm_gemini_hooks()


# =============================================================================
# 全域 Usage 收集器與 Callback 實作 (規格 3 & 4)
# =============================================================================
SESSION_USAGE_RECORDS: List[Dict[str, Any]] = []
LAST_USAGE_RECORD: Dict[str, Any] = {}
_CALLBACK_LOCK = threading.Lock()
_CALLBACK_EVENT = threading.Event()


def _parse_provider_and_model(raw_model: str, litellm_params: Dict[str, Any]) -> tuple[str, str]:
    """解析 provider 與乾淨的模型名稱。"""
    provider = str(litellm_params.get("custom_llm_provider") or "").strip().lower()
    model_str = str(raw_model or "").strip()

    if "/" in model_str:
        prefix, rest = model_str.split("/", 1)
        if prefix.lower() in ("gemini", "vertex_ai", "google"):
            provider = "gemini"
            model_str = rest
        elif not provider:
            provider = prefix.lower()
            model_str = rest

    if model_str.startswith("models/"):
        model_str = model_str[len("models/") :]

    if not provider:
        provider = "gemini"

    return provider, model_str


def _compute_duration_seconds(start_time: Any, end_time: Any) -> float:
    """由 Callback 的 end_time - start_time 計算耗時秒數。"""
    try:
        if isinstance(start_time, datetime) and isinstance(end_time, datetime):
            return round(max(0.0, (end_time - start_time).total_seconds()), 2)
        if isinstance(start_time, (int, float)) and isinstance(end_time, (int, float)):
            return round(max(0.0, float(end_time) - float(start_time)), 2)
    except Exception:
        pass
    return 0.0


def _ensure_original_response_on_completion(
    completion_response: Any, kwargs: Dict[str, Any]
) -> Optional[Any]:
    """確保 completion_response._hidden_params['original_response'] 存在並回傳。"""
    if completion_response is None:
        return None

    hidden_params = getattr(completion_response, "_hidden_params", None)
    if hidden_params is None or not isinstance(hidden_params, dict):
        hidden_params = {}
        try:
            setattr(completion_response, "_hidden_params", hidden_params)
        except Exception:
            pass

    orig = hidden_params.get("original_response")
    if orig is None:
        raw_kw_orig = kwargs.get("original_response")
        if isinstance(raw_kw_orig, str) and raw_kw_orig.strip().startswith("{"):
            try:
                orig = _to_attr_dict(json.loads(raw_kw_orig))
            except Exception:
                orig = None
        elif isinstance(raw_kw_orig, dict):
            orig = _to_attr_dict(raw_kw_orig)

    if orig is None and _LATEST_ORIGINAL_RESPONSE is not None:
        orig = _LATEST_ORIGINAL_RESPONSE

    if orig is not None:
        hidden_params["original_response"] = orig

    return hidden_params.get("original_response")


def _extract_gemini_code_execution(completion_response: Any, kwargs: Dict[str, Any]) -> tuple[bool, int, List[Dict[str, str]]]:
    """從 completion_response._hidden_params.get("original_response") 的
    candidates -> content -> parts 解析 executable_code。
    """
    orig_response = _ensure_original_response_on_completion(completion_response, kwargs)
    if orig_response is None and completion_response is not None:
        orig_response = getattr(completion_response, "_hidden_params", {}).get("original_response")

    executed_codes: List[Dict[str, str]] = []
    if orig_response is not None:
        candidates = _get_field(orig_response, "candidates") or []
        for candidate in candidates:
            content = _get_field(candidate, "content")
            parts = _get_field(content, "parts") or [] if content is not None else []
            for part in parts:
                exec_code = _get_field(part, "executable_code") or _get_field(part, "executableCode")
                if exec_code is not None:
                    lang = _get_field(exec_code, "language") or "PYTHON"
                    code_text = _get_field(exec_code, "code") or ""
                    if code_text:
                        executed_codes.append(
                            {
                                "language": str(lang),
                                "code": str(code_text),
                            }
                        )

    call_count = len(executed_codes)
    return (call_count > 0), call_count, executed_codes


def litellm_success_callback(
    kwargs: Dict[str, Any],
    completion_response: Any,
    start_time: Any,
    end_time: Any,
) -> None:
    """LiteLLM 全域成功回呼函式 (解析 19 項標準 Usage 指標與 Gemini Code Execution 明細)。"""
    global LAST_USAGE_RECORD

    try:
        now_tw = datetime.now(TW_TZ)
        litellm_params = kwargs.get("litellm_params", {}) or {}
        metadata = litellm_params.get("metadata", {}) or kwargs.get("metadata", {}) or {}

        # 若觸發 Fallback，保留原始呼叫的路由群組別名於 metadata["model_group"]
        if metadata.get("original_model_group"):
            metadata["model_group"] = metadata["original_model_group"]

        stage = str(metadata.get("stage") or "unknown")
        model_group = str(metadata.get("model_group") or STAGE_MODEL_ALIASES.get(stage, stage))
        raw_date = str(metadata.get("target_date") or now_tw.strftime("%Y%m%d"))
        try:
            date_str = clean_date_str(raw_date)
        except Exception:
            date_str = now_tw.strftime("%Y%m%d")

        raw_model_name = (
            getattr(completion_response, "model", None)
            or kwargs.get("model")
            or DEFAULT_GEMINI_MODEL
        )
        provider, model_name = _parse_provider_and_model(str(raw_model_name), litellm_params)

        # 解析 finish_reason
        finish_reason = "stop"
        choices = getattr(completion_response, "choices", None) or []
        if choices:
            fr = getattr(choices[0], "finish_reason", None)
            if fr:
                finish_reason = str(fr).lower()

        duration_seconds = _compute_duration_seconds(start_time, end_time)

        # 解析 completion_response._hidden_params.get("original_response") 中的 Code Execution 明細
        code_execution_used, code_execution_call_count, executed_codes = _extract_gemini_code_execution(
            completion_response, kwargs
        )

        # 解析 Usage Token 指標
        usage = getattr(completion_response, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0
        total_tokens = int(getattr(usage, "total_tokens", 0) or 0) if usage else 0

        prompt_details = getattr(usage, "prompt_tokens_details", None) if usage else None
        completion_details = getattr(usage, "completion_tokens_details", None) if usage else None

        cached_tokens = int(getattr(prompt_details, "cached_tokens", 0) or 0) if prompt_details else 0

        # 確保 completion_tokens_details.tool_use_tokens 可直接取得
        orig_resp = getattr(completion_response, "_hidden_params", {}).get("original_response")
        orig_u_meta = _get_field(orig_resp, "usageMetadata") or {} if orig_resp else {}
        if completion_details is not None and getattr(completion_details, "tool_use_tokens", None) in (None, 0):
            fallback_tool_tokens = (
                (getattr(prompt_details, "tool_use_tokens", None) if prompt_details else None)
                or orig_u_meta.get("toolUsePromptTokenCount")
                or 0
            )
            try:
                setattr(completion_details, "tool_use_tokens", int(fallback_tool_tokens))
            except Exception:
                pass

        tool_use_tokens = int(
            (getattr(completion_details, "tool_use_tokens", 0) if completion_details else 0)
            or (getattr(prompt_details, "tool_use_tokens", 0) if prompt_details else 0)
            or orig_u_meta.get("toolUsePromptTokenCount")
            or 0
        )
        reasoning_tokens = int(
            (getattr(completion_details, "reasoning_tokens", 0) if completion_details else 0)
            or (getattr(usage, "reasoning_tokens", 0) if usage else 0)
            or orig_u_meta.get("thoughtsTokenCount")
            or 0
        )

        # 解析 response_cost
        raw_cost = kwargs.get("response_cost")
        if not raw_cost:
            try:
                raw_cost = litellm.completion_cost(
                    completion_response=completion_response,
                    model=f"{provider}/{model_name}",
                )
            except Exception:
                raw_cost = 0.0
        response_cost = round(float(raw_cost or 0.0), 6)

        record: Dict[str, Any] = {
            # 【時間與路由識別】
            "timestamp": now_tw.isoformat(timespec="seconds"),
            "date": date_str,
            "provider": provider,
            "model": model_name,
            "model_group": model_group,
            "stage": stage,
            "status": "success",
            "finish_reason": finish_reason,
            "duration_seconds": duration_seconds,
            # 【LiteLLM 原生 Token 與成本指標】
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cached_tokens": cached_tokens,
            "tool_use_tokens": tool_use_tokens,
            "reasoning_tokens": reasoning_tokens,
            "response_cost": response_cost,
            # 【Gemini Code Execution 明細】
            "code_execution_used": code_execution_used,
            "code_execution_call_count": code_execution_call_count,
            "executed_codes": executed_codes,
        }

        with _CALLBACK_LOCK:
            LAST_USAGE_RECORD = record
            SESSION_USAGE_RECORDS.append(record)
            _CALLBACK_EVENT.set()
    except Exception as e:
        print(f"[警告] litellm_success_callback 解析失敗: {e}")


def litellm_failure_callback(
    kwargs: Dict[str, Any],
    completion_response: Any,
    start_time: Any,
    end_time: Any,
) -> None:
    """LiteLLM 全域失敗回呼函式。"""
    global LAST_USAGE_RECORD

    try:
        now_tw = datetime.now(TW_TZ)
        litellm_params = kwargs.get("litellm_params", {}) or {}
        metadata = litellm_params.get("metadata", {}) or kwargs.get("metadata", {}) or {}

        if metadata.get("original_model_group"):
            metadata["model_group"] = metadata["original_model_group"]

        stage = str(metadata.get("stage") or "unknown")
        model_group = str(metadata.get("model_group") or STAGE_MODEL_ALIASES.get(stage, stage))
        raw_date = str(metadata.get("target_date") or now_tw.strftime("%Y%m%d"))
        try:
            date_str = clean_date_str(raw_date)
        except Exception:
            date_str = now_tw.strftime("%Y%m%d")

        raw_model_name = kwargs.get("model") or DEFAULT_GEMINI_MODEL
        provider, model_name = _parse_provider_and_model(str(raw_model_name), litellm_params)
        duration_seconds = _compute_duration_seconds(start_time, end_time)

        record: Dict[str, Any] = {
            # 【時間與路由識別】
            "timestamp": now_tw.isoformat(timespec="seconds"),
            "date": date_str,
            "provider": provider,
            "model": model_name,
            "model_group": model_group,
            "stage": stage,
            "status": "failed",
            "finish_reason": "error",
            "duration_seconds": duration_seconds,
            # 【LiteLLM 原生 Token 與成本指標】
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cached_tokens": 0,
            "tool_use_tokens": 0,
            "reasoning_tokens": 0,
            "response_cost": 0.0,
            # 【Gemini Code Execution 明細】
            "code_execution_used": False,
            "code_execution_call_count": 0,
            "executed_codes": [],
        }

        with _CALLBACK_LOCK:
            LAST_USAGE_RECORD = record
            SESSION_USAGE_RECORDS.append(record)
            _CALLBACK_EVENT.set()
    except Exception as e:
        print(f"[警告] litellm_failure_callback 記錄失敗: {e}")


# 註冊全域 LiteLLM Callbacks
litellm.success_callback = [litellm_success_callback]
litellm.failure_callback = [litellm_failure_callback]


# =============================================================================
# 本地歷史 Usage 結算與合併 (寫入 usage_history.json)
# =============================================================================
USAGE_HISTORY_PATHS: List[Path] = [
    BASE_DIR / "portfolio_dashboard" / "usage_history.json",
    PROJECT_ROOT / "data" / "D-Paln_Output" / "usage_history.json",
]


def _normalize_usage_record_schema(rec: Dict[str, Any]) -> Dict[str, Any]:
    """將舊版或新版 Usage 紀錄統一正規化為 19 欄 LiteLLM 標準 Schema。"""
    stage = str(rec.get("stage") or "unknown").lower()
    raw_model = str(rec.get("model") or "")
    provider = str(rec.get("provider") or "gemini")
    if "/" in raw_model:
        _, raw_model = raw_model.split("/", 1)

    # 處理 executed_codes: 舊版可能為 list[str]，新版為 list[dict]
    raw_codes = rec.get("executed_codes") or []
    norm_codes: List[Dict[str, str]] = []
    for item in raw_codes:
        if isinstance(item, dict):
            norm_codes.append(
                {
                    "language": str(item.get("language") or "PYTHON"),
                    "code": str(item.get("code") or ""),
                }
            )
        elif isinstance(item, str) and item.strip():
            norm_codes.append({"language": "PYTHON", "code": item})

    call_count = int(rec.get("code_execution_call_count", len(norm_codes)) or len(norm_codes))
    code_used = bool(rec.get("code_execution_used", call_count > 0))

    prompt_tokens = int(rec.get("prompt_tokens") or 0)
    completion_tokens = int(rec.get("completion_tokens", rec.get("candidates_tokens", 0)) or 0)
    total_tokens = int(rec.get("total_tokens") or 0)
    cached_tokens = int(rec.get("cached_tokens") or 0)
    tool_use_tokens = int(rec.get("tool_use_tokens") or 0)
    reasoning_tokens = int(rec.get("reasoning_tokens", rec.get("thought_tokens", 0)) or 0)

    raw_cost = float(rec.get("response_cost") or 0.0)
    if raw_cost <= 0.0 and (prompt_tokens > 0 or completion_tokens > 0):
        pricing = _GEMINI_MODEL_PRICING.get(raw_model) or _GEMINI_MODEL_PRICING.get(f"{provider}/{raw_model}")
        if pricing:
            non_cached_prompt = max(0, prompt_tokens - cached_tokens)
            # 舊版紀錄之 candidates_tokens 不含 thought_tokens，若為舊版則加總計費
            billable_output = (
                completion_tokens + reasoning_tokens
                if "candidates_tokens" in rec and "completion_tokens" not in rec
                else completion_tokens
            )
            raw_cost = (
                non_cached_prompt * float(pricing.get("input_cost_per_token", 0.0))
                + cached_tokens * float(pricing.get("cache_read_input_token_cost", 0.0))
                + billable_output * float(pricing.get("output_cost_per_token", 0.0))
            )

    return {
        "timestamp": str(rec.get("timestamp") or ""),
        "date": str(rec.get("date") or ""),
        "provider": provider,
        "model": raw_model,
        "model_group": str(rec.get("model_group") or STAGE_MODEL_ALIASES.get(stage, f"stage-{stage}")),
        "stage": stage,
        "status": str(rec.get("status") or "success"),
        "finish_reason": str(rec.get("finish_reason") or "stop").lower(),
        "duration_seconds": round(float(rec.get("duration_seconds") or 0.0), 2),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cached_tokens": cached_tokens,
        "tool_use_tokens": tool_use_tokens,
        "reasoning_tokens": reasoning_tokens,
        "response_cost": round(raw_cost, 6),
        "code_execution_used": code_used,
        "code_execution_call_count": call_count,
        "executed_codes": norm_codes,
    }


def settle_usage_history(extra_records: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """收集所有階段 Usage JSON 與本次執行紀錄，合併寫入本地 `usage_history.json` 並結算統計數據。"""
    primary_history_file = USAGE_HISTORY_PATHS[0]
    existing_records: List[Dict[str, Any]] = []

    if primary_history_file.is_file():
        try:
            data = json.loads(primary_history_file.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("records"), list):
                existing_records = data["records"]
            elif isinstance(data, list):
                existing_records = data
        except Exception:
            existing_records = []

    # 掃描 data/D-Paln_Output/<stage>/usage/*_usage_*.json
    dplan_out_dir = PROJECT_ROOT / "data" / "D-Paln_Output"
    stage_files = sorted(dplan_out_dir.glob("*/usage/*_usage_*.json")) if dplan_out_dir.is_dir() else []

    # 以 (date, stage, timestamp) 進行合併，並對同 (date, stage) 的最新檔案做更新
    merged_by_date_stage: Dict[tuple[str, str], Dict[str, Any]] = {}

    for rec in existing_records:
        if isinstance(rec, dict) and rec.get("date") and rec.get("stage"):
            norm = _normalize_usage_record_schema(rec)
            merged_by_date_stage[(norm["date"], norm["stage"])] = norm

    for sf in stage_files:
        try:
            raw_rec = json.loads(sf.read_text(encoding="utf-8"))
            if isinstance(raw_rec, dict):
                # 由檔名補齊 stage / date (相容舊版無 stage 欄位之檔案)
                m = re.match(r"^([a-z0-9]+)_usage_(\d{8})\.json$", sf.name, re.IGNORECASE)
                if m:
                    raw_rec.setdefault("stage", m.group(1).lower())
                    raw_rec.setdefault("date", m.group(2))
                norm = _normalize_usage_record_schema(raw_rec)
                if norm["date"] and norm["stage"]:
                    merged_by_date_stage[(norm["date"], norm["stage"])] = norm
        except Exception:
            continue

    all_session = list(SESSION_USAGE_RECORDS) + (list(extra_records) if extra_records else [])
    for rec in all_session:
        if isinstance(rec, dict) and rec.get("date") and rec.get("stage"):
            norm = _normalize_usage_record_schema(rec)
            merged_by_date_stage[(norm["date"], norm["stage"])] = norm

    stage_order = {"l1": 1, "l2m": 2, "l2": 3, "l3": 4, "l4": 5}
    sorted_records = sorted(
        merged_by_date_stage.values(),
        key=lambda r: (r.get("date", ""), stage_order.get(r.get("stage", ""), 99), r.get("timestamp", "")),
    )

    # 結算每日與總體統計
    daily_summary: Dict[str, Dict[str, Any]] = {}
    total_summary: Dict[str, Any] = {
        "total_calls": len(sorted_records),
        "success_calls": 0,
        "failed_calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cached_tokens": 0,
        "tool_use_tokens": 0,
        "reasoning_tokens": 0,
        "response_cost": 0.0,
        "duration_seconds": 0.0,
        "code_execution_call_count": 0,
    }

    for r in sorted_records:
        d = r["date"]
        if d not in daily_summary:
            daily_summary[d] = {
                "date": d,
                "calls": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "cached_tokens": 0,
                "tool_use_tokens": 0,
                "reasoning_tokens": 0,
                "response_cost": 0.0,
                "duration_seconds": 0.0,
                "code_execution_call_count": 0,
                "stages": {},
            }

        day_bucket = daily_summary[d]
        day_bucket["calls"] += 1
        for k in (
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "cached_tokens",
            "tool_use_tokens",
            "reasoning_tokens",
            "code_execution_call_count",
        ):
            day_bucket[k] += int(r.get(k, 0) or 0)
            total_summary[k] += int(r.get(k, 0) or 0)

        day_bucket["response_cost"] = round(day_bucket["response_cost"] + float(r.get("response_cost", 0.0) or 0.0), 6)
        day_bucket["duration_seconds"] = round(
            day_bucket["duration_seconds"] + float(r.get("duration_seconds", 0.0) or 0.0), 2
        )
        day_bucket["stages"][r["stage"]] = {
            "model": r["model"],
            "model_group": r["model_group"],
            "status": r["status"],
            "finish_reason": r["finish_reason"],
            "duration_seconds": r["duration_seconds"],
            "prompt_tokens": r["prompt_tokens"],
            "completion_tokens": r["completion_tokens"],
            "total_tokens": r["total_tokens"],
            "cached_tokens": r["cached_tokens"],
            "tool_use_tokens": r["tool_use_tokens"],
            "reasoning_tokens": r["reasoning_tokens"],
            "response_cost": r["response_cost"],
            "code_execution_used": r["code_execution_used"],
            "code_execution_call_count": r["code_execution_call_count"],
        }

        if r.get("status") == "success":
            total_summary["success_calls"] += 1
        else:
            total_summary["failed_calls"] += 1
        total_summary["response_cost"] = round(
            total_summary["response_cost"] + float(r.get("response_cost", 0.0) or 0.0), 6
        )
        total_summary["duration_seconds"] = round(
            total_summary["duration_seconds"] + float(r.get("duration_seconds", 0.0) or 0.0), 2
        )

    history_payload: Dict[str, Any] = {
        "updated_at": datetime.now(TW_TZ).isoformat(timespec="seconds"),
        "summary": total_summary,
        "daily_summary": daily_summary,
        "records": sorted_records,
    }

    for path in USAGE_HISTORY_PATHS:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(history_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[警告] 寫入歷史 Usage 檔案 {path} 失敗: {e}")

    return history_payload


# =============================================================================
# JSON 清理與修復輔助函式
# =============================================================================
def extract_and_clean_json(raw_text: str) -> str:
    """清理並修復 LLM 回傳的不合規 JSON 字串。"""
    text = raw_text.strip()

    # 1. 移除 ```json ... ``` 或 ``` ... ``` 區塊標籤
    code_block_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if code_block_match:
        text = code_block_match.group(1).strip()

    # 2. 定位最外層的 '{' 與 '}'
    start_idx = text.find("{")
    end_idx = text.rfind("}")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        text = text[start_idx : end_idx + 1]

    # 3. 修復非法反斜線跳脫
    text = re.sub(r'\\(?![/\"\\bfnrt]|u[0-9a-fA-F]{4})', r"\\\\", text)

    # 4. 移除物件或陣列結尾的多餘逗號
    text = re.sub(r",\s*([}\]])", r"\1", text)

    return text


# =============================================================================
# LiteLLM Router 單例管理
# =============================================================================
_SHARED_ROUTER: Optional[Router] = None
_ROUTER_CONFIG_DATA: Dict[str, Any] = {}


def get_litellm_router(force_reload: bool = False) -> tuple[Router, Dict[str, Any]]:
    """載入 `models_config.yaml` 並初始化 `litellm.Router`。"""
    global _SHARED_ROUTER, _ROUTER_CONFIG_DATA

    # 確保 GEMINI_API_KEY 已載入 os.environ
    get_gemini_api_key()

    if _SHARED_ROUTER is not None and not force_reload:
        return _SHARED_ROUTER, _ROUTER_CONFIG_DATA

    config_path = get_models_config_path()
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    model_list = cfg.get("model_list", [])
    router_settings = cfg.get("router_settings", {}) or {}

    _ROUTER_CONFIG_DATA = cfg
    _SHARED_ROUTER = Router(
        model_list=model_list,
        fallbacks=router_settings.get("fallbacks", []),
        num_retries=router_settings.get("num_retries", 2),
        timeout=router_settings.get("timeout", 600),
        cooldown_time=router_settings.get("cooldown_time", 30),
    )
    return _SHARED_ROUTER, _ROUTER_CONFIG_DATA


# =============================================================================
# GeminiClient (相容原有呼叫端介面，底層全面採用 LiteLLM Router)
# =============================================================================
class GeminiClient:
    """基於 LiteLLM Router 的 Google Gemini API 客戶端。"""

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        stage: Optional[str] = None,
        target_date: Optional[str] = None,
    ) -> None:
        """初始化 LiteLLM Router 與預設任務階段設定。

        Args:
            model: 模型名稱或 Router 別名 (如 "stage-l1", "stage-l2", "gemini/gemini-4-argon")。
            api_key: 選填 API 金鑰，若未提供則由 `.env` 讀取並注入 `os.environ["GEMINI_API_KEY"]`。
            stage: 任務階段標籤 (如 "l1", "l2m", "l2", "l3", "l4")。
            target_date: 目標交易日 (YYYYMMDD)。
        """
        if api_key:
            os.environ["GEMINI_API_KEY"] = api_key.strip()
            self.api_key = api_key.strip()
        else:
            self.api_key = get_gemini_api_key()

        self.stage = (stage or "l2").lower()
        self.target_date = clean_date_str(target_date) if target_date else datetime.now(TW_TZ).strftime("%Y%m%d")
        self.router, self.router_config = get_litellm_router()

        # 決定預設路由模型別名
        if model:
            self.default_model = model
        else:
            self.default_model = STAGE_MODEL_ALIASES.get(self.stage, DEFAULT_STAGE_ALIAS)

        self.last_usage: Dict[str, Any] = {}

    def _resolve_routing_target(
        self,
        model: Optional[str] = None,
        stage: Optional[str] = None,
        target_date: Optional[str] = None,
    ) -> tuple[str, str, str, str]:
        """解析本次呼叫的 (router_model_arg, stage_name, model_group_alias, target_date_str)。"""
        eff_stage = (stage or self.stage or "l2").lower()
        eff_date = clean_date_str(target_date) if target_date else self.target_date
        default_group = STAGE_MODEL_ALIASES.get(eff_stage, f"stage-{eff_stage}")

        requested = (model or self.default_model or default_group).strip()
        configured_names = {
            m.get("model_name") for m in self.router_config.get("model_list", []) if isinstance(m, dict)
        }

        if requested in configured_names:
            return requested, eff_stage, requested, eff_date

        # 若傳入的是階段簡稱 (如 "l1", "l2")
        if requested.lower() in STAGE_MODEL_ALIASES and STAGE_MODEL_ALIASES[requested.lower()] in configured_names:
            alias = STAGE_MODEL_ALIASES[requested.lower()]
            return alias, requested.lower(), alias, eff_date

        # 若外部透過 CLI --model 指定特定 Gemini 模型名稱 (如 "gemini-3.8-flash")
        if not requested.startswith("gemini/"):
            full_model = f"gemini/{requested}"
        else:
            full_model = requested

        # 檢查該模型是否已存在於 Router 部署節點，若無則動態註冊一個臨時部署節點於 Router
        dynamic_alias = f"custom-{full_model.split('/', 1)[1]}"
        if dynamic_alias not in configured_names:
            new_deployment = {
                "model_name": dynamic_alias,
                "litellm_params": {
                    "model": full_model,
                    "api_key": "os.environ/GEMINI_API_KEY",
                },
            }
            self.router.model_list.append(new_deployment)
            self.router_config.setdefault("model_list", []).append(new_deployment)
            try:
                self.router.set_model_list(self.router.model_list)
            except Exception:
                pass

        return dynamic_alias, eff_stage, default_group, eff_date

    @staticmethod
    def _build_messages(prompt: str, system_instruction: Optional[str] = None) -> List[Dict[str, str]]:
        """組裝 OpenAI 標準格式之 messages 列表。"""
        messages: List[Dict[str, str]] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
        return messages

    def save_usage_metadata(
        self,
        output_dir: Path,
        stage_prefix: str,
        target_date: str,
    ) -> Optional[Path]:
        """將最近一次 API 呼叫的 LiteLLM Usage 紀錄存為 JSON 檔案，並同步合併至 `usage_history.json`。

        輸出路徑：<output_dir>/usage/<stage_prefix>_usage_<YYYYMMDD>.json
        """
        if not self.last_usage:
            return None

        c_date = clean_date_str(target_date)
        stage_clean = stage_prefix.strip().lower()

        # 確保 date 與 stage 與呼叫端一致
        self.last_usage["date"] = c_date
        self.last_usage["stage"] = stage_clean
        if not self.last_usage.get("model_group") or self.last_usage.get("model_group") == "unknown":
            self.last_usage["model_group"] = STAGE_MODEL_ALIASES.get(stage_clean, f"stage-{stage_clean}")

        usage_dir = output_dir / "usage"
        usage_dir.mkdir(parents=True, exist_ok=True)
        usage_file = usage_dir / f"{stage_clean}_usage_{c_date}.json"

        with open(usage_file, "w", encoding="utf-8") as f:
            json.dump(self.last_usage, f, ensure_ascii=False, indent=2)

        print(
            f"[用量紀錄] 已儲存至: {usage_file} "
            f"(model: {self.last_usage.get('model')}, group: {self.last_usage.get('model_group')}, "
            f"total_tokens: {self.last_usage.get('total_tokens', 0):,}, "
            f"cost: ${self.last_usage.get('response_cost', 0.0):.6f}, "
            f"耗時: {self.last_usage.get('duration_seconds', 0)}s)"
        )

        # 同步合併更新本地歷史 Usage JSON (usage_history.json)
        settle_usage_history(extra_records=[self.last_usage])
        return usage_file

    def generate_text(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        enable_code_execution: bool = False,
        stage: Optional[str] = None,
        target_date: Optional[str] = None,
    ) -> str:
        """透過 `router.completion()` 發送純文字請求並回傳模型生成的文字回應。"""
        router_model, eff_stage, model_group, eff_date = self._resolve_routing_target(
            model=model, stage=stage, target_date=target_date
        )
        messages = self._build_messages(prompt, system_instruction)

        call_kwargs: Dict[str, Any] = {
            "model": router_model,
            "messages": messages,
            "temperature": temperature,
            "metadata": {
                "stage": eff_stage,
                "model_group": model_group,
                "original_model_group": model_group,
                "target_date": eff_date,
            },
        }
        if enable_code_execution:
            call_kwargs["tools"] = [{"code_execution": {}}]

        _CALLBACK_EVENT.clear()
        response = self.router.completion(**call_kwargs)
        _CALLBACK_EVENT.wait(timeout=2.0)

        with _CALLBACK_LOCK:
            self.last_usage = dict(LAST_USAGE_RECORD) if LAST_USAGE_RECORD else {}

        content = ""
        if getattr(response, "choices", None):
            content = getattr(response.choices[0].message, "content", "") or ""
        return content

    def generate_stream(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        enable_code_execution: bool = False,
        stage: Optional[str] = None,
        target_date: Optional[str] = None,
        response_format: Optional[Any] = None,
    ) -> str:
        """透過 `router.completion(..., stream=True)` 即時串流印出回應（包含思考過程與 Code Execution），最後回傳完整文字。"""
        router_model, eff_stage, model_group, eff_date = self._resolve_routing_target(
            model=model, stage=stage, target_date=target_date
        )
        messages = self._build_messages(prompt, system_instruction)

        call_kwargs: Dict[str, Any] = {
            "model": router_model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
            "metadata": {
                "stage": eff_stage,
                "model_group": model_group,
                "original_model_group": model_group,
                "target_date": eff_date,
            },
        }
        if enable_code_execution:
            call_kwargs["tools"] = [{"code_execution": {}}]
        elif response_format is not None:
            call_kwargs["response_format"] = response_format

        full_text: List[str] = []
        collected_chunks: List[Any] = []
        is_thinking = False
        is_answering = False

        _CALLBACK_EVENT.clear()
        _STREAM_STATE.print_code_execution = True
        start_dt = datetime.now(timezone.utc)
        stream_response = None
        try:
            stream_response = self.router.completion(**call_kwargs)
            for chunk in stream_response:
                collected_chunks.append(chunk)
                if not getattr(chunk, "choices", None):
                    continue
                delta = getattr(chunk.choices[0], "delta", None)
                if delta is None:
                    continue

                reasoning_piece = getattr(delta, "reasoning_content", None)
                if reasoning_piece:
                    if not is_thinking:
                        print("\n[模型思考過程 (Thinking)]", flush=True)
                        is_thinking = True
                        is_answering = False
                    print(reasoning_piece, end="", flush=True)

                content_piece = getattr(delta, "content", None)
                if content_piece:
                    if not is_answering:
                        print("\n\n[模型最終輸出 (JSON Response)]\n", flush=True)
                        is_answering = True
                        is_thinking = False
                    print(content_piece, end="", flush=True)
                    full_text.append(content_piece)
        finally:
            _STREAM_STATE.print_code_execution = False

        print()  # 換行

        end_dt = datetime.now(timezone.utc)
        rebuilt = None
        if collected_chunks:
            try:
                rebuilt = litellm.stream_chunk_builder(chunks=collected_chunks)
            except Exception:
                pass

        # 若背景 callback 未能設定 Usage，或記錄到的 total_tokens 為 0，以 rebuilt 重建結果主動更新
        with _CALLBACK_LOCK:
            curr_tokens = LAST_USAGE_RECORD.get("total_tokens", 0) if LAST_USAGE_RECORD else 0

        if (not _CALLBACK_EVENT.wait(timeout=1.0) or curr_tokens == 0) and rebuilt is not None:
            try:
                litellm_success_callback(call_kwargs, rebuilt, start_dt, end_dt)
            except Exception:
                pass

        with _CALLBACK_LOCK:
            self.last_usage = dict(LAST_USAGE_RECORD) if LAST_USAGE_RECORD else {}

        return "".join(full_text)

        return "".join(full_text)

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.1,
        stream: bool = False,
        enable_code_execution: bool = False,
        stage: Optional[str] = None,
        target_date: Optional[str] = None,
    ) -> T:
        """透過 `router.completion()` 發送請求並強制回傳符合指定 Pydantic Schema 的結構化物件。"""
        router_model, eff_stage, model_group, eff_date = self._resolve_routing_target(
            model=model, stage=stage, target_date=target_date
        )

        schema_json_str = json.dumps(response_model.model_json_schema(), ensure_ascii=False, indent=2)
        schema_prompt = (
            "\n\n【輸出格式強制規範】\n"
            "完成所有分析與程式碼計算後，你的最終回覆必須是且僅是一個符合以下 JSON Schema 的純 JSON 字串（請勿包含任何前後文或額外說明）：\n"
            f"```json\n{schema_json_str}\n```"
        )
        effective_sys = (system_instruction or "") + schema_prompt

        def _parse_and_validate(target_text: str) -> T:
            cleaned = extract_and_clean_json(target_text)
            try:
                return response_model.model_validate_json(cleaned)
            except Exception:
                pass

            try:
                parsed = json.loads(cleaned, strict=False)
                return response_model.model_validate(parsed)
            except Exception:
                pass

            if json_repair is not None:
                try:
                    repaired = json_repair.loads(cleaned)
                    if isinstance(repaired, dict):
                        return response_model.model_validate(repaired)
                except Exception:
                    pass

            # 若仍失敗，直接執行一次嚴格驗證以拋出標準 ValidationError 或 JSONDecodeError
            return response_model.model_validate_json(cleaned)

        if stream:
            raw_text = self.generate_stream(
                prompt=prompt,
                system_instruction=effective_sys if enable_code_execution else system_instruction,
                model=router_model,
                temperature=temperature,
                enable_code_execution=enable_code_execution,
                stage=eff_stage,
                target_date=eff_date,
                response_format=None if enable_code_execution else response_model,
            )
            return _parse_and_validate(raw_text)

        # 非串流模式
        messages = self._build_messages(prompt, effective_sys if enable_code_execution else system_instruction)
        call_kwargs: Dict[str, Any] = {
            "model": router_model,
            "messages": messages,
            "temperature": temperature,
            "metadata": {
                "stage": eff_stage,
                "model_group": model_group,
                "original_model_group": model_group,
                "target_date": eff_date,
            },
        }
        if enable_code_execution:
            # Gemini 原生沙盒與 response_format (application/json) 不可同時開啟，透過 Schema Prompt 與 JSON 解析驗證
            call_kwargs["tools"] = [{"code_execution": {}}]
        else:
            call_kwargs["response_format"] = response_model

        _CALLBACK_EVENT.clear()
        response = self.router.completion(**call_kwargs)
        _CALLBACK_EVENT.wait(timeout=2.0)

        with _CALLBACK_LOCK:
            self.last_usage = dict(LAST_USAGE_RECORD) if LAST_USAGE_RECORD else {}

        raw_text = ""
        if getattr(response, "choices", None):
            raw_text = getattr(response.choices[0].message, "content", "") or ""

        if not raw_text:
            raise RuntimeError(f"LiteLLM Router ({router_model}) 未回傳有效內容: {response}")

        return _parse_and_validate(raw_text)


# =============================================================================
# 獨立執行測試 (CLI Smoke Test)
# =============================================================================
if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    print("=== 測試 LiteLLM Router + GeminiClient 連線與 Usage Callback ===")
    try:
        client = GeminiClient(stage="l1", target_date="20261113")
        print(f"[成功] 已載入 Router 設定檔: {get_models_config_path()}")
        print(f"[成功] 預設路由群組: {client.default_model}")
        reply = client.generate_text("請用繁體中文回答：1+1 等於多少？（請在 20 字以內簡答）", stage="l1", target_date="20261113")
        print(f"[模型回覆] {reply.strip()}")
        print(f"[Usage Callback 紀錄]\n{json.dumps(client.last_usage, ensure_ascii=False, indent=2)}")
    except Exception as exc:
        print(f"[失敗] 發生錯誤：{exc}")
