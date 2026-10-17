from __future__ import annotations

from typing import Protocol

from fastapi import APIRouter

from .models import (
    AssistantChatRequest,
    AssistantReply,
    AssistantStatus,
    CodeReviewRequest,
    LearningModuleContext,
    ModuleIntroductionRequest,
    ReviewContext,
)
from .service import AssistantService


class AssistantContextGateway(Protocol):
    """Application-supplied adapter; the AI package never imports grading or storage."""

    def get_module(self, case_id: str) -> LearningModuleContext: ...

    def get_review(self, request_id: str) -> tuple[ReviewContext, LearningModuleContext]: ...


def create_assistant_router(
    service: AssistantService,
    gateway: AssistantContextGateway,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])

    @router.get("/status", response_model=AssistantStatus)
    async def assistant_status() -> AssistantStatus:
        return service.status()

    @router.post("/chat", response_model=AssistantReply)
    async def assistant_chat(body: AssistantChatRequest) -> AssistantReply:
        module = gateway.get_module(body.case_id) if body.case_id else None
        return await service.chat(body.messages, module)

    @router.post("/module-introduction", response_model=AssistantReply)
    async def assistant_module_introduction(body: ModuleIntroductionRequest) -> AssistantReply:
        return await service.introduce(gateway.get_module(body.case_id))

    @router.post("/code-review", response_model=AssistantReply)
    async def assistant_code_review(body: CodeReviewRequest) -> AssistantReply:
        review, module = gateway.get_review(body.request_id)
        return await service.review_code(review, module)

    return router
