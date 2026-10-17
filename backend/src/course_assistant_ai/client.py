from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any

import httpx

DEFAULT_ENDPOINT = "https://maas-api.cn-huabei-1.xf-yun.com/v2/chat/completions"
DEFAULT_MODEL = "spark-x2.5-1.7b"
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class AssistantUnavailableError(RuntimeError):
    """Raised when the assistant has not been configured on the server."""


class AssistantProviderError(RuntimeError):
    """Raised when the upstream model request fails."""


def _read_float(name: str, default: float, minimum: float) -> float:
    try:
        return max(minimum, float(os.getenv(name, str(default))))
    except ValueError:
        return default


def _read_int(name: str, default: int, minimum: int) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except ValueError:
        return default


@dataclass(frozen=True, slots=True)
class SparkSettings:
    api_key: str | None
    endpoint: str = DEFAULT_ENDPOINT
    model: str = DEFAULT_MODEL
    timeout_seconds: float = 30.0
    max_retries: int = 2
    retry_backoff_seconds: float = 1.0

    @classmethod
    def from_env(cls) -> SparkSettings:
        return cls(
            api_key=os.getenv("SPARK_API_KEY") or os.getenv("SPARK_API_PASSWORD"),
            endpoint=os.getenv("SPARK_API_ENDPOINT", DEFAULT_ENDPOINT),
            model=os.getenv("SPARK_MODEL", DEFAULT_MODEL),
            timeout_seconds=_read_float("SPARK_TIMEOUT_SECONDS", 30.0, minimum=1.0),
            max_retries=_read_int("SPARK_MAX_RETRIES", 2, minimum=0),
            retry_backoff_seconds=_read_float(
                "SPARK_RETRY_BACKOFF_SECONDS", 1.0, minimum=0.0
            ),
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

        attempts = self.settings.max_retries + 1
        last_error = "AI 模型服务当前无法连接"
        for attempt in range(attempts):
            if attempt:
                await asyncio.sleep(self.settings.retry_backoff_seconds * attempt)
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
                last_error = f"AI 模型服务当前无法连接：{exc}".rstrip("：")
                continue

            if not response.is_success:
                detail = " ".join(response.text.split())[:300]
                suffix = f"：{detail}" if detail else ""
                message = f"AI 模型服务返回异常状态（{response.status_code}）{suffix}"
                if response.status_code in RETRYABLE_STATUS_CODES:
                    last_error = message
                    continue
                raise AssistantProviderError(message)

            try:
                payload: dict[str, Any] = response.json()
                reply = payload["choices"][0]["message"]["content"]
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                raise AssistantProviderError("AI 模型返回了无法识别的结果") from exc
            if not isinstance(reply, str) or not reply.strip():
                raise AssistantProviderError("AI 模型未返回有效内容")
            return reply.strip()

        raise AssistantProviderError(last_error)
