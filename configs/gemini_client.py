"""Gemini API 包裝器 (支援 Structured Outputs / JSON Schema)。

依據官方 Google GenAI SDK 與 Interactions API 規範實作：
- SDK: google-genai (`from google import genai`)
- 支援直接傳入 api_key 進行認證 (無需依賴全域環境變數)
- 支援純文字生成、串流 (streaming) 與結構化 JSON 輸出 (Structured Outputs)
"""

from typing import Any, Dict, Generator, List, Optional, Type, Union
from google import genai
from pydantic import BaseModel

try:
    from configs.settings import DEFAULT_GEMINI_MODEL, get_gemini_api_key
except ImportError:
    # 支援直接以腳本路徑單獨執行時的匯入處理
    from settings import DEFAULT_GEMINI_MODEL, get_gemini_api_key


class GeminiClient:
    """Gemini Interactions API 客戶端包裝器。"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: str = DEFAULT_GEMINI_MODEL,
    ):
        """初始化 Gemini 客戶端。

        Args:
            api_key: Gemini API 金鑰。若為 None，則自動從本地 credentials.json 讀取。
            default_model: 預設呼叫的模型名稱 (例如 "gemini-3.8-flash")。
        """
        self.api_key = api_key or get_gemini_api_key()
        self.default_model = default_model

        # 依據 google-genai 規範，將 api_key 明確傳入 Client 進行驗證
        self.client = genai.Client(api_key=self.api_key)

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

    def generate_text(
        self,
        prompt: Union[str, List[Any]],
        model: Optional[str] = None,
        system_instruction: Optional[str] = None,
    ) -> str:
        """發送文字或多模態請求並取得模型回覆純文字。

        Args:
            prompt: 提示詞字串或結構化輸入列表。
            model: 模型名稱 (預設使用 default_model)。
            system_instruction: 系統提示指令 (選用)。

        Returns:
            str: 模型的文字回應。
        """
        target_model = model or self.default_model
        kwargs: Dict[str, Any] = {
            "model": target_model,
            "input": prompt,
        }

        # 若有指定系統指令，可放入設定
        if system_instruction:
            kwargs["system_instruction"] = system_instruction

        interaction = self.client.interactions.create(**kwargs)
        return interaction.output_text

    def generate_stream(
        self,
        prompt: Union[str, List[Any]],
        model: Optional[str] = None,
    ) -> Generator[str, None, None]:
        """以串流方式生成回覆。

        Args:
            prompt: 提示詞字串。
            model: 模型名稱。

        Yields:
            str: 每個事件區塊的文字增量。
        """
        target_model = model or self.default_model
        stream = self.client.interactions.create(
            model=target_model,
            input=prompt,
            stream=True,
        )
        for event in stream:
            yield event

    def generate_structured(
        self,
        prompt: Union[str, List[Any]],
        response_model: Type[BaseModel],
        model: Optional[str] = None,
    ) -> BaseModel:
        """要求模型依據指定的 Pydantic 模型產生結構化 JSON 輸出。

        Args:
            prompt: 提示詞字串。
            response_model: Pydantic 的 BaseModel 衍生類別。
            model: 模型名稱。

        Returns:
            BaseModel: 依 response_model 解析並驗證後的物件。
        """
        target_model = model or self.default_model
        interaction = self.client.interactions.create(
            model=target_model,
            input=prompt,
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": response_model.model_json_schema(),
            },
        )
        # 使用 Pydantic 解析模型輸出的 JSON 字串
        return response_model.model_validate_json(interaction.output_text)


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
