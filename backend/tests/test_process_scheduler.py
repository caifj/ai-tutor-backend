import asyncio
import json
from pathlib import Path

import pytest
from ai_tutor_backend.app import create_app
from ai_tutor_backend.code_execution import (
    CodeExecutionStatus,
    ExecutionRuntime,
    LocalPythonRunner,
    PythonRunResult,
)
from ai_tutor_backend.models import ExecutionContext
from ai_tutor_backend.registry import CaseInputError, CaseRegistry
from ai_tutor_backend.repository import SQLiteResultRepository
from cases import register_cases
from cases.case_01_process_scheduler import ProcessSchedulerCase
from cases.case_01_process_scheduler.evaluation import build_requests, reference, validate_result
from cases.case_01_process_scheduler.runtime_harness import MARKER
from fastapi.testclient import TestClient

CORRECT = (Path(__file__).parents[1] / "testcase/case1_correct.py").read_text(encoding="utf-8")


def execute(source, runner=None):
    return asyncio.run(
        ProcessSchedulerCase().execute(
            {"filename": "student.py", "source_code": source},
            ExecutionContext(
                request_id="case1-test",
                runtime=ExecutionRuntime(code_runner=runner or LocalPythonRunner()),
            ),
        )
    )


def test_correct_original_classes_pass_all_checks():
    result = execute(CORRECT)
    assert result.metrics["functionality_score"] == 80
    assert result.metrics["runtime_tests_passed"] == 72
    assert len(result.datasets[3].rows) == 24
    idle = next(r for r in result.datasets[3].rows if r["test_case"] == "FCFS · CPU空闲")
    assert idle["cpu_utilization_percent"] == pytest.approx(55.5556)
    assert idle["average_waiting_time"] == 0


def test_function_interface_and_wrong_student_metrics():
    source = (
        CORRECT
        + """
def schedule(processes, algorithm, quantum=2):
    types = {"fcfs": FCFSScheduler, "sjf": SJFScheduler,
             "rr": RRScheduler, "priority": PriorityScheduler}
    scheduler = types[algorithm](quantum) if algorithm == "rr" else types[algorithm]()
    result = scheduler.schedule([Process(**p) for p in processes]).to_dict()
    result["summary"]["average_waiting_time"] = -100
    return result
"""
    )
    result = execute(source)
    assert result.metrics["runtime_tests_passed"] == 48
    assert result.metrics["functionality_score"] == pytest.approx(53.33)
    assert all(r["average_waiting_time"] >= 0 for r in result.datasets[3].rows)


@pytest.mark.parametrize(
    "source,status",
    [
        ("def broken(:", "compile_error"),
        ("raise RuntimeError('student failed')", "succeeded"),
        ("def schedule(processes, algorithm, quantum=2): return {}", "succeeded"),
        ("print('hello')", "succeeded"),
        ("import os; os._exit(2)", "runtime_error"),
    ],
)
def test_bad_submissions_cannot_pass(source, status):
    result = execute(source)
    assert result.metrics["functionality_score"] == 0
    assert result.metrics["runtime_status"] == status
    assert result.datasets[1].rows == []


class FakeRunner:
    def __init__(self, **kwargs):
        self.result = PythonRunResult(
            status=CodeExecutionStatus.SUCCEEDED, compile_succeeded=True, **kwargs
        )

    async def run_python(self, spec):
        assert spec.entrypoint == "case_harness.py"
        assert len(spec.files) == 2
        assert "expected" not in spec.stdin
        return self.result


@pytest.mark.parametrize("payload", [None, [], {}, {"results": []}, {"checks": [True]}])
def test_malformed_runner_output_is_a_diagnostic_not_server_error(payload):
    result = execute("pass", FakeRunner(stdout=MARKER + json.dumps(payload)))
    assert result.metrics["functionality_score"] == 0
    assert any(d.code == "CASE1_RUNTIME_ERROR" for d in result.diagnostics)


def test_duplicate_result_ids_and_truncated_output_are_rejected():
    rows = [{"id": "fcfs_0", "result": {}}] * 24
    for runner in [
        FakeRunner(stdout=MARKER + json.dumps({"results": rows})),
        FakeRunner(output_truncated=True),
    ]:
        assert execute("pass", runner).metrics["functionality_score"] == 0


