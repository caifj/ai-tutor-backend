from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

DEFAULT_ENDPOINT = "https://maas-api.cn-huabei-1.xf-yun.com/v2/chat/completions"
DEFAULT_MODEL = "spark-x2.5-1.7b"


class AssistantUnavailableError(RuntimeError):
    """Raised when the assistant has not been configured on the server."""


class AssistantProviderError(RuntimeError):
    """Raised when the upstream model request fails."""


@dataclass(frozen=True, slots=True)
class SparkSettings:
    api_key: str | None
    endpoint: str = DEFAULT_ENDPOINT
    model: str = DEFAULT_MODEL
    timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> SparkSettings:
        raw_timeout = os.getenv("SPARK_TIMEOUT_SECONDS", "30")
        try:
            timeout = max(1.0, float(raw_timeout))
        except ValueError:
            timeout = 30.0
        return cls(
            api_key=os.getenv("SPARK_API_KEY") or os.getenv("SPARK_API_PASSWORD"),
            endpoint=os.getenv("SPARK_API_ENDPOINT", DEFAULT_ENDPOINT),
            model=os.getenv("SPARK_MODEL", DEFAULT_MODEL),
            timeout_seconds=timeout,
        )


class SparkChatClient:
    def __init__(self, settings: SparkSettings | None = None) -> None:
        self.settings = settings or SparkSettings.from_env()

    @property
    def model_name(self) -> str:
        return self.settings.model

    @property
    def configured(self) -> bool:
        return bool(self.settings.api_key)

    async def complete(self, messages: list[dict[str, str]]) -> str:
        if not self.settings.api_key:
            raise AssistantUnavailableError("AI 助手尚未配置 API Key")

        try:
            async with httpx.AsyncClient(timeout=self.settings.timeout_seconds) as client:
                response = await client.post(
                    self.settings.endpoint,
                    headers={
                        "Authorization": f"Bearer {self.settings.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.settings.model,
                        "messages": messages,
                        "stream": False,
                    },
                )
        except httpx.RequestError as exc:
            raise AssistantProviderError("AI 模型服务当前无法连接") from exc

        if not response.is_success:
            raise AssistantProviderError(f"AI 模型服务返回异常状态（{response.status_code}）")

        try:
            payload: dict[str, Any] = response.json()
            reply = payload["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise AssistantProviderError("AI 模型返回了无法识别的结果") from exc
        if not isinstance(reply, str) or not reply.strip():
            raise AssistantProviderError("AI 模型未返回有效内容")
        return reply.strip()
