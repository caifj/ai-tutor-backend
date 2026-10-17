from __future__ import annotations

import pytest

from ai_tutor_backend.models import ExecutionContext
from ai_tutor_backend.registry import CaseInputError, CaseRegistry
from cases import register_cases
from cases.case_05_alg_complex_analyzer import AlgorithmComplexityAnalyzerCase
from cases.case_05_alg_complex_analyzer.benchmark import analyze


def execute(input_data: dict) -> object:
    return AlgorithmComplexityAnalyzerCase().execute(
        input_data,
        ExecutionContext(request_id="test-request"),
    )


def normalize_model(label: str) -> str:
    """Ignore spacing and superscript differences in complexity notation."""
    return label.replace(" ", "").replace("²", "2")


def test_case_registers_with_schema() -> None:
    registry = CaseRegistry()
    register_cases(registry)

    adapter = registry.get("algorithm.complexity-analyzer")

    assert isinstance(adapter, AlgorithmComplexityAnalyzerCase)
    assert adapter.descriptor.course == "算法与数据结构"
    assert adapter.descriptor.version == "2.0.0"
    assert set(adapter.descriptor.output_datasets) == {
        "benchmark_curve",
        "fitted_curve",
        "complexity_analysis",
    }
    schema = adapter.descriptor.input_schema
    assert set(schema["properties"]) == {"algorithms", "max_size"}
    assert schema["properties"]["algorithms"]["type"] == "array"
    assert "冒泡排序" in schema["properties"]["algorithms"]["x-enum-labels"]["bubble_sort"]


@pytest.mark.parametrize(
    ("algorithm", "expected"),
    [
        ("bubble_sort", "O(n²)"),
        ("selection_sort", "O(n²)"),
        ("quick_sort", "O(n log n)"),
        ("merge_sort", "O(n log n)"),
        ("linear_search", "O(n)"),
        ("binary_search", "O(log n)"),
    ],
)
def test_algorithm_fits_expected_complexity(algorithm: str, expected: str) -> None:
    report = analyze([algorithm], max_size=1000, seed=42)
    item = report["results"][0]

    assert normalize_model(item["best_model"]) == normalize_model(expected)
    best = max(item["models"], key=lambda model: model["r_squared"])
    assert normalize_model(best["model"]) == normalize_model(expected)
    assert best["r_squared"] > 0.9


def test_multiple_algorithms_compared_in_one_run() -> None:
    result = execute(
        {
            "algorithms": ["bubble_sort", "merge_sort", "linear_search", "binary_search"],
            "max_size": 500,
        }
    )

    assert result.metrics["对比算法数"] == 4
    assert result.metrics["采样点数"] == 5
    assert isinstance(result.metrics["复杂度拟合"], list)
    assert len(result.metrics["复杂度拟合"]) == 4

    expected_names = {"冒泡排序", "归并排序", "顺序查找", "二分查找"}
    curve = result.datasets[0]
    assert len(curve.rows) == 4 * 5
    assert {row["algorithm_name"] for row in curve.rows} == expected_names

    analysis = result.datasets[2]
    assert len(analysis.rows) == 4 * 4
    assert {row["algorithm_name"] for row in analysis.rows} == expected_names
    assert {row["is_best_fit"] for row in analysis.rows} == {True, False}

    fitted = result.datasets[1]
    assert len(fitted.rows) == 4 * 20


def test_output_uses_chinese_names_without_machine_identifiers() -> None:
    result = execute({"algorithms": ["bubble_sort"], "max_size": 500})

    for dataset in result.datasets:
        assert "algorithm" not in {column.key for column in dataset.columns}
    assert "bubble_sort" not in result.summary
    assert "对比算法数" in result.metrics
    assert result.diagnostics[0].code == "基准测试完成"


@pytest.mark.parametrize(
    "input_data",
    [
        {"algorithms": []},
        {"algorithms": ["unknown"]},
        {"max_size": 99},
        {"max_size": 3001},
        {"algorithms": ["bubble_sort"], "extra": True},
    ],
)
def test_invalid_input_raises_case_input_error(input_data: dict) -> None:
    with pytest.raises(CaseInputError, match="输入不合法"):
        AlgorithmComplexityAnalyzerCase().execute(
            input_data,
            ExecutionContext(request_id="test-request"),
        )
