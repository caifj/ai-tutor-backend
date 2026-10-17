from __future__ import annotations

import pytest

from ai_tutor_backend.models import ExecutionContext
from ai_tutor_backend.registry import CaseInputError, CaseRegistry
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
    return NetworkProtocolAnalyzerCase().execute(
        {"filename": filename, "source_code": source},
        ExecutionContext(request_id="test-request"),
    )


def test_case_registers_with_python_file_schema() -> None:
    registry = CaseRegistry()
    register_cases(registry)

    adapter = registry.get("network.protocol-analyzer")

    assert isinstance(adapter, NetworkProtocolAnalyzerCase)
    assert adapter.descriptor.version == "2.0.0"
    assert adapter.descriptor.input_schema["x-ui-mode"] == "python-file"
    assert set(adapter.descriptor.input_schema["properties"]) == {"filename", "source_code"}
    assert {item.case_id for item in registry.list()} == {
        "database.sql-execution-plan",
        "algorithm.complexity-analyzer",
        "demo.echo",
        "network.protocol-analyzer",
    }


def test_complete_submission_passes_core_static_checks() -> None:
    result = execute(COMPLETE_SUBMISSION)
    checks = {row["check_id"]: row for row in result.datasets[0].rows}

    assert result.metrics["syntax_valid"] is True
    assert result.metrics["tests_passed"] == result.metrics["tests_total"]
    assert result.metrics["test_pass_rate"] == 100.0
    assert result.metrics["functionality_score"] == 80.0
    assert result.metrics["overall_score"] >= 90
    assert "duplication_score" not in result.metrics
    assert len(result.datasets[1].rows) == 2
    assert all(row["passed"] for row in checks.values())


def test_incomplete_submission_gets_explainable_failures() -> None:
    result = execute("def hello():\n    return 'hello'\n")
    checks = result.datasets[0].rows

    assert result.metrics["syntax_valid"] is True
    assert result.metrics["tests_passed"] == 0
    assert any("未" in row["evidence"] for row in checks)
    assert result.datasets[1].name == "quality_scores"
    assert result.datasets[2].name == "code_issues"


def test_syntax_error_returns_zero_score_and_line_number() -> None:
    result = execute("def broken(:\n    pass\n")

    assert result.metrics["syntax_valid"] is False
    assert result.metrics["overall_score"] == 0.0
    assert result.datasets[2].rows[0]["line"] == 1
    assert result.diagnostics[0].code == "PYTHON_SYNTAX_ERROR"


@pytest.mark.parametrize("input_data", [{}, {"filename": "answer.txt", "source_code": "pass"}])
def test_submission_rejects_missing_or_non_python_file(input_data: dict) -> None:
    with pytest.raises(CaseInputError, match="代码文件输入不合法"):
        NetworkProtocolAnalyzerCase().execute(
            input_data,
            ExecutionContext(request_id="test-request"),
        )
