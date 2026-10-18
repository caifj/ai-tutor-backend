"""案例 7 SQL 执行计划可视化工具代码评测测试。"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from ai_tutor_backend import CaseInputError, CaseRegistry, ExecutionContext, ExecutionRuntime
from ai_tutor_backend.app import create_app
from ai_tutor_backend.code_execution import LocalPythonRunner
from ai_tutor_backend.repository import SQLiteResultRepository
from cases import register_cases
from cases.case_07_sql_execution_plan import SqlExecutionPlanCase

COMPLETE_SUBMISSION = '''
def parse_explain(plan_text):
    """Parse simplified MySQL EXPLAIN rows."""
    nodes = []
    index_usage = []
    full_scan_findings = []
    for line in plan_text.splitlines():
        fields = {}
        for part in line.replace("->", "").split(","):
            if "=" in part:
                key, value = part.strip().split("=", 1)
                fields[key] = value
        if fields:
            nodes.append(fields)
            if fields.get("key") not in {None, "NULL"}:
                index_usage.append(fields["key"])
            if fields.get("type") == "ALL":
                full_scan_findings.append(fields.get("table", "unknown"))
    return {
        "nodes": nodes,
        "index_usage": index_usage,
        "full_scan_findings": full_scan_findings,
    }


def build_btree(keys, order=3):
    """Build a small test-friendly tree representation."""
    return {"order": order, "keys": sorted(keys)}


def lookup(root, key):
    """Return a trace that contains the target when it exists."""
    return [root["keys"], key] if key in root["keys"] else [root["keys"]]
'''


def execute(source: str):
    return asyncio.run(
        SqlExecutionPlanCase().execute(
            {"filename": "student.py", "source_code": source},
            ExecutionContext(
                request_id="test-request",
                runtime=ExecutionRuntime(code_runner=LocalPythonRunner()),
            ),
        )
    )


def make_client() -> TestClient:
    registry = CaseRegistry()
    register_cases(registry)
    app = create_app(
        registry=registry,
        repository=SQLiteResultRepository(":memory:"),
        code_runner=LocalPythonRunner(),
    )
    return TestClient(app)


def submit(source: str) -> dict:
    response = make_client().post(
        "/api/v1/executions",
        json={
            "case_id": "database.sql-execution-plan",
            "input": {"filename": "student.py", "source_code": source},
            "metadata": {"submitter": "student-a"},
        },
    )
    assert response.status_code == 200
    return response.json()["payload"]


class TestAdapter:
    """适配器测试。"""

    def test_descriptor(self):
        """测试描述符。"""
        case = SqlExecutionPlanCase()
        descriptor = case.descriptor
        assert descriptor.case_id == "database.sql-execution-plan"
        assert descriptor.name == "SQL执行计划可视化工具代码评测"
        assert descriptor.course == "数据库系统"
        assert descriptor.course_number == 7
        assert descriptor.version == "4.0.0"
        assert descriptor.python_static_evaluation is True
        assert "functional_tests" not in descriptor.output_datasets
        assert "runtime_tests" in descriptor.output_datasets
        assert "quality_scores" in descriptor.output_datasets

    def test_validate_input_valid(self):
        """测试有效输入。"""
        case = SqlExecutionPlanCase()
        input_data = {
            "filename": "student.py",
            "source_code": "def parse_explain(plan_text):\n    return {}",
        }
        submission = case._validate_input(input_data)
        assert submission.filename == "student.py"
        assert submission.source_code.startswith("def parse_explain")

    def test_validate_input_invalid_extension(self):
        """测试非法文件扩展名。"""
        case = SqlExecutionPlanCase()
        input_data = {
            "filename": "student.txt",
            "source_code": "def parse_explain(plan_text):\n    return {}",
        }
        with pytest.raises(CaseInputError, match="代码文件输入不合法"):
            case._validate_input(input_data)

    def test_validate_input_missing_field(self):
        """测试缺少必需字段。"""
        case = SqlExecutionPlanCase()
        input_data = {"filename": "student.py"}
        with pytest.raises(CaseInputError):
            case._validate_input(input_data)


class TestIntegration:
    """集成测试。"""

    def test_register_cases(self):
        """测试案例注册。"""
        registry = CaseRegistry()
        register_cases(registry)
        adapter = registry.get("database.sql-execution-plan")
        assert isinstance(adapter, SqlExecutionPlanCase)
        assert adapter.descriptor.course_number == 7

    def test_case_adapter_only_returns_runtime_analysis(self):
        result = execute(COMPLETE_SUBMISSION)
        checks = {row["check_id"]: row for row in result.datasets[0].rows}

        assert result.metrics["runtime_status"] == "succeeded"
        assert result.metrics["runtime_tests_passed"] == result.metrics["runtime_tests_total"]
        assert result.metrics["functionality_score"] == 80.0
        assert result.metrics["overall_score"] == 80.0
        assert [dataset.name for dataset in result.datasets] == ["runtime_tests"]
        assert all(row["passed"] for row in checks.values())

    def test_base_adds_generic_static_evaluation(self):
        payload = submit(COMPLETE_SUBMISSION)
        datasets = {dataset["name"]: dataset for dataset in payload["datasets"]}
        dimensions = {row["dimension"] for row in datasets["quality_scores"]["rows"]}

        assert payload["metrics"]["case_score"] == 80.0
        assert payload["metrics"]["pep8_score"] > 0
        assert payload["metrics"]["modularity_score"] > 0
        assert dimensions == {"PEP8 规范", "模块化程度", "重复代码检测"}
        assert "functional_tests" not in datasets

    def test_missing_functions_fail_runtime_instead_of_keyword_static_checks(self):
        result = execute("def hello():\n    return 'hello'\n")

        assert result.metrics["runtime_status"] == "succeeded"
        assert result.metrics["runtime_tests_passed"] == 0
        assert all(not row["passed"] for row in result.datasets[0].rows)

    def test_syntax_error_is_reported_by_base(self):
        payload = submit("def broken(:\n    pass\n")
        datasets = {dataset["name"]: dataset for dataset in payload["datasets"]}

        assert payload["metrics"]["syntax_valid"] is False
        assert payload["metrics"]["overall_score"] == 0.0
        assert datasets["code_issues"]["rows"][0]["line"] == 1
        assert any(item["code"] == "PYTHON_SYNTAX_ERROR" for item in payload["diagnostics"])


class TestRuntimeHarness:
    """运行时夹具测试。"""

    def test_harness_source_contains_marker(self):
        """测试夹具包含结果标记。"""
        from cases.case_07_sql_execution_plan.runtime_harness import HARNESS_SOURCE

        assert "__AI_TUTOR_CASE7_RESULT__" in HARNESS_SOURCE

    def test_harness_source_contains_tests(self):
        """测试夹具包含测试函数。"""
        from cases.case_07_sql_execution_plan.runtime_harness import HARNESS_SOURCE

        assert "test_parse_explain" in HARNESS_SOURCE
        assert "test_btree" in HARNESS_SOURCE
