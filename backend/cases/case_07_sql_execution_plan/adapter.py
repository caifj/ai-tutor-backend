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
                "提交一个 Python 文件，在隔离环境中验证 SQL 执行计划解析、索引使用分析、"
                "全表扫描检测、B+ 树构建与查找；通用静态测评由基座统一完成。"
            ),
            version="4.0.0",
            input_schema=schema,
            input_template='''def parse_explain(plan_text):
    # 解析 MySQL EXPLAIN 或 PostgreSQL 文本执行计划。
    # plan_text: str，多行执行计划原文，每行描述一个计划节点。
    # 返回: dict，包含 nodes、index_usage、full_scan_findings。
    ...

def build_btree(keys, order=3):
    # 根据键值集合构建可查找的 B+ 树结构。
    # keys: list[int]，需要写入索引的键；应排序并处理重复值。
    # order: int，B+ 树阶数，表示单节点最大分支能力，且 >= 3。
    # 返回: 树对象或等价结构，供 lookup 使用。
    ...

def lookup(tree, key):
    # 在已构建的 B+ 树中查找键并展示访问路径。
    # tree: build_btree 的返回值；key: int，待查找的目标键。
    # 返回: list，按访问顺序列出经过的节点，命中结果需包含 key。
    ...''',
            output_summary='''nodes: list[dict]
  执行计划节点，包含引擎、表、操作、索引和估算行数。

index_usage / full_scan_findings: list
  索引使用情况与全表扫描问题。

lookup(...) -> list
  按访问顺序返回 B+ 树查找路径。''',
            output_template='''{
  "nodes": [{
    "engine": "mysql", "table": "orders",
    "operation": "ALL", "index": None,
    "estimated_rows": 1200, "raw": "..."
  }],
  "index_usage": [],
  "full_scan_findings": [{
    "table": "orders", "operation": "ALL",
    "estimated_rows": 1200, "suggestion": "..."
  }]
}

lookup(tree, 25) -> [[20, 35], [25, 30], [25, 30]]''',
            starter_filename="case07_sql_execution_plan_template.py",
            starter_code='''"""课程 07：SQL 执行计划与 B+ 树代码模板。"""

from __future__ import annotations


def parse_explain(plan_text: str) -> dict:
    """解析执行计划并返回节点、索引使用和全表扫描结果。"""
    raise NotImplementedError("请实现执行计划解析")


def build_btree(keys: list[int], order: int = 3):
    """根据键值列表和阶数构建 B+ 树或等价结构。"""
    raise NotImplementedError("请实现 B+ 树构建")


def lookup(tree, key: int) -> list:
    """查找目标键并按顺序返回访问节点路径。"""
    raise NotImplementedError("请实现 B+ 树查找")
''',
            output_datasets=[
                "runtime_tests",
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
