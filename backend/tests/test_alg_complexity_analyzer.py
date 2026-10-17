from __future__ import annotations

import pytest

from ai_tutor_backend.models import ExecutionContext
from ai_tutor_backend.registry import CaseInputError, CaseRegistry
from cases import register_cases
from cases.case_05_alg_complex_analyzer import AlgorithmComplexityAnalyzerCase

COMPLETE_SUBMISSION = '''
import json
import math
import random
import timeit


def bubble_sort(data):
    arr = data[:]
    for i in range(len(arr) - 1):
        for j in range(len(arr) - i - 1):
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
    return arr


def selection_sort(data):
    arr = data[:]
    for i in range(len(arr) - 1):
        k = i
        for j in range(i + 1, len(arr)):
            if arr[j] < arr[k]:
                k = j
        arr[i], arr[k] = arr[k], arr[i]
    return arr


def quick_sort(data):
    if len(data) <= 1:
        return data
    pivot = data[0]
    left = [x for x in data if x < pivot]
    mid = [x for x in data if x == pivot]
    right = [x for x in data if x > pivot]
    return quick_sort(left) + mid + quick_sort(right)


def merge_sort(data):
    if len(data) <= 1:
        return data
    m = len(data) // 2
    return merge(merge_sort(data[:m]), merge_sort(data[m:]))


def merge(left, right):
    out = []
    i = j = 0
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            out.append(left[i])
            i += 1
        else:
            out.append(right[j])
            j += 1
    return out + left[i:] + right[j:]


def linear_search(data, target):
    for i, value in enumerate(data):
        if value == target:
            return i
    return -1


def binary_search(data, target):
    low, high = 0, len(data) - 1
    while low <= high:
        mid = (low + high) // 2
        if data[mid] == target:
            return mid
        if data[mid] < target:
            low = mid + 1
        else:
            high = mid - 1
    return -1


ALGORITHMS = {"bubble": bubble_sort, "selection": selection_sort,
              "quick": quick_sort, "merge": merge_sort}


def benchmark(sizes):
    rows = []
    for size in sizes:
        data = [random.randint(0, 9999) for _ in range(size)]
        for name, func in ALGORITHMS.items():
            elapsed = timeit.timeit(lambda f=func, d=data: f(d), number=1)
            rows.append({"size": size, "algorithm": name, "time": elapsed})
    return rows


def fit_complexity(sizes, times):
    return [math.log2(n) if n > 0 else 0 for n in sizes]


def main():
    sizes = [100, 200, 400, 800]
    rows = benchmark(sizes)
    result = {"rows": rows, "fit": fit_complexity(sizes, [row["time"] for row in rows])}
    with open("result.json", "w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False)
    return result


if __name__ == "__main__":
    main()
'''


def execute(source: str, filename: str = "student.py"):
    return AlgorithmComplexityAnalyzerCase().execute(
        {"filename": filename, "source_code": source},
        ExecutionContext(request_id="test-request"),
    )


def test_case_registers_with_python_file_schema() -> None:
    registry = CaseRegistry()
    register_cases(registry)

    adapter = registry.get("algorithm.complexity-analyzer")

    assert isinstance(adapter, AlgorithmComplexityAnalyzerCase)
    assert adapter.descriptor.name == "算法复杂度分析平台"
    assert adapter.descriptor.course == "数据结构与算法"
    assert adapter.descriptor.version == "3.0.0"
    assert adapter.descriptor.input_schema["x-ui-mode"] == "python-file"
    assert set(adapter.descriptor.input_schema["properties"]) == {"filename", "source_code"}
    assert set(adapter.descriptor.output_datasets) == {
        "functional_tests",
        "quality_scores",
        "code_issues",
    }
    assert {item.case_id for item in registry.list()} == {
        "algorithm.complexity-analyzer",
        "demo.echo",
        "network.protocol-analyzer",
    }


def test_complete_submission_passes_core_checks() -> None:
    result = execute(COMPLETE_SUBMISSION)
    checks = {row["check_id"]: row for row in result.datasets[0].rows}

    assert result.metrics["syntax_valid"] is True
    assert result.metrics["tests_passed"] == result.metrics["tests_total"]
    assert result.metrics["test_pass_rate"] == 100.0
    assert result.metrics["functionality_score"] == 80.0
    assert result.metrics["overall_score"] >= 90
    assert len(result.datasets[1].rows) == 2
    assert all(row["passed"] for row in checks.values())


def test_incomplete_submission_gets_explainable_failures() -> None:
    result = execute("def hello():\n    return 'hello'\n")
    checks = result.datasets[0].rows

    assert result.metrics["syntax_valid"] is True
    assert result.metrics["tests_passed"] == 0
    assert any("未" in row["evidence"] for row in checks)
    assert result.datasets[1].name == "quality_scores"
    assert result.datasets[2].name == "code_issues"


def test_syntax_error_returns_zero_score_and_line_number() -> None:
    result = execute("def broken(:\n    pass\n")

    assert result.metrics["syntax_valid"] is False
    assert result.metrics["overall_score"] == 0.0
    assert result.datasets[2].rows[0]["line"] == 1
    assert result.diagnostics[0].code == "PYTHON_SYNTAX_ERROR"


@pytest.mark.parametrize("input_data", [{}, {"filename": "answer.txt", "source_code": "pass"}])
def test_submission_rejects_missing_or_non_python_file(input_data: dict) -> None:
    with pytest.raises(CaseInputError, match="代码文件输入不合法"):
        AlgorithmComplexityAnalyzerCase().execute(
            input_data,
            ExecutionContext(request_id="test-request"),
        )
