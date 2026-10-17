from __future__ import annotations

import pytest
from pydantic import ValidationError

from ai_tutor_backend.models import CaseDescriptor, ExecutionContext, ResultPayload
from ai_tutor_backend.registry import (
    CaseAdapter,
    CaseNotFoundError,
    CaseRegistry,
    DuplicateCaseError,
)


class StubAdapter(CaseAdapter):
    @property
    def descriptor(self) -> CaseDescriptor:
        return CaseDescriptor(case_id="stub", name="Stub", course="Tests", course_number=1)

    def execute(self, input_data: dict, context: ExecutionContext) -> ResultPayload:
        return ResultPayload(summary="ok")


def test_registry_registers_and_lists_adapters() -> None:
    registry = CaseRegistry()
    registry.register(StubAdapter())

    assert [item.case_id for item in registry.list()] == ["stub"]
    assert registry.get("stub").descriptor.name == "Stub"


def test_registry_rejects_duplicates_and_unknown_cases() -> None:
    registry = CaseRegistry()
    registry.register(StubAdapter())

    with pytest.raises(DuplicateCaseError):
        registry.register(StubAdapter())
    with pytest.raises(CaseNotFoundError):
        registry.get("missing")


def test_visible_case_requires_course_number() -> None:
    with pytest.raises(ValidationError, match="course_number"):
        CaseDescriptor(case_id="visible", name="Visible", course="Tests")


def test_hidden_case_can_omit_course_number() -> None:
    descriptor = CaseDescriptor(
        case_id="hidden",
        name="Hidden",
        course="Tests",
        catalog_visible=False,
    )

    assert descriptor.course_number is None
