from __future__ import annotations

from fastapi.testclient import TestClient

from ai_tutor_backend.app import create_app
from ai_tutor_backend.models import (
    CaseDescriptor,
    ColumnSpec,
    Dataset,
    DataType,
    ExecutionContext,
    ResultPayload,
)
from ai_tutor_backend.registry import CaseAdapter, CaseInputError, CaseRegistry
from ai_tutor_backend.repository import SQLiteResultRepository


class TestAdapter(CaseAdapter):
    @property
    def descriptor(self) -> CaseDescriptor:
        return CaseDescriptor(
            case_id="test.echo",
            name="Echo adapter",
            course="Test",
            input_schema={"type": "object", "required": ["value"]},
            output_datasets=["echo"],
        )

    def execute(self, input_data: dict, context: ExecutionContext) -> ResultPayload:
        if "value" not in input_data:
            raise CaseInputError("value is required", {"field": "value"})
        return ResultPayload(
            summary="ok",
            datasets=[
                Dataset(
                    name="echo",
                    title="Echo",
                    columns=[ColumnSpec(key="value", title="Value", data_type=DataType.STRING)],
                    rows=[{"value": str(input_data["value"])}],
                )
            ],
        )


def make_client() -> TestClient:
    registry = CaseRegistry()
    registry.register(TestAdapter())
    app = create_app(
        registry=registry,
        repository=SQLiteResultRepository(":memory:"),
    )
    return TestClient(app)


def test_execute_read_and_grade_workflow() -> None:
    client = make_client()
    execution = client.post(
        "/api/v1/executions",
        json={"case_id": "test.echo", "input": {"value": "hello"}},
    )
    assert execution.status_code == 200
    result = execution.json()
    request_id = result["request_id"]

    stored = client.get(f"/api/v1/results/{request_id}")
    assert stored.status_code == 200
    assert stored.json()["payload"]["datasets"][0]["rows"] == [{"value": "hello"}]

    grade = client.post(
        "/api/v1/grades",
        json={"actual_result_id": request_id, "expected": result["payload"]},
    )
    assert grade.status_code == 200
    assert grade.json()["passed"] is True


def test_csv_and_standardized_errors() -> None:
    client = make_client()
    csv_response = client.post(
        "/api/v1/executions?format=csv",
        json={"case_id": "test.echo", "input": {"value": "你好"}},
    )
    assert csv_response.status_code == 200
    assert csv_response.headers["content-type"].startswith("text/csv")
    assert "record_type" in csv_response.text

    missing_case = client.post("/api/v1/executions", json={"case_id": "missing", "input": {}})
    assert missing_case.status_code == 404
    assert missing_case.json()["error"]["code"] == "case_not_found"

    bad_input = client.post("/api/v1/executions", json={"case_id": "test.echo", "input": {}})
    assert bad_input.status_code == 422
    assert bad_input.json()["error"]["details"] == {"field": "value"}


def test_frontend_is_served_from_root() -> None:
    response = make_client().get("/")

    assert response.status_code == 200
    assert "知行实验室" in response.text
    assert "/assets/app.js" in response.text
