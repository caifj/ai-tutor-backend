"""虚拟内存分页模拟器（案例 2 参考实现）。

本文件是提交给案例 2 的**正确示例**，用于演示一份应通过全部功能检查的分页模拟器：
它建立页表、拆分逻辑地址、处理缺页中断，并分别用 FIFO / LRU / OPT 三种策略做页面置换，
最后扫描 1 ~ 逻辑页总数各档内存页框数，输出“内存页框数 → 缺页率”的对应关系。

评测采用静态分析，本文件不会被后端执行；可以直接运行它查看输出。
"""

from __future__ import annotations

from collections import deque


class PageTable:
    """记录逻辑页到物理页框的映射。"""

    def __init__(self, frame_count: int) -> None:
        if frame_count <= 0:
            raise ValueError("物理内存页框数必须为正整数")
        self.frame_count = frame_count
        self.frames: list[int | None] = [None] * frame_count
        self.page_table: dict[int, int] = {}
        self.used_at: list[int] = [-1] * frame_count

    def lookup(self, page_no: int) -> int | None:
        """命中返回物理页框号，未命中返回 None。"""

        return self.page_table.get(page_no)

    def install(self, page_no: int, frame_index: int, stamp: int) -> None:
        """把逻辑页装入指定页框，并更新该页框的最近访问时间。"""

        self.frames[frame_index] = page_no
        self.page_table[page_no] = frame_index
        self.used_at[frame_index] = stamp

    def free_frame(self) -> int | None:
        """返回第一个空闲页框号。"""

        for index, page in enumerate(self.frames):
            if page is None:
                return index
        return None


def translate_address(logical_address: int, page_size: int) -> tuple[int, int]:
    """把逻辑地址拆成 (页号, 页内偏移)。

    页号必须用整除求、偏移必须用取模求，不能用浮点除法 /。
    """

    page_no, offset = divmod(logical_address, page_size)
    return page_no, offset


def choose_victim(
    table: PageTable,
    algorithm: str,
    sequence: list[int],
    stamp: int,
    arrival_order: deque[int],
) -> int:
    """按指定策略选择要换出的物理页框。

    FIFO 换出装入时间最早的页框，LRU 换出最近最久未被访问的页框，
    OPT 换出未来最长时间不再被访问的页框。
    """

    free = table.free_frame()
    if free is not None:
        return free
    if algorithm == "FIFO":
        return arrival_order[0]
    if algorithm == "LRU":
        return min(range(table.frame_count), key=lambda index: table.used_at[index])
    if algorithm == "OPT":
        farthest = -1
        victim = 0
        for index in range(table.frame_count):
            page = table.frames[index]
            next_use = next(
                (
                    offset
                    for offset in range(stamp + 1, len(sequence))
                    if sequence[offset] == page
                ),
                None,
            )
            if next_use is None or next_use > farthest:
                farthest = next_use if next_use is not None else farthest
                victim = index
        return victim
    raise ValueError(f"未知的页面置换算法: {algorithm}")


def handle_page_fault(
    sequence: list[int],
    frame_count: int,
    algorithm: str,
) -> dict[str, float]:
    """模拟一次完整分页过程，返回缺页次数、命中次数与缺页率。"""

    table = PageTable(frame_count)
    arrival_order: deque[int] = deque()
    page_faults = 0

    for stamp, page in enumerate(sequence):
        frame_index = table.lookup(page)
        if frame_index is None:
            # 缺页中断：先找空闲页框，没有空闲页框则按策略置换
            page_faults += 1
            victim = choose_victim(table, algorithm, list(sequence), stamp, arrival_order)
            previous = table.frames[victim]
            if previous is not None:
                del table.page_table[previous]
                arrival_order.remove(victim)
            table.install(page, victim, stamp)
            arrival_order.append(victim)
        else:
            table.used_at[frame_index] = stamp

    return {
        "page_faults": float(page_faults),
        "frame_hits": float(len(sequence) - page_faults),
        "page_fault_rate": fault_rate(page_faults, len(sequence)),
    }


def fault_rate(page_faults: int, reference_length: int) -> float:
    """缺页率 = 缺页次数 / 总访问次数。"""

    if reference_length == 0:
        return 0.0
    return page_faults / reference_length * 100


def build_reference_sequence(page_span: int = 9, windows: int = 4) -> list[int]:
    """构造带局部性的页面访问序列。"""

    sequence: list[int] = []
    for index in range(windows):
        start = (index * 3) % page_span
        window = [(start + step) % page_span for step in range(4)]
        sequence.extend(window)
        sequence.extend(window)
    return sequence


def sweep_frame_counts(
    sequence: list[int],
    page_span: int,
    algorithms: tuple[str, ...] = ("FIFO", "LRU", "OPT"),
) -> list[dict[str, object]]:
    """扫描多档内存页框数，输出内存页框数与缺页率的对应关系。"""

    rows: list[dict[str, object]] = []
    for algorithm in algorithms:
        for frame_count in range(1, page_span + 1):
            result = handle_page_fault(sequence, frame_count, algorithm)
            rows.append(
                {
                    "algorithm_name": algorithm,
                    "frame_count": frame_count,
                    "page_fault_rate": result["page_fault_rate"],
                }
            )
    return rows


def main() -> None:
    page_span = 9
    sequence = build_reference_sequence(page_span)
    print(f"页面访问序列（共 {len(sequence)} 次访问）：{sequence}")
    for row in sweep_frame_counts(sequence, page_span):
        rate = row["page_fault_rate"]
        print(f"{row['algorithm_name']:>4} {row['frame_count']} 页框 缺页率 {rate:.2f}%")


if __name__ == "__main__":
    main()