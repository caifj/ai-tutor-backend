from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ai_tutor_backend import (
    CaseAdapter,
    CaseDescriptor,
    CaseInputError,
    ColumnSpec,
    Dataset,
    DataType,
    Diagnostic,
    DiagnosticLevel,
    ExecutionContext,
    ResultPayload,
)

from .capture import LiveCaptureUnavailableError, capture_live_packets
from .codec import PacketCodecError, ParsedPacket, build_packet, normalize_packet_hex, parse_packet
from .detection import detect_anomalies


class AnalyzerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["construct", "analyze", "capture"] = Field(
        default="construct",
        title="操作",
        description="construct 构造报文；analyze 解析单个十六进制报文；capture 分析捕获记录。",
    )
    protocol: Literal["ARP", "ICMP", "TCP"] = Field(
        default="TCP",
        title="构造协议",
        description="仅在 construct 操作中使用。",
    )
    packet_hex: str = Field(
        default="",
        title="待解析报文",
        max_length=1_000_000,
        description="analyze 操作使用的完整以太网帧十六进制，可包含空格、冒号或换行。",
    )
    capture_source: Literal["offline", "live"] = Field(
        default="offline",
        title="捕获来源",
        description="capture 操作可读取离线记录，或通过可选 Scapy/Npcap 进行实时抓包。",
    )
    capture_packets_json: str = Field(
        default="[]",
        title="离线捕获记录 JSON",
        max_length=5_000_000,
        description='JSON 数组；元素可为十六进制字符串或 {"timestamp":"...","packet_hex":"..."}。',
    )
    capture_interface: str = Field(
        default="",
        title="实时抓包网卡",
        max_length=200,
        description="留空时使用 Scapy 默认网卡；仅 capture/live 使用。",
    )
    capture_count: int = Field(
        default=20,
        ge=1,
        le=100,
        title="最大抓包数量",
    )
    capture_timeout: int = Field(
        default=5,
        ge=1,
        le=15,
        title="抓包超时（秒）",
    )
    source_mac: str = Field(default="02:00:00:00:00:01", title="源 MAC")
    destination_mac: str = Field(default="ff:ff:ff:ff:ff:ff", title="目标 MAC")
    source_ip: str = Field(default="192.168.1.10", title="源 IPv4")
    destination_ip: str = Field(default="192.168.1.1", title="目标 IPv4")
    source_port: int = Field(default=40000, ge=0, le=65535, title="源端口")
    destination_port: int = Field(default=80, ge=0, le=65535, title="目标端口")
    tcp_flags: str = Field(
        default="SYN",
        max_length=80,
        title="TCP 标志",
        description="使用逗号分隔，例如 SYN 或 SYN,ACK。",
    )
    arp_operation: Literal["request", "reply"] = Field(default="request", title="ARP 操作")
    payload_text: str = Field(default="AI Tutor", max_length=4096, title="负载文本")
    scan_threshold: int = Field(
        default=4,
        ge=2,
        le=100,
        title="扫描判定阈值",
        description="同一来源访问不同端口或主机达到该数量时报告扫描行为。",
    )


