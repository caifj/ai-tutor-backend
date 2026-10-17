"""
计数版本的算法：执行算法并统计关键操作（元素比较）的次数。
复杂度分析本质上关注操作次数随规模的增长率，计数比计时更稳定、无噪声。
"""


def count_bubble_sort(arr):
    result = arr[:]
    n = len(result)
    comparisons = 0
    for i in range(n - 1):
        swapped = False
        for j in range(n - i - 1):
            comparisons += 1
            if result[j] > result[j + 1]:
                result[j], result[j + 1] = result[j + 1], result[j]
                swapped = True
        if not swapped:
            break
    return comparisons


def count_selection_sort(arr):
    result = arr[:]
    n = len(result)
    comparisons = 0
    for i in range(n - 1):
        min_index = i
        for j in range(i + 1, n):
            comparisons += 1
            if result[min_index] > result[j]:
                min_index = j
        if min_index != i:
            result[i], result[min_index] = result[min_index], result[i]
    return comparisons


def count_quick_sort(arr):
    if len(arr) <= 1:
        return 0
    pivot = arr[0]
    comparisons = 0
    left, middle, right = [], [], []
    for x in arr:
        comparisons += 1
        if x < pivot:
            left.append(x)
        elif x == pivot:
            middle.append(x)
        else:
            right.append(x)
    return comparisons + count_quick_sort(left) + count_quick_sort(right)


def count_merge_sort(arr):
    if len(arr) <= 1:
        return 0
    mid = len(arr) // 2
    left = arr[:mid]
    right = arr[mid:]
    return count_merge_sort(left) + count_merge_sort(right) + _count_merge(left, right)


def _count_merge(left, right):
    i = j = 0
    comparisons = 0
    while i < len(left) and j < len(right):
        comparisons += 1
        if left[i] <= right[j]:
            i += 1
        else:
            j += 1
    return comparisons


def count_linear_search(arr, target):
    comparisons = 0
    for value in arr:
        comparisons += 1
        if value == target:
            break
    return comparisons


def count_binary_search(arr, target):
    comparisons = 0
    low = 0
    high = len(arr) - 1
    while low <= high:
        comparisons += 1
        mid = (low + high) // 2
        value = arr[mid]
        if value == target:
            break
        if value < target:
            low = mid + 1
        else:
            high = mid - 1
    return comparisons
