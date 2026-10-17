"""案例5 演示样例：算法复杂度分析平台（应通过全部功能检查）。"""

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


ALGORITHMS = {
    "bubble": bubble_sort,
    "selection": selection_sort,
    "quick": quick_sort,
    "merge": merge_sort,
}


def benchmark(sizes):
    rows = []
    for size in sizes:
        data = [random.randint(0, 9999) for _ in range(size)]
        for name, func in ALGORITHMS.items():
            elapsed = timeit.timeit(lambda f=func, d=data: f(d), number=1)
            rows.append({"size": size, "algorithm": name, "time": elapsed})
    return rows


def fit_complexity(sizes, times):
    """用对数变换近似拟合复杂度曲线。"""
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
