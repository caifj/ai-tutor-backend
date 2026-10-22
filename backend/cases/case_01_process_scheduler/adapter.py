from __future__ import annotations

import json

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

from .algorithms import FCFSScheduler
from .evaluation import build_requests, reference, validate_result
from .models import ExecutionSegment, Process
from .runtime_harness import HARNESS_SOURCE, MARKER


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str = Field(min_length=4, max_length=255, title="文件名")
    source_code: str = Field(min_length=1, max_length=500_000, title="Python 源代码")

    @model_validator(mode="after")
    def validate_file(self):
        if not self.filename.lower().endswith(".py"):
            raise ValueError("请提交 .py 文件")
        if len(self.source_code.encode("utf-8")) > 500_000:
            raise ValueError("文件不得超过 500000 字节")
        return self


def dataset(name, title, fields, rows):
    return Dataset(
        name=name,
        title=title,
        columns=[ColumnSpec(key=key, title=label, data_type=kind) for key, label, kind in fields],
        rows=rows,
    )


class ProcessSchedulerCase(CaseAdapter):
    @property
    def descriptor(self):
        schema = Submission.model_json_schema()
        schema.update(
            {"x-ui-mode": "python-file", "x-accepted-extension": ".py", "x-max-file-bytes": 500_000}
        )
        return CaseDescriptor(
            case_id="os.process-scheduler",
            name="进程调度代码评测",
            course="操作系统",
            course_number=1,
            version="1.0.0",
            python_static_evaluation=True,
            description="提交实现 schedule(processes, algorithm, quantum=2) 的单个 Python 文件，"
            "或含 Process 与四个调度器类的单文件版本。评测 FCFS、非抢占 SJF、RR、"
            "非抢占优先级，展示进程指标与甘特图。桌面 GUI/系统监控另行验收。",
            input_schema=schema,
            input_template='''def schedule(processes, algorithm, quantum=2):
    """统一执行一种进程调度算法。

    processes: list[dict]
        待调度进程列表，每个字典必须包含：
        - pid: str，进程唯一标识，如 "P1"
        - arrival_time: int | float，到达就绪队列的时间，且 >= 0
        - burst_time: int | float，需要占用 CPU 的总时长，且 > 0
        - priority: int，优先级数值；数值越小表示优先级越高
    algorithm: str
        调度算法名称："fcfs"、"sjf"、"rr" 或 "priority"。
    quantum: int | float
        RR 时间片长度，必须 > 0；其他算法可忽略此参数。

    返回: dict
        必须包含 segments、process_metrics、summary 三个字段。
    """
    ...''',
            output_summary='''segments: list[dict]
  调度时间片；每项包含 pid、start、end。

process_metrics: list[dict]
  每个进程的到达、执行、等待、周转和响应指标。

summary: dict
  平均等待/周转/响应时间、CPU 利用率和总时长。''',
            output_template='''{
  "segments": [{"pid": "P1", "start": 0, "end": 2}],
  "process_metrics": [{
    "pid": "P1", "arrival_time": 0, "burst_time": 5,
    "priority": 2, "first_start_time": 0,
    "completion_time": 5, "waiting_time": 0,
    "turnaround_time": 5, "response_time": 0
  }],
  "summary": {
    "average_waiting_time": 0.0,
    "average_turnaround_time": 5.0,
    "average_response_time": 0.0,
    "cpu_utilization_percent": 100.0,
    "total_time": 5
  }
}''',
            starter_filename="case01_process_scheduler_template.py",
            starter_code='''"""课程 01：进程调度代码模板。"""

from __future__ import annotations


def schedule(processes: list[dict], algorithm: str, quantum: int | float = 2) -> dict:
    """按指定算法调度进程并返回时间线、逐进程指标和汇总指标。"""
    raise NotImplementedError("请实现 schedule 函数")
''',
            output_datasets=[
                "runtime_tests",
                "scheduling_gantt",
                "process_metrics",
                "scheduling_summary",
                "quality_scores",
                "code_issues",
            ],
        )

    async def execute(self, input_data: dict, context: ExecutionContext):
        try:
            submission = Submission.model_validate(input_data)
        except ValidationError as exc:
            raise CaseInputError(
                "代码文件输入不合法",
                {"errors": json.loads(exc.json(include_context=False, include_url=False))},
            ) from exc
        requests = build_requests()
        if context.runtime is None:
            run = PythonRunResult(
                status=CodeExecutionStatus.UNAVAILABLE,
                compile_succeeded=False,
                stderr="基座未配置代码运行沙箱",
            )
        else:
            run = await context.runtime.code_runner.run_python(
                PythonRunSpec(
                    files=[
                        CodeFile(path="student.py", content=submission.source_code),
                        CodeFile(path="case_harness.py", content=HARNESS_SOURCE),
                    ],
                    entrypoint="case_harness.py",
                    stdin=json.dumps(requests, ensure_ascii=False),
                    timeout_seconds=5,
                    memory_limit_mb=128,
                    max_output_bytes=256_000,
                )
            )
        observations, error = self._parse(run, requests)
        tests, gantt, processes, summaries = [], [], [], []
        for request in requests:
            expected = reference(request)
            observation = observations.get(request["id"], {})
            actual = observation.get("result")
            checks = validate_result(actual, expected)
            for suffix, title, (passed, evidence) in zip(
                ("schedule", "metrics", "summary"),
                ("调度时间线", "逐进程指标", "平均性能指标"),
                checks,
            ):
                detail = observation.get("error") or error
                if not passed and not detail:
                    key = {
                        "schedule": "segments",
                        "metrics": "process_metrics",
                        "summary": "summary",
                    }[suffix]
                    detail = (
                        "学生返回："
                        + json.dumps(
                            actual.get(key) if isinstance(actual, dict) else actual,
                            ensure_ascii=False,
                        )[:800]
                    )
                tests.append(
                    {
                        "check_id": request["id"] + "_" + suffix,
                        "title": request["title"] + " · " + title,
                        "passed": passed,
                        "evidence": evidence + ("；" + detail if detail else ""),
                    }
                )
            # Show only a verified schedule; never render a teacher answer as student output.
            if checks[0][0]:
                common = {"test_case": request["title"], "algorithm": request["algorithm"].upper()}
                for segment in actual["segments"]:
                    gantt.append(common | {k: segment[k] for k in ("pid", "start", "end")})
                # Derive display metrics from the returned, verified student timeline.
                display = (
                    FCFSScheduler()
                    ._build_result(
                        [Process(**p) for p in request["processes"]],
                        [
                            ExecutionSegment(**{k: segment[k] for k in ("pid", "start", "end")})
                            for segment in actual["segments"]
                        ],
                    )
                    .to_dict()
                )
                processes.extend(common | row for row in display["process_metrics"])
                summaries.append(common | display["summary"])
        passed_count = sum(row["passed"] for row in tests)
        score = round(80 * passed_count / len(tests), 2)
        s, n, b = DataType.STRING, DataType.NUMBER, DataType.BOOLEAN
        common_fields = [("test_case", "测试场景", s), ("algorithm", "算法", s)]
        metrics_labels = {
            "pid": "进程",
            "arrival_time": "到达时间",
            "burst_time": "服务时间",
            "priority": "优先级",
            "first_start_time": "首次开始时间",
            "completion_time": "完成时间",
            "waiting_time": "等待时间",
            "turnaround_time": "周转时间",
            "response_time": "响应时间",
        }
        summary_labels = {
            "average_waiting_time": "平均等待时间",
            "average_turnaround_time": "平均周转时间",
            "average_response_time": "平均响应时间",
            "cpu_utilization_percent": "模拟 CPU 利用率 (%)",
            "total_time": "总时长",
        }
        diagnostics = [
            Diagnostic(
                code="CASE1_SCOPE",
                level=DiagnosticLevel.INFO,
                message="本评分覆盖调度算法及输出契约；PyQt6、psutil、桌面绘图与数据联动需另行验收。"
                "页面指标根据已校验的学生时间线计算，学生原始指标的正确性见测试项。",
            )
        ]
        if error:
            diagnostics.append(
                Diagnostic(code="CASE1_RUNTIME_ERROR", level=DiagnosticLevel.ERROR, message=error)
            )
        summary = (
            f"{submission.filename}：调度检查 {passed_count}/{len(tests)} 通过，"
            f"案例功能得分 {score:g}/80。"
        )
        if error:
            summary += "本次评测未完整完成：" + error
        return ResultPayload(
            summary=summary,
            metrics={
                "functionality_score": score,
                "overall_score": score,
                "runtime_status": run.status.value,
                "compile_succeeded": run.compile_succeeded,
                "runtime_tests_passed": passed_count,
                "runtime_tests_total": len(tests),
                "tests_passed": passed_count,
                "tests_total": len(tests),
                "test_pass_rate": round(100 * passed_count / len(tests), 1),
                "runtime_pass_rate": round(100 * passed_count / len(tests), 1),
                "runtime_duration_ms": round(run.duration_ms, 1),
            },
            datasets=[
                dataset(
                    "runtime_tests",
                    "调度代码检查",
                    [
                        ("check_id", "检查项", s),
                        ("title", "要求", s),
                        ("passed", "通过", b),
                        ("evidence", "证据", s),
                    ],
                    tests,
                ),
                dataset(
                    "scheduling_gantt",
                    "学生代码调度甘特图",
                    common_fields + [("pid", "进程", s), ("start", "开始", n), ("end", "结束", n)],
                    gantt,
                ),
                dataset(
                    "process_metrics",
                    "逐进程指标（由已校验时间线计算）",
                    common_fields
                    + [(k, v, s if k == "pid" else n) for k, v in metrics_labels.items()],
                    processes,
                ),
                dataset(
                    "scheduling_summary",
                    "平均性能指标（由已校验时间线计算）",
                    common_fields + [(k, v, n) for k, v in summary_labels.items()],
                    summaries,
                ),
            ],
            diagnostics=diagnostics,
        )

    @staticmethod
    def _parse(run, requests):
        if run.status != CodeExecutionStatus.SUCCEEDED or run.output_truncated:
            return {}, f"运行状态 {run.status.value}；{run.stderr[-1000:]}" + (
                "；输出被截断" if run.output_truncated else ""
            )
        try:
            lines = [
                line[len(MARKER) :] for line in run.stdout.splitlines() if line.startswith(MARKER)
            ]
            if len(lines) != 1:
                raise ValueError("缺少或重复结构化报文")
            payload = json.loads(lines[0])
            if not isinstance(payload, dict):
                raise TypeError("报文必须为对象")
            if "load_error" in payload:
                raise ValueError(str(payload["load_error"])[:1000])
            rows = payload.get("results")
            if not isinstance(rows, list) or len(rows) != len(requests):
                raise ValueError("测试结果数量不完整")
            observations = {}
            for row in rows:
                if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                    raise TypeError("测试结果格式不正确")
                if row["id"] in observations:
                    raise ValueError("测试结果 ID 重复")
                if "error" in row and not isinstance(row["error"], str):
                    raise ValueError("错误信息格式不正确")
                observations[row["id"]] = row
            if set(observations) != {r["id"] for r in requests}:
                raise ValueError("测试结果 ID 不匹配")
            return observations, ""
        except (ValueError, TypeError, RecursionError) as exc:
            return {}, "沙箱报文无效：" + str(exc)
