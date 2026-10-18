"""Bounded, deterministic fixtures and server-side result validation."""

import math
import random

from .algorithms import FCFSScheduler, PriorityScheduler, RRScheduler, SJFScheduler
from .models import Process

SCHEDULERS = {
    "fcfs": FCFSScheduler,
    "sjf": SJFScheduler,
    "rr": RRScheduler,
    "priority": PriorityScheduler,
}


def build_requests():
    samples = [
        [("A", 0, 5, 2), ("B", 0, 2, 1), ("C", 0, 3, 3)],
        [("A", 2, 3, 1), ("B", 7, 2, 2)],
        [("P3", 1, 3, 2), ("P1", 0, 3, 2), ("P2", 1, 3, 2)],
        [("A", 0, 5, 3), ("B", 2, 2, 1), ("C", 3, 1, 2)],
        [("solo", 3, 7, 0)],
    ]
    rng = random.Random(202601)
    samples.append(
        [(f"P{i}", rng.randrange(6), rng.randrange(1, 8), rng.randrange(4)) for i in range(5)]
    )
    names = ["同时到达", "CPU空闲", "平局与乱序", "时间片边界到达", "单进程", "混合输入"]
    return [
        {
            "id": f"{algorithm}_{index}",
            "title": f"{algorithm.upper()} · {names[index]}",
            "algorithm": algorithm,
            "quantum": [2, 2, 1, 2, 3, 4][index],
            "processes": [
                dict(zip(("pid", "arrival_time", "burst_time", "priority"), row)) for row in sample
            ],
        }
        for algorithm in SCHEDULERS
        for index, sample in enumerate(samples)
    ]


def reference(request):
    cls = SCHEDULERS[request["algorithm"]]
    scheduler = cls(quantum=request["quantum"]) if request["algorithm"] == "rr" else cls()
    return scheduler.schedule([Process(**p) for p in request["processes"]]).to_dict()


def numeric_equal(actual, expected):
    try:
        return (
            type(actual) in (int, float)
            and math.isfinite(actual)
            and math.isclose(actual, expected, abs_tol=0.0001, rel_tol=1e-6)
        )
    except OverflowError:
        return False


def validate_result(actual, expected):
    """Never trust reported pass flags or scores from the student's process."""
    if not isinstance(actual, dict):
        return [(False, "返回值必须为字典，含 segments、process_metrics 和 summary")] * 3
    segments = actual.get("segments")
    expected_segments = expected["segments"]
    valid_segments = isinstance(segments, list) and len(segments) == len(expected_segments)
    if valid_segments:
        valid_segments = all(
            isinstance(a, dict)
            and a.get("pid") == e["pid"]
            and all(numeric_equal(a.get(k), e[k]) for k in ("start", "end"))
            and ("duration" not in a or numeric_equal(a["duration"], e["duration"]))
            for a, e in zip(segments, expected_segments)
        )
    metrics = actual.get("process_metrics")
    valid_metrics = isinstance(metrics, list) and len(metrics) == len(expected["process_metrics"])
    indexed = {}
    if valid_metrics:
        for row in metrics:
            if not isinstance(row, dict) or not isinstance(row.get("pid"), str):
                valid_metrics = False
                break
            if row["pid"] in indexed:
                valid_metrics = False
            indexed[row["pid"]] = row
        valid_metrics = valid_metrics and all(
            e["pid"] in indexed
            and all(numeric_equal(indexed[e["pid"]].get(k), v) for k, v in e.items() if k != "pid")
            for e in expected["process_metrics"]
        )
    summary = actual.get("summary")
    valid_summary = isinstance(summary, dict) and all(
        numeric_equal(summary.get(k), v) for k, v in expected["summary"].items()
    )
    return [
        (bool(valid_segments), "核对进程顺序、起止时间、空闲段及 RR 时间片边界"),
        (bool(valid_metrics), "核对每个进程的完成、等待、周转、响应时间及 PCB 字段"),
        (bool(valid_summary), "核对平均等待/周转/响应时间、CPU 利用率和总时长"),
    ]
