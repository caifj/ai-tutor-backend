from __future__ import annotations

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

from .benchmark import (
    ALGORITHM_KEYS,
    ALGORITHM_LABELS,
    MAX_DATA_SIZE,
    AlgorithmKey,
    analyze,
    fitted_curve_points,
)


class AnalyzerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    algorithms: list[AlgorithmKey] = Field(
        default=list(ALGORITHM_KEYS),
        min_length=1,
        title="待对比算法",
        description="选择多个排序、查找算法，同时基准测试并对比其复杂度曲线。",
    )
    max_size: int = Field(
        default=1000,
        ge=100,
        le=MAX_DATA_SIZE,
        title="最大数据规模(上限3000)",
        description="系统会在 100 到该上限之间取 5 个等距点进行测试。",
    )


class AlgorithmComplexityAnalyzerCase(CaseAdapter):
    @property
    def descriptor(self) -> CaseDescriptor:
        schema = AnalyzerInput.model_json_schema()
        schema["properties"]["algorithms"]["x-enum-labels"] = ALGORITHM_LABELS
        return CaseDescriptor(
            case_id="algorithm.complexity-analyzer",
            name="算法复杂度分析仪",
            course="算法与数据结构",
            description=(
                "对比排序、查找等算法在不同数据规模下的运行时间与操作次数，"
                "输出时间-规模关系数据，并拟合出各自的复杂度曲线。"
            ),
            version="2.0.0",
            input_schema=schema,
            output_datasets=["benchmark_curve", "fitted_curve", "complexity_analysis"],
        )

    def execute(self, input_data: dict, context: ExecutionContext) -> ResultPayload:
        data = self._validate_input(input_data)
        # report = analyze(data.algorithms, data.max_size, data.random_seed)
        report = analyze(data.algorithms, data.max_size)

        sizes = report["sample_sizes"]
        results = report["results"]

        curve_rows, fitted_rows, analysis_rows = self._build_datasets(results, sizes)

        fragments = "，".join(
            f"{item['display_name']}≈{item['best_model']}" for item in results
        )
        summary = (
            f"已对比 {len(results)} 个算法在 {sizes[0]}~{sizes[-1]} 的 "
            f"{len(sizes)} 个数据规模下的运行情况，拟合复杂度：{fragments}。"
        )

        return ResultPayload(
            summary=summary,
            datasets=[
                self._curve_dataset(curve_rows),
                self._fitted_dataset(fitted_rows),
                self._analysis_dataset(analysis_rows),
            ],
            metrics={
                "对比算法数": len(results),
                "采样点数": len(sizes),
                "最大规模": data.max_size,
                "复杂度拟合": [
                    f"{item['display_name']}≈{item['best_model']}" for item in results
                ],
            },
            diagnostics=[
                Diagnostic(
                    code="基准测试完成",
                    level=DiagnosticLevel.INFO,
                    message=f"已对 {len(results)} 个算法完成基准测试与复杂度拟合。",
                    details={"request_id": context.request_id},
                )
            ],
        )

    @staticmethod
    def _build_datasets(results: list[dict], sizes: list[int]) -> tuple[list, list, list]:
        curve_rows: list[dict] = []
        fitted_rows: list[dict] = []
        analysis_rows: list[dict] = []
        for item in results:
            for size, time, comparisons in zip(sizes, item["times"], item["comparisons"]):
                curve_rows.append(
                    {
                        "algorithm_name": item["display_name"],
                        "size": size,
                        "time_seconds": round(time, 6),
                        "comparisons": round(comparisons),
                        "repeat": item["repeat"],
                    }
                )
            for point in fitted_curve_points(
                sizes, item["best_model"], item["best_coefficient"], item["best_intercept"]
            ):
                fitted_rows.append(
                    {
                        "algorithm_name": item["display_name"],
                        "complexity_class": item["best_model"],
                        "size": point["size"],
                        "fitted_comparisons": round(point["fitted_comparisons"], 3),
                    }
                )
            for model in item["models"]:
                analysis_rows.append(
                    {
                        "algorithm_name": item["display_name"],
                        "complexity_model": model["model"],
                        "coefficient": round(model["coefficient"], 6),
                        "r_squared": round(model["r_squared"], 6),
                        "is_best_fit": model["model"] == item["best_model"],
                    }
                )
        return curve_rows, fitted_rows, analysis_rows

    @staticmethod
    def _curve_dataset(rows: list[dict]) -> Dataset:
        return Dataset(
            name="benchmark_curve",
            title="时间-规模关系数据",
            columns=[
                ColumnSpec(key="algorithm_name", title="算法", data_type=DataType.STRING),
                ColumnSpec(key="size", title="数据规模 n", data_type=DataType.INTEGER),
                ColumnSpec(
                    key="time_seconds",
                    title="运行时间",
                    data_type=DataType.NUMBER,
                    unit="s",
                ),
                ColumnSpec(key="comparisons", title="比较次数", data_type=DataType.INTEGER),
                ColumnSpec(key="repeat", title="计时重复次数", data_type=DataType.INTEGER),
            ],
            rows=rows,
        )

    @staticmethod
    def _fitted_dataset(rows: list[dict]) -> Dataset:
        return Dataset(
            name="fitted_curve",
            title="拟合复杂度曲线",
            columns=[
                ColumnSpec(key="algorithm_name", title="算法", data_type=DataType.STRING),
                ColumnSpec(
                    key="complexity_class",
                    title="拟合复杂度",
                    data_type=DataType.STRING,
                ),
                ColumnSpec(key="size", title="数据规模 n", data_type=DataType.INTEGER),
                ColumnSpec(
                    key="fitted_comparisons",
                    title="拟合比较次数",
                    data_type=DataType.NUMBER,
                ),
            ],
            rows=rows,
        )

    @staticmethod
    def _analysis_dataset(rows: list[dict]) -> Dataset:
        return Dataset(
            name="complexity_analysis",
            title="复杂度拟合分析",
            columns=[
                ColumnSpec(key="algorithm_name", title="算法", data_type=DataType.STRING),
                ColumnSpec(
                    key="complexity_model",
                    title="候选复杂度",
                    data_type=DataType.STRING,
                ),
                ColumnSpec(key="coefficient", title="拟合系数", data_type=DataType.NUMBER),
                ColumnSpec(key="r_squared", title="拟合优度 R²", data_type=DataType.NUMBER),
                ColumnSpec(key="is_best_fit", title="是否最佳拟合", data_type=DataType.BOOLEAN),
            ],
            rows=rows,
        )

    @staticmethod
    def _validate_input(input_data: dict) -> AnalyzerInput:
        try:
            return AnalyzerInput.model_validate(input_data)
        except ValidationError as exc:
            raise CaseInputError(
                "算法复杂度分析仪输入不合法",
                {"errors": exc.errors(include_context=False, include_url=False)},
            ) from exc
