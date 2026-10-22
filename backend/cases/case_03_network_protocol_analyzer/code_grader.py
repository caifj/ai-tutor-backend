from __future__ import annotations

import json
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ai_tutor_backend import (
    CaseAdapter,
    CaseDescriptor,
    CaseInputError,
    CodeExecutionStatus,
    CodeFile,
    ColumnSpec,
    Dataset,
    DataType,
    Diagnostic,
    DiagnosticLevel,
    ExecutionContext,
    PythonRunResult,
    PythonRunSpec,
    ResultPayload,
)

from .runtime_harness import HARNESS_SOURCE

RUNTIME_RESULT_MARKER = "__AI_TUTOR_CASE3_RESULT__"


@dataclass
class RuntimeEvaluation:
    run: PythonRunResult
    checks: list[dict] = field(default_factory=list)
    observations: dict = field(default_factory=dict)
    output_valid: bool = False

    @property
    def tests_total(self) -> int:
        return len(self.checks)

    @property
    def tests_passed(self) -> int:
        return sum(bool(item.get("passed")) for item in self.checks)

    @property
    def pass_rate(self) -> float:
        return self.tests_passed / self.tests_total * 100 if self.tests_total else 0.0


class CodeSubmission(BaseModel):
    """API representation of the single .py file selected in the browser."""

    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=4, max_length=255, title="文件名")
    source_code: str = Field(
        min_length=1,
        max_length=500_000,
        title="Python 源代码",
        description="浏览器从所选 .py 文件中读取的 UTF-8 文本。",
    )

    @model_validator(mode="after")
    def validate_python_file(self) -> CodeSubmission:
        if not self.filename.lower().endswith(".py"):
            raise ValueError("仅允许提交 .py 文件")
        return self