class NetworkProtocolAnalyzerCase(CaseAdapter):
    @property
    def descriptor(self) -> CaseDescriptor:
        return CaseDescriptor(
            case_id="network.protocol-analyzer",
            name="网络协议分析仪",
            course="计算机网络",
            course_number=3,
            description="构造、捕获并解析 ARP、ICMP、TCP 报文，识别端口扫描、主机扫描和 ARP 地址冲突。",
            version="1.0.0",
            input_schema=AnalyzerInput.model_json_schema(),
            output_datasets=["packet_records", "anomaly_findings"],
        )

    def execute(self, input_data: dict, context: ExecutionContext) -> ResultPayload:
        data = self._validate_input(input_data)
        diagnostics: list[Diagnostic] = []

        if data.operation == "construct":
            captured = self._construct(data)
            diagnostics.append(
                Diagnostic(
                    code="PACKET_CONSTRUCTED",
                    level=DiagnosticLevel.INFO,
                    message=f"已构造并解析 1 个 {data.protocol} 报文。",
                )
            )
        elif data.operation == "analyze":
            if not data.packet_hex.strip():
                raise CaseInputError("analyze 操作必须提供 packet_hex", {"field": "packet_hex"})
            captured = [
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "packet_bytes": self._decode_hex(data.packet_hex, "packet_hex"),
                }
            ]
        elif data.capture_source == "live":
            captured = self._capture_live(data)
            diagnostics.append(
                Diagnostic(
                    code="LIVE_CAPTURE_COMPLETED",
                    level=DiagnosticLevel.INFO,
                    message=f"实时抓包结束，共收到 {len(captured)} 个目标协议报文。",
                )
            )
        else:
            captured = self._read_offline_capture(data.capture_packets_json)

        parsed, parse_diagnostics = self._parse_captured(captured)
        diagnostics.extend(parse_diagnostics)
        if not parsed:
            raise CaseInputError(
                "没有可输出的有效 ARP、ICMP 或 TCP 报文",
                {"received_count": len(captured)},
            )

        findings = detect_anomalies([packet for _, packet in parsed], data.scan_threshold)
        packet_rows = [
            {
                "index": index + 1,
                "timestamp": timestamp,
                "protocol": packet.protocol,
                "source": packet.source,
                "destination": packet.destination,
                "length": packet.length,
                "summary": packet.summary,
                "fields": packet.fields,
                "packet_hex": packet.packet_hex,
            }
            for index, (timestamp, packet) in enumerate(parsed)
        ]
        protocol_counts = {
            protocol: sum(packet.protocol == protocol for _, packet in parsed)
            for protocol in ("ARP", "ICMP", "TCP")
        }

        if findings:
            diagnostics.append(
                Diagnostic(
                    code="ANOMALIES_DETECTED",
                    level=DiagnosticLevel.WARNING,
                    message=f"检测到 {len(findings)} 项异常流量特征，请结合网络环境复核。",
                )
            )
        else:
            diagnostics.append(
                Diagnostic(
                    code="NO_ANOMALY_DETECTED",
                    level=DiagnosticLevel.INFO,
                    message="当前样本未达到异常流量判定阈值。",
                )
            )

        return ResultPayload(
            summary=f"已解析 {len(parsed)} 个报文，发现 {len(findings)} 项异常流量特征。",
            datasets=[self._packet_dataset(packet_rows), self._finding_dataset(findings)],
            metrics={
                "packet_count": len(parsed),
                "invalid_packet_count": len(captured) - len(parsed),
                "total_bytes": sum(packet.length for _, packet in parsed),
                "protocol_counts": protocol_counts,
                "anomaly_count": len(findings),
                "scan_threshold": data.scan_threshold,
            },
            diagnostics=diagnostics,
        )

    @staticmethod
    def _validate_input(input_data: dict) -> AnalyzerInput:
        try:
            return AnalyzerInput.model_validate(input_data)
        except ValidationError as exc:
            raise CaseInputError(
                "网络协议分析仪输入不合法",
                {"errors": exc.errors(include_context=False, include_url=False)},
            ) from exc

    @staticmethod
    def _construct(data: AnalyzerInput) -> list[dict]:
        try:
            frame = build_packet(
                protocol=data.protocol,
                source_mac=data.source_mac,
                destination_mac=data.destination_mac,
                source_ip=data.source_ip,
                destination_ip=data.destination_ip,
                source_port=data.source_port,
                destination_port=data.destination_port,
                tcp_flags=data.tcp_flags,
                arp_operation=data.arp_operation,
                payload_text=data.payload_text,
            )
        except (PacketCodecError, ValueError) as exc:
            raise CaseInputError("报文构造参数不合法", {"reason": str(exc)}) from exc
        return [{"timestamp": datetime.now(UTC).isoformat(), "packet_bytes": frame}]

    @staticmethod
    def _decode_hex(value: str, field: str) -> bytes:
        try:
            return normalize_packet_hex(value)
        except PacketCodecError as exc:
            raise CaseInputError(
                "十六进制报文格式不合法", {"field": field, "reason": str(exc)}
            ) from exc

    def _read_offline_capture(self, value: str) -> list[dict]:
        try:
            document = json.loads(value)
        except json.JSONDecodeError as exc:
            raise CaseInputError(
                "capture_packets_json 不是合法 JSON",
                {"line": exc.lineno, "column": exc.colno},
            ) from exc
        if not isinstance(document, list) or not document:
            raise CaseInputError("离线捕获记录必须是非空 JSON 数组")
        if len(document) > 1000:
            raise CaseInputError("单次最多分析 1000 条离线捕获记录")

        captured = []
        for index, item in enumerate(document):
            if isinstance(item, str):
                packet_hex = item
                timestamp = datetime.now(UTC).isoformat()
            elif isinstance(item, dict):
                packet_hex = item.get("packet_hex")
                timestamp = str(item.get("timestamp") or datetime.now(UTC).isoformat())
            else:
                raise CaseInputError(
                    "离线捕获记录元素必须是字符串或对象",
                    {"index": index},
                )
            if not isinstance(packet_hex, str):
                raise CaseInputError(
                    "离线捕获记录缺少 packet_hex 字符串",
                    {"index": index},
                )
            captured.append(
                {
                    "timestamp": timestamp,
                    "packet_bytes": self._decode_hex(
                        packet_hex, f"capture_packets_json[{index}].packet_hex"
                    ),
                }
            )
        return captured

    @staticmethod
    def _capture_live(data: AnalyzerInput) -> list[dict]:
        try:
            return capture_live_packets(
                interface=data.capture_interface,
                count=data.capture_count,
                timeout=data.capture_timeout,
            )
        except LiveCaptureUnavailableError as exc:
            raise CaseInputError("实时抓包不可用", {"reason": str(exc)}) from exc

    @staticmethod
    def _parse_captured(
        captured: list[dict],
    ) -> tuple[list[tuple[str, ParsedPacket]], list[Diagnostic]]:
        parsed: list[tuple[str, ParsedPacket]] = []
        diagnostics: list[Diagnostic] = []
        for index, item in enumerate(captured):
            try:
                parsed.append((item["timestamp"], parse_packet(item["packet_bytes"])))
            except PacketCodecError as exc:
                diagnostics.append(
                    Diagnostic(
                        code="PACKET_PARSE_FAILED",
                        level=DiagnosticLevel.ERROR,
                        message=f"第 {index + 1} 个报文解析失败：{exc}",
                        location=f"capture[{index}]",
                    )
                )
        return parsed, diagnostics

    @staticmethod
    def _packet_dataset(rows: list[dict]) -> Dataset:
        return Dataset(
            name="packet_records",
            title="抓包与解析记录",
            columns=[
                ColumnSpec(key="index", title="序号", data_type=DataType.INTEGER),
                ColumnSpec(key="timestamp", title="时间", data_type=DataType.STRING),
                ColumnSpec(key="protocol", title="协议", data_type=DataType.STRING),
                ColumnSpec(key="source", title="源", data_type=DataType.STRING),
                ColumnSpec(key="destination", title="目标", data_type=DataType.STRING),
                ColumnSpec(key="length", title="长度", data_type=DataType.INTEGER, unit="bytes"),
                ColumnSpec(key="summary", title="摘要", data_type=DataType.STRING),
                ColumnSpec(key="fields", title="解析字段", data_type=DataType.OBJECT),
                ColumnSpec(key="packet_hex", title="原始报文", data_type=DataType.STRING),
            ],
            rows=rows,
        )

    @staticmethod
    def _finding_dataset(rows: list[dict]) -> Dataset:
        return Dataset(
            name="anomaly_findings",
            title="异常流量识别结果",
            columns=[
                ColumnSpec(key="code", title="异常类型", data_type=DataType.STRING),
                ColumnSpec(key="severity", title="严重程度", data_type=DataType.STRING),
                ColumnSpec(key="source", title="来源", data_type=DataType.STRING),
                ColumnSpec(key="target", title="目标", data_type=DataType.STRING),
                ColumnSpec(key="evidence", title="判定依据", data_type=DataType.STRING),
                ColumnSpec(key="recommendation", title="处置建议", data_type=DataType.STRING),
            ],
            rows=rows,
        )


# Compatibility import: the registered v2 case is the source-code grader.
# The packet simulator above is retained only as an internal reference implementation.
from .code_grader import NetworkProtocolAnalyzerCase  # noqa: F401, F811
