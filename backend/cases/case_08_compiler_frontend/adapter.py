# -*- coding: utf-8 -*-
"""案例 8：迷你编译器前端代码评测（CaseAdapter 实现）。

评测学生提交的 Python 文件是否实现：

* ``tokenize(source) -> list[dict]`` 词法分析（Token 含 kind/lexeme/line/column）
* ``parse(source) -> {"ast": ..., "errors": [{"line","column","message"}]}`` 语法分析
* 可选合并写法 ``analyze(source) -> {"tokens","ast","errors"}``

静态部分由 :mod:`.evaluator` 完成，行为部分由 :mod:`.runtime_harness` 在基座沙箱中运行。
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

RUNTIME_RESULT_MARKER = "__AI_TUTOR_CASE8_RESULT__"

# AST 预览行数上限（学生 AST 结构未知，按通用 JSON 树展开）
AST_ROW_CAP = 300


def _flatten_ast(root: object) -> list[dict]:
    """把任意 JSON 形态的 AST 展开成「节点表」，供前端用树/图组件渲染。"""
    rows: list[dict] = []

    def add(parent: int | None, depth: int, label: str, node: object) -> int | None:
        if len(rows) >= AST_ROW_CAP:
            return None
        line = None
        if isinstance(node, dict):
            raw = node.get("line")
            if isinstance(raw, int) and not isinstance(raw, bool):
                line = raw
        rows.append({
            "node_id": len(rows) + 1,
            "parent_id": parent,
            "depth": depth,
            "label": label[:200],
            "line": line,
        })
        return len(rows)

    def walk(node: object, parent: int | None, depth: int, key: str) -> None:
        if isinstance(node, (dict, list)):
            node_id = add(parent, depth, str(key), node)
            if node_id is None:
                return
            pairs = node.items() if isinstance(node, dict) else enumerate(node)
            for raw_key, value in pairs:
                if isinstance(node, dict) and raw_key == "line":
                    continue
                label = str(raw_key) if isinstance(node, dict) else f"[{raw_key}]"
                if isinstance(value, (dict, list)):
                    walk(value, node_id, depth + 1, label)
                else:
                    add(node_id, depth + 1, f"{label} = {value}", None)
        else:
            add(parent, depth, str(node), None)

    if root is not None:
        walk(root, None, 0, "ast")
    return rows


def _error_rows(observations: dict) -> list[dict]:
    """把夹具回传的两组语法错误整理成「错误定位表」。"""
    rows: list[dict] = []
    for program, key in (("缺少右括号", "errors_paren"), ("缺少分号", "errors_semi")):
        items = observations.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            line = item.get("line")
            column = item.get("column")
            rows.append({
                "program": program,
                "line": line if isinstance(line, int) and not isinstance(line, bool) else None,
                "column": column if isinstance(column, int) and not isinstance(column, bool) else None,
                "message": str(item.get("message", ""))[:200],
            })
    return rows


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
        return sum(1 for item in self.checks if item.get("passed"))

    @property
    def pass_rate(self) -> float:
        return self.tests_passed / self.tests_total * 100 if self.tests_total else 0.0

    @property
    def earned_weight(self) -> float:
        return sum(float(item.get("weight", 0)) for item in self.checks if item.get("passed"))


class CodeSubmission(BaseModel):
    """浏览器中选择的单个 .py 文件。"""

    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=4, max_length=255, title="文件名")
    source_code: str = Field(
        min_length=1,
        max_length=500_000,
        title="Python 源代码",
        description="浏览器从所选 .py 文件中读取的 UTF-8 文本。",
    )

    @model_validator(mode="after")
    def validate_python_file(self) -> "CodeSubmission":
        if not self.filename.lower().endswith(".py"):
            raise ValueError("仅允许提交 .py 文件")
        return self


class MiniCompilerFrontendCase(CaseAdapter):
    """案例 8：评测学生实现的 MiniC 词法/语法分析器。"""

    @property
    def descriptor(self) -> CaseDescriptor:
        schema = CodeSubmission.model_json_schema()
        schema["x-ui-mode"] = "python-file"
        schema["x-accepted-extension"] = ".py"
        schema["x-max-file-bytes"] = 500_000
        return CaseDescriptor(
            case_id="compiler.mini-frontend",
            name="迷你编译器前端代码评测",
            course="编译原理",
            course_number=8,
            description=(
                "提交一个 Python 文件实现 MiniC 词法/语法分析："
                "tokenize(source) 返回带 kind/lexeme/line/column 的 Token 列表；"
                "parse(source) 返回 {'ast': 语法树, 'errors': [{'line','column','message'}]}。"
                "系统会静态检查接口与代码质量，并在隔离沙箱中用测试程序验证 Token 切分、"
                "AST 构造与语法错误定位，给出通过率与总分。"
            ),
            version="1.0.0",
            input_schema=schema,
            output_datasets=[
                "functional_tests",
                "runtime_tests",
                "ast_tree",
                "error_locations",
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
            summary = f"{submission.filename} 编译失败，请先修复 Python 语法错误后重新提交。"
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
                self._ast_dataset(runtime.observations),
                self._error_dataset(runtime.observations),
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
                "ast_rows": len(_flatten_ast(runtime.observations.get("ast"))),
                "error_rows": len(_error_rows(runtime.observations)),
                "output_truncated": runtime.run.output_truncated,
            },
            diagnostics=diagnostics,
        )

    # ------------------------------------------------------------------
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
                line[len(RUNTIME_RESULT_MARKER):]
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
        normalized = [item for item in checks if isinstance(item, dict)]
        return RuntimeEvaluation(
            run=run,
            checks=normalized,
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
            issue = report.issues[0] if report.issues else {
                "message": "Python 语法错误", "line": None
            }
            return [
                Diagnostic(
                    code="PYTHON_SYNTAX_ERROR",
                    level=DiagnosticLevel.ERROR,
                    message=issue["message"],
                    location=f"line:{issue['line']}" if issue.get("line") else None,
                )
            ]

        diagnostics: list[Diagnostic] = []
        if runtime.run.output_truncated:
            diagnostics.append(Diagnostic(
                code="OUTPUT_TRUNCATED",
                level=DiagnosticLevel.WARNING,
                message="学生程序输出超过上限已被截断，部分检查可能不准确。",
            ))
        if runtime.run.status == CodeExecutionStatus.UNAVAILABLE:
            diagnostics.append(Diagnostic(
                code="CODE_RUNNER_UNAVAILABLE",
                level=DiagnosticLevel.WARNING,
                message="代码运行沙箱当前不可用，本次仅保留静态分析评分。",
            ))
        elif runtime.run.status == CodeExecutionStatus.COMPILE_ERROR:
            diagnostics.append(Diagnostic(
                code="PYTHON_COMPILE_ERROR",
                level=DiagnosticLevel.ERROR,
                message="提交的文件未通过基座编译（py_compile），请检查语法。",
                details={"stderr": runtime.run.stderr[-1000:]},
            ))
        elif runtime.run.status == CodeExecutionStatus.TIMED_OUT:
            diagnostics.append(Diagnostic(
                code="CODE_EXECUTION_TIMEOUT",
                level=DiagnosticLevel.ERROR,
                message="学生代码运行超时，已由基座终止。",
            ))
        elif runtime.run.status == CodeExecutionStatus.INTERNAL_ERROR:
            diagnostics.append(Diagnostic(
                code="CODE_RUNNER_INTERNAL_ERROR",
                level=DiagnosticLevel.WARNING,
                message="代码运行器内部错误，本次评测结果可能不完整。",
                details={"stderr": runtime.run.stderr[-1000:]},
            ))
        elif runtime.run.status == CodeExecutionStatus.RUNTIME_ERROR:
            diagnostics.append(Diagnostic(
                code="CODE_RUNTIME_ERROR",
                level=DiagnosticLevel.ERROR,
                message="学生代码运行失败，请根据运行错误修复。",
                details={"stderr": runtime.run.stderr[-1000:]},
            ))
        elif runtime.run.status == CodeExecutionStatus.SUCCEEDED and runtime.output_valid:
            diagnostics.append(Diagnostic(
                code="SANDBOX_EXECUTION_COMPLETE",
                level=DiagnosticLevel.INFO,
                message=(
                    f"代码已在隔离沙箱中完成运行测试"
                    f"（{runtime.tests_passed}/{runtime.tests_total} 项通过）。"
                ),
                details={"observations": runtime.observations},
            ))
        elif runtime.run.status == CodeExecutionStatus.SUCCEEDED:
            diagnostics.append(Diagnostic(
                code="RUNTIME_RESULT_INVALID",
                level=DiagnosticLevel.WARNING,
                message="代码运行完成，但测试夹具未返回可识别的结构化结果。",
            ))

        failed = [c for c in runtime.checks if not c.get("passed")]
        if failed:
            diagnostics.append(Diagnostic(
                code="RUNTIME_CHECKS_FAILED",
                level=DiagnosticLevel.WARNING,
                message=f"沙箱运行中有 {len(failed)} 项检查未通过。",
                details={"failed": [c.get("check_id") for c in failed][:10]},
            ))

        risky = [issue for issue in report.issues if issue["severity"] == "warning"]
        if risky:
            diagnostics.append(Diagnostic(
                code="REVIEW_WARNINGS",
                level=DiagnosticLevel.WARNING,
                message=f"发现 {len(risky)} 项需要人工复核的代码问题。",
            ))
        return diagnostics

    # ------------------------------------------------------------------
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
        # 夹具里的 weight 用于算分，不属于该数据集的列，这里按列裁剪
        rows = [
            {
                "check_id": str(item.get("check_id", "")),
                "title": str(item.get("title", "")),
                "passed": bool(item.get("passed")),
                "evidence": str(item.get("evidence", "")),
            }
            for item in runtime.checks
            if item.get("check_id")
        ]
        if not rows:
            rows = [{
                "check_id": "RUNTIME",
                "title": "基座运行状态",
                "passed": False,
                "evidence": runtime.run.stderr or runtime.run.status.value,
            }]
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
    def _ast_dataset(observations: dict) -> Dataset:
        """学生编译器实际产出的语法树（节点表，前端可用树/图组件渲染）。"""
        rows = _flatten_ast(observations.get("ast"))
        if not rows:
            rows = [{
                "node_id": 1, "parent_id": None, "depth": 0,
                "label": "（未返回可用的 AST）", "line": None,
            }]
        return Dataset(
            name="ast_tree",
            title="学生实现产出的语法树（节点表）",
            columns=[
                ColumnSpec(key="node_id", title="节点编号", data_type=DataType.INTEGER),
                ColumnSpec(key="parent_id", title="父节点", data_type=DataType.INTEGER,
                           nullable=True),
                ColumnSpec(key="depth", title="层级", data_type=DataType.INTEGER),
                ColumnSpec(key="label", title="节点/字段", data_type=DataType.STRING),
                ColumnSpec(key="line", title="源码行号", data_type=DataType.INTEGER,
                           nullable=True),
            ],
            rows=rows,
        )

    @staticmethod
    def _error_dataset(observations: dict) -> Dataset:
        """学生编译器报出的语法错误定位（对应课程要求的"错误定位信息"）。"""
        rows = _error_rows(observations)
        if not rows:
            rows = [{
                "program": "（无）", "line": None, "column": None,
                "message": "未返回语法错误信息",
            }]
        return Dataset(
            name="error_locations",
            title="语法错误定位（来自学生实现）",
            columns=[
                ColumnSpec(key="program", title="测试程序", data_type=DataType.STRING),
                ColumnSpec(key="line", title="行号", data_type=DataType.INTEGER, nullable=True),
                ColumnSpec(key="column", title="列号", data_type=DataType.INTEGER, nullable=True),
                ColumnSpec(key="message", title="错误信息", data_type=DataType.STRING),
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
                ColumnSpec(key="line", title="行号", data_type=DataType.INTEGER, nullable=True),
                ColumnSpec(key="code", title="规则", data_type=DataType.STRING),
                ColumnSpec(key="message", title="问题", data_type=DataType.STRING),
                ColumnSpec(key="suggestion", title="建议", data_type=DataType.STRING),
            ],
            rows=report.issues,
        )
