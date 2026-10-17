"""Independent AI learning-assistant package."""

from .client import AssistantProviderError, AssistantUnavailableError, SparkChatClient
from .models import (
    AssistantChatRequest,
    AssistantMessage,
    AssistantReply,
    AssistantStatus,
    CodeReviewRequest,
    LearningModuleContext,
    ModuleIntroductionRequest,
    ReviewContext,
)
from .router import AssistantContextGateway, create_assistant_router
from .service import AssistantService

__all__ = [
    "AssistantChatRequest",
    "AssistantContextGateway",
    "AssistantMessage",
    "AssistantProviderError",
    "AssistantReply",
    "AssistantService",
    "AssistantStatus",
    "AssistantUnavailableError",
    "CodeReviewRequest",
    "LearningModuleContext",
    "ModuleIntroductionRequest",
    "ReviewContext",
    "SparkChatClient",
    "create_assistant_router",
]
