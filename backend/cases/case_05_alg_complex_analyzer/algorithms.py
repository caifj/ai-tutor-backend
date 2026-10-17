"""
排序算法模块
所有函数都接收一个列表，返回一个新的排序后的列表（不修改原列表）
"""

import random


#算法一：冒泡排序
def bubble_sort(arr):
    result = arr[:]
    n = len(result)
    for i in range(n-1):
        isswap = False
        for j in range(n-i-1):
            if result[j] > result[j+1]:
                result[j],result[j+1] = result[j+1],result[j]
                isswap = True
        if not isswap:
            break
    return result

#算法二：选择排序
def selection_sort(arr):
    result = arr[:]
    n = len(result)
    for i in range(n-1):
        min_index = i
        for j in range(i+1,n):
            if result[min_index] > result[j]:
                min_index = j
        if min_index != i:
            result[i],result[min_index] = result[min_index],result[i]
    return result

#算法三：快速排序
def quick_sort(arr):
    if len(arr) <= 1:
        return arr
    pivot = arr[0]
    left = [x for x in arr if x < pivot]
    middle = [x for x in arr if x == pivot]
    right = [x for x in arr if x > pivot]
    return quick_sort(left)+middle+quick_sort(right)

#算法四：归并排序
def merge_sort(arr):
    if len(arr) <= 1:
        return arr
    
    # 整除，去中间位置
    mid = len(arr) // 2
    # 数组切片，分成两个数组
    left_half = arr[:mid]
    right_half = arr[mid:]

    left_sorted = merge_sort(left_half)
    right_sorted = merge_sort(right_half)

    return _merge(left_sorted,right_sorted)

def _merge(left,right):
    result = []
    i = 0
    j = 0
    # 左右数组都没比较晚就循环比较大小
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            result.append(left[i])
            i += 1
        else:
            result.append(right[j])
            j += 1
    #此时至少有一个数组遍历完毕，将未遍历完毕的数组追加到最后
    result.extend(left[i:])
    result.extend(right[j:])
    return result

#模块自测代码
if __name__ == "__main__":
    import timeit
    from functools import partial

    algorithms = {
        "冒泡排序": bubble_sort,
        "选择排序": selection_sort,
        "快速排序": quick_sort,
        "归并排序": merge_sort,
    }
    sizes = [100,500,1000,2000,3000]
    print("\n" + "=" * 70)
    print("  排序算法耗时对比（单位：秒），测试数据：随机整数列表")
    print("=" * 70)
    header = f"{'n':<8s}"
    for name in algorithms:
        header += f"{name:<12s}"
    print(header)
    print("-" * 70)
    for n in sizes:
        test_data = [random.randint(0,9999) for _ in range(n)]
        row = f"{n:<8d}"
        for k, v in algorithms.items():
            if k in ("冒泡排序","选择排序"):
                elapsed = timeit.timeit(partial(v, test_data), number=1)
            else:
                elapsed = timeit.timeit(partial(v, test_data), number=10) / 10
            row += f"{elapsed:<16.6f}"
        print(row)