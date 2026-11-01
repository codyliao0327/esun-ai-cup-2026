"""Gemini API 包裝器 (支援 Structured Outputs / JSON Schema / Streaming)。

依據官方 Google GenAI SDK 與 Interactions API 規範實作：
- SDK: google-genai (`from google import genai`)
- 支援直接傳入 api_key 進行認證 (無需依賴全域環境變數)
- 支援純文字生成、串流 (streaming) 與結構化 JSON 輸出 (Structured Outputs)
"""

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Type, Union

from google import genai
from pydantic import BaseModel

try:
    from configs.settings import DEFAULT_GEMINI_MODEL, get_gemini_api_key
except ImportError:
    # 支援直接以腳本路徑單獨執行時的匯入處理
    from settings import DEFAULT_GEMINI_MODEL, get_gemini_api_key

TW_TZ = timezone(timedelta(hours=8))


class GeminiClient:
    """Gemini Interactions API 客戶端包裝器。"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: str = DEFAULT_GEMINI_MODEL,
        enable_code_execution: bool = False,
    ):
        """初始化 Gemini 客戶端。

        Args:
            api_key: Gemini API 金鑰。若為 None，則自動從本地 credentials.json 讀取。
            default_model: 預設呼叫的模型名稱 (例如 "gemini-3.8-flash")。
            enable_code_execution: 是否預設啟用 Gemini 內建 Python 程式碼執行 (Code Execution)。預設為 False。
        """
        self.api_key = api_key or get_gemini_api_key()
        self.default_model = default_model
        self.enable_code_execution = enable_code_execution
        self.last_usage: Optional[Dict[str, Any]] = None

        # 依據 google-genai 規範，將 api_key 明確傳入 Client 進行驗證
        self.client = genai.Client(api_key=self.api_key)

    @staticmethod
    def _log_code_execution(interaction_or_event: Any) -> None:
        """從 Interaction、Step 或 Event 物件中檢查並印出 Code Execution 過程。"""
        if interaction_or_event is None:
            return

        # 1. 處理 interaction 物件中的 steps 清單 (批次/非串流模式)
        steps = getattr(interaction_or_event, "steps", None)
        if steps and isinstance(steps, (list, tuple)):
            for step in steps:
                stype = getattr(step, "type", None)
                if stype == "code_execution_call":
                    args = getattr(step, "arguments", None)
                    code = getattr(args, "code", None) if args else None
                    if not code and isinstance(args, dict):
                        code = args.get("code")
                    if code:
                        print("\n" + "=" * 65)
                        print("[Gemini 產生並執行 Python 程式碼]:")
                        print("-" * 65)
                        print(str(code).strip())
                        print("-" * 65)
                elif stype == "code_execution_result":
                    res = getattr(step, "result", None)
                    if res is not None:
                        print("[Gemini 程式碼執行輸出結果]:")
                        print(str(res).strip())
                        print("=" * 65 + "\n")

        # 2. 處理單一串流 event (串流模式)
        stype = getattr(interaction_or_event, "type", None)
        if stype == "code_execution_call":
            args = getattr(interaction_or_event, "arguments", None)
            code = getattr(args, "code", None) if args else None
            if not code and isinstance(args, dict):
                code = args.get("code")
            if code:
                print("\n" + "=" * 65)
                print("[Gemini 產生並執行 Python 程式碼 (串流)]: ")
                print("-" * 65)
                print(str(code).strip())
                print("-" * 65)
        elif stype == "code_execution_result":
            res = getattr(interaction_or_event, "result", None)
            if res is not None:
                print("[Gemini 程式碼執行輸出結果 (串流)]: ")
                print(str(res).strip())
                print("=" * 65 + "\n")

    @staticmethod
    def _extract_chunk_text(chunk: Any) -> str:
        """從各種串流事件格式中提取增量文字。"""
        if isinstance(chunk, str):
            return chunk

        # 忽略 code execution 相關事件，避免程式碼或執行標準輸出混入文字或結構化 JSON
        chunk_type = getattr(chunk, "type", None)
        if chunk_type in ("code_execution_call", "code_execution_result"):
            return ""

        # 1. 優先嘗試常用屬性 (output_text / text)
        for attr in ("text", "output_text"):
            val = getattr(chunk, attr, None)
            if isinstance(val, str) and val:
                return val

        # 2. 嘗試 delta 物件
        delta = getattr(chunk, "delta", None)
        if delta is not None:
            for attr in ("text", "output_text"):
                val = getattr(delta, attr, None)
                if isinstance(val, str) and val:
                    return val

        # 3. 嘗試 content / content_block 結構 (Interactions API step 格式)
        content = getattr(chunk, "content", None)
        if content and isinstance(content, (list, tuple)):
            text_parts = []
            for b in content:
                b_type = getattr(b, "type", None) if not isinstance(b, dict) else b.get("type")
                if b_type == "text":
                    t = getattr(b, "text", None) if not isinstance(b, dict) else b.get("text")
                    if t:
                        text_parts.append(t)
            if text_parts:
                return "".join(text_parts)

        # 4. 嘗試 candidates 物件 (標準 generate_content 格式)
        candidates = getattr(chunk, "candidates", None)
        if candidates and len(candidates) > 0:
            c = candidates[0]
            c_content = getattr(c, "content", None)
            if c_content:
                parts = getattr(c_content, "parts", None)
                if parts:
                    return "".join(getattr(p, "text", "") for p in parts)
        return ""

    def test_connection(self, model: Optional[str] = None) -> bool:
        """測試 API 金鑰與連線是否正常。

        Returns:
            bool: 連線成功回傳 True，若發生例外則拋出或回傳 False。
        """
        target_model = model or self.default_model
        try:
            interaction = self.client.interactions.create(
                model=target_model,
                input="Ping: Please respond with 'OK' if you receive this message.",
            )
            print(f"[GeminiClient] 連線成功！模型回應: {interaction.output_text.strip()}")
            return True
        except Exception as e:
            print(f"[GeminiClient] 連線測試失敗: {e}")
            raise

    def _record_usage(
        self,
        interaction_or_event: Any,
        model: str,
        start_dt: datetime,
        end_dt: datetime,
        prompt_text: Optional[str] = None,
        output_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """從 Interaction、Response 或 Event 中萃取 Usage 並儲存於 self.last_usage。"""
        duration = max(0.0, (end_dt - start_dt).total_seconds())

        prompt_tokens = 0
        candidates_tokens = 0
        total_tokens = 0
        cached_tokens = 0

        # 1. 嘗試讀取 interaction_or_event 上的 usage 屬性
        raw_usage = getattr(interaction_or_event, "usage", None)
        if raw_usage is None:
            raw_usage = getattr(interaction_or_event, "usage_metadata", None)

        if raw_usage is not None:
            # 支援物件屬性或字典
            def _get_val(keys):
                for k in keys:
                    v = getattr(raw_usage, k, None) if not isinstance(raw_usage, dict) else raw_usage.get(k)
                    if v is not None:
                        try:
                            return int(v)
                        except (ValueError, TypeError):
                            pass
                return 0

            prompt_tokens = _get_val(["prompt_token_count", "input_tokens", "prompt_tokens"])
            candidates_tokens = _get_val(["candidates_token_count", "output_tokens", "completion_tokens"])
            total_tokens = _get_val(["total_token_count", "total_tokens"])
            cached_tokens = _get_val(["cached_content_token_count", "cached_tokens", "cache_tokens"])

        # 2. 若 total_tokens 仍為 0，嘗試以 prompt/output 長度與官方 count_tokens 備援
        if total_tokens == 0:
            if prompt_tokens == 0 and prompt_text:
                try:
                    if hasattr(self.client, "models") and hasattr(self.client.models, "count_tokens"):
                        cnt = self.client.models.count_tokens(model=model, contents=prompt_text)
                        prompt_tokens = int(getattr(cnt, "total_tokens", len(prompt_text) // 3))
                    else:
                        prompt_tokens = len(prompt_text) // 3
                except Exception:
                    prompt_tokens = len(prompt_text) // 3

            if candidates_tokens == 0 and output_text:
                candidates_tokens = max(1, len(output_text) // 3)

            total_tokens = prompt_tokens + candidates_tokens

        usage_data = {
            "timestamp": end_dt.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
            "model": model,
            "duration_seconds": round(duration, 2),
            "prompt_tokens": prompt_tokens,
            "candidates_tokens": candidates_tokens,
            "total_tokens": total_tokens,
            "cached_tokens": cached_tokens,
        }
        self.last_usage = usage_data
        return usage_data

    def save_usage_metadata(
        self,
        output_dir: Union[str, Path],
        stage_prefix: str,
        target_date: str,
        extra_info: Optional[Dict[str, Any]] = None,
    ) -> Path:
        """在該階段輸出目錄下的 usage/ 資料夾儲存 Gemini Usage 統計。

        儲存路徑如: <output_dir>/usage/<stage_prefix>_usage_<YYYYMMDD>.json
        """
        out_base = Path(output_dir)
        usage_dir = out_base / "usage"
        usage_dir.mkdir(parents=True, exist_ok=True)

        c_date = re.sub(r"\D", "", str(target_date).strip())
        usage_file = usage_dir / f"{stage_prefix}_usage_{c_date}.json"

        now_dt = datetime.now(TW_TZ)
        payload = dict(self.last_usage or {
            "timestamp": now_dt.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
            "model": self.default_model,
            "duration_seconds": 0.0,
            "prompt_tokens": 0,
            "candidates_tokens": 0,
            "total_tokens": 0,
            "cached_tokens": 0,
        })
        payload["date"] = c_date
        payload["stage"] = stage_prefix

        if extra_info:
            payload.update(extra_info)

        with open(usage_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        print(
            f"[GeminiClient] Usage 紀錄已儲存至: {usage_file}\n"
            f" -> Model: {payload.get('model')} | Prompt: {payload.get('prompt_tokens')} | "
            f"Candidates: {payload.get('candidates_tokens')} | Total: {payload.get('total_tokens')} | 耗時: {payload.get('duration_seconds')}s"
        )
        return usage_file

    def generate_text(
        self,
        prompt: Union[str, List[Any]],
        model: Optional[str] = None,
        system_instruction: Optional[str] = None,
        enable_code_execution: Optional[bool] = None,
    ) -> str:
        """發送文字或多模態請求並取得模型回覆純文字。

        Args:
            prompt: 提示詞字串或結構化輸入列表。
            model: 模型名稱 (預設使用 default_model)。
            system_instruction: 系統提示指令 (選用)。
            enable_code_execution: 是否啟用 Python 程式碼執行 (Code Execution)。若為 None 則使用實例預設值。

        Returns:
            str: 模型的文字回應。
        """
        target_model = model or self.default_model
        use_code_exec = self.enable_code_execution if enable_code_execution is None else enable_code_execution
        kwargs: Dict[str, Any] = {
            "model": target_model,
            "input": prompt,
        }

        # 若有指定系統指令，可放入設定
        if system_instruction:
            kwargs["system_instruction"] = system_instruction

        if use_code_exec:
            kwargs["tools"] = [{"type": "code_execution"}]

        start_dt = datetime.now(TW_TZ)
        interaction = self.client.interactions.create(**kwargs)
        end_dt = datetime.now(TW_TZ)

        if use_code_exec:
            self._log_code_execution(interaction)

        self._record_usage(
            interaction_or_event=interaction,
            model=target_model,
            start_dt=start_dt,
            end_dt=end_dt,
            prompt_text=str(prompt),
            output_text=interaction.output_text,
        )
        return interaction.output_text

    def generate_stream(
        self,
        prompt: Union[str, List[Any]],
        model: Optional[str] = None,
        enable_code_execution: Optional[bool] = None,
    ) -> Generator[Any, None, None]:
        """以串流方式生成回覆。

        Args:
            prompt: 提示詞字串。
            model: 模型名稱。
            enable_code_execution: 是否啟用 Python 程式碼執行 (Code Execution)。若為 None 則使用實例預設值。

        Yields:
            Any: 每個事件區塊。
        """
        target_model = model or self.default_model
        use_code_exec = self.enable_code_execution if enable_code_execution is None else enable_code_execution
        kwargs: Dict[str, Any] = {
            "model": target_model,
            "input": prompt,
            "stream": True,
        }
        if use_code_exec:
            kwargs["tools"] = [{"type": "code_execution"}]

        stream = self.client.interactions.create(**kwargs)
        for event in stream:
            if use_code_exec:
                self._log_code_execution(event)
            yield event

    def generate_structured(
        self,
        prompt: Union[str, List[Any]],
        response_model: Type[BaseModel],
        model: Optional[str] = None,
        stream: bool = True,
        print_stream: bool = True,
        enable_code_execution: Optional[bool] = None,
    ) -> BaseModel:
        """要求模型依據指定的 Pydantic 模型產生結構化 JSON 輸出。

        支援 Stream 模式：可即時在終端機印出產字過程，便於即時監看內容與在中斷時節省輸出 Token。
        支援 Code Execution：模型可自動撰寫並執行 Python 程式碼，依據運算結果產出結構化輸出。

        Args:
            prompt: 提示詞字串。
            response_model: Pydantic 的 BaseModel 衍生類別。
            model: 模型名稱。
            stream: 是否使用串流 (Streaming) 方式即時生成。預設為 True。
            print_stream: 串流模式下是否即時將字元輸出至 stdout。預設為 True。
            enable_code_execution: 是否啟用 Python 程式碼執行 (Code Execution)。若為 None 則使用實例預設值。

        Returns:
            BaseModel: 依 response_model 解析並驗證後的物件。
        """
        target_model = model or self.default_model
        use_code_exec = self.enable_code_execution if enable_code_execution is None else enable_code_execution
        tools = [{"type": "code_execution"}] if use_code_exec else None

        response_format = {
            "type": "text",
            "mime_type": "application/json",
            "schema": response_model.model_json_schema(),
        }

        def _safe_parse_json(text_content: str) -> BaseModel:
            """解析 JSON 並驗證為 response_model，若有外部標籤做容錯正則抽取。"""
            try:
                return response_model.model_validate_json(text_content)
            except Exception:
                # 容錯嘗試：搜尋第一個符合的 { ... }
                m = re.search(r"(\{.*\})", text_content, re.DOTALL)
                if m:
                    return response_model.model_validate_json(m.group(1))
                raise

        start_dt = datetime.now(TW_TZ)
        if not stream:
            kwargs: Dict[str, Any] = {
                "model": target_model,
                "input": prompt,
                "response_format": response_format,
            }
            if tools:
                kwargs["tools"] = tools

            interaction = self.client.interactions.create(**kwargs)
            end_dt = datetime.now(TW_TZ)

            if use_code_exec:
                self._log_code_execution(interaction)

            self._record_usage(
                interaction_or_event=interaction,
                model=target_model,
                start_dt=start_dt,
                end_dt=end_dt,
                prompt_text=str(prompt),
                output_text=interaction.output_text,
            )
            return _safe_parse_json(interaction.output_text)

        # 串流生成模式
        try:
            kwargs = {
                "model": target_model,
                "input": prompt,
                "response_format": response_format,
                "stream": True,
            }
            if tools:
                kwargs["tools"] = tools

            stream_resp = self.client.interactions.create(**kwargs)
            chunks: List[str] = []
            last_event = None
            for event in stream_resp:
                last_event = event
                if use_code_exec:
                    self._log_code_execution(event)
                piece = self._extract_chunk_text(event)
                if piece:
                    chunks.append(piece)
                    if print_stream:
                        print(piece, end="", flush=True)

            if print_stream:
                print()  # 串流結束換行

            end_dt = datetime.now(TW_TZ)
            full_text = "".join(chunks)

            # 若 chunks 為空但 last_event 包含 output_text 則備援使用
            if not full_text.strip() and last_event:
                full_text = getattr(last_event, "output_text", "") or ""

            self._record_usage(
                interaction_or_event=last_event,
                model=target_model,
                start_dt=start_dt,
                end_dt=end_dt,
                prompt_text=str(prompt),
                output_text=full_text,
            )
            return _safe_parse_json(full_text)
        except Exception as e:
            # 若串流請求在特定環境不支援，自動 fallback 為非串流批次模式
            if "stream" in str(e).lower() or type(e).__name__ in ("NotImplementedError", "TypeError"):
                print(f"\n[GeminiClient 提示] 串流模式未就緒 ({e})，自動切換為批次生成...")
                fb_start = datetime.now(TW_TZ)
                fb_kwargs: Dict[str, Any] = {
                    "model": target_model,
                    "input": prompt,
                    "response_format": response_format,
                }
                if tools:
                    fb_kwargs["tools"] = tools

                interaction = self.client.interactions.create(**fb_kwargs)
                fb_end = datetime.now(TW_TZ)

                if use_code_exec:
                    self._log_code_execution(interaction)

                self._record_usage(
                    interaction_or_event=interaction,
                    model=target_model,
                    start_dt=fb_start,
                    end_dt=fb_end,
                    prompt_text=str(prompt),
                    output_text=interaction.output_text,
                )
                return _safe_parse_json(interaction.output_text)
            raise


if __name__ == "__main__":
    print("=== Gemini Client 連線測試程式碼範例 ===")
    print("說明：請確認在專案根目錄已建立 credentials.json 並填入有效 API Key。")
    print("當準備好測試連線時，可取消下方註解並手動執行此腳本進行連線測試：\n")

    # [使用者手動測試區塊]
    try:
        client = GeminiClient()
        print("初始化 Client 成功，正在發送測試請求...")
        client.test_connection()
    except Exception as e:
        print(f"測試發生錯誤: {e}")