def test_no_runtime_is_not_a_pass():
    result = asyncio.run(
        ProcessSchedulerCase().execute(
            {"filename": "a.py", "source_code": "pass"}, ExecutionContext(request_id="none")
        )
    )
    assert result.metrics["runtime_status"] == "unavailable"
    assert result.metrics["runtime_tests_total"] == 72
    assert result.metrics["functionality_score"] == 0


def test_timeout_uses_foundation_runner():
    result = execute("while True: pass")
    assert result.metrics["runtime_status"] == "timed_out"
    assert result.metrics["functionality_score"] == 0


@pytest.mark.parametrize("field,value", [("filename", "a.txt"), ("source_code", "")])
def test_invalid_input(field, value):
    submission = {"filename": "a.py", "source_code": "pass", field: value}
    with pytest.raises(CaseInputError):
        asyncio.run(ProcessSchedulerCase().execute(submission, ExecutionContext(request_id="bad")))


@pytest.mark.parametrize(
    "submission",
    [
        {"filename": "a.txt", "source_code": "pass"},
        {"filename": "a.py", "source_code": ""},
        {"source_code": "pass"},
        {"filename": "a.py", "source_code": "汉" * 166_667},
    ],
)
def test_api_invalid_submission_returns_json_422(submission):
    registry = CaseRegistry()
    registry.register(ProcessSchedulerCase())
    with TestClient(
        create_app(registry=registry, repository=SQLiteResultRepository(":memory:")),
        raise_server_exceptions=False,
    ) as client:
        response = client.post(
            "/api/v1/executions",
            json={
                "case_id": "os.process-scheduler",
                "input": submission,
                "metadata": {"submitter": "case1-invalid-input-test"},
            },
        )
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "case_input_error"
    assert error["details"]["errors"]
    assert all(isinstance(item["loc"], list) for item in error["details"]["errors"])


def test_metrics_reject_booleans_nan_duplicates_and_bad_segments():
    expected = reference(build_requests()[0])
    for value in [True, float("nan"), float("inf"), "0", 10**400]:
        actual = json.loads(json.dumps(expected))
        actual["process_metrics"][0]["waiting_time"] = value
        assert validate_result(actual, expected)[1][0] is False
    actual = json.loads(json.dumps(expected))
    actual["process_metrics"][1] = actual["process_metrics"][0]
    assert not validate_result(actual, expected)[1][0]
    actual["segments"][0]["end"] = -1
    assert not validate_result(actual, expected)[0][0]


@pytest.mark.parametrize(
    "algorithm,order,waiting",
    [
        ("fcfs", ["A", "B", "C"], [0, 5, 7]),
        ("sjf", ["B", "C", "A"], [5, 0, 2]),
        ("priority", ["B", "A", "C"], [2, 0, 7]),
        ("rr", ["A", "B", "C", "A", "C", "A"], [5, 2, 6]),
    ],
)
def test_reference_against_hand_calculated_schedule(algorithm, order, waiting):
    request = next(r for r in build_requests() if r["id"] == algorithm + "_0")
    result = reference(request)
    assert [s["pid"] for s in result["segments"]] == order
    assert [m["waiting_time"] for m in result["process_metrics"]] == waiting
    assert result["summary"]["average_waiting_time"] == pytest.approx(sum(waiting) / 3, abs=0.0001)


def test_api_catalog_execution_saved_result_and_exports():
    registry = CaseRegistry()
    register_cases(registry)
    client = TestClient(
        create_app(
            registry=registry,
            repository=SQLiteResultRepository(":memory:"),
            code_runner=LocalPythonRunner(),
        )
    )
    with client:
        catalog = client.get("/api/v1/cases").json()["items"]
        descriptor = next(c for c in catalog if c["case_id"] == "os.process-scheduler")
        assert descriptor["course_number"] == 1
        assert descriptor["input_schema"]["x-ui-mode"] == "python-file"
        response = client.post(
            "/api/v1/executions",
            json={
                "case_id": "os.process-scheduler",
                "input": {"filename": "correct.py", "source_code": CORRECT},
                "metadata": {"submitter": "case1-integration-test"},
            },
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["payload"]["metrics"]["functionality_score"] == 80
        assert {d["name"] for d in result["payload"]["datasets"]} >= {
            "scheduling_gantt",
            "process_metrics",
            "scheduling_summary",
            "quality_scores",
        }
        url = "/api/v1/results/" + result["request_id"]
        assert client.get(url).json()["payload"] == result["payload"]
        csv = client.get(url + "?format=csv")
        assert csv.status_code == 200
        assert "waiting_time" in csv.text
