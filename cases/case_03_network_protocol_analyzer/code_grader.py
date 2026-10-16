from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

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

from .evaluator import EvaluationReport, evaluate_python_source


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
            description=(
                "提交一个 Python 文件，逐项检查其是否实现 ARP、ICMP、TCP 报文构造与解析、"
                "流量捕获和扫描行为识别，并给出代码质量评分。"
            ),
            version="2.0.0",
            input_schema=schema,
            output_datasets=["functional_tests", "quality_scores", "code_issues"],
        )

    def execute(self, input_data: dict, context: ExecutionContext) -> ResultPayload:
        submission = self._validate_input(input_data)
        report = evaluate_python_source(submission.source_code)
        diagnostics = self._diagnostics(report)

        if not report.syntax_valid:
            summary = f"{submission.filename} 语法解析失败，请先修复语法错误后重新提交。"
        else:
            judgment = "符合核心要求" if report.overall_score >= 70 else "尚未完全符合要求"
            summary = (
                f"{submission.filename} 静态评测完成：{report.tests_passed}/"
                f"{report.tests_total} 项功能检查通过，总分 {report.overall_score:.1f}/100，"
                f"当前判断为“{judgment}”。"
            )

        return ResultPayload(
            summary=summary,
            datasets=[
                self._functional_dataset(report),
                self._quality_dataset(report),
                self._issues_dataset(report),
            ],
            metrics={
                "syntax_valid": report.syntax_valid,
                "test_pass_rate": round(report.pass_rate, 1),
                "tests_passed": report.tests_passed,
                "tests_total": report.tests_total,
                "functionality_score": round(report.functionality_score, 1),
                "pep8_score": round(report.pep8_score, 1),
                "modularity_score": round(report.modularity_score, 1),
                "overall_score": round(report.overall_score, 1),
            },
            diagnostics=diagnostics,
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
    def _diagnostics(report: EvaluationReport) -> list[Diagnostic]:
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

        diagnostics = [
            Diagnostic(
                code="STATIC_ANALYSIS_ONLY",
                level=DiagnosticLevel.INFO,
                message="为确保安全，本次评测不会运行上传代码或发起真实抓包。",
            )
        ]
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
