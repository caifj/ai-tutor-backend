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

RUNTIME_RESULT_MARKER = "__AI_TUTOR_CASE5_RESULT__"


@dataclass
class RuntimeEvaluation:
    run: PythonRunResult
    checks: list[dict] = field(default_factory=list)
    observations: dict = field(default_factory=dict)
    output_valid: bool = False
    load_error: str | None = None

    @property
    def tests_total(self) -> int:
        return len(self.checks)

    @property
    def tests_passed(self) -> int:
        return sum(bool(item.get("passed")) for item in self.checks)

    @property
    def pass_rate(self) -> float:
        return self.tests_passed / self.tests_total * 100 if self.tests_total else 0.0

    @property
    def curve(self) -> list[dict]:
        value = self.observations.get("curve")
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


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


class AlgorithmComplexityAnalyzerCase(CaseAdapter):
    @property
    def descriptor(self) -> CaseDescriptor:
        schema = CodeSubmission.model_json_schema()
        schema["x-ui-mode"] = "python-file"
        schema["x-accepted-extension"] = ".py"
        schema["x-max-file-bytes"] = 500_000
        return CaseDescriptor(
            case_id="algorithm.complexity-analyzer",
            name="算法复杂度分析平台",
            course="数据结构与算法",
            course_number=5,
            description=(
                "提交一个 Python 文件，在隔离沙箱中运行排序与查找算法、按不同数据规模计时，"
                "回传时间-规模数据用于绘制复杂度曲线；通用静态测评由基座统一完成。"
            ),
            version="5.0.0",
            input_schema=schema,
            output_datasets=[
                "runtime_tests",
                "runtime_curve",
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
                self._runtime_curve_dataset(runtime),
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
                timeout_seconds=8,
                memory_limit_mb=128,
                max_output_bytes=128_000,
            )
        )
        if run.status != CodeExecutionStatus.SUCCEEDED:
            return RuntimeEvaluation(run=run)
        marker_line = next(
            (
                line[line.rindex(RUNTIME_RESULT_MARKER) + len(RUNTIME_RESULT_MARKER) :]
                for line in reversed(run.stdout.splitlines())
                if RUNTIME_RESULT_MARKER in line
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
        load_error = payload.get("load_error")
        return RuntimeEvaluation(
            run=run,
            checks=normalized_checks,
            observations=observations,
            output_valid=True,
            load_error=load_error if isinstance(load_error, str) else None,
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
                    message="学生代码运行超时，已由基座终止；请检查算法是否存在死循环或过慢规模。",
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
            if runtime.load_error:
                diagnostics.append(
                    Diagnostic(
                        code="STUDENT_CODE_LOAD_ERROR",
                        level=DiagnosticLevel.WARNING,
                        message=(f"学生代码在加载阶段抛出异常，算法未能运行：{runtime.load_error}"),
                    )
                )
            diagnostics.append(
                Diagnostic(
                    code="SANDBOX_EXECUTION_COMPLETE",
                    level=DiagnosticLevel.INFO,
                    message="代码已在隔离沙箱中以样例数据完成排序/查找运行测试与计时，未访问真实文件系统或网络。",
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
                    "evidence": runtime.load_error
                    or runtime.run.stderr
                    or runtime.run.status.value,
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
    def _runtime_curve_dataset(runtime: RuntimeEvaluation) -> Dataset:
        return Dataset(
            name="runtime_curve",
            title="运行时间-规模曲线",
            columns=[
                ColumnSpec(key="algorithm_name", title="算法", data_type=DataType.STRING),
                ColumnSpec(key="size", title="数据规模", data_type=DataType.INTEGER),
                ColumnSpec(
                    key="time_seconds",
                    title="运行耗时",
                    data_type=DataType.NUMBER,
                    unit="s",
                ),
            ],
            rows=runtime.curve,
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
                if name != "curve"
            ],
        )
