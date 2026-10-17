from __future__ import annotations

from course_assistant_ai import LearningModuleContext, ReviewContext

from .registry import CaseRegistry
from .repository import SQLiteResultRepository


class BackendAssistantContextGateway:
    """Maps backend domain objects to the AI package's narrow context contracts."""

    def __init__(
        self,
        registry: CaseRegistry,
        repository: SQLiteResultRepository,
    ) -> None:
        self.registry = registry
        self.repository = repository

    def get_module(self, case_id: str) -> LearningModuleContext:
        descriptor = self.registry.get(case_id).descriptor
        return LearningModuleContext(
            case_id=descriptor.case_id,
            name=descriptor.name,
            course=descriptor.course,
            description=descriptor.description,
            output_datasets=list(descriptor.output_datasets),
        )

    def get_review(self, request_id: str) -> tuple[ReviewContext, LearningModuleContext]:
        result = self.repository.get(request_id)
        issue_dataset = next(
            (dataset for dataset in result.payload.datasets if dataset.name == "code_issues"),
            None,
        )
        issues: list[str] = []
        for row in (issue_dataset.rows if issue_dataset else [])[:6]:
            message = str(row.get("message", "")).strip()
            suggestion = str(row.get("suggestion", "")).strip()
            if message or suggestion:
                issues.append(f"{message}；建议：{suggestion}")
        review = ReviewContext(
            summary=result.payload.summary,
            metrics=dict(result.payload.metrics),
            issues=issues,
        )
        return review, self.get_module(result.case_id)
