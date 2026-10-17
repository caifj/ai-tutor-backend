"""Decoupled AI learning-assistant integration."""

from .client import AssistantProviderError, AssistantUnavailableError, SparkChatClient
from .models import (
    AssistantChatRequest,
    AssistantMessage,
    AssistantReply,
    AssistantStatus,
    CodeReviewRequest,
    ModuleIntroductionRequest,
)
from .service import AssistantService

__all__ = [
    "AssistantChatRequest",
    "AssistantMessage",
    "AssistantProviderError",
    "AssistantReply",
    "AssistantService",
    "AssistantStatus",
    "AssistantUnavailableError",
    "CodeReviewRequest",
    "ModuleIntroductionRequest",
    "SparkChatClient",
]
