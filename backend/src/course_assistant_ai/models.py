from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class AssistantModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LearningModuleContext(AssistantModel):
    """Minimal trusted module context owned by the AI boundary."""

    case_id: str
    name: str
    course: str
    description: str = ""
    output_datasets: list[str] = Field(default_factory=list)


class ReviewContext(AssistantModel):
    """Sanitized review facts; student source code must never cross this boundary."""

    summary: str = ""
    metrics: dict[str, JsonValue] = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)


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


class CodeReviewRequest(AssistantModel):
    request_id: str = Field(min_length=1, max_length=100)


class AssistantReply(AssistantModel):
    reply: str
    model: str
    kind: Literal["chat", "module_introduction", "code_review"]
    case_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AssistantStatus(AssistantModel):
    configured: bool
    model: str
