"""
查找算法模块
所有函数都接收一个列表和目标值，返回目标值在列表中的下标，找不到返回 -1。
"""


def linear_search(arr, target):
    for index, value in enumerate(arr):
        if value == target:
            return index
    return -1


def binary_search(arr, target):
    low = 0
    high = len(arr) - 1
    while low <= high:
        mid = (low + high) // 2
        value = arr[mid]
        if value == target:
            return mid
        if value < target:
            low = mid + 1
        else:
            high = mid - 1
    return -1
