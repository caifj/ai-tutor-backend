"""案例2：虚拟内存分页模拟器代码评测（案例适配器）。

评测方式为**静态检测**，不运行学生代码：

1. 用基座自带的参考分页模拟器（:mod:`.paging_reference`）跑一遍固定页面访问序列，
   得到“物理内存页框数 → 缺页率”的对应关系与缺页率变化曲线，作为标准答案数据返回；
2. 用 AST 静态分析（:mod:`.evaluator`）逐项检查学生是否实现了页表管理、地址转换、
   缺页中断处理、FIFO / LRU / OPT 三种置换算法、缺页率统计以及多档内存扫描；
3. 把案例功能分写入 metrics["overall_score"]（满分 80）。

PEP8 规范与模块化程度由基座统一评估：描述符声明 ``python_static_evaluation = True`` 后，
``ai_tutor_backend.service`` 会自动注入 ``quality_scores``、``code_issues`` 两个数据集，
并把案例功能分与基座质量分相加得到 100 分制的总分，本案例不重复实现这两项。
"""

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

from .evaluator import FUNCTIONALITY_MAX_SCORE, EvaluationReport, evaluate_python_source
from .paging_reference import (
    ALGORITHM_FIFO,
    ALGORITHM_LRU,
    ALGORITHM_OPT,
    FRAME_COUNT_RANGE,
    REFERENCE_PAGE_SPAN,
    REFERENCE_SEQUENCE,
    TIMELINE_ALGORITHM,
    TIMELINE_FRAME_COUNT,
    FaultRateSample,
    average_fault_rates,
    best_algorithm,
    fault_rate_curve,
    find_belady_anomaly,
    occupancy_timeline,
)

#: 供外部（如自动校对）引用本案例数据集名称的常量。
CURVE_DATASET_NAME = "fault_rate_curve"
TABLE_DATASET_NAME = "frame_fault_rate_table"
TIMELINE_DATASET_NAME = "frame_occupancy_timeline"
ISSUES_DATASET_NAME = "paging_issues"


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


def _sample_row(sample: FaultRateSample) -> dict:
    return {
        "algorithm_name": sample.algorithm,
        "frame_count": sample.frame_count,
        "page_faults": sample.page_faults,
        "frame_hits": sample.frame_hits,
        "reference_length": sample.reference_length,
        "page_fault_rate": sample.page_fault_rate,
    }


def _curve_row(sample: FaultRateSample) -> dict:
    return {
        "algorithm_name": sample.algorithm,
        "frame_count": sample.frame_count,
        "page_fault_rate": sample.page_fault_rate,
    }


