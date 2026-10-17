from __future__ import annotations

import pytest

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
        return CaseDescriptor(case_id="stub", name="Stub", course="Tests")

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
