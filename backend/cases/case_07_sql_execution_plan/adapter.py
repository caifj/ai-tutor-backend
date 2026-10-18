"""案例7：SQL 执行计划可视化工具代码评测（案例适配器）。

评测学生提交的 Python 代码，检查是否实现：
- SQL 执行计划解析器（parse_explain）
- B+ 树构建（build_btree）
- B+ 树查找（lookup）
"""

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

from .evaluator import EvaluationReport, evaluate_python_source
from .runtime_harness import HARNESS_SOURCE

RUNTIME_RESULT_MARKER = "__AI_TUTOR_CASE7_RESULT__"


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


class SqlExecutionPlanCase(CaseAdapter):
    """案例7：评测学生实现的 SQL 执行计划解析和 B+ 树索引代码。"""

    @property
    def descriptor(self) -> CaseDescriptor:
        schema = CodeSubmission.model_json_schema()
        schema["x-ui-mode"] = "python-file"
        schema["x-accepted-extension"] = ".py"
        schema["x-max-file-bytes"] = 500_000
        return CaseDescriptor(
            case_id="database.sql-execution-plan",
            name="SQL执行计划可视化工具代码评测",
            course="数据库系统",
            course_number=7,
            description=(
                "提交一个 Python 文件，逐项检查其是否实现 SQL 执行计划解析、"
                "索引使用分析、全表扫描检测、B+ 树构建与查找，并给出代码质量评分。"
            ),
            version="3.0.0",
            input_schema=schema,
            output_datasets=[
                "functional_tests",
                "runtime_tests",
                "quality_scores",
                "code_issues",
            ],
        )

    async def execute(self, input_data: dict, context: ExecutionContext) -> ResultPayload:
        submission = self._validate_input(input_data)
        report = evaluate_python_source(submission.source_code)
        runtime = await self._evaluate_runtime(submission, context)
        diagnostics = self._diagnostics(report, runtime)

        runtime_functionality_score = runtime.pass_rate / 100 * 80
        runtime_affects_score = runtime.run.status in {
            CodeExecutionStatus.SUCCEEDED,
            CodeExecutionStatus.RUNTIME_ERROR,
            CodeExecutionStatus.TIMED_OUT,
        }
        functionality_score = report.functionality_score
        if report.syntax_valid and runtime_affects_score:
            functionality_score = (report.functionality_score + runtime_functionality_score) / 2
        overall_score = min(
            100.0,
            functionality_score + report.pep8_score + report.modularity_score,
        )

        if not report.syntax_valid:
            summary = f"{submission.filename} 编译失败，请先修复语法错误后重新提交。"
        else:
            judgment = "符合核心要求" if overall_score >= 70 else "尚未完全符合要求"
            if runtime.output_valid:
                execution_summary = (
                    f"运行测试 {runtime.tests_passed}/{runtime.tests_total} 项通过"
                )
            else:
                execution_summary = f"运行状态 {runtime.run.status.value}"
            summary = (
                f"{submission.filename} 评测完成：静态检查 {report.tests_passed}/"
                f"{report.tests_total} 项通过，{execution_summary}，总分 {overall_score:.1f}/100，"
                f"当前判断为“{judgment}”。"
            )

        return ResultPayload(
            summary=summary,
            datasets=[
                self._functional_dataset(report),
                self._runtime_dataset(runtime),
                self._quality_dataset(report),
                self._issues_dataset(report),
            ],
            metrics={
                "syntax_valid": report.syntax_valid,
                "test_pass_rate": round(report.pass_rate, 1),
                "tests_passed": report.tests_passed,
                "tests_total": report.tests_total,
                "functionality_score": round(functionality_score, 1),
                "pep8_score": round(report.pep8_score, 1),
                "modularity_score": round(report.modularity_score, 1),
                "overall_score": round(overall_score, 1),
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
    def _diagnostics(
        report: EvaluationReport,
        runtime: RuntimeEvaluation,
    ) -> list[Diagnostic]:
        if not report.syntax_valid:
            issue = report.issues[0]
            return [
                Diagnostic(
                    code="PYTHON_SYNTAX_ERROR",
                    level=DiagnosticLevel.ERROR,
                    message=issue["message"],
                    location=f"line:{issue['line']}" if issue["line"] else None,
                )
            ]

        diagnostics: list[Diagnostic] = []
        if runtime.run.status == CodeExecutionStatus.UNAVAILABLE:
            diagnostics.append(
                Diagnostic(
                    code="CODE_RUNNER_UNAVAILABLE",
                    level=DiagnosticLevel.WARNING,
                    message="代码运行沙箱当前不可用，本次仅保留静态分析评分。",
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
                    message="代码已在隔离沙箱中完成运行测试。",
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
        risky = [issue for issue in report.issues if issue["severity"] == "warning"]
        if risky:
            diagnostics.append(
                Diagnostic(
                    code="REVIEW_WARNINGS",
                    level=DiagnosticLevel.WARNING,
                    message=f"发现 {len(risky)} 项需要人工复核的代码问题。",
                )
            )
        return diagnostics

    @staticmethod
    def _functional_dataset(report: EvaluationReport) -> Dataset:
        return Dataset(
            name="functional_tests",
            title="功能检查明细",
            columns=[
                ColumnSpec(key="check_id", title="检查项", data_type=DataType.STRING),
                ColumnSpec(key="title", title="要求", data_type=DataType.STRING),
                ColumnSpec(key="passed", title="通过", data_type=DataType.BOOLEAN),
                ColumnSpec(key="weight", title="分值", data_type=DataType.NUMBER),
                ColumnSpec(key="earned", title="得分", data_type=DataType.NUMBER),
                ColumnSpec(key="evidence", title="代码证据", data_type=DataType.STRING),
                ColumnSpec(key="suggestion", title="改进建议", data_type=DataType.STRING),
            ],
            rows=report.functional_checks,
        )

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
    def _quality_dataset(report: EvaluationReport) -> Dataset:
        return Dataset(
            name="quality_scores",
            title="代码质量评分",
            columns=[
                ColumnSpec(key="dimension", title="维度", data_type=DataType.STRING),
                ColumnSpec(key="score", title="得分", data_type=DataType.NUMBER),
                ColumnSpec(key="max_score", title="满分", data_type=DataType.NUMBER),
                ColumnSpec(key="summary", title="结论", data_type=DataType.STRING),
                ColumnSpec(key="details", title="评分依据", data_type=DataType.STRING),
            ],
            rows=report.quality_scores,
        )

    @staticmethod
    def _issues_dataset(report: EvaluationReport) -> Dataset:
        return Dataset(
            name="code_issues",
            title="代码问题与建议",
            columns=[
                ColumnSpec(key="severity", title="级别", data_type=DataType.STRING),
                ColumnSpec(
                    key="line",
                    title="行号",
                    data_type=DataType.INTEGER,
                    nullable=True,
                ),
                ColumnSpec(key="code", title="规则", data_type=DataType.STRING),
                ColumnSpec(key="message", title="问题", data_type=DataType.STRING),
                ColumnSpec(key="suggestion", title="建议", data_type=DataType.STRING),
            ],
            rows=report.issues,
        )
