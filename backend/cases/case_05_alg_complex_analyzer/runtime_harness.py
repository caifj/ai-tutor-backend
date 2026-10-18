"""案例5 运行时测试夹具（在沙箱中运行学生代码并验证排序/查找算法）。

夹具由基座沙箱以 `case_harness.py` 为入口运行，学生代码保存为同目录下的
`student.py`。夹具不导入任何第三方依赖，只使用标准库，运行结束后在标准输出
打印一行 marker + JSON 报文，供案例解析。
"""

HARNESS_SOURCE = r'''
import json
import random
import runpy
import time

MARKER = "__AI_TUTOR_CASE5_RESULT__"

SIZE_POINTS = [100, 200, 400]

SORT_SPECS = [
    ("BUBBLE_SORT", "冒泡排序", ("bubble",)),
    ("SELECTION_SORT", "选择排序", ("selection",)),
    ("QUICK_SORT", "快速排序", ("quick",)),
    ("MERGE_SORT", "归并排序", ("merge",)),
]

SEARCH_SPECS = [
    ("LINEAR_SEARCH", "顺序查找", ("linear",)),
    ("BINARY_SEARCH", "二分查找", ("binary",)),
]

checks = []
observations = {}
found_sorts = []


def _record(check_id, title, operation):
    try:
        passed, evidence = operation()
        checks.append(
            {
                "check_id": check_id,
                "title": title,
                "passed": bool(passed),
                "evidence": str(evidence),
            }
        )
    except BaseException as exc:
        checks.append(
            {
                "check_id": check_id,
                "title": title,
                "passed": False,
                "evidence": "{0}: {1}".format(type(exc).__name__, exc),
            }
        )


def _find_function(namespace, keywords, prefer):
    candidates = []
    for name, value in namespace.items():
        if not callable(value):
            continue
        lowered = name.lower()
        if any(keyword in lowered for keyword in keywords):
            candidates.append((name, value, prefer in lowered))
    if not candidates:
        return None, None
    candidates.sort(key=lambda item: item[2], reverse=True)
    name, value, _ = candidates[0]
    return name, value


def _sort_operation(label, keywords):
    def operation():
        name, func = _find_function(submitted, keywords, "sort")
        if func is None:
            raise AssertionError("未找到{0}函数".format(label))
        sample = [9, 3, 7, 1, 8, 3, -2, 5]
        result = func(list(sample))
        if result is None:
            raise AssertionError("{0} 未返回结果".format(name))
        values = list(result)
        if values != sorted(sample):
            raise AssertionError("{0} 排序结果不正确：{1}".format(name, values))
        found_sorts.append((label, func))
        return True, "已调用 {0} 并核对升序排序结果".format(name)

    return operation


def _search_operation(label, keywords):
    def operation():
        name, func = _find_function(submitted, keywords, "search")
        if func is None:
            raise AssertionError("未找到{0}函数".format(label))
        data = list(range(0, 100, 2))
        target = 42
        result = func(list(data), target)
        if result in (21, target, True):
            return True, "已调用 {0} 命中目标 {1}".format(name, target)
        raise AssertionError("{0} 查找结果不正确：{1}".format(name, result))

    return operation


def _benchmark_operation():
    def operation():
        if not found_sorts:
            raise AssertionError("没有可运行的排序函数，无法采集时间-规模数据")
        base = [random.randint(0, 1000000) for _ in range(max(SIZE_POINTS))]
        curve = []
        for label, func in found_sorts:
            for size in SIZE_POINTS:
                data = list(base[:size])
                started = time.perf_counter()
                func(data)
                elapsed = time.perf_counter() - started
                curve.append(
                    {
                        "algorithm_name": label,
                        "size": size,
                        "time_seconds": round(elapsed, 8),
                    }
                )
        observations["curve"] = curve
        observations["sizes"] = list(SIZE_POINTS)
        return True, "已在隔离沙箱中对 {0} 种排序算法采集 {1} 个时间-规模数据点".format(
            len(found_sorts), len(curve)
        )

    return operation


try:
    submitted = runpy.run_path("student.py")
    for check_id, label, keywords in SORT_SPECS:
        _record(check_id, "运行验证：" + label, _sort_operation(label, keywords))
    for check_id, label, keywords in SEARCH_SPECS:
        _record(check_id, "运行验证：" + label, _search_operation(label, keywords))
    _record("BENCHMARK", "运行验证：多规模计时采集", _benchmark_operation())
    payload = {"checks": checks, "observations": observations}
except BaseException as exc:
    payload = {
        "checks": checks,
        "observations": observations,
        "load_error": "{0}: {1}".format(type(exc).__name__, exc),
    }

print(MARKER + json.dumps(payload, ensure_ascii=False, default=str))
'''
