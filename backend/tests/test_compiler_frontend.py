from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from ai_tutor_backend.app import create_app
from ai_tutor_backend.code_execution import ExecutionRuntime, LocalPythonRunner
from ai_tutor_backend.models import ExecutionContext
from ai_tutor_backend.registry import CaseRegistry
from ai_tutor_backend.repository import SQLiteResultRepository
from cases import register_cases
from cases.case_08_compiler_frontend import MiniCompilerFrontendCase

TESTCASE_DIR = Path(__file__).resolve().parents[1] / "testcase"
COMPLETE_SUBMISSION = (TESTCASE_DIR / "case8_correct.py").read_text(encoding="utf-8")
INCOMPLETE_SUBMISSION = (TESTCASE_DIR / "case8_incorrect.py").read_text(encoding="utf-8")


def execute(source: str):
    return asyncio.run(
        MiniCompilerFrontendCase().execute(
            {"filename": "student.py", "source_code": source},
            ExecutionContext(
                request_id="case8-test",
                runtime=ExecutionRuntime(code_runner=LocalPythonRunner()),
            ),
        )
    )


def make_client() -> TestClient:
    registry = CaseRegistry()
    register_cases(registry)
    return TestClient(
        create_app(
            registry=registry,
            repository=SQLiteResultRepository(":memory:"),
            code_runner=LocalPythonRunner(),
        )
    )


def submit(source: str, submitter: str = "student-a") -> dict:
    response = make_client().post(
        "/api/v1/executions",
        json={
            "case_id": "compiler.mini-frontend",
            "input": {"filename": "student.py", "source_code": source},
            "metadata": {"submitter": submitter},
        },
    )
    assert response.status_code == 200
    return response.json()["payload"]


def test_case_uses_base_static_evaluation_contract() -> None:
    descriptor = MiniCompilerFrontendCase().descriptor

    assert descriptor.version == "2.0.0"
    assert descriptor.python_static_evaluation is True
    assert descriptor.input_schema["x-ui-mode"] == "python-file"
    assert set(descriptor.output_datasets) == {
        "runtime_tests",
        "ast_tree",
        "error_locations",
        "quality_scores",
        "code_issues",
    }


def test_case_adapter_returns_only_case_specific_runtime_analysis() -> None:
    result = execute(COMPLETE_SUBMISSION)

    assert result.metrics["functionality_score"] == 80.0
    assert result.metrics["overall_score"] == 80.0
    assert result.metrics["runtime_status"] == "succeeded"
    assert result.metrics["runtime_pass_rate"] == 100.0
    assert "pep8_score" not in result.metrics
    assert "modularity_score" not in result.metrics
    assert [dataset.name for dataset in result.datasets] == [
        "runtime_tests",
        "ast_tree",
        "error_locations",
    ]


def test_base_adds_generic_static_evaluation() -> None:
    payload = submit(COMPLETE_SUBMISSION)
    datasets = {dataset["name"]: dataset for dataset in payload["datasets"]}
    dimensions = {row["dimension"] for row in datasets["quality_scores"]["rows"]}

    assert payload["metrics"]["case_score"] == 80.0
    assert payload["metrics"]["pep8_score"] > 0
    assert payload["metrics"]["modularity_score"] > 0
    assert payload["metrics"]["overall_score"] >= 80.0
    assert dimensions == {"PEP8 规范", "模块化程度", "重复代码检测"}
    assert "functional_tests" not in datasets


def test_incomplete_submission_is_scored_by_runtime_checks() -> None:
    result = execute(INCOMPLETE_SUBMISSION)

    assert result.metrics["functionality_score"] < 64.0
    assert result.metrics["overall_score"] == result.metrics["functionality_score"]
    assert any(not row["passed"] for row in result.datasets[0].rows)


def test_syntax_error_is_reported_by_base_static_evaluation() -> None:
    payload = submit("def broken(:\n    pass\n")
    datasets = {dataset["name"]: dataset for dataset in payload["datasets"]}

    assert payload["metrics"]["syntax_valid"] is False
    assert payload["metrics"]["overall_score"] == 0.0
    assert datasets["code_issues"]["rows"][0]["line"] == 1
    assert any(item["code"] == "PYTHON_SYNTAX_ERROR" for item in payload["diagnostics"])
