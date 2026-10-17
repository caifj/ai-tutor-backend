from __future__ import annotations

import math
import random
import timeit
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Literal

from .algorithms import bubble_sort, merge_sort, quick_sort, selection_sort
from .counting import (
    count_binary_search,
    count_bubble_sort,
    count_linear_search,
    count_merge_sort,
    count_quick_sort,
    count_selection_sort,
)
from .searching import binary_search, linear_search

AlgorithmKey = Literal[
    "bubble_sort",
    "selection_sort",
    "quick_sort",
    "merge_sort",
    "linear_search",
    "binary_search",
]

MAX_DATA_SIZE = 3000
MIN_SAMPLE_SIZE = 10
VALUE_RANGE = 9999
FITTED_CURVE_POINTS = 20
TRIALS = 3

COMPLEXITY_MODELS: dict[str, Callable[[float], float]] = {
    "O(logn)": lambda n: math.log2(n),
    "O(n)": lambda n: n,
    "O(nlogn)": lambda n: n * math.log2(n),
    "O(n²)": lambda n: n * n,
}


@dataclass(frozen=True)
class AlgorithmSpec:
    key: AlgorithmKey
    display_name: str
    complexity: str
    category: Literal["sort", "search"]
    func: Callable[..., object]
    count_func: Callable[..., int]
    repeat: int
    sorted_input: bool = False


SPECS: dict[AlgorithmKey, AlgorithmSpec] = {
    spec.key: spec
    for spec in (
        AlgorithmSpec(
            "bubble_sort", "冒泡排序", "O(n²)", "sort", bubble_sort, count_bubble_sort, 1
        ),
        AlgorithmSpec(
            "selection_sort",
            "选择排序",
            "O(n²)",
            "sort",
            selection_sort,
            count_selection_sort,
            1,
        ),
        AlgorithmSpec(
            "quick_sort", "快速排序", "O(nlogn)", "sort", quick_sort, count_quick_sort, 10
        ),
        AlgorithmSpec(
            "merge_sort", "归并排序", "O(nlogn)", "sort", merge_sort, count_merge_sort, 10
        ),
        AlgorithmSpec(
            "linear_search", "顺序查找", "O(n)", "search", linear_search, count_linear_search, 1000
        ),
        AlgorithmSpec(
            "binary_search",
            "二分查找",
            "O(logn)",
            "search",
            binary_search,
            count_binary_search,
            5000,
            sorted_input=True,
        ),
    )
}

ALGORITHM_KEYS: tuple[AlgorithmKey, ...] = tuple(SPECS)

ALGORITHM_LABELS: dict[str, str] = {
    key: f"{spec.display_name}（{spec.complexity}）" for key, spec in SPECS.items()
}


def build_sample_sizes(max_size: int) -> list[int]:
    if max_size <= MIN_SAMPLE_SIZE:
        return [MIN_SAMPLE_SIZE]
    lo = math.log10(MIN_SAMPLE_SIZE)
    hi = math.log10(max_size)
    return [
        max(MIN_SAMPLE_SIZE, round(10 ** (lo + (hi - lo) * i / 4)))
        for i in range(5)
    ]


def _generate_data(spec: AlgorithmSpec, n: int, rng: random.Random) -> list[int]:
    data = [rng.randint(0, VALUE_RANGE) for _ in range(n)]
    if spec.sorted_input:
        data.sort()
    return data


def _measure_time(spec: AlgorithmSpec, data: list[int]) -> float:
    args = (data, -1) if spec.category == "search" else (data,)
    workload = partial(spec.func, *args)
    if spec.repeat == 1:
        return timeit.timeit(workload, number=1)
    return timeit.timeit(workload, number=spec.repeat) / spec.repeat


def _measure_comparisons(spec: AlgorithmSpec, data: list[int]) -> int:
    args = (data, -1) if spec.category == "search" else (data,)
    return spec.count_func(*args)


def fit_models(sizes: list[int], measurements: list[float]) -> list[dict]:
    point_count = len(sizes)
    mean_value = sum(measurements) / point_count
    ss_total = sum((v - mean_value) ** 2 for v in measurements)

    models: list[dict] = []
    for label, growth in COMPLEXITY_MODELS.items():
        base = [growth(n) for n in sizes]
        sx = sum(base)
        sy = sum(measurements)
        sxx = sum(f * f for f in base)
        sxy = sum(f * v for f, v in zip(base, measurements))
        denominator = point_count * sxx - sx * sx
        if denominator == 0:
            coefficient = 0.0
            intercept = mean_value
        else:
            coefficient = (point_count * sxy - sx * sy) / denominator
            intercept = (sxx * sy - sx * sxy) / denominator
        predicted = [coefficient * f + intercept for f in base]
        ss_residual = sum((v - p) ** 2 for v, p in zip(measurements, predicted))
        r_squared = 1 - ss_residual / ss_total if ss_total > 0 else 0.0
        models.append(
            {
                "model": label,
                "coefficient": coefficient,
                "intercept": intercept,
                "r_squared": r_squared,
            }
        )
    return models


def fitted_curve_points(
    sizes: list[int],
    model_label: str,
    coefficient: float,
    intercept: float,
    points: int = FITTED_CURVE_POINTS,
) -> list[dict]:
    growth = COMPLEXITY_MODELS[model_label]
    start, end = sizes[0], sizes[-1]
    if points <= 1 or end <= start:
        xs = [start]
    else:
        step = (end - start) / (points - 1)
        xs = [start + step * i for i in range(points)]
    return [
        {
            "size": round(x),
            "fitted_comparisons": max(0.0, coefficient * growth(x) + intercept),
        }
        for x in xs
    ]


def analyze(
    algorithms: list[AlgorithmKey],
    max_size: int,
    seed: int | None = None,
    trials: int = TRIALS,
) -> dict:
    sizes = build_sample_sizes(max_size)
    rng = random.Random(seed)

    results: list[dict] = []
    for key in algorithms:
        spec = SPECS[key]
        time_sums = [0.0] * len(sizes)
        comparison_sums = [0.0] * len(sizes)
        for _ in range(trials):
            for index, n in enumerate(sizes):
                data = _generate_data(spec, n, rng)
                time_sums[index] += _measure_time(spec, data)
                comparison_sums[index] += _measure_comparisons(spec, data)

        times = [total / trials for total in time_sums]
        comparisons = [total / trials for total in comparison_sums]

        models = fit_models(sizes, comparisons)
        best = max(models, key=lambda item: item["r_squared"])
        results.append(
            {
                "algorithm": key,
                "display_name": spec.display_name,
                "complexity": spec.complexity,
                "repeat": spec.repeat,
                "times": times,
                "comparisons": comparisons,
                "models": models,
                "best_model": best["model"],
                "best_coefficient": best["coefficient"],
                "best_intercept": best["intercept"],
            }
        )

    return {"sample_sizes": sizes, "results": results}
