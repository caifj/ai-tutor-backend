"""案例5 演示样例：故意不完整，用于展示未通过/待完善状态。"""


def BubbleSort(arr):
    result = arr[:]
    n = len(arr)
    for i in range(n - 1):
        for j in range(n - i - 1):
            if result[j] > result[j + 1]:
                result[j], result[j + 1] = result[j + 1], result[j]
    return result


data = eval(input("请输入一个整数列表："))
print("排序结果为：", BubbleSort(data), "提示：本文件故意缺少查找、计时与曲线展示，用于演示未通过状态")
