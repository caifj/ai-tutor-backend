from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AssistantModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AssistantMessage(AssistantModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class AssistantChatRequest(AssistantModel):
    messages: list[AssistantMessage] = Field(min_length=1, max_length=20)
    case_id: str | None = Field(
        default=None,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9._-]*$",
    )

    @model_validator(mode="after")
    def require_latest_user_message(self) -> AssistantChatRequest:
        if self.messages[-1].role != "user":
            raise ValueError("the latest assistant message must come from the user")
        return self


class ModuleIntroductionRequest(AssistantModel):
    case_id: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9._-]*$",
    )


class AssistantReply(AssistantModel):
    reply: str
    model: str
    kind: Literal["chat", "module_introduction"]
    case_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AssistantStatus(AssistantModel):
    configured: bool
    model: str