class VirtualMemoryPagingCase(CaseAdapter):
    """案例2：评测学生实现的虚拟内存分页模拟器，并输出缺页率基准曲线。"""

    @property
    def descriptor(self) -> CaseDescriptor:
        schema = CodeSubmission.model_json_schema()
        schema["x-ui-mode"] = "python-file"
        schema["x-accepted-extension"] = ".py"
        schema["x-max-file-bytes"] = 500_000
        return CaseDescriptor(
            case_id="os.virtual-memory-paging",
            name="虚拟内存分页模拟器代码评测",
            course="操作系统",
            course_number=2,
            description=(
                "提交一个 Python 文件，逐项检查其是否实现页表管理、逻辑地址到物理地址的转换、"
                "缺页中断处理、FIFO / LRU / OPT 三种页面置换算法、缺页率统计，"
                "以及多档内存页框数扫描；同时输出物理内存页框数与缺页率的对应关系和变化曲线。"
                "PEP8 与模块化由基座统一评估。"
            ),
            version="3.0.0",
            input_schema=schema,
            output_datasets=[
                "functional_tests",
                ISSUES_DATASET_NAME,
                TABLE_DATASET_NAME,
                CURVE_DATASET_NAME,
                TIMELINE_DATASET_NAME,
            ],
            python_static_evaluation=True,
        )

    def execute(self, input_data: dict, context: ExecutionContext) -> ResultPayload:
        submission = self._validate_input(input_data)
        report = evaluate_python_source(submission.source_code)
        samples = fault_rate_curve()
        averages = average_fault_rates()
        best_name, best_rate = best_algorithm()
        anomaly = find_belady_anomaly(samples)

        if not report.syntax_valid:
            summary = (
                f"{submission.filename} 语法解析失败，请先修复语法错误后重新提交；"
                "语法通过后基座会继续完成 PEP8 与模块化评分。"
            )
        else:
            judgment = (
                "符合核心要求" if report.overall_score >= FUNCTIONALITY_MAX_SCORE * 0.875 else "尚未完全符合要求"
            )
            summary = (
                f"{submission.filename} 静态评测完成：{report.tests_passed}/"
                f"{report.tests_total} 项功能检查通过，案例功能分 "
                f"{report.overall_score:.1f}/{FUNCTIONALITY_MAX_SCORE:.0f}，"
                f"当前判断为“{judgment}”。参考序列含 {len(REFERENCE_SEQUENCE)} 次访问、"
                f"{REFERENCE_PAGE_SPAN} 个逻辑页；在 {FRAME_COUNT_RANGE[0]} ~ "
                f"{FRAME_COUNT_RANGE[-1]} 页框全区间内，{best_name} 的平均缺页率最低"
                f"（{best_rate}%）。"
            )
            if anomaly is not None:
                anomaly_frames, anomaly_fifo, anomaly_lru = anomaly
                summary += (
                    f" 注意：{anomaly_frames} 页框时 FIFO 缺页率 {anomaly_fifo}% 反而低于 "
                    f"LRU 的 {anomaly_lru}%，这正是 Belady 异常。"
                )

        return ResultPayload(
            summary=summary,
            datasets=[
                self._functional_dataset(report),
                self._issues_dataset(report),
                self._fault_rate_table_dataset(samples),
                self._fault_rate_curve_dataset(samples),
                self._timeline_dataset(),
            ],
            metrics=self._metrics(report, samples, averages, best_name, best_rate, anomaly),
            diagnostics=self._diagnostics(report, samples, anomaly),
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
    def _metrics(
        report: EvaluationReport,
        samples: tuple[FaultRateSample, ...],
        averages: dict[str, float],
        best_name: str,
        best_rate: float,
        anomaly: tuple[int, float, float] | None,
    ) -> dict:
        """案例指标；PEP8、模块化与 100 分制总分由基座在服务层追加。"""

        metrics: dict = {
            "test_pass_rate": round(report.pass_rate, 1),
            "tests_passed": report.tests_passed,
            "tests_total": report.tests_total,
            "functionality_score": round(report.functionality_score, 1),
            "overall_score": round(report.overall_score, 1),
            "reference_sequence_length": len(REFERENCE_SEQUENCE),
            "reference_page_span": REFERENCE_PAGE_SPAN,
            "frame_count_min": FRAME_COUNT_RANGE[0],
            "frame_count_max": FRAME_COUNT_RANGE[-1],
            "curve_sample_count": len(samples),
            "best_algorithm": best_name,
            "best_algorithm_average_fault_rate": best_rate,
        }
        for algorithm, rate in averages.items():
            metrics[f"{algorithm.lower()}_average_fault_rate"] = rate
        if anomaly is not None:
            metrics["belady_anomaly_frame_count"] = anomaly[0]
        return metrics

    @staticmethod
    def _diagnostics(
        report: EvaluationReport,
        samples: tuple[FaultRateSample, ...],
        anomaly: tuple[int, float, float] | None,
    ) -> list[Diagnostic]:
        if not report.syntax_valid:
            # 语法错误由基座统一报告为 PYTHON_SYNTAX_ERROR，这里不重复。
            return [
                Diagnostic(
                    code="STATIC_ANALYSIS_ONLY",
                    level=DiagnosticLevel.INFO,
                    message="为保证安全，本次评测不运行上传代码，仅做 AST 静态分析。",
                )
            ]

        diagnostics = [
            Diagnostic(
                code="STATIC_ANALYSIS_ONLY",
                level=DiagnosticLevel.INFO,
                message="为保证安全，本次评测不运行上传代码，仅做 AST 静态分析。",
            ),
            Diagnostic(
                code="REFERENCE_PAGING_DATA",
                level=DiagnosticLevel.INFO,
                message=(
                    f"已用参考模拟器生成 {len(samples)} 组基准数据，"
                    "可对照自查各内存页框数下的缺页率是否一致。"
                ),
                details={
                    "sequence_length": len(REFERENCE_SEQUENCE),
                    "algorithms": [ALGORITHM_FIFO, ALGORITHM_LRU, ALGORITHM_OPT],
                    "frame_counts": list(FRAME_COUNT_RANGE),
                },
            ),
        ]

        if anomaly is not None:
            anomaly_frames, anomaly_fifo, anomaly_lru = anomaly
            diagnostics.append(
                Diagnostic(
                    code="BELADY_ANOMALY",
                    level=DiagnosticLevel.INFO,
                    message=(
                        f"{anomaly_frames} 页框时 FIFO 缺页率 {anomaly_fifo}% 低于 LRU 的 "
                        f"{anomaly_lru}%，出现 Belady 异常，说明两种置换策略确实被分别实现。"
                    ),
                    details={
                        "frame_count": anomaly_frames,
                        "fifo_fault_rate": anomaly_fifo,
                        "lru_fault_rate": anomaly_lru,
                    },
                )
            )

        if not report.check("FRAME_SWEEP")["passed"]:
            diagnostics.append(
                Diagnostic(
                    code="MISSING_FRAME_SWEEP",
                    level=DiagnosticLevel.WARNING,
                    message="提交的代码未扫描多档内存页框数，页面暂时无法自行输出缺页率曲线。",
                    details={"suggestion": report.check("FRAME_SWEEP")["suggestion"]},
                )
            )

        risky = [issue for issue in report.issues if issue["severity"] in {"error", "warning"}]
        if risky:
            diagnostics.append(
                Diagnostic(
                    code="REVIEW_WARNINGS",
                    level=DiagnosticLevel.WARNING,
                    message=f"发现 {len(risky)} 项需要人工复核的分页实现问题。",
                )
            )
        return diagnostics

    @staticmethod
    def _functional_dataset(report: EvaluationReport) -> Dataset:
        return Dataset(
            name="functional_tests",
            title="分页模拟器功能检查",
            columns=[
                ColumnSpec(key="check_id", title="检查项", data_type=DataType.STRING),
                ColumnSpec(key="title", title="要求", data_type=DataType.STRING),
                ColumnSpec(key="passed", title="通过", data_type=DataType.BOOLEAN),
                ColumnSpec(key="weight", title="分值", data_type=DataType.NUMBER),
                ColumnSpec(key="earned", title="得分", data_type=DataType.NUMBER),
                ColumnSpec(key="evidence", title="判定证据", data_type=DataType.STRING),
                ColumnSpec(key="suggestion", title="改进建议", data_type=DataType.STRING),
            ],
            rows=report.functional_checks,
        )

    @staticmethod
    def _issues_dataset(report: EvaluationReport) -> Dataset:
        """分页模拟器专有的实现问题；基座的通用 code_issues 会另行注入。"""

        return Dataset(
            name=ISSUES_DATASET_NAME,
            title="分页实现问题与建议",
            columns=[
                ColumnSpec(key="severity", title="级别", data_type=DataType.STRING),
                ColumnSpec(key="line", title="行号", data_type=DataType.INTEGER, nullable=True),
                ColumnSpec(key="code", title="规则", data_type=DataType.STRING),
                ColumnSpec(key="message", title="问题", data_type=DataType.STRING),
                ColumnSpec(key="suggestion", title="建议", data_type=DataType.STRING),
            ],
            rows=report.issues,
        )

    @staticmethod
    def _fault_rate_table_dataset(samples: tuple[FaultRateSample, ...]) -> Dataset:
        """物理内存页框数与缺页率的对应关系表。"""

        return Dataset(
            name=TABLE_DATASET_NAME,
            title="内存页框数与缺页率对应关系",
            columns=[
                ColumnSpec(key="algorithm_name", title="置换算法", data_type=DataType.STRING),
                ColumnSpec(
                    key="frame_count",
                    title="物理内存页框数",
                    data_type=DataType.INTEGER,
                    unit="页",
                ),
                ColumnSpec(key="page_faults", title="缺页次数", data_type=DataType.INTEGER, unit="次"),
                ColumnSpec(key="frame_hits", title="命中次数", data_type=DataType.INTEGER, unit="次"),
                ColumnSpec(
                    key="reference_length",
                    title="访问总次数",
                    data_type=DataType.INTEGER,
                    unit="次",
                ),
                ColumnSpec(key="page_fault_rate", title="缺页率", data_type=DataType.NUMBER, unit="%"),
            ],
            rows=[_sample_row(sample) for sample in samples],
        )

    @staticmethod
    def _fault_rate_curve_dataset(samples: tuple[FaultRateSample, ...]) -> Dataset:
        """缺页率变化曲线数据，横轴为内存页框数，纵轴为缺页率。"""

        return Dataset(
            name=CURVE_DATASET_NAME,
            title="缺页率随内存页框数变化曲线",
            columns=[
                ColumnSpec(key="algorithm_name", title="置换算法", data_type=DataType.STRING),
                ColumnSpec(
                    key="frame_count",
                    title="物理内存页框数",
                    data_type=DataType.INTEGER,
                    unit="页",
                ),
                ColumnSpec(key="page_fault_rate", title="缺页率", data_type=DataType.NUMBER, unit="%"),
            ],
            rows=[_curve_row(sample) for sample in samples],
        )

    @staticmethod
    def _timeline_dataset() -> Dataset:
        """页框占用时间线（LRU 算法、4 页框），展示页面换入换出过程。"""

        rows = []
        for segment in occupancy_timeline():
            if segment.page_number is None:
                label = f"页框 {segment.frame_index}：空闲"
            else:
                label = f"页框 {segment.frame_index}：装入逻辑页 {segment.page_number}"
            rows.append(
                {
                    "algorithm_name": TIMELINE_ALGORITHM,
                    "frame_index": segment.frame_index,
                    "start": segment.start,
                    "end": segment.end,
                    "page_number": segment.page_number,
                    "label": label,
                }
            )
        return Dataset(
            name=TIMELINE_DATASET_NAME,
            title=f"页框占用过程（{TIMELINE_ALGORITHM} 算法，{TIMELINE_FRAME_COUNT} 页框）",
            columns=[
                ColumnSpec(key="algorithm_name", title="置换算法", data_type=DataType.STRING),
                ColumnSpec(key="frame_index", title="物理页框", data_type=DataType.INTEGER),
                ColumnSpec(key="start", title="起始访问序号", data_type=DataType.INTEGER, unit="次"),
                ColumnSpec(key="end", title="结束访问序号", data_type=DataType.INTEGER, unit="次"),
                ColumnSpec(
                    key="page_number",
                    title="逻辑页号",
                    data_type=DataType.INTEGER,
                    nullable=True,
                ),
                ColumnSpec(key="label", title="区间说明", data_type=DataType.STRING),
            ],
            rows=rows,
        )