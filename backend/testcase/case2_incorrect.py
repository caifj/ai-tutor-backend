"""虚拟内存分页模拟器（案例 2 未通过示例）。

本文件语法有效，但故意缺少绝大多数功能要求，用于演示评测结果中的待完善状态：
没有地址转换、没有缺页处理、没有任何页面置换算法、内存页框数被硬编码，
并且用 eval 求缺页率、用 while True 循环访问引用串。
"""

frames = [None] * 4
page_table = {}
faults = 0


def simulate(sequence):
    """只用固定 4 个页框循环装入页面。"""

    global faults
    for page in sequence:
        if page not in frames:
            faults += 1
            frames[0] = page
            page_table[page] = 0
    return frames


def report(sequence):
    """用 eval 计算缺页率，属于高风险写法。"""

    while True:
        simulate(sequence)
        break
    return eval("faults / len(sequence) * 100")


def main():
    sequence = [0, 1, 2, 3, 0, 1, 4, 0, 1, 2, 3, 4]
    print(report(sequence))
