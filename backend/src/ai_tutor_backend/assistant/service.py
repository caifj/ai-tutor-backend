from __future__ import annotations

from typing import Protocol

from ai_tutor_backend.models import CaseDescriptor, ExecutionResult

from .client import SparkChatClient
from .models import AssistantMessage, AssistantReply, AssistantStatus
from .policy import build_code_review_prompt, build_module_introduction_prompt, build_system_prompt

MODULE_INTRODUCTION_MAX_CHARS = 100


def _limit_assistant_text(text: str) -> str:
    compact = " ".join(text.split())
    if len(compact) <= MODULE_INTRODUCTION_MAX_CHARS:
        return compact
    shortened = compact[: MODULE_INTRODUCTION_MAX_CHARS - 1].rstrip("，、；：,. ")
    return f"{shortened}…"


class CompletionClient(Protocol):
    @property
    def configured(self) -> bool: ...

    @property
    def model_name(self) -> str: ...

    async def complete(self, messages: list[dict[str, str]]) -> str: ...


class AssistantService:
    def __init__(self, client: CompletionClient | None = None) -> None:
        self.client = client or SparkChatClient()

    def status(self) -> AssistantStatus:
        return AssistantStatus(configured=self.client.configured, model=self.client.model_name)

    async def chat(
        self,
        messages: list[AssistantMessage],
        case: CaseDescriptor | None = None,
    ) -> AssistantReply:
        provider_messages = [{"role": "system", "content": build_system_prompt(case)}]
        provider_messages.extend(message.model_dump() for message in messages)
        reply = await self.client.complete(provider_messages)
        return AssistantReply(
            reply=reply,
            model=self.client.model_name,
            kind="chat",
            case_id=case.case_id if case else None,
        )

    async def introduce(self, case: CaseDescriptor) -> AssistantReply:
        reply = await self.client.complete(
            [
                {"role": "system", "content": build_system_prompt(case)},
                {"role": "user", "content": build_module_introduction_prompt(case)},
            ]
        )
        return AssistantReply(
            reply=_limit_assistant_text(reply),
            model=self.client.model_name,
            kind="module_introduction",
            case_id=case.case_id,
        )

    async def review_code(
        self,
        result: ExecutionResult,
        case: CaseDescriptor,
    ) -> AssistantReply:
        reply = await self.client.complete(
            [
                {"role": "system", "content": build_system_prompt(case)},
                {"role": "user", "content": build_code_review_prompt(result)},
            ]
        )
        return AssistantReply(
            reply=_limit_assistant_text(reply),
            model=self.client.model_name,
            kind="code_review",
            case_id=case.case_id,
        )
