from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from ai_tutor_backend.app import create_app
from ai_tutor_backend.code_execution import ExecutionRuntime, LocalPythonRunner
from ai_tutor_backend.models import ExecutionContext
from ai_tutor_backend.registry import CaseInputError, CaseRegistry
from ai_tutor_backend.repository import SQLiteResultRepository
from cases import register_cases
from cases.case_03_network_protocol_analyzer import NetworkProtocolAnalyzerCase

COMPLETE_SUBMISSION = '''
from collections import defaultdict
from scapy.all import ARP, ICMP, IP, TCP, Ether, sniff


def build_arp_packet(source, target):
    """Build an ARP request."""
    return Ether() / ARP(psrc=source, pdst=target)


def build_icmp_packet(source, target):
    """Build an ICMP echo request."""
    return IP(src=source, dst=target) / ICMP(type=8)


def build_tcp_packet(source, target, port):
    """Build a TCP SYN packet."""
    return IP(src=source, dst=target) / TCP(dport=port, flags="S")


def capture_packets(count=20):
    """Capture packets with a finite count and timeout."""
    return sniff(count=count, timeout=5)


def parse_arp_packet(packet):
    """Parse ARP fields."""
    return {"source": packet[ARP].psrc, "target": packet[ARP].pdst}


def parse_icmp_packet(packet):
    """Parse ICMP fields."""
    return {"type": packet[ICMP].type, "code": packet[ICMP].code}


def parse_tcp_packet(packet):
    """Parse TCP fields."""
    return {"source_port": packet[TCP].sport, "target_port": packet[TCP].dport}


def detect_port_scan(packets, threshold=4):
    """Detect a source contacting many distinct destination ports."""
    unique_ports = defaultdict(set)
    for packet in packets:
        if packet.haslayer(TCP) and packet[TCP].flags == "S":
            unique_ports[packet[IP].src].add(packet[TCP].dport)
    return [source for source, ports in unique_ports.items() if len(ports) >= threshold]


def analyze():
    """Return structured capture and anomaly results."""
    packets = capture_packets()
    packet_records = [parse_tcp_packet(packet) for packet in packets if packet.haslayer(TCP)]
    anomaly_findings = detect_port_scan(packets)
    return {"packet_records": packet_records, "anomaly_findings": anomaly_findings}
'''