class NetworkProtocolAnalyzerCase(CaseAdapter):
    @property
    def descriptor(self) -> CaseDescriptor:
        schema = CodeSubmission.model_json_schema()
        schema["x-ui-mode"] = "python-file"
        schema["x-accepted-extension"] = ".py"
        schema["x-max-file-bytes"] = 500_000
        return CaseDescriptor(
            case_id="network.protocol-analyzer",
            name="网络协议分析仪代码评测",
            course="计算机网络",
            course_number=3,
            description=(
                "提交一个 Python 文件，在隔离环境中验证 ARP、ICMP、TCP 报文构造与解析、"
                "流量捕获和扫描行为识别；通用静态测评由基座统一完成。"
            ),
            version="4.0.0",
            input_schema=schema,
            input_template='''def build_arp_packet(source_ip, target_ip):
    # 构造 ARP 请求报文。
    # source_ip: str，本机 IPv4 地址；target_ip: str，待查询的 IPv4 地址。
    # 返回: 含 Ether/ARP 层且 ARP.op=1 的报文对象。
    ...

def build_icmp_packet(source_ip, target_ip):
    # 构造 ICMP Echo Request。
    # source_ip: str，源 IPv4；target_ip: str，目标 IPv4。
    # 返回: 含 IP/ICMP 层且 ICMP.type=8 的报文对象。
    ...

def build_tcp_packet(source_ip, target_ip, target_port):
    # 构造 TCP SYN 探测报文。
    # source_ip: str，源 IPv4；target_ip: str，目标 IPv4。
    # target_port: int，目标端口，范围 1~65535。
    # 返回: 含 IP/TCP 层、dport 正确且 flags 含 "S" 的报文对象。
    ...

def capture_packets(interface=None, count=20):
    # 在限定数量/超时条件下捕获报文。
    # interface: str | None，网卡名；None 表示使用默认网卡。
    # count: int，最多捕获的报文数，须为正整数。
    # 返回: list | tuple，捕获到的报文集合。
    ...

def parse_arp_packet(packet):
    # packet: 含 ARP 层的报文对象。
    # 返回: dict，至少能体现源 IP 与目标 IP。
    ...

def parse_icmp_packet(packet):
    # packet: 含 IP/ICMP 层的报文对象。
    # 返回: dict，至少能体现 ICMP type 与 code。
    ...

def parse_tcp_packet(packet):
    # packet: 含 IP/TCP 层的报文对象。
    # 返回: dict，至少能体现源端口与目标端口。
    ...

def detect_port_scan(packets, threshold=4):
    # packets: 可迭代报文集合；只统计 TCP SYN 探测。
    # threshold: int，同一来源触发告警所需的不同目标端口数。
    # 返回: list，列出达到阈值的扫描来源或结构化告警。
    ...

def analyze_network(interface=None):
    # 统一完成抓包、解析与异常识别。
    # interface: str | None，传给 capture_packets 的网卡名。
    # 返回: dict，包含 packet_records 与 anomaly_findings。
    ...''',
            output_summary='''packet_records: list[dict]
  结构化抓包记录，包含协议、通信端点、端口或协议字段。

anomaly_findings: list[dict]
  异常流量识别结果，端口扫描需给出来源和目标端口集合。''',
            output_template='''{
  "packet_records": [{
    "protocol": "TCP", "source_ip": "10.0.0.1",
    "target_ip": "10.0.0.2", "source_port": 40000,
    "target_port": 443, "flags": "S"
  }],
  "anomaly_findings": [{
    "type": "TCP_SYN_PORT_SCAN", "source": "10.0.0.1",
    "distinct_ports": [21, 22, 80, 443]
  }]
}''',
            starter_filename="case03_network_protocol_analyzer_template.py",
            starter_code='''"""课程 03：网络协议分析仪代码模板。"""

from __future__ import annotations

from scapy.all import ARP, ICMP, IP, TCP, Ether, sniff


def build_arp_packet(source_ip: str, target_ip: str):
    """构造 ARP 请求报文。"""
    raise NotImplementedError("请实现 ARP 报文构造")


def build_icmp_packet(source_ip: str, target_ip: str):
    """构造 ICMP Echo Request 报文。"""
    raise NotImplementedError("请实现 ICMP 报文构造")


def build_tcp_packet(source_ip: str, target_ip: str, target_port: int):
    """构造 TCP SYN 探测报文。"""
    raise NotImplementedError("请实现 TCP 报文构造")


def capture_packets(interface: str | None = None, count: int = 20):
    """在限定数量和超时条件下捕获报文。"""
    raise NotImplementedError("请实现有限抓包")


def parse_arp_packet(packet) -> dict:
    """解析 ARP 报文的地址与操作字段。"""
    raise NotImplementedError("请实现 ARP 报文解析")


def parse_icmp_packet(packet) -> dict:
    """解析 ICMP 报文的端点、类型与代码。"""
    raise NotImplementedError("请实现 ICMP 报文解析")


def parse_tcp_packet(packet) -> dict:
    """解析 TCP 报文的端口与标志位。"""
    raise NotImplementedError("请实现 TCP 报文解析")


def detect_port_scan(packets, threshold: int = 4) -> list:
    """识别同一来源访问多个目标端口的 SYN 扫描。"""
    raise NotImplementedError("请实现端口扫描识别")


def analyze_network(interface: str | None = None) -> dict:
    """统一执行抓包、解析和异常识别。"""
    raise NotImplementedError("请实现结构化分析入口")
''',
            output_datasets=[
                "runtime_tests",
                "runtime_packets",
                "runtime_observations",
                "quality_scores",
                "code_issues",
            ],
            python_static_evaluation=True,
        )

    async def execute(self, input_data: dict, context: ExecutionContext) -> ResultPayload:
        submission = self._validate_input(input_data)
        runtime = await self._evaluate_runtime(submission, context)
        diagnostics = self._diagnostics(runtime)

        runtime_affects_score = runtime.run.status in {
            CodeExecutionStatus.SUCCEEDED,
            CodeExecutionStatus.COMPILE_ERROR,
            CodeExecutionStatus.RUNTIME_ERROR,
            CodeExecutionStatus.TIMED_OUT,
        }
        functionality_score = runtime.pass_rate / 100 * 80 if runtime_affects_score else 0.0

        if runtime.run.status == CodeExecutionStatus.COMPILE_ERROR:
            summary = f"{submission.filename} 编译失败，请先修复语法错误后重新提交。"
        else:
            judgment = "符合案例运行要求" if functionality_score >= 64 else "尚未完全符合要求"
            if runtime.output_valid:
                execution_summary = f"运行测试 {runtime.tests_passed}/{runtime.tests_total} 项通过"
            else:
                execution_summary = f"运行状态 {runtime.run.status.value}"
            summary = (
                f"{submission.filename} 案例评测完成：{execution_summary}，案例功能得分 "
                f"{functionality_score:.1f}/80，当前判断为“{judgment}”。"
            )

        return ResultPayload(
            summary=summary,
            datasets=[
                self._runtime_dataset(runtime),
                self._runtime_packets_dataset(runtime),
                self._runtime_observations_dataset(runtime),
            ],
            metrics={
                "functionality_score": round(functionality_score, 1),
                "overall_score": round(functionality_score, 1),
                "compile_succeeded": runtime.run.compile_succeeded,
                "runtime_status": runtime.run.status.value,
                "runtime_duration_ms": round(runtime.run.duration_ms, 1),
                "runtime_tests_passed": runtime.tests_passed,
                "runtime_tests_total": runtime.tests_total,
                "runtime_pass_rate": round(runtime.pass_rate, 1),
            },
            diagnostics=diagnostics,
        )

    @staticmethod
    async def _evaluate_runtime(
        submission: CodeSubmission,
        context: ExecutionContext,
    ) -> RuntimeEvaluation:
        if context.runtime is None:
            return RuntimeEvaluation(
                run=PythonRunResult(
                    status=CodeExecutionStatus.UNAVAILABLE,
                    compile_succeeded=False,
                    stderr="执行上下文未提供代码运行器",
                )
            )
        run = await context.runtime.code_runner.run_python(
            PythonRunSpec(
                files=[
                    CodeFile(path="student.py", content=submission.source_code),
                    CodeFile(path="case_harness.py", content=HARNESS_SOURCE),
                ],
                entrypoint="case_harness.py",
                timeout_seconds=5,
                memory_limit_mb=128,
                max_output_bytes=128_000,
            )
        )
        if run.status != CodeExecutionStatus.SUCCEEDED:
            return RuntimeEvaluation(run=run)
        marker_line = next(
            (
                line[len(RUNTIME_RESULT_MARKER) :]
                for line in reversed(run.stdout.splitlines())
                if line.startswith(RUNTIME_RESULT_MARKER)
            ),
            None,
        )
        if marker_line is None:
            return RuntimeEvaluation(run=run)
        try:
            payload = json.loads(marker_line)
        except json.JSONDecodeError:
            return RuntimeEvaluation(run=run)
        checks = payload.get("checks")
        observations = payload.get("observations")
        if not isinstance(checks, list) or not isinstance(observations, dict):
            return RuntimeEvaluation(run=run)
        normalized_checks = [item for item in checks if isinstance(item, dict)]
        return RuntimeEvaluation(
            run=run,
            checks=normalized_checks,
            observations=observations,
            output_valid=True,
        )

    @staticmethod
    def _validate_input(input_data: dict) -> CodeSubmission:
        try:
            return CodeSubmission.model_validate(input_data)
        except ValidationError as exc:
            raise CaseInputError(
                "代码文件输入不合法",
                {"errors": exc.errors(include_context=False, include_url=False)},
            ) from exc

    @staticmethod
    def _diagnostics(runtime: RuntimeEvaluation) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        if runtime.run.status == CodeExecutionStatus.UNAVAILABLE:
            diagnostics.append(
                Diagnostic(
                    code="CODE_RUNNER_UNAVAILABLE",
                    level=DiagnosticLevel.WARNING,
                    message="代码运行沙箱当前不可用，无法完成案例功能测评。",
                )
            )
        elif runtime.run.status == CodeExecutionStatus.COMPILE_ERROR:
            diagnostics.append(
                Diagnostic(
                    code="CODE_COMPILE_ERROR",
                    level=DiagnosticLevel.ERROR,
                    message="学生代码编译失败，请先修复语法错误。",
                    details={"stderr": runtime.run.stderr[-1000:]},
                )
            )
        elif runtime.run.status == CodeExecutionStatus.TIMED_OUT:
            diagnostics.append(
                Diagnostic(
                    code="CODE_EXECUTION_TIMEOUT",
                    level=DiagnosticLevel.ERROR,
                    message="学生代码运行超时，已由基座终止。",
                )
            )
        elif runtime.run.status == CodeExecutionStatus.RUNTIME_ERROR:
            diagnostics.append(
                Diagnostic(
                    code="CODE_RUNTIME_ERROR",
                    level=DiagnosticLevel.ERROR,
                    message="学生代码运行失败，请根据运行错误修复。",
                    details={"stderr": runtime.run.stderr[-1000:]},
                )
            )
        elif runtime.run.status == CodeExecutionStatus.SUCCEEDED and runtime.output_valid:
            diagnostics.append(
                Diagnostic(
                    code="SANDBOX_EXECUTION_COMPLETE",
                    level=DiagnosticLevel.INFO,
                    message="代码已在隔离沙箱中使用模拟报文完成运行测试，未访问真实网卡。",
                )
            )
        elif runtime.run.status == CodeExecutionStatus.SUCCEEDED:
            diagnostics.append(
                Diagnostic(
                    code="RUNTIME_RESULT_INVALID",
                    level=DiagnosticLevel.WARNING,
                    message="代码运行完成，但测试夹具未返回可识别的结构化结果。",
                )
            )
        return diagnostics

    @staticmethod
    def _runtime_dataset(runtime: RuntimeEvaluation) -> Dataset:
        rows = runtime.checks
        if not rows:
            rows = [
                {
                    "check_id": "RUNTIME",
                    "title": "基座运行状态",
                    "passed": False,
                    "evidence": runtime.run.stderr or runtime.run.status.value,
                }
            ]
        return Dataset(
            name="runtime_tests",
            title="隔离运行测试",
            columns=[
                ColumnSpec(key="check_id", title="检查项", data_type=DataType.STRING),
                ColumnSpec(key="title", title="要求", data_type=DataType.STRING),
                ColumnSpec(key="passed", title="通过", data_type=DataType.BOOLEAN),
                ColumnSpec(key="evidence", title="运行证据", data_type=DataType.STRING),
            ],
            rows=rows,
        )

    @staticmethod
    def _runtime_observations_dataset(runtime: RuntimeEvaluation) -> Dataset:
        return Dataset(
            name="runtime_observations",
            title="运行输出数据",
            columns=[
                ColumnSpec(key="name", title="数据项", data_type=DataType.STRING),
                ColumnSpec(key="value", title="输出值", data_type=DataType.STRING),
            ],
            rows=[
                {
                    "name": str(name),
                    "value": json.dumps(value, ensure_ascii=False, default=str),
                }
                for name, value in sorted(runtime.observations.items())
            ],
        )

    @staticmethod
    def _runtime_packets_dataset(runtime: RuntimeEvaluation) -> Dataset:
        packet_checks = {
            "BUILD_ARP": ("ARP", "构造"),
            "BUILD_ICMP": ("ICMP", "构造"),
            "BUILD_TCP": ("TCP", "构造"),
            "PARSE_ARP": ("ARP", "解析"),
            "PARSE_ICMP": ("ICMP", "解析"),
            "PARSE_TCP": ("TCP", "解析"),
        }
        rows = []
        for check_id, (protocol, stage) in packet_checks.items():
            value = runtime.observations.get(check_id)
            if not isinstance(value, dict):
                continue
            source = value.get("source", value.get("source_ip", value.get("psrc")))
            target = value.get("target", value.get("target_ip", value.get("pdst")))
            rows.append(
                {
                    "protocol": protocol,
                    "stage": stage,
                    "source": source,
                    "target": target,
                    "details": json.dumps(value, ensure_ascii=False, default=str),
                }
            )
        return Dataset(
            name="runtime_packets",
            title="基座返回的模拟报文",
            columns=[
                ColumnSpec(key="protocol", title="协议", data_type=DataType.STRING),
                ColumnSpec(key="stage", title="阶段", data_type=DataType.STRING),
                ColumnSpec(key="source", title="源地址", data_type=DataType.STRING, nullable=True),
                ColumnSpec(
                    key="target", title="目标地址", data_type=DataType.STRING, nullable=True
                ),
                ColumnSpec(key="details", title="报文字段", data_type=DataType.STRING),
            ],
            rows=rows,
        )
