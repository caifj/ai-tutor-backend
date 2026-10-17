from __future__ import annotations

import inspect
from time import perf_counter
from uuid import uuid4

from .code_similarity import CodeSimilarityService, SimilarityReview
from .models import (
    Diagnostic,
    DiagnosticLevel,
    ExecutionContext,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    ResultPayload,
)
from .registry import CaseRegistry
from .repository import SQLiteResultRepository


class ExecutionService:
    def __init__(self, registry: CaseRegistry, repository: SQLiteResultRepository) -> None:
        self.registry = registry
        self.repository = repository
        self.code_similarity = CodeSimilarityService(repository)

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        adapter = self.registry.get(request.case_id)
        request_id = str(uuid4())
        context = ExecutionContext(
            request_id=request_id,
            parameters=request.parameters,
            metadata=request.metadata,
        )
        started = perf_counter()
        payload = adapter.execute(request.input, context)
        if inspect.isawaitable(payload):
            payload = await payload
        source_code = request.input.get("source_code")
        filename = request.input.get("filename")
        student_id = request.metadata.get("student_id")
        if not isinstance(student_id, str) or not student_id.strip():
            student_id = None
        elif len(student_id) > 128:
            student_id = student_id[:128]

        similarity_review: SimilarityReview | None = None
        if isinstance(source_code, str):
            similarity_review = self.code_similarity.review(
                request.case_id,
                student_id,
                source_code,
            )
            self._apply_similarity_review(payload, similarity_review)
        duration_ms = (perf_counter() - started) * 1000
        result = ExecutionResult(
            request_id=request_id,
            case_id=request.case_id,
            status=ExecutionStatus.SUCCEEDED,
            payload=payload,
            duration_ms=duration_ms,
        )
        self.repository.save(result)
        if isinstance(source_code, str):
            self.repository.save_code_submission(
                request_id=request_id,
                case_id=request.case_id,
                student_id=student_id,
                filename=filename if isinstance(filename, str) else "submission.py",
                source_code=source_code,
            )
        return result

    @staticmethod
    def _apply_similarity_review(payload: ResultPayload, review: SimilarityReview) -> None:
        payload.metrics["similarity_checked_submissions"] = review.checked_submissions
        payload.metrics["similarity_score"] = round(review.similarity * 100, 1)
        payload.metrics["similarity_threshold"] = round(review.threshold * 100, 1)
        payload.metrics["similarity_penalty"] = 0.0
        if not review.is_high:
            return

        original_score = payload.metrics.get("overall_score")
        diagnostic_message = (
            f"代码与同案例历史提交的最高相似度为 {review.similarity * 100:.1f}%，"
            f"超过 {review.threshold * 100:.1f}% 阈值。"
        )
        if isinstance(original_score, (int, float)) and not isinstance(original_score, bool):
            adjusted_score = max(0.0, round(float(original_score) - review.penalty, 1))
            payload.metrics["original_score"] = round(float(original_score), 1)
            payload.metrics["overall_score"] = adjusted_score
            payload.metrics["similarity_penalty"] = review.penalty
            payload.summary = (
                f"{payload.summary} 同案例代码最高相似度 {review.similarity * 100:.1f}%，"
                f"查重扣除 {review.penalty:.1f} 分，最终得分 {adjusted_score:.1f}/100。"
            )
            diagnostic_message += f"已扣除 {review.penalty:.1f} 分。"
        else:
            diagnostic_message += "当前结果没有总分字段，已标记教师复核但未自动扣分。"
        payload.diagnostics.append(
            Diagnostic(
                code="CODE_SIMILARITY_HIGH",
                level=DiagnosticLevel.WARNING,
                message=diagnostic_message,
                details={
                    "similarity_percent": round(review.similarity * 100, 1),
                    "threshold_percent": round(review.threshold * 100, 1),
                    "penalty": payload.metrics["similarity_penalty"],
                    "checked_submissions": review.checked_submissions,
                },
            )
        )