def execute(source: str, filename: str = "student.py"):
    return asyncio.run(
        NetworkProtocolAnalyzerCase().execute(
            {"filename": filename, "source_code": source},
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


def submit(
    source: str,
    submitter: str = "student-a",
    client: TestClient | None = None,
) -> dict:
    response = (client or make_client()).post(
        "/api/v1/executions",
        json={
            "case_id": "network.protocol-analyzer",
            "input": {"filename": "student.py", "source_code": source},
            "metadata": {"submitter": submitter},
        },
    )
    assert response.status_code == 200
    return response.json()["payload"]


def test_case_registers_with_python_file_schema() -> None:
    registry = CaseRegistry()
    register_cases(registry)

    adapter = registry.get("network.protocol-analyzer")

    assert isinstance(adapter, NetworkProtocolAnalyzerCase)
    assert adapter.descriptor.version == "4.0.0"
    assert adapter.descriptor.python_static_evaluation is True
    assert adapter.descriptor.input_schema["x-ui-mode"] == "python-file"
    assert set(adapter.descriptor.input_schema["properties"]) == {"filename", "source_code"}
    assert {item.case_id for item in registry.list()} == {
        "os.process-scheduler",
        "database.sql-execution-plan",
        "algorithm.complexity-analyzer",
        "compiler.mini-frontend",
        "demo.echo",
        "network.protocol-analyzer",
    }


def test_case_adapter_only_returns_case_specific_runtime_analysis() -> None:
    result = execute(COMPLETE_SUBMISSION)
    checks = {row["check_id"]: row for row in result.datasets[0].rows}

    assert result.metrics["functionality_score"] == 80.0
    assert result.metrics["overall_score"] == 80.0
    assert result.metrics["runtime_status"] == "succeeded"
    assert result.metrics["runtime_tests_passed"] == result.metrics["runtime_tests_total"]
    assert result.metrics["runtime_pass_rate"] == 100.0
    assert "duplication_score" not in result.metrics
    assert [dataset.name for dataset in result.datasets] == [
        "runtime_tests",
        "runtime_packets",
        "runtime_observations",
    ]
    packet_dataset = result.datasets[1]
    assert packet_dataset.name == "runtime_packets"
    assert {row["protocol"] for row in packet_dataset.rows} == {"ARP", "ICMP", "TCP"}
    assert any(row["source"] == "10.0.0.1" for row in packet_dataset.rows)
    assert all(row["passed"] for row in checks.values())


def test_base_adds_generic_static_evaluation_and_similarity_result() -> None:
    payload = submit(COMPLETE_SUBMISSION)
    datasets = {dataset["name"]: dataset for dataset in payload["datasets"]}
    dimensions = {row["dimension"] for row in datasets["quality_scores"]["rows"]}

    assert payload["metrics"]["case_score"] == 80.0
    assert payload["metrics"]["pep8_score"] == 10.0
    assert payload["metrics"]["modularity_score"] >= 8.0
    assert payload["metrics"]["overall_score"] >= 98.0
    assert payload["metrics"]["similarity_checked_submissions"] == 0
    assert dimensions == {"PEP8 规范", "模块化程度", "重复代码检测"}
    assert "functional_tests" not in datasets


def test_base_similarity_evaluation_penalizes_only_other_submitters() -> None:
    client = make_client()
    first = submit(COMPLETE_SUBMISSION, "student-a", client)
    revision = submit(COMPLETE_SUBMISSION, "student-a", client)
    copied = submit(COMPLETE_SUBMISSION, "student-b", client)
    quality = {
        row["dimension"]: row
        for row in next(
            dataset for dataset in copied["datasets"] if dataset["name"] == "quality_scores"
        )["rows"]
    }

    assert first["metrics"]["similarity_penalty"] == 0.0
    assert revision["metrics"]["similarity_checked_submissions"] == 0
    assert revision["metrics"]["similarity_penalty"] == 0.0
    assert copied["metrics"]["similarity_score"] == 100.0
    assert copied["metrics"]["similarity_penalty"] == 30.0
    assert quality["重复代码检测"]["score"] == 0.0
    assert quality["重复代码检测"]["summary"] == "相似度超过阈值"


def test_incomplete_submission_gets_explainable_failures() -> None:
    result = execute("def hello():\n    return 'hello'\n")
    checks = result.datasets[0].rows

    assert result.metrics["runtime_tests_passed"] == 0
    assert all(not row["passed"] for row in checks)
    assert result.datasets[0].name == "runtime_tests"
    assert result.datasets[1].name == "runtime_packets"
    assert result.datasets[2].name == "runtime_observations"


def test_syntax_error_returns_zero_score_and_line_number() -> None:
    payload = submit("def broken(:\n    pass\n")
    datasets = {dataset["name"]: dataset for dataset in payload["datasets"]}

    assert payload["metrics"]["syntax_valid"] is False
    assert payload["metrics"]["overall_score"] == 0.0
    assert datasets["code_issues"]["rows"][0]["line"] == 1
    assert any(item["code"] == "PYTHON_SYNTAX_ERROR" for item in payload["diagnostics"])


@pytest.mark.parametrize("input_data", [{}, {"filename": "answer.txt", "source_code": "pass"}])
def test_submission_rejects_missing_or_non_python_file(input_data: dict) -> None:
    with pytest.raises(CaseInputError, match="代码文件输入不合法"):
        asyncio.run(
            NetworkProtocolAnalyzerCase().execute(
                input_data,
                ExecutionContext(request_id="test-request"),
            )
        )
