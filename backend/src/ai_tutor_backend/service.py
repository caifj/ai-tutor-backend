from __future__ import annotations

import inspect
from time import perf_counter
from uuid import uuid4

from .code_execution import CodeRunner, ExecutionRuntime, create_code_runner_from_env
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
from .registry import CaseInputError, CaseRegistry
from .repository import SQLiteResultRepository
from .static_evaluation import (
    PythonStaticEvaluation,
    evaluate_python_static,
    issues_dataset,
    quality_dataset,
)


class ExecutionService:
    def __init__(
        self,
        registry: CaseRegistry,
        repository: SQLiteResultRepository,
        code_runner: CodeRunner | None = None,
    ) -> None:
        self.registry = registry
        self.repository = repository
        self.code_similarity = CodeSimilarityService(repository)
        self.code_runner = code_runner or create_code_runner_from_env()

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        adapter = self.registry.get(request.case_id)
        descriptor = adapter.descriptor
        request_id = str(uuid4())
        source_code = request.input.get("source_code")
        filename = request.input.get("filename")
        submitter = self._normalized_submitter(request.metadata)
        if isinstance(source_code, str) and submitter is None:
            raise CaseInputError(
                "提交 Python 代码时必须填写提交人",
                {"field": "metadata.submitter"},
            )
        context = ExecutionContext(
            request_id=request_id,
            parameters=request.parameters,
            metadata=request.metadata,
            runtime=ExecutionRuntime(code_runner=self.code_runner),
        )
        started = perf_counter()
        payload = adapter.execute(request.input, context)
        if inspect.isawaitable(payload):
            payload = await payload
        if isinstance(source_code, str) and descriptor.python_static_evaluation:
            static_evaluation = evaluate_python_static(
                source_code,
                filename if isinstance(filename, str) else "submission.py",
            )
            self._apply_static_evaluation(payload, static_evaluation)
        similarity_review: SimilarityReview | None = None
        if isinstance(source_code, str):
            similarity_review = self.code_similarity.review(
                request.case_id,
                submitter,
                source_code,
            )
            self._apply_similarity_review(
                payload,
                similarity_review,
                include_quality_dataset=descriptor.python_static_evaluation,
            )
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
                submitter=submitter,
                filename=filename if isinstance(filename, str) else "submission.py",
                source_code=source_code,
            )
        return result

    @staticmethod
    def _normalized_submitter(metadata: dict) -> str | None:
        value = metadata.get("submitter")
        if not isinstance(value, str) or not value.strip():
            # Keep old API clients working while the explicit submitter field replaces
            # the browser-generated student_id.
            value = metadata.get("student_id")
        if not isinstance(value, str) or not value.strip():
            return None
        return value.strip()[:128]

    @staticmethod
    def _apply_static_evaluation(
        payload: ResultPayload,
        evaluation: PythonStaticEvaluation,
    ) -> None:
        payload.datasets = [
            dataset
            for dataset in payload.datasets
            if dataset.name not in {"quality_scores", "code_issues"}
        ]
        payload.datasets.extend([quality_dataset(evaluation), issues_dataset(evaluation)])
        payload.metrics["syntax_valid"] = evaluation.syntax_valid
        payload.metrics["pep8_score"] = round(evaluation.pep8_score, 1)
        payload.metrics["modularity_score"] = round(evaluation.modularity_score, 1)

        case_score = payload.metrics.get("overall_score", 0.0)
        if not isinstance(case_score, (int, float)) or isinstance(case_score, bool):
            case_score = 0.0
        overall_score = min(
            100.0,
            float(case_score) + evaluation.pep8_score + evaluation.modularity_score,
        )
        payload.metrics["case_score"] = round(float(case_score), 1)
        payload.metrics["overall_score"] = round(overall_score, 1)
        payload.summary = (
            f"{payload.summary} 基座静态测评：PEP8 {evaluation.pep8_score:.1f}/10，"
            f"模块化 {evaluation.modularity_score:.1f}/10，当前总分 {overall_score:.1f}/100。"
        )
        if not evaluation.syntax_valid:
            issue = evaluation.issues[0]
            payload.diagnostics.append(
                Diagnostic(
                    code="PYTHON_SYNTAX_ERROR",
                    level=DiagnosticLevel.ERROR,
                    message=str(issue["message"]),
                    location=f"line:{issue['line']}" if issue["line"] else None,
                )
            )

    @staticmethod
    def _apply_similarity_review(
        payload: ResultPayload,
        review: SimilarityReview,
        *,
        include_quality_dataset: bool = False,
    ) -> None:
        payload.metrics["similarity_checked_submissions"] = review.checked_submissions
        payload.metrics["similarity_score"] = round(review.similarity * 100, 1)
        payload.metrics["similarity_threshold"] = round(review.threshold * 100, 1)
        payload.metrics["similarity_penalty"] = 0.0
        if include_quality_dataset:
            ExecutionService._append_similarity_quality(payload, review)
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

    @staticmethod
    def _append_similarity_quality(payload: ResultPayload, review: SimilarityReview) -> None:
        dataset = next(
            (item for item in payload.datasets if item.name == "quality_scores"),
            None,
        )
        if dataset is None:
            return
        similarity_percent = round(review.similarity * 100, 1)
        if review.checked_submissions == 0:
            summary = "暂无跨提交样本"
            details = "同一案例中暂时没有其他提交人的代码可供比较。"
        elif review.is_high:
            summary = "相似度超过阈值"
            details = (
                f"与其他提交人的最高相似度为 {similarity_percent:.1f}%，"
                f"阈值为 {review.threshold * 100:.1f}%。"
            )
        else:
            summary = "未发现高相似代码"
            details = (
                f"已比较 {review.checked_submissions} 份同案例代码，最高相似度为 "
                f"{similarity_percent:.1f}%。"
            )
        dataset.rows.append(
            {
                "dimension": "重复代码检测",
                "score": round(100.0 - similarity_percent, 1),
                "max_score": 100.0,
                "summary": summary,
                "details": details,
            }
        )
