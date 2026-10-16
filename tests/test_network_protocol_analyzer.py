from __future__ import annotations

import json

import pytest

from ai_tutor_backend.models import ExecutionContext
from ai_tutor_backend.registry import CaseInputError, CaseRegistry
from cases import register_cases
from cases.case_03_network_protocol_analyzer import NetworkProtocolAnalyzerCase
from cases.case_03_network_protocol_analyzer.codec import build_packet, parse_packet

BASE_BUILD_ARGS = {
    "source_mac": "02:00:00:00:00:01",
    "destination_mac": "ff:ff:ff:ff:ff:ff",
    "source_ip": "192.168.1.10",
    "destination_ip": "192.168.1.1",
    "source_port": 40000,
    "destination_port": 80,
    "tcp_flags": "SYN",
    "arp_operation": "request",
    "payload_text": "AI Tutor",
}


@pytest.mark.parametrize("protocol", ["ARP", "ICMP", "TCP"])
def test_build_and_parse_supported_protocols(protocol: str) -> None:
    frame = build_packet(protocol=protocol, **BASE_BUILD_ARGS)

    packet = parse_packet(frame)

    assert packet.protocol == protocol
    assert packet.length == len(frame)
    assert packet.fields["source_mac"] == "02:00:00:00:00:01"
    if protocol in {"ICMP", "TCP"}:
        assert packet.fields["ip_checksum_valid"] is True
    if protocol == "TCP":
        assert packet.fields["tcp_checksum_valid"] is True
        assert packet.fields["tcp_flags"] == ["SYN"]


def test_case_registers_and_constructs_a_packet() -> None:
    registry = CaseRegistry()
    register_cases(registry)

    adapter = registry.get("network.protocol-analyzer")
    result = adapter.execute(
        {"operation": "construct", "protocol": "ICMP"},
        ExecutionContext(request_id="test-request"),
    )

    assert isinstance(adapter, NetworkProtocolAnalyzerCase)
    assert result.metrics["packet_count"] == 1
    assert result.datasets[0].rows[0]["protocol"] == "ICMP"
    assert result.datasets[1].rows == []


def test_offline_capture_detects_tcp_syn_port_scan() -> None:
    capture = []
    for port in (22, 23, 80, 443):
        args = {**BASE_BUILD_ARGS, "destination_port": port}
        capture.append(
            {
                "timestamp": f"2026-10-16T10:00:0{port % 10}Z",
                "packet_hex": build_packet(protocol="TCP", **args).hex(),
            }
        )

    result = NetworkProtocolAnalyzerCase().execute(
        {
            "operation": "capture",
            "capture_source": "offline",
            "capture_packets_json": json.dumps(capture),
            "scan_threshold": 4,
        },
        ExecutionContext(request_id="test-request"),
    )

    findings = result.datasets[1].rows
    assert result.metrics["packet_count"] == 4
    assert result.metrics["anomaly_count"] == 1
    assert findings[0]["code"] == "TCP_SYN_PORT_SCAN"
    assert "22" in findings[0]["evidence"]


def test_analyze_rejects_invalid_or_missing_hex() -> None:
    adapter = NetworkProtocolAnalyzerCase()
    context = ExecutionContext(request_id="test-request")

    with pytest.raises(CaseInputError, match="必须提供"):
        adapter.execute({"operation": "analyze"}, context)
    with pytest.raises(CaseInputError, match="格式不合法"):
        adapter.execute({"operation": "analyze", "packet_hex": "not-hex"}, context)
