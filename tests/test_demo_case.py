from __future__ import annotations

import pytest

from ai_tutor_backend.models import ExecutionContext
from ai_tutor_backend.registry import CaseInputError, CaseRegistry
from examples.demo_case_package import EchoCase, register_cases


def test_demo_package_registers_and_executes() -> None:
    registry = CaseRegistry()
    register_cases(registry)

    adapter = registry.get("demo.echo")
    result = adapter.execute(
        {"text": "hello", "repeat": 2},
        ExecutionContext(request_id="test-request"),
    )

    assert isinstance(adapter, EchoCase)
    assert result.metrics["repeat_count"] == 2
    assert result.datasets[0].rows == [
        {"sequence": 1, "text": "hello"},
        {"sequence": 2, "text": "hello"},
    ]


def test_demo_package_translates_validation_errors() -> None:
    with pytest.raises(CaseInputError, match="输入不合法"):
        EchoCase().execute(
            {"text": "", "repeat": 0},
            ExecutionContext(request_id="test-request"),
        )
