from __future__ import annotations

from fastapi.testclient import TestClient

from ai_tutor_backend.app import create_app
from ai_tutor_backend.code_similarity import calculate_code_similarity
from ai_tutor_backend.models import CaseDescriptor, ExecutionContext, ResultPayload
from ai_tutor_backend.registry import CaseAdapter, CaseRegistry
from ai_tutor_backend.repository import SQLiteResultRepository

SOURCE_A = """
from collections import defaultdict

def analyze_packets(packets):
    ports = defaultdict(set)
    results = []
    for packet in packets:
        if packet.haslayer("TCP"):
            source = packet.source
            target = packet.target
            port = packet.port
            ports[source].add(port)
            results.append({"source": source, "target": target, "port": port})
    suspicious = [source for source, values in ports.items() if len(values) > 5]
    return {"packets": results, "suspicious": suspicious}
"""

SOURCE_B = """
from collections import defaultdict

def inspect_traffic(items):
    observed = defaultdict(set)
    records = []
    for item in items:
        if item.haslayer("UDP"):
            origin = item.origin
            destination = item.destination
            service = item.service
            observed[origin].add(service)
            records.append({"origin": origin, "destination": destination, "service": service})
    alerts = [origin for origin, services in observed.items() if len(services) > 20]
    return {"records": records, "alerts": alerts}
"""


class PythonScoreCase(CaseAdapter):
    @property
    def descriptor(self) -> CaseDescriptor:
        return CaseDescriptor(
            case_id="test.python-score",
            name="Python score",
            course="Test",
            input_schema={"type": "object"},
        )

    def execute(self, input_data: dict, context: ExecutionContext) -> ResultPayload:
        return ResultPayload(summary="评测完成。", metrics={"overall_score": 90.0})


def make_client() -> tuple[TestClient, SQLiteResultRepository]:
    registry = CaseRegistry()
    registry.register(PythonScoreCase())
    repository = SQLiteResultRepository(":memory:")
    app = create_app(registry=registry, repository=repository)
    return TestClient(app), repository


def submit(client: TestClient, student_id: str, source: str = SOURCE_A):
    return client.post(
        "/api/v1/executions",
        json={
            "case_id": "test.python-score",
            "input": {"filename": "answer.py", "source_code": source},
            "metadata": {"student_id": student_id},
        },
    )


def test_similarity_ignores_comments_and_literal_values() -> None:
    changed_literals = SOURCE_A.replace("> 5", "> 8").replace(
        "def analyze_packets", "# student comment\ndef analyze_packets"
    )

    assert calculate_code_similarity(SOURCE_A, SOURCE_A) == 1.0
    assert calculate_code_similarity(SOURCE_A, changed_literals) >= 0.85
    assert calculate_code_similarity(SOURCE_A, SOURCE_B) < 0.85


def test_submissions_are_scoped_by_case_and_can_exclude_same_student() -> None:
    repository = SQLiteResultRepository(":memory:")
    repository.save_code_submission(
        request_id="r1",
        case_id="case.one",
        student_id="student-a",
        filename="a.py",
        source_code=SOURCE_A,
    )
    repository.save_code_submission(
        request_id="r2",
        case_id="case.two",
        student_id="student-b",
        filename="b.py",
        source_code=SOURCE_A,
    )

    assert len(repository.list_code_submissions("case.one")) == 1
    assert repository.list_code_submissions(
        "case.one", excluding_student_id="student-a"
    ) == []
    assert repository.list_code_submissions("case.two")[0].request_id == "r2"


def test_high_similarity_from_another_student_reduces_overall_score() -> None:
    client, repository = make_client()

    first = submit(client, "student-a")
    same_student_revision = submit(client, "student-a")
    copied = submit(client, "student-b")

    assert first.status_code == 200
    assert first.json()["payload"]["metrics"]["similarity_checked_submissions"] == 0
    assert same_student_revision.json()["payload"]["metrics"]["similarity_penalty"] == 0.0

    payload = copied.json()["payload"]
    assert payload["metrics"]["similarity_score"] == 100.0
    assert payload["metrics"]["similarity_penalty"] == 30.0
    assert payload["metrics"]["original_score"] == 90.0
    assert payload["metrics"]["overall_score"] == 60.0
    assert any(item["code"] == "CODE_SIMILARITY_HIGH" for item in payload["diagnostics"])
    assert len(repository.list_code_submissions("test.python-score")) == 3


def test_different_code_does_not_receive_similarity_penalty() -> None:
    client, _ = make_client()
    submit(client, "student-a", SOURCE_A)

    result = submit(client, "student-b", SOURCE_B)

    assert result.status_code == 200
    metrics = result.json()["payload"]["metrics"]
    assert metrics["similarity_score"] < 85.0
    assert metrics["similarity_penalty"] == 0.0
    assert metrics["overall_score"] == 90.0
