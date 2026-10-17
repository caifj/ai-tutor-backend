from __future__ import annotations

from typing import Protocol

from .client import SparkChatClient
from .models import (
    AssistantMessage,
    AssistantReply,
    AssistantStatus,
    LearningModuleContext,
    ReviewContext,
)
from .policy import build_code_review_prompt, build_module_introduction_prompt, build_system_prompt

ASSISTANT_SHORT_TEXT_MAX_CHARS = 100


def _limit_assistant_text(text: str) -> str:
    compact = " ".join(text.split())
    if len(compact) <= ASSISTANT_SHORT_TEXT_MAX_CHARS:
        return compact
    shortened = compact[: ASSISTANT_SHORT_TEXT_MAX_CHARS - 1].rstrip("，、；：,. ")
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
        module: LearningModuleContext | None = None,
    ) -> AssistantReply:
        provider_messages = [{"role": "system", "content": build_system_prompt(module)}]
        provider_messages.extend(message.model_dump() for message in messages)
        reply = await self.client.complete(provider_messages)
        return AssistantReply(
            reply=reply,
            model=self.client.model_name,
            kind="chat",
            case_id=module.case_id if module else None,
        )

    async def introduce(self, module: LearningModuleContext) -> AssistantReply:
        reply = await self.client.complete(
            [
                {"role": "system", "content": build_system_prompt(module)},
                {"role": "user", "content": build_module_introduction_prompt(module)},
            ]
        )
        return AssistantReply(
            reply=_limit_assistant_text(reply),
            model=self.client.model_name,
            kind="module_introduction",
            case_id=module.case_id,
        )

    async def review_code(
        self,
        review: ReviewContext,
        module: LearningModuleContext,
    ) -> AssistantReply:
        reply = await self.client.complete(
            [
                {"role": "system", "content": build_system_prompt(module)},
                {"role": "user", "content": build_code_review_prompt(review)},
            ]
        )
        return AssistantReply(
            reply=_limit_assistant_text(reply),
            model=self.client.model_name,
            kind="code_review",
            case_id=module.case_id,
        )
